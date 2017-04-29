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
import tty

VERSION = '0.0.1'
TAB_STOP = 8

class Row(object):
    def __init__(self, chars):
        self.chars = chars
        self.render = chars.replace('\t', ' ' * TAB_STOP)


CONFIG = {
    'cx': 0,
    'cy': 0,
    'rx': 0,
    'original_termios': None,
    'rowoff': 0,
    'coloff': 0,
    'screen_rows': 0,
    'screen_cols': 0,
    'num_rows': 0,
    'row': [],
    'filename': None,
}

ARROW_LEFT = 1000
ARROW_RIGHT = 1001
ARROW_UP = 1002
ARROW_DOWN = 1003
DEL_KEY = 1004
HOME_KEY = 1005
END_KEY = 1006
PAGE_UP = 1007
PAGE_DOWN = 1008

def ctrl(key):
    return chr(ord(key) & 0x1f)

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

def row_cx_to_rx(row, cx):
    rx = 0
    for i in xrange(cx):
        if row.chars[i] == '\t':
            rx += (TAB_STOP - 1) - (rx % TAB_STOP)
        rx += 1
    return rx

# File I/O

def editor_open(filename):
    CONFIG['filename'] = filename
    f = open(filename, 'r')
    try:
        for line in f.readlines():
            if line and line[-1] in ('\r', '\n'):
                line = line[:-1]
            CONFIG['row'].append(Row(line))
            CONFIG['num_rows'] += 1
    finally:
        f.close()

# Output

def editor_scroll():
    CONFIG['rx'] = 0
    if CONFIG['cy'] < CONFIG['num_rows']:
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
        if filerow >= CONFIG['num_rows']:
            if CONFIG['num_rows'] == 0 and i == CONFIG['screen_rows'] / 3:
                welcome = 'Ted editor -- version %s' % VERSION
                buffer += '~' + welcome[:width].center(width)[1:]
            else:
                buffer += '~'
        else:
            buffer += CONFIG['row'][filerow].render[CONFIG['coloff']:][:width]
        buffer += '\x1b[K\r\n'
    return buffer

def draw_status_bar():
    filename = CONFIG['filename'][:20] if CONFIG['filename'] else '[No Name]'
    status = '%s - %d lines' % (filename, CONFIG['num_rows'])
    rstatus = '%d/%d' % (CONFIG['cy'] + 1, CONFIG['num_rows'])
    rstatus = rstatus.rjust(CONFIG['screen_cols'] - len(status))
    return '\x1b[7m' + (status + rstatus)[:CONFIG['screen_cols']] + '\x1b[m'

def refresh_screen(fd):
    editor_scroll()

    buffer = ''
    buffer += '\x1b[?25l'
    buffer += '\x1b[H'
    buffer += draw_rows()
    buffer += draw_status_bar()
    buffer += '\x1b[%d;%dH' % ((CONFIG['cy'] - CONFIG['rowoff']) + 1, 
                               (CONFIG['rx'] - CONFIG['coloff']) + 1)
    buffer += '\x1b[?25h'

    os.write(fd, buffer)

# Input

def move_cursor(key_code):
    row = CONFIG['row'][CONFIG['cy']].chars if CONFIG['cy'] < CONFIG['num_rows'] else None

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
    elif key_code == ARROW_DOWN and CONFIG['cy'] < CONFIG['num_rows'] - 1:
        CONFIG['cy'] += 1

    row = CONFIG['row'][CONFIG['cy']].chars if CONFIG['cy'] < CONFIG['num_rows'] else ''
    CONFIG['cx'] = min(CONFIG['cx'], len(row))

def process_key_press(fd):
    code = read_key(fd)

    if code == ord(ctrl('q')):
        os.write(fd, '\x1b[2J')
        os.write(fd, '\x1b[H')
        sys.exit(0)
    elif code == HOME_KEY:
        CONFIG['cx'] = 0
    elif code == END_KEY:
        if CONFIG['cy'] < CONFIG['num_rows']:
            CONFIG['cx'] = len(CONFIG['row'][CONFIG['cy']].chars)
    elif code == PAGE_UP:
        CONFIG['cy'] = CONFIG['rowoff']
        for i in xrange(CONFIG['screen_rows']):
            move_cursor(ARROW_UP)
    elif code == PAGE_DOWN:
        CONFIG['cy'] = min(CONFIG['rowoff'] + CONFIG['screen_rows'] - 1,
                           CONFIG['num_rows'])
        for i in xrange(CONFIG['screen_rows']):
            move_cursor(ARROW_DOWN)
    else:
        move_cursor(code)

def init_editor(fd):
    CONFIG.update(get_window_size(fd))
    CONFIG['screen_rows'] -= 1


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
