#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat Jan 23 20:15:51 CET 2010

import event
import errno
import fcntl
import os
import signal
import socket
import stackless
import sys

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

def SendException(tasklet, exc_info):
  """Send exception to tasklet, even if it's blocked on a channel.

  To get the tasklet is activated (to handle the exception) after
  SendException, call tasklet.run() after calling SendException.

  tasklet.insert() is called automatically to ensure that it eventually gets
  scheduled.
  """
  if not isinstance(exc_info, list) and not isinstance(exc_info, tuple):
    raise TypeError
  if tasklet == stackless.current:
    if len(exc_info) < 3:
      exc_info = list(exc_info) + [None, None]
    raise exc_info[0], exc_info[1], exc_info[2]
  bomb = stackless.bomb(*exc_info)
  if tasklet.blocked:
    c = tasklet._channel
    old_preference = c.preference
    c.preference = 1  # Prefer the sender.
    for i in xrange(-c.balance):
      c.send(bomb)
    c.preference = old_preference
  else:
    tasklet.tempval = bomb
  tasklet.insert()

def HandleWakeup(ev, fd, evtype, tasklet):
  tasklet.insert()

def Accept(sock):
  while True:
    try:
      return sock.accept()
    except socket.error, e:
      if e.errno != errno.EAGAIN:
        raise
      event.event(HandleWakeup, handle=sock.fileno(), evtype=event.EV_READ,
                  arg=stackless.current).add()
      stackless.schedule_remove()

def ReadAtMost(fd, size):
  while True:
    try:
      return os.read(fd, size)
    except OSError, e:
      if e.errno != errno.EAGAIN:
        raise
      event.event(HandleWakeup, handle=fd, evtype=event.EV_READ,
                  arg=stackless.current).add()
      stackless.schedule_remove()

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
                  arg=stackless.current).add()
      stackless.schedule_remove()

def MainLoop():
  while True:
    # Exceptions (if any) in event handlers would propagate to here.
    # Argument: nonblocking: don't block if nothing available.
    event.loop(stackless.runcount > 1)
    stackless.schedule()

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

def SignalHandler(ev, sig, evtype, arg):
  SendException(stackless.main, (KeyboardInterrupt,))
  # TODO(pts): ev.delete()?
  stackless.main.run()

if __name__ == '__main__':
  event.event(SignalHandler, handle=signal.SIGINT,
              evtype=event.EV_SIGNAL|event.EV_PERSIST).add()
  stackless.tasklet(MainLoop)()

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
    stackless.tasklet(Handler)(cs, csaddr)
    cs = None  # Save memory.
