#!/usr/bin/env python

import atexit
import curses.ascii
import os
import sys
import termios

ORIG_TERMIOS = None

def enable_raw_mode():
    global ORIG_TERMIOS

    fd = sys.stdin.fileno()
    ORIG_TERMIOS = termios.tcgetattr(fd)

    raw = termios.tcgetattr(fd)
    raw[0] = raw[0] & ~(termios.IXON | termios.ICRNL)
    raw[1] = raw[1] & ~(termios.OPOST)
    raw[3] = raw[3] & ~(termios.ECHO | termios.ICANON | termios.ISIG | termios.IEXTEN)
    raw[6][termios.VMIN] = 0
    raw[6][termios.VTIME] = 1

    termios.tcsetattr(fd, termios.TCSAFLUSH, raw)

    atexit.register(disable_raw_mode)
    return fd

def disable_raw_mode():
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSAFLUSH, ORIG_TERMIOS)


if __name__ == '__main__':
    fd = enable_raw_mode()

    while True:
        c = os.read(fd, 1)
        if not c:
            continue
        if curses.ascii.iscntrl(c):
            print '%d\r' % ord(c)
        else:
            print "%d ('%c')\r" % (ord(c), c)
        if c == 'q':
            break
