#!/usr/bin/env python

import sys
import termios

def enable_raw_mode():
    fd = sys.stdin.fileno()
    raw = termios.tcgetattr(fd)
    raw[3] = raw[3] & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSAFLUSH, raw)


if __name__ == '__main__':
    enable_raw_mode()

    while True:
        c = sys.stdin.read(1)
        if c is None:
            break
        elif c == 'q':
            break
