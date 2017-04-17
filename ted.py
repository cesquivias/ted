#!/usr/bin/env python

import atexit
import curses.ascii
import errno
import functools
import os
import sys
import termios
import tty

def ctrl(key):
    return chr(ord(key) & 0x1f)

def on_exit_func(fd, tcattr):
    def on_exit():
        os.write(fd, '\x1b[2J')
        os.write(fd, '\x1b[H')
        termios.tcsetattr(fd, termios.TCSAFLUSH, tcattr)
    return on_exit

def enable_raw_mode(fd):
    original_attrs = termios.tcgetattr(fd)
    atexit.register(on_exit_func(fd, original_attrs))
    tty.setraw(fd)

def read_key(fd):
    try:
        return os.read(fd, 1)
    except OSError as err:
        if err.errno == errno.EAGAIN:
            return None
        else:
            raise

def refresh_screen(fd):
    os.write(fd, '\x1b[2J')
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
