#! /usr/bin/python2.5
# by pts@fazekas.hu at Sun Nov 14 21:48:04 CET 2010

import errno
import fcntl
import os
import select
import sys
import time
import types

STDIN_FD = 0

stdin_read = []
deadlines = [] # [(deadline, generator)]
reads = {}  # {fd: [generator]}
writes = {}  # {fd: [generator]}
readys = []  # [(generator, value_to_send)]
followers = {}  # {generator_to_stop_first: [generator_to_resume_after]}

def SetNonBlocking(fd):
  flags = fcntl.fcntl(fd, fcntl.F_GETFL)
  fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

class WaitForEvent(dict):
  pass

def AddTask(function):
  assert isinstance(function, types.FunctionType)
  generator = function()
  assert isinstance(generator, types.GeneratorType)
  readys.append(generator)

def Sleep(timeout):
  return WaitForEvent({'deadline': time.time() + float(timeout)})

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
      yield WaitForEvent({'read': STDIN_FD})
  if got:
    i = got.find('\n') + 1
    stdin_read.append(got[:i])
    line = ''.join(stdin_read)
    del stdin_read[:]
    if i < len(got):
      stdin_read.append(got[i:])
  else:
    line = ''.join(stdin_read)
    del stdin_read[:]
  raise StopIteration(line)  # Disadvantage: can't use `return' here.

def GetBlockedGenerators():
  blockeds = set()
  for fd in reads:
    blockeds.update(reads[fd])
  for fd in writes:
    blockeds.update(writes[fd])
  for _, generator in deadlines:
    blockeds.add(generator)
  for generator0 in followers:
    blockeds.update(followers[generator0])
  return blockeds

def MainLoop():
  while deadlines or reads or writes or readys:
    if readys:
      timeout = 0
    elif deadlines:
      timeout = max(0, min(pair[0] for pair in deadlines) - time.time())
    else:
      timeout = None
    read_fds, write_fds, _ = select.select(reads, writes, (), timeout)
    for fd in read_fds:
      if fd in reads:
        # TODO(pts): Remove the generator from writes and deadlines.
        readys.extend(reads.pop(fd))
    for fd in write_fds:
      if fd in writes:
        readys.extend(writes.pop(fd))
    now = time.time()
    i = j = 0
    for pair in deadlines:
      if now >= pair[0]:
        readys.append(pair[1])
      else:
        deadlines[j] = pair
        j += 1
    del deadlines[j:]

    # When a generator becomes ready, remove it from reads, writes and
    # deadlines. This implementation is quite slow.
    readys_set = set(readys)
    for fd in reads:
      reads[fd][:] = [generator for generator in reads[fd]
                      if generator not in readys_set]
      if not reads[fd]:
        del reads[fd]
    for fd in writes:
      writes[fd][:] = [generator for generator in writes[fd]
                       if generator not in readys_set]
      if not writes[fd]:
        del writes[fd]
    deadlines[:] = [pair for pair in deadlines if pair[1] not in readys_set]
      
    to_call = [(generator, None) for generator in readys]
    del readys[:]
    for generator, value_to_send in to_call:
      try:
        wait_condition = generator.send(value_to_send)
      except StopIteration, exc:
        generators = followers.pop(generator, None)
        if generators:
          if exc.args:
            value_to_send = exc[0] # Return value of the previous generator.
          else:
            value_to_send = None
          for generator in generators:
            to_call.append((generator, value_to_send))
          continue
      if isinstance(wait_condition, WaitForEvent):
        fd = wait_condition.get('read')
        if fd is not None:
          reads.setdefault(fd, []).append(generator)
        fd = wait_condition.get('write')
        if fd is not None:
          writes.setdefault(fd, []).append(generator)
        deadline = wait_condition.get('deadline')
        if deadline is not None:
          deadlines.append((deadline, generator))
      elif isinstance(wait_condition, types.GeneratorType):
        followers.setdefault(wait_condition, []).append(generator)
        if wait_condition not in GetBlockedGenerators():
          to_call.append((wait_condition, None))
      else:
        assert 0, 'got wait_condition of type %r' % type(wait_condition)
  assert not followers

# --- Application

line_count_ary = [0]

def Ticker():
  i = 0
  while True:
    i += 1
    print 'Tick %d with %d lines.' % (i, line_count_ary[0])
    yield Sleep(3)

def Repeater():
  print 'Hi, please type and press Enter.'
  while True:
    line = yield ReadLine()
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
