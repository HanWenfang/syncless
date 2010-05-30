#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon Apr 19 02:16:27 CEST 2010

"""Demo for hosting a circuits webserver within a Syncless process."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys

from circuits.web import Server, Controller
from syncless import coio
from syncless import patch


class Lprng(object):
  __slots__ = ['seed']
  def __init__(self, seed=0):
    self.seed = int(seed) & 0xffffffff
  def next(self):
    """Generate a 32-bit unsigned random number."""
    # http://en.wikipedia.org/wiki/Linear_congruential_generator
    self.seed = (
        ((1664525 * self.seed) & 0xffffffff) + 1013904223) & 0xffffffff
    return self.seed
  def __iter__(self):
    return self


class Root(Controller):
  def index(self, num=None):
    print >>sys.stderr, 'info: got connection'  # TODO(pts): Where from?
    if num is not None:
      num = int(num)
      next_num = Lprng(num).next()
      return ('<a href="/?num=%d">continue with %d</a>\n' %
              (next_num, next_num))
    else:
      return '<a href="/?num=0">start at 0</a><p>Hello, World!\n'


def ProgressReporter(delta_sec):
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)


if __name__ == "__main__":
  # Without this line ProgressReporter wouldn't be scheduled, and thus the
  # progress dots wouldn't be printed.
  patch.patch_circuits()
  coio.stackless.tasklet(ProgressReporter)(0.05)
  print >>sys.stderr, 'info: will listen on port 6666'
  # SUXX: 127.0.1.1
  (Server(6666) + Root()).run()
