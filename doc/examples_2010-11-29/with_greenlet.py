#! /usr/bin/python2.4
# by pts@fazekas.hu at Thu Nov 11 13:48:42 CET 2010

import greenlet
import errno
import fcntl
import os
import select
import sys
import time
import types

STDIN_FD = 0

main = greenlet.getcurrent()
tasks = []
stdin_read = []

def SetNonBlocking(fd):
  flags = fcntl.fcntl(fd, fcntl.F_GETFL)
  fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

def AddTask(function):
  assert isinstance(function, types.FunctionType)
  tasks.append(greenlet.greenlet(function))

def Sleep(timeout):
  deadline = time.time() + timeout
  main.switch({'deadline': deadline})
  while time.time() < deadline:
    main.switch({'deadline': deadline})

def ReadLine():
  while True:
    try:
      got = os.read(STDIN_FD, 1024)
      if not got or '\n' in got:
        break
      stdin_read.append(got)
    except OSError, e:
      if e[0] != errno.EAGAIN:
        raise
      main.switch({'read': STDIN_FD})
  if got:
    i = got.find('\n') + 1
    stdin_read.append(got[:i])
    line = ''.join(stdin_read)
    del stdin_read[:]
    if i < len(got):
      stdin_read.append(got[i:])
    return line
  else:
    line = ''.join(stdin_read)
    del stdin_read[:]
    return line

def MainLoop():
  assert main is greenlet.getcurrent()
  read_fds = set()
  write_fds = set()
  # TODO(pts): Explain why no exception handling.
  while tasks:
    read_fds.clear()
    write_fds.clear()
    deadline = None
    for task in list(tasks):
      try:
        event = task.switch()
      except greenlet.GreenletExit:
        tasks.remove(task)
        continue
      if 'deadline' in event:
        if deadline is None:
          deadline = float(event['deadline'])
        else:
          deadline = min(deadline, float(event['deadline']))
      if 'read' in event:
        read_fds.add(int(event['read']))
      if 'write' in event:
        write_fds.add(int(event['write']))
    if deadline is None:
      timeout = None
    else:
      timeout = deadline - time.time()
      if timeout < 0:
        timeout = 0
    select.select(read_fds, write_fds, (), timeout)
    # TODO(pts): Don't resume a task (with task.next()) in the next
    # iteration if its event hasn't happened.

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
  SetNonBlocking(STDIN_FD)
  AddTask(Ticker)
  AddTask(Repeater)
  MainLoop()
