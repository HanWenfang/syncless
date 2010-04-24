#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon Apr 19 02:16:27 CEST 2010

"""Demo for communicating with children via popen2 in non-blocking way."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import warnings
warnings.simplefilter('ignore', DeprecationWarning)  # for popen2

import popen2
import stackless
import sys

from syncless import coio
from syncless import patch

def ProgressReporter(delta_sec):
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)

if __name__ == "__main__":
  # Without this patch_...() call the ProgressReporter wouldn't be scheduled,
  # and thus the progress dots wouldn't be printed.
  if len(sys.argv) > 1:
    patch.patch_os()
  else:
    patch.patch_popen2()
  stackless.tasklet(ProgressReporter)(0.05)
  r, w = popen2.popen2('sleep 1; ps x')
  for line in r:
    print repr(line)
  print 'bye'
