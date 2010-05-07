#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Apr 25 01:44:48 CEST 2010

"""Demo for communicating with children via os.popen in non-blocking way."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import os
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
  patch.patch_os()
  coio.stackless.tasklet(ProgressReporter)(0.05)
  f = os.popen('sleep 1; ps x; exit 10', 'r')
  for line in f:
    print repr(line)
  status = f.close()
  print 'status code = 0x%x' % status
  assert status == 0xa00  # 2560
