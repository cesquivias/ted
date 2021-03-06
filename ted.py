#!/usr/bin/env python

import atexit
import curses.ascii
import errno
import fcntl
import functools
import os
import sys
import struct
import termios
import time
import tty

VERSION = '0.0.1'
TAB_STOP = 8
QUIT_TIMES = 3

HL_NORMAL = 0
HL_NUMBER = 1
HL_MATCH = 2
HL_STRING = 3
HL_COMMENT = 4
HL_KEYWORD1 = 5
HL_KEYWORD2 = 6
HL_MLCOMMENT = 7

SYNTAX_TO_COLOR = {
    HL_NORMAL: 37,
    HL_NUMBER: 31,
    HL_MATCH: 34,
    HL_STRING: 35,
    HL_COMMENT: 36,
    HL_MLCOMMENT: 36,
    HL_KEYWORD1: 33,
    HL_KEYWORD2: 32,
}

class Row(object):
    def __init__(self, chars, idx):
        self.chars = chars
        self.idx = idx
        self.hl_open_comment = 0

    @property
    def hl(self):
        hl = [HL_NORMAL] * len(self.chars)

        if not CONFIG['syntax']:
            return hl

        singleline_comment_start = CONFIG['syntax']['singleline_comment_start']
        mcs = CONFIG['syntax']['multiline_comment_start']
        mce = CONFIG['syntax']['multiline_comment_end']
        prev_sep = True
        string_delim = None
        in_comment = self.idx > 0 and CONFIG['row'][self.idx - 1].hl_open_comment

        l = len(self.chars)
        i = 0
        while i < l:
            prev_hl = hl[i - 1] if i > 0 else HL_NORMAL
            c = self.chars[i]

            if singleline_comment_start and not string_delim and not in_comment:
                if self.chars[i:].startswith(singleline_comment_start):
                    hl[i:] = [HL_COMMENT] * (len(self.chars) - i)
                    break

            if mcs and mce and not string_delim:
                if in_comment:
                    hl[i] = HL_MLCOMMENT
                    if self.chars.startswith(mce, i):
                        hl[i:i+len(mce)] = [HL_MLCOMMENT] * len(mce)
                        i += len(mce)
                        in_comment = False
                        prev_sep = 1
                    else:
                        i += 1
                        continue
                elif self.chars.startswith(mcs, i):
                    hl[i:i+len(mcs)] = [HL_MLCOMMENT] * len(mcs)
                    i += len(mcs)
                    in_comment = True
                    continue

            if CONFIG['syntax']['flags'] & HL_HIGHLIGHT_STRINGS:
                if string_delim:
                    hl[i] = HL_STRING
                    if c == '\\' and i + 1 < len(self.chars):
                        hl[i + 1] = HL_STRING
                        i += 2
                        continue
                    if c == string_delim:
                        string_delim = None
                    i += 1
                    prev_sep = 1
                    continue
                else:
                    if c in ('"', "'"):
                        string_delim = c
                        hl[i] = HL_STRING
                        i += 1
                        continue

            if CONFIG['syntax']['flags'] & HL_HIGHLIGHT_NUMBERS:
                if (c.isdigit() and (prev_sep or prev_hl == HL_NUMBER)) or (
                        c == '.' and prev_hl == HL_NUMBER):
                    hl[i] = HL_NUMBER
                    i += 1
                    prev_sep = False
                    continue

            if prev_sep:
                keyword_found = False
                for key, color in [('keywords1', HL_KEYWORD1),
                                   ('keywords2', HL_KEYWORD2)]:
                    for keyword in CONFIG['syntax'][key]:
                        klen = len(keyword)
                        if (keyword.startswith(c) and 
                            self.chars[i:i+klen] == keyword and
                            is_separtor(self.chars[i + klen])):
                            hl[i:i+klen] = [color] * klen
                            i += klen
                            keyword_found = True
                            break
                    else:
                        continue
                    break
                if keyword_found:
                    prev_sep = False
                    continue

            prev_sep = is_separtor(c)
            i += 1

        changed = self.hl_open_comment != in_comment
        self.hl_open_comment = in_comment
        if changed and self.idx + 1 < len(CONFIG['row']):
            pass
        return hl

    @property
    def chars(self):
        return self._chars

    @chars.setter
    def chars(self, chars):
        self._chars = chars

    @property
    def render(self):
        return self._chars.replace('\t', ' ' * TAB_STOP)


CONFIG = {
    'cx': 0,
    'cy': 0,
    'rx': 0,
    'original_termios': None,
    'rowoff': 0,
    'coloff': 0,
    'screen_rows': 0,
    'screen_cols': 0,
    'row': [],
    'dirty': 0,
    'filename': None,
    'status_msg': '',
    'status_msg_time': 0,
    'syntax': None,
    'quit_times': QUIT_TIMES,
}

BACKSPACE = 127
ARROW_LEFT = 1000
ARROW_RIGHT = 1001
ARROW_UP = 1002
ARROW_DOWN = 1003
DEL_KEY = 1004
HOME_KEY = 1005
END_KEY = 1006
PAGE_UP = 1007
PAGE_DOWN = 1008

HL_HIGHLIGHT_NUMBERS = 1 << 0
HL_HIGHLIGHT_STRINGS = 1 << 1

HLDB = [
    {'filetype': 'c',
     'filematch': ['.c', '.h', '.cpp'],
     'keywords1': ['switch', 'if', 'while', 'for', 'break', 'continue', 
                   'return', 'else', 'struct', 'union', 'typedef', 'static',
                   'enum', 'class', 'case'],
     'keywords2': ['int', 'long', 'double', 'float', 'char', 'unsigned',
                   'signed', 'void'],
     'singleline_comment_start': '//',
     'multiline_comment_start': '/*',
     'multiline_comment_end': '*/',
     'flags': HL_HIGHLIGHT_NUMBERS | HL_HIGHLIGHT_STRINGS,
    },
]

def ctrl(key):
    return chr(ord(key) & 0x1f)

def is_separtor(c):
    return c in " ,.()+-/*=~%<>[];"

@atexit.register
def on_exit():
    os.write(fd, '\x1b[2J')
    os.write(fd, '\x1b[H')
    termios.tcsetattr(fd, termios.TCSAFLUSH, CONFIG['original_termios'])

def enable_raw_mode(fd):
    CONFIG['original_termios'] = termios.tcgetattr(fd)
    tty.setraw(fd)

def read_key(fd):
    try:
        c = os.read(fd, 1)
    except OSError as err:
        if err.errno == errno.EAGAIN:
            return -1
        else:
            raise
    if c == '\x1b':
        try:
            seq = os.read(fd, 3)
            if seq[0] == '[':
                if ord('0') <= ord(seq[1]) <= ord('9'):
                    if seq[2] == '~':
                        if seq[1] == '1':
                            return HOME_KEY
                        elif seq[1] == '3':
                            return DEL_KEY
                        elif seq[1] == '4':
                            return END_KEY
                        elif seq[1] == '5':
                            return PAGE_UP
                        elif seq[1] == '6':
                            return PAGE_DOWN
                        elif seq[1] == '7':
                            return HOME_KEY
                        elif seq[1] == '8':
                            return END_KEY
                elif seq[1] == 'A':
                    return ARROW_UP
                elif seq[1] == 'B':
                    return ARROW_DOWN
                elif seq[1] == 'C':
                    return ARROW_RIGHT
                elif seq[1] == 'D':
                    return ARROW_LEFT
                elif seq[1] == 'F':
                    return END_KEY
                elif seq[1] == 'H':
                    return HOME_KEY
            elif seq[0] == 'O':
                if seq[1] == 'F':
                    return END_KEY
                elif seq[1] == 'H':
                    return HOME_KEY
        except (OSError, IndexError) as err:
            return 0x1b
        return 0x1b
    return ord(c)

def get_cursor_position(fd):
    os.write(fd, '\x1b[6n')
    output = os.read(fd, 10)
    left, right = output.split(';')
    return (int(left[2:]), int(right[:2]))

def get_window_size(fd):
    try:
        size = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
    except IOError:
        os.write(fd, '\x1b[999C\x1b[999B')
        size = get_cursor_position(fd)
    return dict(zip(('screen_rows', 'screen_cols'), size))

def select_sytnax_highlight():
    CONFIG['syntax'] = None
    if CONFIG['filename'] is None:
        return
    ext = os.path.splitext(CONFIG['filename'])[1]
    for syntax in HLDB:
        if ext in syntax['filematch']:
            CONFIG['syntax'] = syntax
            return

# row operations

def row_cx_to_rx(row, cx):
    rx = 0
    for i in xrange(cx):
        if row.chars[i] == '\t':
            rx += (TAB_STOP - 1) - (rx % TAB_STOP)
        rx += 1
    return rx

def row_rx_to_cx(row, rx):
    cur_rx = 0
    for cx, c in enumerate(row.chars):
        if c == '\t':
            cur_rx += (TAB_STOP - 1) - (cur_rx % TAB_STOP)
        cur_rx += 1

        if cur_rx > rx:
            return cx
    return cx

def row_delete(at):
    rows = CONFIG['row']
    if at < 0 or at >= len(rows):
        return
    for i, row in enumerate(rows[at:], start=at + 1):
        row.idx -= 1
    del rows[at]
    CONFIG['dirty'] += 1

def row_insert_char(row, at, c):
    at = min(at, len(row.chars))
    row.chars = row.chars[:at] + c + row.chars[at:]
    CONFIG['dirty'] += 1

def row_delete_char(row, at):
    if at < 0 or at >= len(row.chars):
        return
    row.chars = row.chars[:at] + row.chars[at+1:]
    CONFIG['dirty'] += 1

# Editor Operations
def editor_insert_row(at, s):
    rows = CONFIG['row']
    for i, row in enumerate(rows[at:], start=at + 1):
        row.idx += 1
    # rows.append(Row(s, at))
    rows.insert(at, Row(s, at))

def editor_insert_char(c):
    if CONFIG['cy'] == len(CONFIG['row']):
        editor_insert_row(CONFIG['cy'], '')
    row_insert_char(CONFIG['row'][CONFIG['cy']], CONFIG['cx'], c)
    CONFIG['cx'] += 1
    CONFIG['dirty'] += 1

def editor_insert_newline():
    if CONFIG['cx'] == 0:
        editor_insert_row(CONFIG['cy'], '')
        # CONFIG['row'].insert(CONFIG['cy'], Row('', CONFIG['cy']))
    else:
        row = CONFIG['row'][CONFIG['cy']]
        # CONFIG['row'].insert(CONFIG['cy'] + 1, Row(row.chars[CONFIG['cx']:],
        #CONFIG['cy']))
        editor_insert_row(CONFIG['cy'] + 1, row.chars[CONFIG['cx']:])
        row.chars = row.chars[:CONFIG['cx']]
    CONFIG['cy'] += 1
    CONFIG['cx'] = 0
    CONFIG['dirty'] += 1

def editor_delete_char():
    if CONFIG['cy'] == len(CONFIG['row']):
        return
    if CONFIG['cx'] == 0 and CONFIG['cy'] == 0:
        return
    row = CONFIG['row'][CONFIG['cy']]
    if CONFIG['cx']:
        row_delete_char(row, CONFIG['cx'] - 1)
        CONFIG['cx'] -= 1
    else:
        CONFIG['cx'] = len(CONFIG['row'][CONFIG['cy'] - 1].chars)
        CONFIG['row'][CONFIG['cy'] - 1].chars += row.chars
        CONFIG['dirty'] += 1
        row_delete(CONFIG['cy'])
        CONFIG['cy'] -= 1

# File I/O

def editor_open(filename):
    CONFIG['filename'] = filename

    select_sytnax_highlight()

    f = open(filename, 'r')
    try:
        line = None
        for i, line in enumerate(f.readlines()):
            if line and line[-1] in ('\r', '\n'):
                editor_insert_row(i, line[:-1])
            else:
                editor_insert_row(i, line)
        else:
            if line and line[-1] in ('\r', '\n'):
                editor_insert_row(i, '')
        CONFIG['dirty'] = 0
    finally:
        f.close()

def editor_save(fd):
    if not CONFIG['filename']:
        CONFIG['filename'] = editor_prompt(fd, 'Save as : %s')
        if CONFIG['filename'] is None:
            set_status_message('Save aborted')
            return
        select_sytnax_highlight()
    try:
        with open(CONFIG['filename'], 'w') as f:
            data = '\n'.join(r.chars for r in CONFIG['row'])
            f.write(data)
    except OSError as e:
        set_status_message("Can't save! I/O error: %s" % e)
    CONFIG['dirty'] = 0
    set_status_message('%d bytes written to disk' % len(data))

# Find

def editor_find_callback(query, code, static={}):
    if static.get('saved_hl') is not None:
        CONFIG['row'][static['saved_hl_line']].hl = static['saved_hl']
        del static['saved_hl']

    if not query or code in (ord('\r'), ord('\x1b')):
        static['last_match'] = -1
        static['direction'] = 1
        return
    elif code in (ARROW_RIGHT, ARROW_DOWN):
        static['direction'] = 1
    elif code in (ARROW_LEFT, ARROW_UP):
        static['direction'] = -1
    else:
        static['last_match'] = -1
        static['direction'] = 1

    if static['last_match'] == -1:
        static['direction'] = 1
    direction = static['direction']
    current = static['last_match']
    i = 0
    while i < len(CONFIG['row']):
        current += direction
        if current == -1:
            current = len(CONFIG['row']) - 1
        elif current == len(CONFIG['row']):
            current = 0
        
        row = CONFIG['row'][current]
        match = row.render.find(query)
        if match != -1:
            static['last_match'] = current
            CONFIG['cy'] = current
            CONFIG['cx'] = row_rx_to_cx(row, match)
            CONFIG['rowoff'] = len(CONFIG['row'])

            static['saved_hl_line'] = current
            static['saved_hl'] = list(CONFIG['row'][current].hl)
            CONFIG['row'][current].hl[match:match + len(query)] = [HL_MATCH] * len(query)

            break
        i += 1


def editor_find(fd):
    saved_cx = CONFIG['cx']
    saved_cy = CONFIG['cy']
    saved_coloff = CONFIG['coloff']
    saved_rowoff = CONFIG['rowoff']

    query = editor_prompt(fd, 'Search: %s (Use ESC/Arrows/Enter)', editor_find_callback)
    if not query:
        CONFIG['cx'] = saved_cx
        CONFIG['cy'] = saved_cy
        CONFIG['coloff'] = saved_coloff
        CONFIG['rowoff'] = saved_rowoff

# Output

def editor_scroll():
    CONFIG['rx'] = 0
    if CONFIG['cy'] < len(CONFIG['row']):
        CONFIG['rx'] = row_cx_to_rx(CONFIG['row'][CONFIG['cy']], CONFIG['cx'])

    if CONFIG['cy'] < CONFIG['rowoff']:
        CONFIG['rowoff'] = CONFIG['cy']
    if CONFIG['cy'] >= CONFIG['rowoff'] + CONFIG['screen_rows']:
        CONFIG['rowoff'] = CONFIG['cy'] - CONFIG['screen_rows'] + 1
    if CONFIG['rx'] < CONFIG['coloff']:
        CONFIG['coloff'] = CONFIG['rx']
    if CONFIG['rx'] >= CONFIG['coloff'] + CONFIG['screen_cols']:
        CONFIG['coloff'] = CONFIG['rx'] - CONFIG['screen_cols'] + 1

def draw_rows():
    width = CONFIG['screen_cols']

    buffer = ''
    for i in xrange(CONFIG['screen_rows']):
        filerow = i + CONFIG['rowoff']
        if filerow >= len(CONFIG['row']):
            if len(CONFIG['row']) == 0 and i == CONFIG['screen_rows'] / 3:
                welcome = 'Ted editor -- version %s' % VERSION
                buffer += '~' + welcome[:width].center(width)[1:]
            else:
                buffer += '~'
        else:
            current_color = -1
            print >> sys.stderr, CONFIG['row'][filerow].hl
            for s, i in zip(CONFIG['row'][filerow].render,
                            CONFIG['row'][filerow].hl)[CONFIG['coloff']:][:width]:
                color = SYNTAX_TO_COLOR[i]
                code = ord(s)
                if curses.ascii.iscntrl(code):
                    sym = chr(ord('@') + code) if code <= 26 else '?'
                    buffer += '\x1b[7m' + sym + '\x1b[m'
                    if current_color != -1:
                        buffer += '\x1b[%dm' % current_color
                elif color == current_color:
                    buffer += s
                else:
                    buffer += '\x1b[%dm%s' % (color, s)
                    current_color = color
            buffer += '\x1b[39m'
        buffer += '\x1b[K\r\n'
    return buffer

def draw_status_bar():
    filename = CONFIG['filename'][:20] if CONFIG['filename'] else '[No Name]'
    status = '%s - %d lines %d:%d %s' % (filename, len(CONFIG['row']),
                                         CONFIG['cy'], CONFIG['cx'],
                                         "(modified)" if CONFIG['dirty'] else '')
    rstatus = '%s | %d/%d' % (
        CONFIG['syntax']['filetype'] if CONFIG['syntax'] else 'no ft',
        CONFIG['cy'] + 1,
        len(CONFIG['row']))
    rstatus = rstatus.rjust(CONFIG['screen_cols'] - len(status))
    return '\x1b[7m' + (status + rstatus)[:CONFIG['screen_cols']] + '\x1b[m\r\n'

def draw_message_bar():
    buffer = '\x1b[K'
    if CONFIG['status_msg'] and  time.time() - CONFIG['status_msg_time'] < 5:
        buffer += CONFIG['status_msg'][:CONFIG['screen_cols']]
    return buffer

def refresh_screen(fd):
    editor_scroll()

    buffer = ''
    buffer += '\x1b[?25l'
    buffer += '\x1b[H'
    buffer += draw_rows()
    buffer += draw_status_bar()
    buffer += draw_message_bar()
    buffer += '\x1b[%d;%dH' % ((CONFIG['cy'] - CONFIG['rowoff']) + 1, 
                               (CONFIG['rx'] - CONFIG['coloff']) + 1)
    buffer += '\x1b[?25h'

    os.write(fd, buffer)

def set_status_message(fmt, *args):
    CONFIG['status_msg'] = fmt
    CONFIG['status_msg_time'] = time.time()

# Input

def editor_prompt(fd, prompt, callback=None):
    buf = ''
    while True:
        set_status_message(prompt % buf)
        refresh_screen(fd)

        code = read_key(fd)
        if code in (DEL_KEY, ctrl('h'), BACKSPACE):
            buf = buf[:-1]
        elif code == ord('\x1b'):
            set_status_message('')
            if callback:
                callback(buf, code)
            return None
        elif code == ord('\r'):
            if buf:
                set_status_message('')
                if callback:
                    callback(buf, code)
                return buf
        elif not curses.ascii.iscntrl(code) and code < 128:
            buf += chr(code)

        if callback:
            callback(buf, code)

def move_cursor(key_code):
    row = CONFIG['row'][CONFIG['cy']].chars if CONFIG['cy'] < len(CONFIG['row']) else None

    if key_code == ARROW_LEFT:
        if CONFIG['cx'] != 0:
            CONFIG['cx'] -= 1
        elif CONFIG['cy'] > 0:
            CONFIG['cy'] -= 1
            CONFIG['cx'] = len(CONFIG['row'][CONFIG['cy']].chars)
    elif key_code == ARROW_RIGHT and row is not None:
        if CONFIG['cx'] < len(row):
            CONFIG['cx'] += 1
        elif CONFIG['cx'] == len(row):
            CONFIG['cy'] += 1
            CONFIG['cx'] = 0
    elif key_code == ARROW_UP and CONFIG['cy'] != 0:
        CONFIG['cy'] -= 1
    elif key_code == ARROW_DOWN and CONFIG['cy'] < len(CONFIG['row']) - 1:
        CONFIG['cy'] += 1

    row = CONFIG['row'][CONFIG['cy']].chars if CONFIG['cy'] < len(CONFIG['row']) else ''
    CONFIG['cx'] = min(CONFIG['cx'], len(row))

def process_key_press(fd):
    code = read_key(fd)

    if code == ord('\r'):
        editor_insert_newline()
    elif code == ord(ctrl('q')):
        if CONFIG['dirty'] and CONFIG['quit_times'] > 0:
            set_status_message('WARNING!!! File has unsaved changes. '
                               'Press Ctrl-Q %d more times to quit.' % 
                               CONFIG['quit_times'])
            CONFIG['quit_times'] -= 1
            return
        os.write(fd, '\x1b[2J')
        os.write(fd, '\x1b[H')
        sys.exit(0)
    elif code == ord(ctrl('s')):
        editor_save(fd)
    elif code == HOME_KEY:
        CONFIG['cx'] = 0
    elif code == END_KEY:
        if CONFIG['cy'] < len(CONFIG['row']):
            CONFIG['cx'] = len(CONFIG['row'][CONFIG['cy']].chars)
    elif code == ord(ctrl('f')):
        editor_find(fd)
    elif code in (BACKSPACE, ctrl('h'), DEL_KEY):
        if code == DEL_KEY:
            move_cursor(ARROW_RIGHT)
        editor_delete_char()
    elif code == PAGE_UP:
        CONFIG['cy'] = CONFIG['rowoff']
        for i in xrange(CONFIG['screen_rows']):
            move_cursor(ARROW_UP)
    elif code == PAGE_DOWN:
        CONFIG['cy'] = min(CONFIG['rowoff'] + CONFIG['screen_rows'] - 1,
                           len(CONFIG['row']))
        for i in xrange(CONFIG['screen_rows']):
            move_cursor(ARROW_DOWN)
    elif code in (ARROW_UP, ARROW_DOWN, ARROW_LEFT, ARROW_RIGHT):
        move_cursor(code)
    elif code in (ctrl('l'), '\x1b'):
        pass
    else:
        editor_insert_char(chr(code))

def init_editor(fd):
    CONFIG.update(get_window_size(fd))
    CONFIG['screen_rows'] -= 2
    set_status_message('HELP: Ctrl-S = save | Ctrl-Q = quit | Ctrl-F = find')


if __name__ == '__main__':
    import sys

    fd = sys.stdin.fileno()
    enable_raw_mode(fd)
    init_editor(fd)
    if len(sys.argv) > 1:
        editor_open(sys.argv[1])

    while True:
        refresh_screen(fd)
        process_key_press(fd)
