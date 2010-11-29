#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Nov 11 18:07:33 CET 2010

import errno
import fcntl
import os
import select
import stackless
import sys
import time
import types

STDIN_FD = 0

stdin_read = []
deadlines = []
reads = {}
writes = {}

def SetNonBlocking(fd):
  flags = fcntl.fcntl(fd, fcntl.F_GETFL)
  fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

def AddTask(function):
  assert isinstance(function, types.FunctionType)
  stackless.tasklet(function)()

def Sleep(timeout):
  deadlines.append((time.time() + float(timeout), stackless.current))
  stackless.schedule_remove()

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
      reads.setdefault(STDIN_FD, []).append(stackless.current)
      stackless.schedule_remove()
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
  while deadlines or reads or writes or stackless.runcount > 1:
    if stackless.runcount > 1:
      timeout = 0
    elif deadlines:
      timeout = max(0, min(pair[0] for pair in deadlines) - time.time())
    else:
      timeout = None
    read_fds, write_fds, _ = select.select(reads, writes, (), timeout)
    to_call = []
    for fd in read_fds:
      if fd in reads:
        to_call.extend(reads.pop(fd))
    for fd in write_fds:
      if fd in writes:
        to_call.extend(writes.pop(fd))
    now = time.time()
    i = j = 0
    for pair in deadlines:
      if now >= pair[0]:
        to_call.append(pair[1])
      else:
        deadlines[j] = pair
        j += 1
    del deadlines[j:]
    for tasklet in to_call:
      tasklet.insert()
    stackless.schedule()

stackless.tasklet(MainLoop)()

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
  AddTask(Repeater)
  Ticker()
