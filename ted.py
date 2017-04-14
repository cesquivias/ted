#!/usr/bin/env python

import sys

if __name__ == '__main__':
    while True:
        c = sys.stdin.read(1)
        if c is None:
            break
        elif c == 'q':
            break
