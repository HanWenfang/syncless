#! /usr/local/bin/stackless2.6

"""Non-blocking I/O classes and the main loop of Syncless.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
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

try:
  import ssl  # Python 2.6 standard module using OpenSSL.
except ImportError:
  ssl = None

VERBOSE = False

# TODO(pts): Let the user specify the full ioloop-mode.
EPOLL_EDGE_TRIGGERED = True

EPOLL_ET_FLAGS = select.EPOLLIN | select.EPOLLOUT | select.EPOLLET

# TODO(pts): Ignore missing constants.
# TODO(pts): Copy more constants from the CherryPy WSGI server.
ERRLIST_ACCEPT_RAISE = [
    errno.EBADF, errno.EINVAL, errno.ENOTSOCK, errno.EOPNOTSUPP, errno.EFAULT]
"""Errnos to be raised in socket.accept()."""

FLOAT_INF = float('inf')
"""The ``infinity'' float value."""

CREDITS_PER_ITERATION = 32
"""Number of non-blocking I/O operations for a tasklet before schedule().

TODO(pts): Decrease this if latency is high.
"""


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


class WaitSlot(object):
  """A file descriptor a MainLoop can wait for and wake up tasklets."""

  __slots__ = ['mode', # 0 for read, 1 for write
               'fd', 'channel', 'wake_up_at', 'credit']

  def fileno(self):
    return self.fd


class NonBlockingFile(object):
  """A non-blocking file using MainLoop."""

  __slots__ = ['write_buf', 'read_fh', 'write_fh', 'read_slot', 'write_slot',
               'closed_wait_slots', 'epoll_fds', 'need_poll',
               'read_wake_up_slots', 'read_slots',
               'write_wake_up_slots', 'write_slots']

  def __init__(self, read_fh, write_fh=()):
    if write_fh is ():
      write_fh = read_fh

    if isinstance(read_fh, int):
      if write_fh == read_fh:
        read_fh = write_fh = os.fdopen(read_fh, 'r+')
      else:
        read_fh = os.fdopen(read_fh, 'r')
    if isinstance(write_fh, int):
      write_fh = os.fdopen(write_fh, 'w')

    # Get access to the real socket object, so we can reliably close it.
    if isinstance(read_fh, socket.socket):
      read_fh = read_fh._sock
    if isinstance(write_fh, socket.socket):
      write_fh = write_fh._sock

    self.write_buf = []
    self.read_fh = read_fh
    self.write_fh = write_fh

    read_slot = self.read_slot = WaitSlot()
    read_slot.mode = 0
    read_slot.fd = read_fh.fileno()
    assert read_slot.fd >= 0
    read_slot.channel = stackless.channel()
    read_slot.channel.preference = 1  # Prefer the sender (main tasklet).
    read_slot.wake_up_at = FLOAT_INF
    read_slot.credit = CREDITS_PER_ITERATION

    write_slot = self.write_slot = WaitSlot()
    write_slot.mode = 1
    write_slot.fd = write_fh.fileno()
    assert write_slot.fd >= 0
    write_slot.channel = stackless.channel()
    write_slot.channel.preference = 1  # Prefer the sender (main tasklet).
    write_slot.wake_up_at = FLOAT_INF
    write_slot.credit = CREDITS_PER_ITERATION

    main_loop = CurrentMainLoop()
    self.need_poll = main_loop.epoll_is_et
    self.epoll_fds = main_loop.epoll_fds
    self.closed_wait_slots = main_loop.closed_wait_slots
    self.read_wake_up_slots = main_loop.read_wake_up_slots
    self.write_wake_up_slots = main_loop.write_wake_up_slots
    self.read_slots = main_loop.read_slots
    self.write_slots = main_loop.write_slots
    main_loop.register_wait_slot(read_slot)
    main_loop.register_wait_slot(write_slot)
    main_loop = None

    # None or a float timestamp when to wake up even if there is nothing to
    # read or write.
    SetFdBlocking(read_slot.fd, False)
    if read_slot.fd != write_slot.fd:
      SetFdBlocking(write_slot.fd, False)

  def Write(self, data):
    """Add data to self.write_buf."""
    self.write_buf.append(str(data))

  def Flush(self):
    """Flush self.write_buf to self.write_fh, doing as many bytes as needed.

    Raises:
      IOError, anything other than EAGAIN.
    """
    if self.write_buf:
      # TODO(pts): Measure special-casing of len(self.write_buf) == 1.
      data = ''.join(self.write_buf)
      del self.write_buf[:]
      write_slot = self.write_slot
      while data:
        write_slot.credit -= 1
        if write_slot.credit < 0:
          write_slot.credit = CREDITS_PER_ITERATION
          stackless.schedule()
        try:
          # TODO(pts): wget + Ctrl-<C> gives errno.ECONNRESET;
          # may also be EPIPE.
          written = os.write(write_slot.fd, data)
        except OSError, e:
          if e.errno == errno.EAGAIN:
            written = 0
          elif e.filename is None:
            raise IOError(*e.args)
          else:
            raise IOError(e.args[0], e.args[1], e.filename)
        if written == len(data):  # Everything flushed.
          break
        else:
          if written:  # Partially flushed. TODO(pts): better buffering.
            data = data[written:]
          self.write_slots.add(self.write_slot)
          write_slot.credit = CREDITS_PER_ITERATION
          write_slot.channel.receive()

  def WaitForReadableTimeout(self, timeout=None, do_check_immediately=False):
    """Return a bool indicating if the channel is now readable."""
    if do_check_immediately or self.need_poll:
      # TODO(pts): Test this with all ioloop modes.
      poll = select.poll()  # TODO(pts): Pool the poll objects?
      poll.register(self.read_slot.fd, select.POLLIN)
      if poll.poll(0):
        return True
    if not (timeout is None or timeout == FLOAT_INF):
      self.read_slot.wake_up_at = time.time() + timeout
      self.read_wake_up_slots.append(self.read_slot)
    self.read_slots.add(self.read_slot)
    return self.read_slot.channel.receive()

  def WaitForWritableTimeout(self, timeout=None, do_check_immediately=False):
    """Return a bool indicating if the channel is now writable."""
    if do_check_immediately or self.need_poll:
      poll = select.poll()
      poll.register(self.write_slot.fd, select.POLLOUT)
      if poll.poll(0):
        return True
    if not (timeout is None or timeout == FLOAT_INF):
      self.write_slot.wake_up_at = time.time() + timeout
      self.write_wake_up_slots.append(self.write_slot)
    self.write_slots.add(self.write_slot)
    return self.write_slot.channel.receive()

  def WaitForReadableExpiration(self, expiration=None,
                                do_check_immediately=False):
    """Return a bool indicating if the channel is now readable."""
    if do_check_immediately or self.need_poll:
      poll = select.poll()
      poll.register(self.read_slot.fd, select.POLLIN)
      if poll.poll(0):
        return True
    if not (expiration is None or expiration == FLOAT_INF):
      self.read_slot.wake_up_at = expiration
      self.read_wake_up_slots.append(self.read_slot)
    self.read_slots.add(self.read_slot)
    return self.read_slot.channel.receive()

  def WaitForWritableExpiration(self, expiration=None,
                                do_check_immediately=False):
    """Return a bool indicating if the channel is now writable."""
    if do_check_immediately or self.need_poll:
      poll = select.poll()
      poll.register(self.write_slot.fd, select.POLLOUT)
      if poll.poll(0):
        return True
    if not (expiration is None or expiration == FLOAT_INF):
      # TODO(pts): Make self.write_slot a local variable (everywhere).
      self.write_slot.wake_up_at = expiration
      self.write_wake_up_slots.append(self.write_slot)
    self.write_slots.add(self.write_slot)
    return self.write_slot.channel.receive()

  def ReadAtMost(self, size):
    """Read at most size bytes (unlike `read', which reads all).

    Raises:
      IOError, anything other than EAGAIN.
    """
    if size <= 0:
      return ''
    # TODO(pts): Implement reading exacly `size' bytes.
    read_slot = self.read_slot
    while True:
      read_slot.credit -= 1
      if read_slot.credit < 0:
        read_slot.credit = CREDITS_PER_ITERATION
        stackless.schedule()
      try:
        got = os.read(read_slot.fd, size)
        break
      except OSError, e:
        if e.errno != errno.EAGAIN:
          if e.filename is None:
            raise IOError(*e.args)
          raise IOError(e.args[0], e.args[1], e.filename)
      self.read_slots.add(self.read_slot)
      read_slot.credit = CREDITS_PER_ITERATION
      read_slot.channel.receive()
    # Don't raise EOFError, sys.stdin.read() doesn't raise that either.
    #if not got:
    #  raise EOFError('end-of-file on fd %d' % self.read_slot.fd)
    return got

  def close(self):
    # TODO(pts): Don't close stdout or stderr.
    # TODO(pts): Assert that there is no unflushed data in the buffer.
    # TODO(pts): Add unregister functionality without closing.
    # TODO(pts): Can an os.close() block on Linux (on the handshake)?
    read_fd = self.read_slot.fd
    epoll_fds = self.epoll_fds
    if read_fd >= 0:
      # The contract is that self.read_fh.close() must call
      # os.close(self.read_slot.fd) -- otherwise the fd wouldn't be removed
      # from the epoll set.
      self.read_fh.close()
      if self.read_slot in self.read_slots:
        self.read_slots.remove(self.read_slot)
      if read_fd in self.epoll_fds:
        del epoll_fds[read_fd]
      self.read_slot.fd = -2 - read_fd
      self.closed_wait_slots.add(self.read_slot)
    write_fd = self.write_slot.fd
    if write_fd >= 0:
      if write_fd != read_fd:
        self.write_fh.close()
      if self.write_slot in self.write_slots:
        self.write_slots.remove(self.write_slot)
      if write_fd in self.epoll_fds:
        del epoll_fds[write_fd]
      self.write_slot.fd = -2 - write_fd
      # TODO(pts): Split closed_wait_slots to reads and writes.
      self.closed_wait_slots.add(self.write_slot)

  def __del__(self):
    self.close()

  def fileno(self):
    return self.read_slot.fd


class NonBlockingSocket(NonBlockingFile):
  """A NonBlockingFile wrapping a socket, with proxy socket.socket methods.

  TODO(pts): Implement socket methods more consistently.  
  """

  __slots__ = NonBlockingFile.__slots__ + ['family', 'type', 'proto']

  _sslobj = None  # SSLSocket compatibility.

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
    if timeout is not None:
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
    Raises:
      socket.error: Only in ERRLIST_ACCEPT_RAISE. Other errnos are ignored.
    """
    read_slot = self.read_slot
    while True:
      try:
        read_slot.credit -= 1
        if read_slot.credit < 0:
          read_slot.credit = CREDITS_PER_ITERATION
          stackless.schedule()
        accepted_socket, peer_name = self.read_fh.accept()
        break
      except socket.error, e:
        if e.errno == errno.EAGAIN:
          pass
        elif e.errno in ERRLIST_ACCEPT_RAISE:
          raise
        else:
          continue
      self.read_slots.add(self.read_slot)
      read_slot.credit = CREDITS_PER_ITERATION
      read_slot.channel.receive()
    return (NonBlockingSocket(accepted_socket), peer_name)

  def recv(self, bufsize, flags=0):
    """Read at most size bytes."""
    read_slot = self.read_slot
    while True:
      read_slot.credit -= 1
      if read_slot.credit < 0:
        read_slot.credit = CREDITS_PER_ITERATION
        stackless.schedule()
      try:
        return self.read_fh.recv(bufsize, flags)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_slots.add(self.read_slot)
      read_slot.credit = CREDITS_PER_ITERATION
      read_slot.channel.receive()

  def recvfrom(self, bufsize, flags=0):
    """Read at most size bytes, return (data, peer_address)."""
    read_slot = self.read_slot
    while True:
      read_slot.credit -= 1
      if read_slot.credit < 0:
        read_slot.credit = CREDITS_PER_ITERATION
        stackless.schedule()
      try:
        return self.read_fh.recvfrom(bufsize, flags)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_slots.add(self.read_slot)
      read_slot.credit = CREDITS_PER_ITERATION
      read_slot.channel.receive()

  def connect(self, addr):
    """Non-blocking version of socket self.write_fh.connect()."""
    # TODO(pts): Test this.
    write_slot = self.write_slot
    while True:
      write_slot.credit -= 1
      if write_slot.credit < 0:
        write_slot.credit = CREDITS_PER_ITERATION
        stackless.schedule()
      try:
        self.write_fh.connect(addr)
        return
      except socket.error, e:
        # errno.EINPROGRESS on Linux 2.6.
        if e.errno not in (errno.EAGAIN, errno.EINPROGRESS):
          raise
      self.write_slots.add(self.write_slot)
      write_slot.credit = CREDITS_PER_ITERATION
      write_slot.channel.receive()

  def send(self, data, flags=0):
    write_slot = self.write_slot
    while True:
      write_slot.credit -= 1
      if write_slot.credit < 0:
        write_slot.credit = CREDITS_PER_ITERATION
        stackless.schedule()
      try:
        return self.write_fh.send(data, flags)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.write_slots.add(self.write_slot)
      write_slot.credit = CREDITS_PER_ITERATION
      write_slot.channel.receive()

  def sendto(self, *args):
    write_slot = self.write_slot
    while True:
      write_slot.credit -= 1
      if write_slot.credit < 0:
        write_slot.credit = CREDITS_PER_ITERATION
        stackless.schedule()
      try:
        return self.write_fh.sendto(*args)
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.write_slots.add(self.write_slot)
      write_slot.credit = CREDITS_PER_ITERATION
      write_slot.channel.receive()

  def sendall(self, data, flags=0):
    assert not self.write_buf, 'unexpected use of write buffer'
    self.write_buf.append(str(data))
    self.Flush()

  # TODO(pts): Raise a NotImplementedError for makefile().

if ssl:
  class NonBlockingSslSocket(NonBlockingSocket):
    """A NonBlockingFile wrapping an SSL client socket.

    TODO(pts): Wrap SSL server sockets.
    TODO(pts): Do signature validation.
    """

    __slots__ = NonBlockingSocket.__slots__ + ['_sslobj', 'sslsock']

    def __init__(self, sock, sock_type=None, proto=0):
      """Create a new NonBlockingSslSocket.
      
      Usage 1: NonBlockingSslSocket(sock)

      Usage 2: NonBlockingSslSocket(family, type[, proto])
      """
      if sock_type is not None:
        may_be_connected = False
        sock = socket.socket(sock, sock_type, proto)  # family, type, proto
      else:
        may_be_connected = True
      if isinstance(sock, socket.socket):
        pass
      elif isinstance(sock, socket._realsocket):
        # SSLSocket needs a socket.socket, so we wrap it here.
        sock = socket.socket(_sock=sock)
      else:
        raise TypeError('cannot create an SSL socket from %r' % (sock,))
      sock.setblocking(False)  # Makybe this is not needed.
      # self.read_fh becomes sock._sock.
      NonBlockingSocket.__init__(self, sock)
      self.sslsock = ssl.SSLSocket(sock, do_handshake_on_connect=False)
      self.sslsock.setblocking(False)
      self._sslobj = self.sslsock._sslobj
      if may_be_connected:  # Do the SSL handshake on a connected socket.
        try:
          self.read_fh.getpeername()
        except socket.error:
          may_be_connected = False
        if may_be_connected:
          self.do_handshake()

    def connect(self, addr):
      """Non-blocking version of socket self.write_fh.connect()."""
      NonBlockingSocket.connect(self, addr)
      if not self._sslobj:
        sslsock = self.sslsock
        # This assignment was copied from the code of ssl.SSLSocket.connect().
        self._sslobj = sslsock._sslobj = ssl._ssl.sslwrap(
           sslsock._sock, False, sslsock.keyfile, sslsock.certfile,
           sslsock.cert_reqs, sslsock.ssl_version,
           sslsock.ca_certs)
      self.do_handshake()

    def do_handshake(self):
      """Do the SSL handshake.
      
      This method must be called >= 1 times after a connect().
      """
      read_slot = self.read_slot
      write_slot = self.write_slot
      while True:
        read_slot.credit -= 1
        if read_slot.credit < 0:
          read_slot.credit = CREDITS_PER_ITERATION
          stackless.schedule()
        try:
          self._sslobj.do_handshake()
          return
        except ssl.SSLError, e:
          if e.errno == ssl.SSL_ERROR_WANT_READ:
            self.read_slots.add(read_slot)
            read_slot.credit = CREDITS_PER_ITERATION
            read_slot.channel.receive()
          elif e.errno == ssl.SSL_ERROR_WANT_WRITE:
            self.write_slots.add(write_slot)
            write_slot.credit = CREDITS_PER_ITERATION
            write_slot.channel.receive()
          else:
            raise

    def bind(self, address):
      raise NotImplementedError

    def listen(self, backlog):
      raise NotImplementedError

    def accept(self):
      raise NotImplementedError

    def recv(self, bufsize, flags=0):
      """Read at most size bytes."""
      if flags:
        raise ValueError('flags must be 0 for SSL socket recv()')
      read_slot = self.read_slot
      while True:
        read_slot.credit -= 1
        if read_slot.credit < 0:
          read_slot.credit = CREDITS_PER_ITERATION
          stackless.schedule()
        try:
          # self._sslobj.read wouldn't check for SSL_ERROR_EOF.
          return self.sslsock.read(bufsize)
        except ssl.SSLError, e:
          if e.errno == ssl.SSL_ERROR_WANT_READ:
            self.read_slots.add(read_slot)
            read_slot.credit = CREDITS_PER_ITERATION
            read_slot.channel.receive()
          elif e.errno == ssl.SSL_ERROR_WANT_WRITE:
            self.write_slots.add(self.write_slot)
            self.write_slot.credit = CREDITS_PER_ITERATION
            self.write_slot.channel.receive()
          else:
            raise

    def recvfrom(self, bufsize, flags=0):
      """Read at most size bytes, return (data, peer_address)."""
      return (self.recv(bufsize, flags), self.read_fh.getpeername())

    def send(self, data, flags=0):
      read_slot = self.read_slot
      write_slot = self.write_slot
      while True:
        write_slot.credit -= 1
        if write_slot.credit < 0:
          write_slot.credit = CREDITS_PER_ITERATION
          stackless.schedule()
        try:
          return self._sslobj.write(data)
        except socket.error, e:
          if e.errno == ssl.SSL_ERROR_WANT_READ:
            self.read_slots.add(read_slot)
            read_slot.credit = CREDITS_PER_ITERATION
            read_slot.channel.receive()
          elif e.errno == ssl.SSL_ERROR_WANT_WRITE:
            self.write_slots.add(write_slot)
            write_slot.credit = CREDITS_PER_ITERATION
            write_slot.channel.receive()
          else:
            raise

    def sendto(self, data, addr, flags=0):
      if flags:
        raise ValueError('flags must be 0 for SSL socket sendto()')
      return self.send(data, flags)

    def sendall(self, data, flags=0):
      if flags:
        raise ValueError('flags must be 0 for SSL socket sendall()')
      write_slot = self.write_slot
      read_slot = self.read_slot
      while data:
        write_slot.credit -= 1
        if write_slot.credit < 0:
          write_slot.credit = CREDITS_PER_ITERATION
          stackless.schedule()
        try:
          got = self._sslobj.write(data)
        except socket.error, e:
          if e.errno == ssl.SSL_ERROR_WANT_READ:
            self.read_slots.add(read_slot)
            read_slot.credit = CREDITS_PER_ITERATION
            read_slot.channel.receive()
          elif e.errno == ssl.SSL_ERROR_WANT_WRITE:
            self.write_slots.add(write_slot)
            write_slot.credit = CREDITS_PER_ITERATION
            write_slot.channel.receive()
          else:
            raise
          got = 0
        if got:
          if got == len(data):
            break
          data = data[got:]  # TODO(pts): Make this faster (less data copy).
else:
  NonBlockingSslSocket = None

def LogInfo(msg):
  Log('info: ' + str(msg))


def LogDebug(msg):
  if VERBOSE:
    Log('debug: ' + str(msg))


def Log(msg):
  """Write log message blockingly to stderr.

  This call blocks so it is possible to log from MainLoop.Run.

  TODO(pts): Make this call non-blocking if called from outside MainLoop.Run.
  """
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
          raise IOError(*e.args)
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
  __slots__ = ['closed_wait_slots', 'run_tasklet', 'reinsert_tasklet',
               'epoll_fh', 'epoll_is_et', 'epoll_fds',
               'read_wake_up_slots', 'read_slots',
               'write_wake_up_slots', 'write_slots', 'register_wait_slot']


  def __init__(self):
    # TODO(pts): Don't we have a circular reference here?
    self.closed_wait_slots = set()
    self.read_wake_up_slots = []
    self.write_wake_up_slots = []
    self.read_slots = set()
    self.write_slots = set()
    self.run_tasklet = stackless.tasklet(self.Run)()
    # Helper tasklet to move self.run_tasklet in the chain.
    self.reinsert_tasklet = stackless.tasklet(self.DoReinsert)()
    self.reinsert_tasklet.remove()
    self.register_wait_slot = lambda wait_slot: None
    try:
      self.epoll_fh = select.epoll()
      self.epoll_is_et = bool(EPOLL_EDGE_TRIGGERED)
      # Maps file descriptors to a value array (depending in self.epoll_is_et).
      self.epoll_fds = {}
      if self.epoll_is_et:
        self.register_wait_slot = self.RegisterWaitSlot
    except (OSError, IOError, select.error, socket.error,
            NameError, AttributeError):
      self.epoll_is_et = False
      self.epoll_fh = None
      self.epoll_fds = ()

  @property
  def ioloop_mode(self):
    if self.epoll_is_et:
      return 'epoll-edge'  # edge-triggered epoll()
    elif self.epoll_fh:
      return 'epoll-level'  # level-triggered epoll()
    else:
      return 'select'  # select()

  def RegisterWaitSlot(self, wait_slot):
    if self.epoll_is_et:
      fd = wait_slot.fd
      epoll_fds = self.epoll_fds
      value = epoll_fds.get(fd)
      i = wait_slot.mode  # 0: read, 1: write
      if value:
        if value[i] is None:
          value[i] = wait_slot
        else:
          assert value[i] == wait_slot, (value, i, wait_slot, wait_slot.fd)
      else:
        # We register for more than what we want to handle, but that
        # overhead is small enough.
        epoll_fds[fd] = value = [None, None]
        value[i] = wait_slot
        # TODO(pts): Don't register for writing if read-only.
        self.epoll_fh.register(fd, EPOLL_ET_FLAGS)

  def DoReinsert(self):
    while True:
      # remove() is needed so that insert() will insert right before us.
      self.run_tasklet.remove()
      self.run_tasklet.insert()
      stackless.schedule_remove()

  def Run(self):
    """Run the main loop until there are no tasklets left, propagate exc."""
    if stackless.current.is_main:
      self.RunWrapped()
    else:
      try:
        self.RunWrapped()
      except TaskletExit:
        raise
      except:
        # Propagate the exception to the main thread, so we don't get a
        # StopIteration instead.
        bomb = stackless.bomb(*sys.exc_info())
        if stackless.main.blocked:
          c = stackless.main._channel
          old_preference = c.preference
          c.preference = 1  # Prefer the sender.
          for i in xrange(-c.balance):
            c.send(bomb)
          c.preference = old_preference
        else:
          stackless.main.tempval = bomb
        stackless.main.run()

  def RunWrapped(self):
    """Run the main loop until there are no tasklets left.
    
    Please call MainLoop.Run instead.
    """
    # Kill the old main loop tasklet if necessary.
    old_run_tasklet = self.run_tasklet
    self.run_tasklet = stackless.current
    if old_run_tasklet != self.run_tasklet:
      assert old_run_tasklet.alive
      assert not old_run_tasklet.blocked
      old_run_tasklet.remove()  # Give control back to us after kill below.
      old_run_tasklet.kill()
    old_run_tasklet = None
    LogInfo('main loop in ioloop mode %s' % self.ioloop_mode)

    # TODO(pts): Make EPOLLIN etc. local to speed up the loop.
    epoll_is_et = self.epoll_is_et
    epoll_fh = self.epoll_fh
    epoll_fds = self.epoll_fds
    reinsert_tasklet = self.reinsert_tasklet
    closed_wait_slots = self.closed_wait_slots
    read_wake_up_slots = self.read_wake_up_slots
    write_wake_up_slots = self.write_wake_up_slots
    read_slots = self.read_slots
    write_slots = self.write_slots
    mainc = 0  # TODO(pts): Maybe move this to self.?
    not_closed_callback = lambda wait_slot: wait_slot not in closed_wait_slots
    while True:
      if closed_wait_slots:
        # TODO(pts): Implement Faster delete_if in Python.
        # TODO(pts): Remove this in .close() -- if they are sets.
        read_wake_up_slots[:] = filter(not_closed_callback, read_wake_up_slots)
        write_wake_up_slots[:] = filter(
            not_closed_callback, write_wake_up_slots)
        closed_wait_slots.clear()

      if read_slots or write_slots:
        # TODO(pts): Use epoll(2) or poll(2) instead of select(2).
        # TODO(pts): Do a wake up without a file descriptor on timeout.
        # TODO(pts): Allow one tasklet to wait for `or' of multiple events.
        if stackless.runcount > 1:
          # Don't wait if we have some cooperative tasklets.
          timeout = 0
        else:
          if read_wake_up_slots:
            earliest_wake_up_at = min(
                read_slot.wake_up_at for read_slot in read_wake_up_slots)
            if write_wake_up_slots:
              earliest_wake_up_at = min(
                earliest_wake_up_at,
                min(write_slot.wake_up_at for write_slot in
                    write_wake_up_slots))
          elif write_wake_up_slots:
            earliest_wake_up_at = min(
              write_slot.wake_up_at for write_slot in write_wake_up_slots)
          else:
            earliest_wake_up_at = FLOAT_INF
          if earliest_wake_up_at == FLOAT_INF:
            timeout = None
          else:
            # We increase the timeout by 1 ms (1/1024 s) to prevent select()
            # from waking up 1ms too early.
            timeout = max(0, earliest_wake_up_at - time.time() + 0.0009765625)
        if epoll_is_et:
          # TODO(pts): Add fd in another channel.
          while True:
            if VERBOSE:
              LogDebug('epoll-edge mainc=%d fds=%r timeout=%r' % (
                  mainc, epoll_fds, timeout))
            try:
              if timeout is None:
                epoll_events = epoll_fh.poll()
              else:
                epoll_events = epoll_fh.poll(timeout)
              break
            except select.error, e:
              if e.errno != errno.EAGAIN:
                raise

          read_available = []
          write_available = []
          for fd, mode in epoll_events:
            value = epoll_fds[fd]
            if mode & (select.EPOLLIN | select.EPOLLHUP):
              read_slot = value[0]
              if read_slot:
                if read_slot.channel.balance < 0:  # There is a receiver waiting.
                  read_available.append(read_slot)
            if mode & (select.EPOLLOUT | select.EPOLLHUP):
              write_slot = value[1]
              if write_slot:
                if write_slot.channel.balance < 0:  # There is a receiver waiting.
                  write_available.append(write_slot)
          epoll_events = None  # Release references.
        elif epoll_fh:
          # SUXX: we get StopIteration ``the main tasklet is receiving without
          # a sender available'' on a NameError here.
          # TODO(pts): Compare epoll() speed to select(), Tornado and Twisted.
          # TODO(pts): Try edge-triggered mode (should work after EAGAIN). What
          #            does Tornado do?
          # TODO(pts): Study how we could make epoll() faster? Maybe
          #            edge-triggered?
          # TODO(pts): Implement poll() as well (for FreeBSD?)
          # TODO(pts): EPOLLERR | EPOLLHUP on wget /infinite Ctrl-<C>
          for fd in epoll_fds:
            epoll_fds[fd][1] = 0
          for read_slot in read_slots:
            fd = read_slot.fd
            value = epoll_fds.get(fd)
            if value is None:
              # We won't clean up WaitSlot objects epool_fds[fd][1] and
              # epoll_fds[fd][2] until the fd is closed.
              epoll_fds[fd] = [select.EPOLLIN, select.EPOLLIN, read_slot, None]
              epoll_fh.register(fd, select.EPOLLIN)
            else:
              if value[1] & select.EPOLLIN:
                assert value[2] == read_slot
              else:
                value[1] |= select.EPOLLIN
                value[2] = read_slot
          for write_slot in write_slots:
            fd = write_slot.fd
            value = epoll_fds.get(fd)
            if value is None:
              epoll_fds[fd] = [select.EPOLLOUT, select.EPOLLOUT, None, write_slot]
              epoll_fh.register(fd, select.EPOLLOUT)
            else:
              if value[1] & select.EPOLLOUT:
                assert value[3] == write_slot
              else:
                value[1] |= select.EPOLLOUT
                value[3] = write_slot
          epoll_fds_to_delete = []
          for fd in epoll_fds:
            value = epoll_fds[fd]
            if value[1]:
              if value[0] != value[1]:
                epoll_fh.modify(fd, value[1])
                value[0] = value[1]
            else:
              epoll_fds_to_delete.append(fd)
          for fd in epoll_fds_to_delete:
            epoll_fh.unregister(fd)
            del epoll_fds[fd]

          while True:
            if VERBOSE:
              LogDebug('epoll-level mainc=%d fds=%r timeout=%r' % (
                  mainc, epoll_fds, timeout))
            try:
              if timeout is None:
                epoll_events = epoll_fh.poll()
              else:
                epoll_events = epoll_fh.poll(timeout)
              break
            except select.error, e:
              if e.errno != errno.EAGAIN:
                raise

          if VERBOSE:
            LogDebug('epoll events=%r' % epoll_events)
          read_available = []
          write_available = []
          for fd, mode in epoll_events:
            value = epoll_fds[fd]
            if mode & select.EPOLLIN:
              read_available.append(value[2])
              if mode & select.EPOLLOUT:
                write_available.append(value[3])
            elif mode & select.EPOLLOUT:
              write_available.append(value[3])
            elif mode & select.EPOLLHUP:
              # If wget(1) /infinity is aborted, we get EPOLLERR|EPOLLHUP even
              # if we are registered for EPOLLOUT only.
              if value[2] in read_slots:
                read_available.append(value[2])
              if value[3] in write_slots:
                write_available.append(value[3])
          epoll_events = None  # Release references.
        else:  # Use select(2).
          while True:
            if VERBOSE:
              LogDebug('select mainc=%d read=%r write=%r timeout=%r' % (
                  mainc, read_slots, write_slots, timeout))
            try:
              # TODO(pts): Verify that there is no duplicate fd in WaitSlot. This
              # is needed for correct operation of select.select() and
              # selet.epoll().
              read_available, write_available, _ = select.select(
                  read_slots, write_slots, (), timeout)
              break
            except select.error, e:
              if e.errno != errno.EAGAIN:
                raise
        if VERBOSE:
          LogDebug('available read=%r write=%r' %
                   (read_available, write_available))
        reinsert_tasklet.remove()
        # Insert reinsert_tasklet just before us to the queue.
        # The .send(...) calls below will insert woken-up tasklet between
        # reinsert_tasklet and us (self.run_tasklet).
        reinsert_tasklet.insert()  # Increases stackless.runcount.
        for write_slot in write_available:
          # TODO(pts): Wake up all waiting tasklets in random or round-robin
          # order to make it more fair.
          c = write_slot.channel
          for i in xrange(-c.balance):
            c.send(True)
          write_slots.remove(write_slot)
        for read_slot in read_available:
          # TODO(pts): Wake up the waiting tasklets in random or round-robin
          # order to make it more fair.
          c = read_slot.channel
          for i in xrange(-c.balance):
            c.send(True)
          read_slots.remove(read_slot)
        c = None
        if timeout is not None and (write_wake_up_slots or read_wake_up_slots):
          now = time.time()
          # TODO(pts): Use a heap for write_wake_up_slots and
          # read_wake_up_slots, and measure the difference.
          j = 0
          for i in xrange(len(write_wake_up_slots)):
            write_slot = write_wake_up_slots[i]
            if write_slot in write_slots:
              if now >= write_slot.wake_up_at:
                write_slot.channel.send(False)
                write_slots.remove(write_slot)
              else:
                write_wake_up_slots[j] = write_wake_up_slots[i]
                j += 1
          del write_wake_up_slots[j:]
          j = 0
          for i in xrange(len(read_wake_up_slots)):
            read_slot = read_wake_up_slots[i]
            if read_slot in read_slots:
              if now >= read_slot.wake_up_at:
                read_slot.channel.send(False)
                read_slots.remove(read_slot)
              else:
                read_wake_up_slots[j] = read_wake_up_slots[i]
                j += 1
          del read_wake_up_slots[j:]
        read_available = write_available = None  # Release reference.

        mainc += 1
        if reinsert_tasklet.next == stackless.current:
          # It would be OK just to call reinsert_tasklet.run() here
          # (just like in the else branch), but this one seems to be faster.
          reinsert_tasklet.remove()
          stackless.schedule()
        else:
          # Run the tasklets inserted above.
          reinsert_tasklet.run()
      elif stackless.runcount <= 1:
        LogDebug('no more files open, nothing to do, end of main loop')
        break
      else:
        mainc += 1
        stackless.schedule()

def HasCurrentMainLoop():
  return stackless.main in MAIN_LOOP_BY_MAIN

def CurrentMainLoop():
  # stackless.main is used as a thread ID.
  main_loop = MAIN_LOOP_BY_MAIN.get(stackless.main)
  if not main_loop:
    main_loop = MAIN_LOOP_BY_MAIN[stackless.main] = MainLoop()
  return main_loop


def RunMainLoop():
  CurrentMainLoop().Run()
