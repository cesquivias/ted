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

CONFIG = {
    'cx': 0,
    'cy': 0,
    'original_termios': None,
    'screen_rows': 0,
    'screen_cols': 0,
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

def draw_rows():
    width = CONFIG['screen_cols']
    num_before_lines = CONFIG['screen_rows'] / 3
    buffer = '~\x1b[K\r\n' * num_before_lines
    welcome = 'Ted editor -- version %s' % VERSION
    buffer += '~' + welcome[:width].center(width)[1:]
    buffer += '~\x1b[K\r\n' * (CONFIG['screen_rows'] - num_before_lines - 2)
    buffer += '~\x1b[K'
    return buffer

def refresh_screen(fd):
    buffer = ''
    buffer += '\x1b[?25l'
    buffer += '\x1b[H'
    buffer += draw_rows()
    buffer += '\x1b[%d;%dH' % (CONFIG['cy'] + 1, CONFIG['cx'] + 1)
    buffer += '\x1b[?25h'

    os.write(fd, buffer)

# Input

def move_cursor(key_code):
    if key_code == ARROW_LEFT and CONFIG['cx'] != 0:
        CONFIG['cx'] -= 1
    elif key_code == ARROW_RIGHT and CONFIG['cx'] < CONFIG['screen_cols'] - 1:
        CONFIG['cx'] += 1
    elif key_code == ARROW_UP and CONFIG['cy'] != 0:
        CONFIG['cy'] -= 1
    elif key_code == ARROW_DOWN and CONFIG['cy'] < CONFIG['screen_rows'] - 1:
        CONFIG['cy'] += 1

def process_key_press(fd):
    code = read_key(fd)

    if code == ord(ctrl('q')):
        os.write(fd, '\x1b[2J')
        os.write(fd, '\x1b[H')
        sys.exit(0)
    elif code == HOME_KEY:
        CONFIG['cx'] = 0
    elif code == END_KEY:
        CONFIG['cx'] = CONFIG['screen_cols'] - 1
    elif code == PAGE_UP:
        for i in xrange(CONFIG['screen_rows']):
            move_cursor(ARROW_UP)
    elif code == PAGE_DOWN:
        for i in xrange(CONFIG['screen_rows']):
            move_cursor(ARROW_DOWN)
    else:
        move_cursor(code)

def init_editor(fd):
    CONFIG.update(get_window_size(fd))


if __name__ == '__main__':
    fd = sys.stdin.fileno()
    enable_raw_mode(fd)
    init_editor(fd)

    while True:
        refresh_screen(fd)
        process_key_press(fd)
