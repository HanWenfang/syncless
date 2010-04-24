#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon Apr 19 02:16:27 CEST 2010

"""Demo for communicating with children via subprocess in non-blocking way."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import stackless
import subprocess
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
    patch.patch_subprocess()
  stackless.tasklet(ProgressReporter)(0.05)
  p = subprocess.Popen('sleep 1; ps x', stdout=subprocess.PIPE, shell=True,
                       close_fds=True)
  for line in p.stdout:
    print repr(line)
  print 'returncode = %d' % p.wait()
