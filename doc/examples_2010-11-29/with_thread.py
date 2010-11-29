#! /usr/bin/python2.4
# by pts@fazekas.hu at Thu Nov 11 13:48:42 CET 2010

import errno
import sys
import thread
import time
import types

lock = thread.allocate_lock()
lock.acquire()

def AddTask(function):
  assert isinstance(function, types.FunctionType)
  thread.start_new_thread(function, ())

def CallReleased(callable_obj, *args):
  try:
    lock.release()
    do_acquire = True
  except thread.error:  # Unacquired lock.
    return callable_obj(*args)
  try:
    return callable_obj(*args)
  finally:
    lock.acquire()

def Sleep(timeout):
  return CallReleased(time.sleep, timeout)

def ReadLine():
  return CallReleased(sys.stdin.readline)

# --- Application

line_count_ary = [0]

def Ticker():
  i = 0
  while True:
    i += 1
    print 'Tick %d with %d lines.' % (i, line_count_ary[0])
    Sleep(3)

def Repeater():
  print 'Hi, please type and press Enter.'
  while True:
    line = ReadLine()
    if not line:
      break
    line_count_ary[0] += 1
    print 'You typed %r.' % line
  print 'End of input.'


if __name__ == '__main__':
  # No need for: SetNonBlocking(STDIN_FD)
  AddTask(Repeater)
  Ticker()
