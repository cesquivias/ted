#!/usr/bin/env python

import atexit
import curses.ascii
import sys
import termios

ORIG_TERMIOS = None

def enable_raw_mode():
    global ORIG_TERMIOS

    fd = sys.stdin.fileno()
    ORIG_TERMIOS = termios.tcgetattr(fd)

    raw = termios.tcgetattr(fd)
    raw[0] = raw[0] & ~(termios.IXON)
    raw[3] = raw[3] & ~(termios.ECHO | termios.ICANON | termios.ISIG)
    termios.tcsetattr(fd, termios.TCSAFLUSH, raw)

    atexit.register(disable_raw_mode)

def disable_raw_mode():
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSAFLUSH, ORIG_TERMIOS)


if __name__ == '__main__':
    enable_raw_mode()

    while True:
        c = sys.stdin.read(1)
        if c is None:
            break
        elif c == 'q':
            break
        if curses.ascii.iscntrl(c):
            print '%d' % ord(c)
        else:
            print "%d ('%c')" % (ord(c), c)
