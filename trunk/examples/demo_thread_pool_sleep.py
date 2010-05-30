#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun May 30 12:18:14 CEST 2010

"""Demo with a thread pool of sleeping workers for Syncless.

If you run this program without an argument, it will run for about 2
seconds, because a thread pool of size 4 will be filled with 4 threads doing
a sleep of 2 seconds each.

If you run this program with an argument, it will run for about 4
seconds, because a thread pool of size 3 will be used by 4 threads doing
a sleep of 2 seconds each, so the last sleep can only be started after the
first thread has finished.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys
import time

from syncless.best_stackless import stackless
from syncless import coio

def ProgressReporter(delta_sec):
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)

if __name__ == '__main__':
  stackless.tasklet(ProgressReporter)(0.05)
  thread_pool_obj = coio.thread_pool(4 - bool(len(sys.argv) > 1))
  stackless.tasklet(thread_pool_obj)(time.sleep, 2)
  stackless.tasklet(thread_pool_obj)(time.sleep, 2)
  stackless.tasklet(thread_pool_obj)(time.sleep, 2)
  sys.stderr.write('S')
  stackless.schedule()
  thread_pool_obj(time.sleep, 2)
  sys.stderr.write('D\n')
