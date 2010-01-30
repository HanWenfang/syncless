#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Jan 24 13:38:30 CET 2010

import event  # pts' private version of pyevent, with event.evbufferobj
import errno
import fcntl
import os
import signal
import socket
import stackless
import sys

import lprng

assert hasattr(event, 'evbufferobj')

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

# !! SUXX: I/O buffering makes it that slow. Move it to C code, and measure it
# with stackless.
class NbFile(object):
  __attrs__ = ['read_fd', 'write_fd', 'read_ebo', 'write_ebo']

  def __init__(self, read_fd, write_fd):
    # TODO(pts): Close.
    self.read_fd = read_fd
    self.write_fd = write_fd
    self.read_ebo = event.evbufferobj()
    self.write_ebo = event.evbufferobj()

  def read_at_most(self, n=-1):
    read_ebo = self.read_ebo
    read_fd = self.read_fd
    # Raises IOError.
    got = read_ebo.read_from_fd_again(read_fd, n)
    while got is None:
      event.event(HandleWakeup, handle=read_fd, evtype=event.EV_READ,
                  arg=stackless.current).add()
      stackless.schedule_remove()
      got = read_ebo.read_from_fd_again(read_fd, n)
    return read_ebo.consume(got)

  def readline(self):
    read_ebo = self.read_ebo
    read_fd = self.read_fd
    # Raises IOError.
    line = read_ebo.consumeline()
    while not line:
      got = read_ebo.read_from_fd_again(read_fd, 8192)
      if got:
        line = read_ebo.peekline()  # TODO(pts): Search only new data.
        if line:
          read_ebo.drain(len(line))
          return line
      elif got == 0:  # EOF
        return read_ebo.consume()
      event.event(HandleWakeup, handle=read_fd, evtype=event.EV_READ,
                  arg=stackless.current).add()
      stackless.schedule_remove()
    return line

  def write(self, data):
    """Append data to write buffer, and maybe flush."""
    # TODO(pts): Shortcut if write_ebo is empty and data is long.
    write_ebo = self.write_ebo
    write_ebo.append(data)
    if len(write_ebo) >= 8192:
      self.flush()

  def flush(self):
    write_ebo = self.write_ebo
    write_fd = self.write_fd
    # Raises IOError.
    write_ebo.write_to_fd_again(write_fd)
    while write_ebo:
      event.event(HandleWakeup, handle=write_fd, evtype=event.EV_WRITE,
                  arg=stackless.current).add()
      stackless.schedule_remove()
      write_ebo.write_to_fd_again(write_fd)

def MainLoop():
  while True:
    # Exceptions (if any) in event handlers would propagate to here.
    # Argument: nonblocking: don't block if nothing available.
    event.loop(stackless.runcount > 1)
    stackless.schedule()

def Handler(cs, csaddr):
  print >>sys.stderr, 'info: connection from %r' % (
      cs.getpeername(),)
  csfd = cs.fileno()
  SetFdBlocking(csfd, False)
  f = NbFile(csfd, csfd)

  #while True:
  #  line = f.readline()
  #  print repr(line)
  #  if not line:
  #    break
  #cs.close()
  #return

  # Read HTTP request.
  line1 = None
  while True:
    line = f.readline().rstrip('\r\n')
    if not line:  # Empty line, end of HTTP request.
      break
    if line1 is None:
      line1 = line

  # Parse HTTP request.
  # Please note that an assertion here doesn't abort the server.
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
    f.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    f.write('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = lprng.Lprng(num).next()
    f.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    f.write('<a href="/%d">continue with %d</a>\n' %
            (next_num, next_num))
  f.flush()
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
