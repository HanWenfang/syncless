#! /usr/local/bin/stackless2.6
#
# example nonblocking HTTP server in Python + Stackless
# by pts@fazekas.hu at Sat Dec 19 18:09:16 CET 2009
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# Doc: http://www.disinterest.org/resource/stackless/2.6.4-docs-html/library/stackless/channels.html
# Doc: http://wiki.netbsd.se/kqueue_tutorial
# Doc: http://stackoverflow.com/questions/554805/stackless-python-network-performance-degrading-over-time
# Doc: WSGI: http://www.python.org/dev/peps/pep-0333/
# Doc: WSGI server in stackless: http://stacklessexamples.googlecode.com/svn/trunk/examples/networking/wsgi/stacklesswsgi.py
#
# Asynchronous DNS for Python:
#
# * twisted.names.client from http://twistedmatrix.com
# * dnspython: http://glyphy.com/asynchronous-dns-queries-python-2008-02-09 + http://www.dnspython.org/
# * 
#
# TODO(pts): Implement an async DNS resolver HTTP interface.
#            (This will demonstrate asynchronous socket creation.)
# TODO(pts): Use epoll (as in tornado--twisted).
# TODO(pts): Document that scheduling is not fair if there are multiple readers
#            on the same fd.
# TODO(pts): Implement broadcasting chatbot.
# TODO(pts): Close connection on 413 Request Entity Too Large.
# TODO(pts): Prove that there is no memory leak over a long running time.
# TODO(pts): Use socket.recv_into() for buffering.

import errno
import fcntl
import os
import re
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

# ---

def ChatWorker(nbf):
  # TODO(pts): Let's select this from the command line.
  try:
    nbf.Write('Type something!\n')  # TODO(pts): Handle EPIPE.
    while True:
      nbf.Flush()
      if not nbf.WaitForReadableTimeout(3.5):  # 3.5 second
        nbf.Write('Come on, type something, I\'m getting bored.\n')
        continue
      s = nbf.ReadAtMost(128)  # TODO(pts): Do line buffering.
      if not s:
        break
      nbf.Write('You typed %r, keep typing.\n' % s)
      # TODO(pts): Add feature to give up control during long computations.
    nbf.Write('Bye!\n')
    nbf.Flush()
  finally:
    nbf.close()

class WsgiErrorsStream(object):
  @classmethod
  def flush(cls):
    pass

  @classmethod
  def write(cls, msg):
    # TODO(pts): Buffer on newline.
    LogDebug(msg)

  @classmethod
  def writelines(cls, msgs):
    for msg in msgs:
      cls.write(msg)

class WsgiInputStream(object):
  """POST data input stream sent to the WSGI application as env['input'].

  The methods read, readline, readlines and __iter__ correspond to the WSGI
  specification.
  """

  # TODO(pts): Add a faster implementation if readline() is not needed.
  # TODO(pts): Handle read errors without dying. (Ignore errors? The WSGI
  #            application would notice that env['CONTENT_LENGTH'] is larger.
  # TODO(pts): Make the buffering faster.

  def __init__(self, nbf, content_length):
    if not isinstance(nbf, NonBlockingFile):
      raise TypeError
    if type(content_length) not in (int, long) or content_length < 0:
      raise TypeError
    self.nbf = nbf
    self.bytes_remaining = content_length
    # This includes data in buffers (self.half_line and self.lines_rev).
    self.bytes_read = 0
    # Buffers strings ending with a \n (except possibly at EOF), in reverse
    # order.
    self.lines_rev = []
    # Buffers strings read without a newline (coming after self.lines_rev).
    self.half_line = []

  def ReadAndDiscardRemaining(self):
    del self.lines_rev[:]
    del self.half_line[:]
    while self.bytes_remaining > 0:
      n = min(self.bytes_remaining, 4096)
      got = len(self.nbf.ReadAtMost(n))
      if got:
        self.bytes_remaining -= got
      else:
        self.bytes_remaining = 0
        break
      self.bytes_read += got

  def AppendToReadBuffer(self, data):
    if data:
      assert len(data) <= self.bytes_remaining
      self.bytes_remaining -= len(data)
      self.bytes_read += len(data)
      # TODO(pts): Support a read buffer which is not split yet.
      half_line = self.half_line
      lines_rev = self.lines_rev
      i = data.rfind('\n')
      if i < 0:
        half_line.append(data)
      else:
        if i != len(data) - 1:
          half_line.append(data[i + 1:])
        data = data[:i]
        data = [item + '\n' for item in data.split('\n')]
        data.reverse()
        lines_rev[:0] = data

  def read(self, size):
    """Read and return a string of at most size bytes."""
    if size <= 0:
      return ''
    lines_rev = self.lines_rev

    # Read from self.lines_rev.
    if lines_rev:
      data = lines_rev.pop()
      if len(data) <= size:
        return data
      # TODO(pts): Make this faster (O(n)) if the buffer is large and size is
      # small.
      lines_rev.append(data[size:])
      return data[:size]

    # Read from self.half_line if available.
    half_line = self.half_line
    if half_line:
      data = ''.join(half_line)
      assert data
      del half_line[:]
      if len(data) <= size:
        return data
      # TODO(pts): Make this faster (O(n)) if the buffer is large and size is
      # small.
      half_line.append(data[size:])
      return data[:size]

    # TODO(pts): Can we return less than size bytes? (WSGI doesn't say.)
    data = self.nbf.ReadAtMost(min(size, self.bytes_remaining))
    if data:
      self.bytes_remaining -= len(data)
    else:
      self.bytes_remaining = 0
    self.bytes_read += len(data)
    return data

  def readline(self):
    # TODO(pts): Create NonBlockingLineBufferedFile and move code there.
    lines_rev = self.lines_rev
    if lines_rev:
      return lines_rev.pop()
    half_line = self.half_line
    while True:
      n = min(4096, self.bytes_remaining)
      if n <= 0:
        if half_line:
          data = ''.join(half_line)
          del half_line[:]
          return data
        else:
          return ''
      data = nbf.ReadAtMost(n)
      if not data:
        self.bytes_remaining = 0
        if half_line:
          data = ''.join(half_line)
          del half_line[:]
          return data
        else:
          return ''
      self.bytes_read += len(data)
      self.bytes_remaining -= len(data)
      i = data.find('\n')
      if i >= 0:
        break
      half_line.append(data)
    if i == len(data) - 1:  # Fisrt newline at the end of the buffer.
      if half_line:
        half_line.append(data)
        data = ''.join(half_line)
        del half_line[:]
      return data
    half_line.append(data)
    lines_rev = ''.join(half_line).split('\n')
    del half_line[:]
    if lines_rev[-1]:
      half_line.append(lines_rev.pop())
    else:
      lines_rev.pop()
    for i in xrange(len(lines_rev)):
      lines_rev[i] += '\n'  # TODO(pts): Optimize this.
    lines_rev.reverse()
    return lines_rev.pop()

  def readlines(self, hint=None):
    lines = []
    while True:
      line = self.readline()
      if not line:
        break
      lines.append(line)
    return lines

  def __iter__(self):
    while True:
      line = self.readline()
      if not line:
        break
      yield line


class WsgiEmptyInputStream(object):
  """Empty POST data input stream sent to the WSGI application as env['input'].

  The methods read, readline, readlines and __iter__ correspond to the WSGI
  specification.
  """

  bytes_read = 0
  bytes_remaining = 0

  @classmethod
  def read(cls, size):
    return ''

  @classmethod
  def readline(cls):
    return ''

  @classmethod
  def readlines(cls, hint=None):
    return []

  @classmethod
  def __iter__(cls):
    return iter(())


HEADER_WORD_LOWER_LETTER_RE = re.compile(r'(?:\A|-)[a-z]')

# TODO(pts): Get it form the HTTP RFC.

SUB_URL_RE = re.compile(r'\A/[-A-Za-z0-9_./,~!@$*()\[\]\';:?&%+=]*\Z')
"""Matches a HTTP sub-URL, as appearing in line 1 of a HTTP request."""

HTTP_1_1_METHODS = ('GET', 'HEAD', 'POST', 'PUT', 'DELETE',
                    'OPTIONS', 'TRACE', 'CONNECT')

HTTP_VERSIONS = ('HTTP/1.0', 'HTTP/1.1')

KEEP_ALIVE_RESPONSES = (
    'Connection: close\r\n',
    'Connection: Keep-Alive\r\n')

WDAY = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
MON = ('', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
       'Oct', 'Nov', 'Dec')

def GetHttpDate(at):
  now = time.gmtime(at)
  return '%s, %2d %s %d %2d:%02d:%02d GMT' % (
      WDAY[now[6]], now[2], MON[now[1]], now[0], now[3], now[4], now[5])
      
def RespondWithBadRequest(date, server_software, nbf, reason):
  msg = 'Bad request: ' + str(reason)
  # TODO(pts): Add Server: and Date:
  nbf.Write('HTTP/1.0 400 Bad Request\r\n'
            'Server: %s\r\n'
            'Date: %s\r\n'
            'Connection: close\r\n'
            'Content-Type: text/plain\r\n'
            'Content-Length: %d\r\n\r\n%s\n' %
            (server_software, date, len(msg) + 1, msg))
  nbf.Flush()

def WsgiWorker(nbf, wsgi_application, default_env, date):
  # TODO(pts): Implement the full WSGI spec
  # http://www.python.org/dev/peps/pep-0333/
  if not isinstance(date, str):
    raise TypeError
  req_buf = ''
  do_keep_alive = True
  server_software = default_env['SERVER_SOFTWARE']
  try:
    while do_keep_alive:
      do_keep_alive = False
      env = dict(default_env)
      env['wsgi.errors'] = WsgiErrorsStream
      if date is None:  # Reusing a keep-alive socket.
        items = data = input
        # For efficiency reasons, we don't check now whether the child has
        # already closed the connection. If so, we'll be notified next time.

        # Let other tasklets make some progress before we serve our next
        # request.
        nbf.cooperative_channel.receive()
        
      # Read HTTP/1.0 or HTTP/1.1 request. (HTTP/0.9 is not supported.)
      # req_buf may contain some bytes after the previous request.
      LogDebug('reading HTTP request on nbf=%x' % id(nbf))
      while True:
        if req_buf:
          # TODO(pts): Support HTTP/0.9 requests without headers.
          i = req_buf.find('\n\n')
          j = req_buf.find('\n\r\n')
          if i >= 0 and i < j:
            req_head = req_buf[:i]
            req_buf = req_buf[i + 2:]
            break
          elif j >= 0:
            req_head = req_buf[:j]
            req_buf = req_buf[j + 3:]
            break
          if len(req_buf) > 32767:
            # Request too long. Just abort the connection since it's too late to
            # notify receiver.
            return
        # TODO(pts): Handle read errors (such as ECONNRESET etc.).
        # TODO(pts): Better buffering than += (do we need that?)
        req_new = nbf.ReadAtMost(4096)
        if not req_new:
          # The HTTP client has closed the connection before sending the headers.
          return
        if date is None:
          date = GetHttpDate(time.time())
        # TODO(pts): Ensure that refcount(req_buf) == 1 -- do the string
        # reference counters increase by slicing?
        req_buf += req_new  # Fast string append if refcount(req_buf) == 1.
        req_new = None

      # TODO(pts): Speed up this splitting?
      req_lines = req_head.rstrip('\r').replace('\r\n', '\n').split('\n')
      req_line1_items = req_lines.pop(0).split(' ', 2)
      if len(req_line1_items) != 3:
        RespondWithBadRequest(date, server_software, nbf, 'bad line1')
        return  # Don't reuse the connection.
      method, suburl, http_version = req_line1_items
      if http_version not in HTTP_VERSIONS:
        RespondWithBadRequest(date, 
            server_software, nbf, 'bad HTTP version: %r' % http_version)
        return  # Don't reuse the connection.
      # TODO(pts): Support more methods for WebDAV.
      if method not in HTTP_1_1_METHODS:
        RespondWithBadRequest(date, server_software, nbf, 'bad method')
        return  # Don't reuse the connection.
      if not SUB_URL_RE.match(suburl):
        # This also fails for HTTP proxy URLS http://...
        RespondWithBadRequest(date, server_software, nbf, 'bad suburl')
        return  # Don't reuse the connection.
      env['REQUEST_METHOD'] = method
      env['SERVER_PROTOCOL'] = http_version
      # TODO(pts): What does appengine set here?
      env['SCRIPT_NAME'] = ''
      i = suburl.find('?')
      if i >= 0:
        env['PATH_INFO'] = suburl[:i]
        env['QUERY_STRING'] = suburl[i + 1:]
      else:
        env['PATH_INFO'] = suburl
        env['QUERY_STRING'] = ''

      content_length = None
      do_req_keep_alive = http_version == 'HTTP/1.1'  # False for HTTP/1.0
      for line in req_lines:
        i = line.find(':')
        if i < 0:
          RespondWithBadRequest(date, server_software, nbf, 'bad header line')
          return
        j = line.find(': ', i)
        if j >= 0:
          value = line[i + 2:]
        else:
          value = line[i + 1:]
        key = line[:i].lower()
        if key == 'connection':
          do_req_keep_alive = value.lower() == 'keep-alive'
        elif key == 'keep-alive':
          pass  # TODO(pts): Implement keep-alive timeout.
        elif key == 'content-length':
          try:
            content_length = int(value)
          except ValueError:
            RespondWithBadRequest(date, server_software, nbf, 'bad content-length')
            return
          env['CONTENT_LENGTH'] = value
        elif key == 'content-type':
          env['CONTENT_TYPE'] = value
        elif not key.startswith('proxy-'):
          env['HTTP_' + key.upper().replace('-', '_')] = value
          # TODO(pts): Maybe override SERVER_NAME and SERVER_PORT from HTTP_HOST?
          # Does Apache do this?

      if content_length is None:
        if method in ('POST', 'PUT'):
          RespondWithBadRequest(date, server_software, nbf, 'missing content')
          return
        env['wsgi.input'] = input = WsgiEmptyInputStream
      else:
        if method not in ('POST', 'PUT'):
          if content_length:
            RespondWithBadRequest(
                date, server_software, nbf, 'unexpected content')
            return
          content_length = None
          del env['CONTENT_LENGTH']
        if content_length:
          env['wsgi.input'] = input = WsgiInputStream(nbf, content_length)
          if len(req_buf) > content_length:
            input.AppendToReadBuffer(req_buf[:content_length])
            req_buf = req_buf[content_length:]
          elif req_buf:
            input.AppendToReadBuffer(req_buf)
            req_buf = ''
        else:
          env['wsgi.input'] = input = WsgiEmptyInputStream

      is_not_head = method != 'HEAD'
      res_content_length = None
      assert not nbf.write_buf

      def StartResponse(status, response_headers, exc_info=None):
        """Callback called by wsgi_application."""
        # Just set it to None, because we don't have to re-raise it since we
        # haven't sent any headers yet.
        exc_info = None
        if nbf.write_buf:  # StartResponse called again by an error handler.
          del nbf.write_buf[:]
          res_content_length = None

        # TODO(pts): Send `Date:' header: Date: Sun, 20 Dec 2009 12:48:56 GMT
        nbf.Write('HTTP/1.0 %s\r\n' % status)
        nbf.Write('Server: %s\r\n' % server_software)
        nbf.Write('Date: %s\r\n' % date)
        for key, value in response_headers:
          key_lower = key.lower()
          if (key not in ('status', 'server', 'date', 'connection') and
              not key.startswith('proxy-') and
              # Apache responds with content-type for HEAD requests.
              (is_not_head or key not in ('content-length',
                                          'content-transfer-encoding'))):
            if key == 'content-length':
              # !! TODO(pts): Cut or pad the output below at content-length.
              # TODO(pts): Handle parsing error here.
              res_content_length = int(value)
            key_capitalized = re.sub(
                HEADER_WORD_LOWER_LETTER_RE,
                lambda match: match.group(0).upper(), key_lower)
            # TODO(pts): Eliminate duplicate keys (except for set-cookie).
            nbf.Write('%s: %s\r\n' % (key_capitalized, value))
        # Don't flush yet.

      # TODO(pts): Join tuple or list response for automatic content-length
      # generation. (Don't generate it from iterator.)

      # TODO(pts): Handle application-level exceptions here.
      items = wsgi_application(env, StartResponse)
      date = None
      if isinstance(items, list) or isinstance(items, tuple):
        if is_not_head:
          data = ''.join(map(str, items))
        else:
          data = ''
        items = None
        if input.bytes_remaining:
          input.ReadAndDiscardRemaining()
        if res_content_length is not None:
          # TODO(pts): Pad or truncate.
          assert len(data) == res_content_length
        if is_not_head:
          nbf.Write('Content-Length: %d\r\n' % len(data))
        do_keep_alive = do_req_keep_alive
        nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive])
        nbf.Write('\r\n')
        nbf.Write(data)
        nbf.Flush()
      elif is_not_head:
        do_keep_alive = do_req_keep_alive and res_content_length is not None
        nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive])
        nbf.Write('\r\n')
        for data in items:
          if input.bytes_remaining:  # TODO(pts): Check only once.
            input.ReadAndDiscardRemaining()
          nbf.Write(data)  # TODO(pts): Don't write if HEAD request.
          nbf.Flush()
        if input.bytes_remaining:
          input.ReadAndDiscardRemaining()
      else:  # HTTP HEAD request.
        do_keep_alive = do_req_keep_alive
        nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive])
        nbf.Write('\r\n')
        nbf.Flush()
        if not do_keep_alive:
          nbf.close()
        for data in items:  # Run the generator function through.
          if input.bytes_remaining:  # TODO(pts): Check only once.
            input.ReadAndDiscardRemaining()
        if input.bytes_remaining:
          input.ReadAndDiscardRemaining()
  finally:
    nbf.close()
    LogDebug('connection closed nbf=%x' % id(nbf))


def WsgiListener(nbs, wsgi_application):
  env = {}
  env['wsgi.version']      = (1, 0)
  env['wsgi.multithread']  = True
  env['wsgi.multiprocess'] = False
  env['wsgi.run_once']     = False
  env['wsgi.url_scheme']   = 'http'  # could be 'https'
  env['HTTPS']             = 'off'  # could be 'on'; Apache sets this
  server_ipaddr, server_port = nbs.getsockname()
  env['SERVER_PORT'] = str(server_port)
  env['SERVER_SOFTWARE'] = 'pts-stackless-wsgi'
  if server_ipaddr:
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = server_ipaddr
  else:
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = socket.getsockname()

  try:
    while True:
      accepted_nbs, peer_name = nbs.accept()
      date = GetHttpDate(time.time())
      if VERBOSE:
        LogDebug('connection accepted from=%r nbf=%x' %
                 (peer_name, id(accepted_nbs)))
      stackless.tasklet(WsgiWorker)(accepted_nbs, wsgi_application, env, date)
  finally:
    nbf.close()


if __name__ == '__main__':
  if len(sys.argv) > 1:
    VERBOSE = True
  try:
    import psyco
    psyco.full()
  except ImportError:
    pass
  listener_nbs = NonBlockingSocket(socket.AF_INET, socket.SOCK_STREAM)
  listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  listener_nbs.bind(('127.0.0.1', 6666))
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  listener_nbs.listen(100)

  def SimpleWsgiApp(env, start_response):
    """Simplest possible application object"""
    error_stream = env['wsgi.errors']
    error_stream.write('Got env=%r\n' % env)
    import time
    status = '200 OK'
    response_headers = [('Content-type', 'text/html')]
    start_response(status, response_headers)
    if env['REQUEST_METHOD'] in ('POST', 'PUT'):
      return ['Posted/put %s.' % env['wsgi.input'].read(10)]
    elif env['PATH_INFO'] == '/hello':
      return ['Hello, <i>World</i> @ %s!\n' % time.time()]
    elif env['PATH_INFO'] == '/foobar':
      return iter(['foo', 'bar'])
    else:
      return ['<a href="/hello">hello</a>\n',
              '<form method="post"><input name=foo><input name=bar>'
              '<input type=submit></form>\n']

  LogInfo('listening on %r' % (listener_nbs.getsockname(),))
  stackless.tasklet(WsgiListener)(listener_nbs, SimpleWsgiApp)
  std_nbf = NonBlockingFile(sys.stdin, sys.stdout)
  stackless.tasklet(ChatWorker)(std_nbf)  # Don't run it right now.
  MainLoop.GetCurrent().Run()
  assert 0, 'unexpected end of main loop'
