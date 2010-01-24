#! /usr/bin/python2.5
# by pts@fazekas.hu at Sat Jan 23 21:32:48 CET 2010
# TODO(pts): Diagnose why 1 request takes 4500 ms. (limitation of greenlet?)

import event
import errno
import fcntl
import os
import signal
import socket
import sys
from collections import deque

from greenlet_fix import greenlet
import lprng

EAGAIN = errno.EAGAIN

def SetFdBlocking(fd, is_blocking):
  """Set a file descriptor blocking or nonblocking.

  Please note that this may affect more than expected, for example it may
  affect sys.stderr when called for sys.stdout.

  Returns:
    The old blocking value (True or False).
  """
  if hasattr(fd, 'fileno'):
    fd = fd.fileno()
  old = fcntl.fcntl(fd, fcntl.F_GETFL)
  if is_blocking:
    value = old & ~os.O_NONBLOCK
  else:
    value = old | os.O_NONBLOCK
  if old != value:
    fcntl.fcntl(fd, fcntl.F_SETFL, value)
  return bool(old & os.O_NONBLOCK)


runnable_greenlets = deque()
main_greenlet = greenlet.getcurrent()
main_loop_greenlet = None
runnable_greenlets.append(main_greenlet)

def SendExceptionAndRun(greenlet_obj, exc_info):
  """Send exception to greenlet, even if it's blocked on a channel.

  The specified greenlet is moved to runnable_greenlets to ensure that it
  eventually gets scheduled.
  """
  if not isinstance(exc_info, list) and not isinstance(exc_info, tuple):
    raise TypeError
  if len(exc_info) < 3:
    exc_info = list(exc_info) + [None, None]
  if greenlet_obj is runnable_greenlets[0]:  # greenlet.getcurrent()
    raise exc_info[0], exc_info[1], exc_info[2]

  i = 0
  for found_greenlet in runnable_greenlets:
    if found_greenlet is greenlet_obj:
      runnable_greenlets.rotate(-i)  # This is also linear.
      greenlet_obj.throw(*exc_info)
      break
    i += 1
  runnable_greenlets.appendleft(greenlet_obj)
  greenlet_obj.throw(*exc_info)

def ScheduleRemove():
  #assert greenlet.getcurrent() is runnable_greenlets.popleft()
  runnable_greenlets.popleft()
  runnable_greenlets[0].switch()

def Schedule():
  #assert greenlet.getcurrent() is runnable_greenlets[0]
  runnable_greenlets.rotate(-1)
  runnable_greenlets[0].switch()

def Run(greenlet_obj):
  """Runs the specified greenlet.

  Please note that this is quadratic in the size of runnable_greenlets.
  """
  i = 0
  for found_greenlet in runnable_greenlets:
    if found_greenlet is greenlet_obj:
      if i:
        runnable_greenlets.rotate(-i)  # This is also linear.
        greenlet_obj.switch()
      break
    i += 1
  runnable_greenlets.appendleft(greenlet_obj)
  greenlet_obj.switch()

def HandleWakeup(ev, fd, evtype, greenlet_obj):
  runnable_greenlets.append(greenlet_obj)

def Accept(sock):
  while True:
    try:
      return sock.accept()
    except socket.error, e:
      if e.args[0] != errno.EAGAIN:
        raise
      event.event(HandleWakeup, handle=sock.fileno(), evtype=event.EV_READ,
                  arg=greenlet.getcurrent()).add()
      ScheduleRemove()

def ReadAtMost(fd, size):
  while True:
    try:
      return os.read(fd, size)
    except OSError, e:
      if e.errno != errno.EAGAIN:
        raise
      event.event(HandleWakeup, handle=fd, evtype=event.EV_READ,
                  arg=greenlet.getcurrent()).add()
      ScheduleRemove()

def Write(fd, data):
  while True:
    try:
      got = os.write(fd, data)
      if got == len(data):
        return
      if got:
        data = data[got:]  # TODO(pts): Do with less copy
    except OSError, e:
      if e.errno != errno.EAGAIN:
        raise
      event.event(HandleWakeup, handle=fd, evtype=event.EV_WRITE,
                  arg=greenlet.getcurrent()).add()
      ScheduleRemove()

def MainLoop():
  while True:
    # Exceptions (if any) in event handlers would propagate to here.
    # Argument: nonblocking: don't block if nothing available.
    event.loop(len(runnable_greenlets) > 1)
    Schedule()

def Handler(cs, csaddr):
  print >>sys.stderr, 'info: connection from %r' % (
      cs.getpeername(),)
  SetFdBlocking(cs, False)
  csfd = cs.fileno()

  # Read HTTP request.
  request = ''
  while True:
    # TODO(pts): Implement (in C) and use line buffering.
    got = ReadAtMost(csfd, 32768)
    assert got
    request += got
    i = request.find('\n\r\n')
    if i >= 0:
      j = request.find('\n\n')
      if j >= 0 and j < i:
        i = j + 2
      else:
        i += 3
      break
    else:
      i = request.find('\n\n')
      if i >= 0:
        i + 2
        break
  head = request[:i]
  body = request[i:]

  # Parse HTTP request.
  # Please note that an assertion here aborts the server.
  i = head.find('\n')
  assert i > 0, (head,)
  if head[i - 1] == '\r':
    line1 = head[:i - 1]
  else:
    line1 = head[:i]
  items = line1.split(' ')
  assert 3 == len(items)
  assert items[2] in ('HTTP/1.0', 'HTTP/1.1')
  assert items[0] == 'GET'
  assert items[1].startswith('/')
  try:
    num = int(items[1][1:])
  except ValueError:
    num = None

  # Write HTTP response.
  if num is None:
    response = ('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n'
                '<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = lprng.Lprng(num).next()
    response = ('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n'
                '<a href="/%d">continue with %d</a>\n' %
                (next_num, next_num))
  Write(csfd, response)
  cs.close()  # No need for event_del, nothing listening (?).

  # TODO(pts): In a finally: block for all greenlets.
  #assert greenlet.getcurrent() is runnable_greenlets.popleft()
  runnable_greenlets.popleft()
  greenlet.getcurrent().parent = runnable_greenlets[0]

def SignalHandler(ev, sig, evtype, arg):
  SendExceptionAndRun(main_greenlet, (KeyboardInterrupt,))

if __name__ == '__main__':
  event.event(SignalHandler, handle=signal.SIGINT,
              evtype=event.EV_SIGNAL|event.EV_PERSIST).add()
  main_loop_greenlet = greenlet.greenlet(MainLoop)
  runnable_greenlets.appendleft(main_loop_greenlet)
  main_loop_greenlet.switch()

  ss = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  SetFdBlocking(ss, False)
  ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  # TODO(pts): Use ss._sock.
  ss.bind(('127.0.0.1', 8080))
  ss.listen(128)
  print >>sys.stderr, 'info: listening on: %r' % (
      ss.getsockname(),)
  while True:
    cs, csaddr = Accept(ss)
    handler_greenlet = greenlet.greenlet(Handler)
    runnable_greenlets.rotate(-1)
    runnable_greenlets.appendleft(handler_greenlet)
    handler_greenlet.switch(cs, csaddr)
    cs = None  # Save memory.
