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

CONFIG = {
    'original_termios': None,
    'screen_rows': 0,
    'screen_cols': 0,
}


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
        return os.read(fd, 1)
    except OSError as err:
        if err.errno == errno.EAGAIN:
            return None
        else:
            raise

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
    return '~\x1b[K\r\n' * (CONFIG['screen_cols'] - 1) + '~'

def refresh_screen(fd):
    buffer = ''
    buffer += '\x1b[?25l'
    buffer += '\x1b[H'
    buffer += draw_rows()
    buffer += '\x1b[H'
    buffer += '\x1b[?25h'

    os.write(fd, buffer)

def process_key_press(fd):
    c = read_key(fd)

    if c == ctrl('q'):
        os.write(fd, '\x1b[2J')
        os.write(fd, '\x1b[H')
        sys.exit(0)

def init_editor(fd):
    CONFIG.update(get_window_size(fd))


if __name__ == '__main__':
    fd = sys.stdin.fileno()
    enable_raw_mode(fd)
    init_editor(fd)

    while True:
        refresh_screen(fd)
        process_key_press(fd)
