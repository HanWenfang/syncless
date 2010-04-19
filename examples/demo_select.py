#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon Apr 19 02:02:18 CEST 2010

"""Demo code for select(2) with Syncless.

Please note that select(2) is inherently slow. Please see FAQ entry Q14 in
README.txt .
"""

import stackless
import sys

from syncless import coio


if __name__ == '__main__':
  if len(sys.argv) <= 1 or sys.argv[1] == 'a':
    print >>sys.stderr, 'A'
    # Returns, immediately, retval[1] becomes [sys.stderr, sys.stdout] or
    # [sys.stdout, sys.stderr].
    print >>sys.stderr, coio.select(
        [sys.stdin], [sys.stderr, sys.stdout], [], 3)
  elif len(sys.argv) > 1 and sys.argv[1] == 'b':
    print >>sys.stderr, 'B'
    # Times out after 3 seconds.
    print >>sys.stderr, coio.select([sys.stdin], [], [], 3)
  elif len(sys.argv) > 1 and sys.argv[1] == 'c':
    print >>sys.stderr, 'C'
    # Waits indefinitely.
    print >>sys.stderr, coio.select([sys.stdin], [], [], None)
  else:
    assert 0
