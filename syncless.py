#! /usr/local/bin/stackless2.6

"""syncless: Asynchronous client and server library using Stackless Python.

started by pts@fazekas.hu at Sat Dec 19 18:09:16 CET 2009

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

Doc: http://www.disinterest.org/resource/stackless/2.6.4-docs-html/library/stackless/channels.html
Doc: http://wiki.netbsd.se/kqueue_tutorial
Doc: http://stackoverflow.com/questions/554805/stackless-python-network-performance-degrading-over-time
Doc: WSGI: http://www.python.org/dev/peps/pep-0333/
Doc: WSGI server in stackless: http://stacklessexamples.googlecode.com/svn/trunk/examples/networking/wsgi/stacklesswsgi.py

Asynchronous DNS for Python:

* twisted.names.client from http://twistedmatrix.com
* dnspython: http://glyphy.com/asynchronous-dns-queries-python-2008-02-09
             http://www.dnspython.org/
* adns-python: http://code.google.com/p/adns/python
*              http://michael.susens-schurter.com/blog/2007/09/18/a-lesson-on-python-dns-and-threads/comment-page-1/

TODO(pts): Implement an async DNS resolver HTTP interface.
           (This will demonstrate asynchronous socket creation.)
TODO(pts): Use epoll (as in tornado--twisted).
TODO(pts): Document that scheduling is not fair if there are multiple readers
           on the same fd.
TODO(pts): Implement broadcasting chatbot.
TODO(pts): Close connection on 413 Request Entity Too Large.
TODO(pts): Prove that there is no memory leak over a long running time.
TODO(pts): Use socket.recv_into() for buffering.
TODO(pts): Handle signals (at least KeyboardInterrupt).
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import errno
import fcntl
import os
import select
import socket
import stackless
import sys
import time

VERBOSE = False

FLOAT_INF = float('inf')
"""The ``infinity'' float value."""

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


class NonBlockingFile(object):
  """A non-blocking file using MainLoop."""

  __slots__ = ['write_buf', 'read_fh', 'write_fh', 'read_fd', 'write_fd',
               'new_nbfs', 'cooperative_channel',
               'read_channel', 'read_wake_up_at',
               'write_channel', 'write_wake_up_at']

  def __init__(self, read_fh, write_fh=()):
    if write_fh is ():
      write_fh = read_fh
    self.write_buf = []
    self.read_fh = read_fh
    self.write_fh = write_fh
    self.read_fd = read_fh.fileno()
    assert self.read_fd >= 0
    self.write_fd = write_fh.fileno()
    assert self.write_fd >= 0
    main_loop = MainLoop.GetCurrent()
    self.new_nbfs = main_loop.new_nbfs
    self.cooperative_channel = main_loop.cooperative_channel
    main_loop = None
    self.read_channel = stackless.channel()
    self.read_channel.preference = 1  # Prefer the sender (main tasklet).
    self.write_channel = stackless.channel()
    self.write_channel.preference = 1  # Prefer the sender (main tasklet).
    # None or a float timestamp when to wake up even if there is nothing to
    # read or write.
    self.read_wake_up_at = FLOAT_INF
    self.write_wake_up_at = FLOAT_INF
    SetFdBlocking(self.read_fd, False)
    if self.read_fd != self.write_fd:
      SetFdBlocking(self.write_fd, False)
    # Create a circular reference which lasts until the MainLoop resolves it.
    # This should be the last operation in __init__ in case others raise an
    # exception.
    self.new_nbfs.append(self)

  def Write(self, data):
    """Add data to self.write_buf."""
    self.write_buf.append(str(data))

  def Flush(self):
    """Flush self.write_buf to self.write_fh, doing as many bytes as needed."""
    while self.write_buf:
      # TODO(pts): Measure special-casing of len(self.write_buf) == 1.
      data = ''.join(self.write_buf)
      del self.write_buf[:]
      if data:
        try:
          written = os.write(self.write_fd, data)
        except OSError, e:
          if e.errno == errno.EAGAIN:
            written = 0
          else:
            raise
        if written == len(data):  # Everything flushed.
          break
        elif written == 0:  # Nothing flushed.
          self.write_buf.append(data)
          self.write_channel.receive()
        else:  # Partially flushed.
          # TODO(pts): Do less string copying to avoid O(n^2) complexity.
          data = data[written:]
          self.write_buf.append(data)
          self.write_channel.receive()

  def WaitForReadableTimeout(self, timeout=None, do_check_immediately=False):
    """Return a bool indicating if the channel is now readable."""
    if do_check_immediately:
      poll = select.poll()  # TODO(pts): Pool the poll objects?
      poll.register(self.read_fd, select.POLLIN)
      if poll.poll(0):
        return
    if timeout is None or timeout == FLOAT_INF:
      self.read_channel.receive()
    else:
      self.read_wake_up_at = time.time() + timeout
      return self.read_channel.receive()

  def WaitForWritableTimeout(self, timeout=None, do_check_immediately=False):
    """Return a bool indicating if the channel is now writable."""
    if do_check_immediately:
      poll = select.poll()
      poll.register(self.write_fd, select.POLLOUT)
      if poll.poll(0):
        return
    if timeout is None or timeout == FLOAT_INF:
      self.write_channel.receive()
    else:
      self.write_wake_up_at = time.time() + timeout
      return self.write_channel.receive()

  def WaitForReadableExpiration(self, expiration=None,
                                do_check_immediately=False):
    """Return a bool indicating if the channel is now readable."""
    if do_check_immediately:
      poll = select.poll()
      poll.register(self.read_fd, select.POLLIN)
      if poll.poll(0):
        return
    if timeout is None or timeout == FLOAT_INF:
      self.read_channel.receive()
    else:
      self.read_wake_up_at = expiration
      return self.read_channel.receive()

  def WaitForWritableExpiration(self, expiration=None,
                                do_check_immediately=False):
    """Return a bool indicating if the channel is now writable."""
    if do_check_immediately:
      poll = select.poll()
      poll.register(self.write_fd, select.POLLOUT)
      if poll.poll(0):
        return
    if timeout is None or timeout == FLOAT_INF:
      self.write_channel.receive()
    else:
      self.write_wake_up_at = expiration
      return self.write_channel.receive()

  def ReadAtMost(self, size):
    """Read at most size bytes (unlike `read', which reads all)."""
    if size <= 0:
      return ''
    # TODO(pts): Implement reading exacly `size' bytes.
    while True:
      try:
        got = os.read(self.read_fd, size)
        break
      except OSError, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_channel.receive()
    # Don't raise EOFError, sys.stdin.read() doesn't raise that either.
    #if not got:
    #  raise EOFError('end-of-file on fd %d' % self.read_fd)
    return got

  def close(self):
    # TODO(pts): Don't close stdout or stderr.
    # TODO(pts): Assert that there is no unflushed data in the buffer.
    # TODO(pts): Add unregister functionality without closing.
    # TODO(pts): Can an os.close() block on Linux (on the handshake)?
    read_fd = self.read_fd
    if read_fd != -1:
      # The contract is that self.read_fh.close() must call
      # os.close(self.read_fd) -- otherwise the fd wouldn't be removed from the
      # epoll set.
      self.read_fh.close()
      self.read_fd = -1
    if self.write_fd != -1 and self.write_fd != read_fd:
      self.write_fh.close()
      self.write_fd = -1
    if self in self.new_nbfs:
      # TODO(pts): Faster remove.
      self.new_nbfs[:] = [nbf for nbf in self.new_nbfs if nbf is not self]

  def fileno(self):
    return self.read_fd


class NonBlockingSocket(NonBlockingFile):
  """A NonBlockingFile wrapping a socket, with proxy socket.socket methods.

  TODO(pts): Implement socket methods more consistently.  
  """

  __slots__ = NonBlockingFile.__slots__ + ['family', 'type', 'proto']

  def __init__(self, sock, sock_type=None, proto=0):
    """Create a new NonBlockingSocket.
    
    Usage 1: NonBlockingSocket(sock)

    Usage 2: NonBlockingSocket(family, type[, proto])
    """
    if sock_type is not None:
      self.family = sock
      sock = socket.socket(sock, sock_type, proto)  # family, type, proto
      self.type = sock_type
      self.proto = proto
    else:
      if not hasattr(sock, 'recvfrom'):
        raise TypeError
      self.family = sock.family
      self.type = sock.type
      self.proto = sock.proto
    NonBlockingFile.__init__(self, sock)

  def bind(self, address):
    self.read_fh.bind(address)

  def listen(self, backlog):
    self.read_fh.listen(backlog)

  def getsockname(self):
    return self.read_fh.getsockname()

  def getpeername(self):
    return self.read_fh.getpeername()

  def settimeout(self, timeout):
    raise NotImplementedError

  def gettimeout(self, timeout):
    return None

  def getpeername(self):
    return self.read_fh.getpeername()

  def setblocking(self, is_blocking):
    pass   # Always non-blocking via MainLoop, but report as blocking.

  def setsockopt(self, *args):
    self.read_fh.setsockopt(*args)

  def getsockopt(self, *args):
    return self.read_fh.getsockopt(*args)

  def accept(self):
    """Non-blocking version of socket self.read_fh.accept().

    Return:
      (accepted_nbf, peer_name)
    """
    while True:
      try:
        accepted_socket, peer_name = self.read_fh.accept()
        break
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      # TODO(pts): Document that non-blocking operations must not be called
      # from the main tasklet.
      assert not stackless.current.is_main
      self.read_channel.receive()
    return (NonBlockingFile(accepted_socket, accepted_socket), peer_name)

  def recv(self, bufsize, flags=0):
    """Read at most size bytes."""
    while True:
      try:
        return self.read_fh.recv(bufsize, flags)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_channel.receive()

  def recvfrom(self, bufsize, flags=0):
    """Read at most size bytes, return (data, peer_address)."""
    while True:
      try:
        return self.read_fh.recvfrom(bufsize, flags)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_channel.receive()

  def connect(self):
    """Non-blocking version of socket self.write_fh.connect()."""
    while True:
      try:
        self.write_fh.connect()
        return
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      # TODO(pts): Document that non-blocking operations must not be called
      # from the main tasklet.
      assert not stackless.current.is_main
      self.write_channel.receive()

  def send(self, data, flags=0):
    while True:
      try:
        return self.write_fh.send(data, flags)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.write_channel.receive()

  def sendto(self, *args):
    while True:
      try:
        return self.write_fh.sendto(*args)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.write_channel.receive()

  def sendall(self, data, flags=0):
    assert not self.write_buf, 'unexpected use of write buffer'
    self.write_buf.append(str(data))
    self.Flush()


def LogInfo(msg):
  Log('info: ' + str(msg))


def LogDebug(msg):
  if VERBOSE:
    Log('debug: ' + str(msg))


def Log(msg):
  """Write blockingly to stderr."""
  msg = str(msg)
  if msg and msg != '\n':
    if msg[-1] != '\n':
      msg += '\n'
    while True:
      try:
        written = os.write(2, msg)
      except OSError, e:
        if e.errno == errno.EAGAIN:
          written = 0
        else:
          raise
      if written == len(msg):
        break
      elif written != 0:
        msg = msg[written:]


# Make sure we can print the final exception which causes the death of the
# program.
orig_excepthook = sys.excepthook
def ExceptHook(*args):
  SetFdBlocking(1, True)
  SetFdBlocking(2, True)
  orig_excepthook(*args)
sys.excepthook = ExceptHook

MAIN_LOOP_BY_MAIN = {}
"""Maps stackless.main (per thread) objects to MainLoop objects."""

class MainLoop(object):
  __slots__ = ['new_nbfs', 'cooperative_channel']

  def __init__(self):
    # List of NonBlockingFile objects to be added in the next iteration
    # within MainLoop.Run().
    self.new_nbfs = []
    # If a worker wants to give the CPU to the other workers, it calls
    # self.cooperative_channel
    self.cooperative_channel = stackless.channel()
    self.cooperative_channel.preference = 1  # Prefer the sender (main tasklet).

  @classmethod
  def GetCurrent(cls):
    main_loop = MAIN_LOOP_BY_MAIN.get(stackless.main)
    if not main_loop:
      main_loop = MAIN_LOOP_BY_MAIN[stackless.main] = MainLoop()
    return main_loop

  def Run(self):
    """Run the main loop until there are no tasklets left."""
    assert stackless.current.is_main
    new_nbfs = self.new_nbfs
    cooperative_channel = self.cooperative_channel
    nbfs = []
    wait_read = []
    wait_write = []
    mainc = 0
    while True:
      mainc += 1
      stackless.run()  # Until all others are blocked.
      del wait_read[:]
      del wait_write[:]
      if new_nbfs:
        nbfs.extend(new_nbfs)
        del new_nbfs[:]
      need_rebuild_nbfs = False
      # TODO(pts): Optimize building earliest_wake_up_at if there are only
      # a few connections waiting for that -- and most of the connections have
      # infinite timeout.
      earliest_wake_up_at = FLOAT_INF
      for nbf in nbfs:
        if nbf.read_fd < 0 and nbf.write_fd < 0:
          need_rebuild_nbfs = True
        if nbf.read_channel.balance < 0 and nbf.read_fd >= 0:
          wait_read.append(nbf.read_fd)
          earliest_wake_up_at = min(earliest_wake_up_at, nbf.read_wake_up_at)
        if nbf.write_channel.balance < 0 and nbf.write_fd >= 0:
          wait_write.append(nbf.write_fd)
          earliest_wake_up_at = min(earliest_wake_up_at, nbf.write_wake_up_at)
      if need_rebuild_nbfs:
        nbfs[:] = [nbf for nbf in nbfs
                   if nbf.read_fd >= 0 and nbf.write_fd >= 0]
      if not (wait_read or wait_write):
        LogDebug('no more files open, end of main loop')
        break

      # TODO(pts): Use epoll(2) or poll(2) instead of select(2).
      cob = cooperative_channel.balance
      assert cob <= 0
      if cob < 0:  # Some cooperative tasklets let others run
        timeout = 0
      elif earliest_wake_up_at == FLOAT_INF:
        timeout = None
      else:
        timeout = max(0, earliest_wake_up_at - time.time())
      while True:
        if VERBOSE:
          LogDebug('select mainc=%d nbfs=%r read=%r write=%r timeout=%r' % (
              mainc,
              [(nbf.read_fd, nbf.write_fd) for nbf in nbfs],
              wait_read, wait_write, timeout))
        try:
          got = select.select(wait_read, wait_write, (), timeout)
          break
        except select.error, e:
          if e.errno != errno.EAGAIN:
            raise
      if VERBOSE:
        LogDebug('select ret=%r' % (got,))
      if timeout is None:
        for nbf in nbfs:
          # TODO(pts): Allow one tasklet to wait for multiple events.
          if nbf.write_fd in got[1]:
            nbf.write_channel.send(True)
          if nbf.read_fd in got[0]:
            nbf.read_channel.send(True)
      else:
        now = time.time()
        for nbf in nbfs:
          if nbf.write_fd in got[1]:
            nbf.write_channel.send(True)
          elif nbf.write_wake_up_at <= now:  # TODO(pts): Better rounding.
            nbf.write_wake_up_at = FLOAT_INF
            nbf.write_channel.send(False)
          if nbf.read_fd in got[0]:
            nbf.read_channel.send(True)
          elif nbf.read_wake_up_at <= now:  # TODO(pts): Better rounding.
            nbf.read_wake_up_at = FLOAT_INF
            nbf.read_channel.send(False)

      # Restore the balance, let cooperative tasklets continue running.
      while cob < 0:
        cooperative_channel.send(None)
        cob += 1


def RunMainLoop():
  MainLoop.GetCurrent().Run()
