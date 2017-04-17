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

def enable_raw_mode(fd):
    original_attrs = termios.tcgetattr(fd)
    atexit.register(functools.partial(termios.tcsetattr, fd, termios.TCSAFLUSH,
                                      original_attrs))
    tty.setraw(fd)

def read_key(fd):
    try:
        return os.read(fd, 1)
    except OSError as err:
        if err.errno == errno.EAGAIN:
            return None
        else:
            raise

def process_key_press(fd):
    c = read_key(fd)

    if c == ctrl('q'):
        sys.exit(0)


if __name__ == '__main__':
    fd = sys.stdin.fileno()
    enable_raw_mode(fd)

    while True:
        process_key_press(fd)
