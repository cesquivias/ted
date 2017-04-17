#!/usr/bin/env python

import atexit
import curses.ascii
import errno
import functools
import os
import sys
import termios
import tty

def enable_raw_mode(fd):
    original_attrs = termios.tcgetattr(fd)
    atexit.register(functools.partial(termios.tcsetattr, fd, termios.TCSAFLUSH,
                                      original_attrs))
    tty.setraw(fd)


if __name__ == '__main__':
    fd = sys.stdin.fileno()
    enable_raw_mode(fd)

    while True:
        try:
            c = os.read(fd, 1)
        except OSError as err:
            if err.errno == errno.EAGAIN:
                c = None
            else:
                raise
        if not c:
            continue
        if curses.ascii.iscntrl(c):
            print '%d\r' % ord(c)
        else:
            print "%d ('%c')\r" % (ord(c), c)
        if c == 'q':
            break
