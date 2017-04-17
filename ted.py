#!/usr/bin/env python

import atexit
import curses.ascii
import errno
import functools
import os
import sys
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

def draw_rows(fd):
    for i in xrange(24):
        os.write(fd, '~\r\n')

def refresh_screen(fd):
    os.write(fd, '\x1b[2J')
    os.write(fd, '\x1b[H')

    draw_rows(fd)

    os.write(fd, '\x1b[H')

def process_key_press(fd):
    c = read_key(fd)

    if c == ctrl('q'):
        os.write(fd, '\x1b[2J')
        os.write(fd, '\x1b[H')
        sys.exit(0)


if __name__ == '__main__':
    fd = sys.stdin.fileno()
    enable_raw_mode(fd)

    while True:
        refresh_screen(fd)
        process_key_press(fd)
