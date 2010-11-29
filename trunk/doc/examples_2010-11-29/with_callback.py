#! /usr/bin/python2.4
# by pts@fazekas.hu at Fri Nov 12 00:49:16 CET 2010

import errno
import fcntl
import os
import select
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
  Sleep(0, function)

def Sleep(timeout, callback):
  assert isinstance(callback, types.FunctionType)
  deadlines.append((time.time() + float(timeout), callback))

def ReadLine(callback):
  def ReadCallback():
    try:
      got = os.read(STDIN_FD, 1024)
    except OSError, e:
      if e[0] != errno.EAGAIN:
        raise
      got = None
    if got == '':  # EOF
      line = ''.join(stdin_read)
      del stdin_read[:]
      callback(line)
    elif got and '\n' in got:
      stdin_read.append(got)
      stdin_read[:] = ''.join(stdin_read).split('\n')
      stdin_read.reverse()
      while len(stdin_read) > 1:
        callback(stdin_read.pop() + '\n')
    else:
      if got:
        stdin_read.append(got)
      reads.setdefault(STDIN_FD, []).append(ReadCallback)
  ReadCallback()

def MainLoop():
  while deadlines or reads or writes:
    if deadlines:
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
    for callback in to_call:
      callback()

# --- Application

line_count_ary = [0]

def Ticker():
  i_ary = [0]
  def Callback():
    i_ary[0] += 1
    print 'Tick %d with %d lines.' % (i_ary[0], line_count_ary[0])
    Sleep(3, Callback)
  Callback()

def Repeater():
  print 'Hi, please type and press Enter.'
  def Callback(line):
    if line:
      print 'You typed %r.' % line
      line_count_ary[0] += 1
      ReadLine(Callback)
    else:
      print 'End of input.'
  ReadLine(Callback)

if __name__ == '__main__':
  SetNonBlocking(STDIN_FD)
  AddTask(Ticker)
  AddTask(Repeater)
  MainLoop()
