#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat May 29 19:05:46 CEST 2010

"""Demo for thread pool of workers returning and raising."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys
import signal
import time

from syncless.best_stackless import stackless
from syncless import coio

def ProgressReporter(delta_sec):
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)


def Sleeper(thread_pool_obj, duration):
  thread_pool_obj(time.sleep, duration)


def Foo():
  thread_pool_obj = coio.thread_pool(3)
  stackless.tasklet(Sleeper)(thread_pool_obj, 9999)
  stackless.tasklet(Sleeper)(thread_pool_obj, 9999)
  stackless.tasklet(Sleeper)(thread_pool_obj, 2)
  stackless.schedule()
  f = lambda a, b: time.sleep(0.2) or a / b
  #f = lambda a, b: sys.exit(42)
  if False:
    for i in xrange(1, 11):
      print i
      assert 42 == worker(f, 84 * i, 2 * i)
  print 'C1'
  print thread_pool_obj(f, -42, -1)
  print 'C2'
  print thread_pool_obj(f, -42, -1)
  print 'C3'
  print thread_pool_obj(f, -42, -1)
  #print 'T'
  #time.sleep(10)
  print 'CR'
  print thread_pool_obj(f, 7, 0)

#coio.stackless.tasklet(ProgressReporter)(0.05)

Foo()
