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
# Docs: http://www.disinterest.org/resource/stackless/2.6.4-docs-html/library/stackless/channels.html
#
# TODO(pts): Use epoll (as in tornado--twisted).
# TODO(pts): http://stackoverflow.com/questions/554805/stackless-python-network-performance-degrading-over-time
# TODO(pts): Document that scheduling is not fair if there are multiple readers
#            on the same fd.
# TODO(pts): Implement broadcasting chatbot.

import errno
import fcntl
import os
import select
import socket
import stackless
import sys

VERBOSE = False

def SetFdBlocking(fd, is_blocking):
  """Set a file descriptor blocking or nonblocking.

  Please note that this may affect more than expected, for example it may
  affect sys.stderr when called for sys.stdout.  
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


class NonBlockingFile(object):
  def __init__(self, read_fh, write_fh, new_nbfs):
    self.write_buf = []
    self.read_fh = read_fh
    self.write_fh = write_fh
    self.read_fd = read_fh.fileno()
    assert self.read_fd >= 0
    self.write_fd = write_fh.fileno()
    assert self.write_fd >= 0
    if not isinstance(new_nbfs, list):
      raise TypeError
    self.new_nbfs = new_nbfs
    self.read_channel = stackless.channel()
    self.read_channel.preference = 1  # Prefer the sender (main task).
    self.write_channel = stackless.channel()
    self.write_channel.preference = 1  # Prefer the sender (main task).
    SetFdBlocking(self.read_fd, False)
    if self.read_fd != self.write_fd:
      SetFdBlocking(self.write_fd, False)
    # Create a circular reference which lasts until the MainLoop resolves it.
    # This should be the last operation in __init__ in case others raise an
    # exception.
    self.new_nbfs.append(self)

  def Write(self, data):
    self.write_buf.append(str(data))

  def Flush(self):
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
          # TODO(pts): Do less string copying.
          data = data[written:]
          self.write_buf.append(data)
          self.write_channel.receive()

  def Read(self, size):
    """Read at most size bytes."""
    # TODO(pts): Implement reading exacly `size' bytes.
    while True:
      try:
        got = os.read(self.read_fd, size)
        break
      except OSError, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_channel.receive()
    if not got:
      # TODO(pts): Better exception handling.
      raise EOFError('end-of-file on fd %d' % self.read_fd)
    return got

  def Close(self):
    # TODO(pts): Don't close stdout or stderr.
    # TODO(pts): Assert there is no unflushed data in the buffer.
    if self.read_fd != -1:
      self.read_fh.close()
      self.read_fd = -1
    if self.write_fd != -1:
      self.write_fh.close()
      self.write_fd = -1

  def Accept(self):
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
      self.read_channel.receive()
    return (NonBlockingFile(accepted_socket, accepted_socket, self.new_nbfs),
            peer_name)


def Log(msg):
  """Writes blockingly to stderr."""
  if not VERBOSE:
    return
  msg = str(msg)
  if msg and msg != '\n':
    if msg[-1] !=' \n':
      msg = 'info: %s%s' % (msg, (msg[-1] != '\n' and '\n') or '')
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


def MainLoop(new_nbfs):
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
    for nbf in nbfs:
      if nbf.read_fd < 0 and nbf.write_fd < 0:
        need_rebuild_nbfs = True
      if nbf.read_channel.balance < 0 and nbf.read_fd >= 0:
        wait_read.append(nbf.read_fd)
      if nbf.write_channel.balance < 0 and nbf.write_fd >= 0:
        wait_write.append(nbf.write_fd)
    if need_rebuild_nbfs:
      nbfs[:] = [nbf for nbf in nbfs
                 if nbf.read_fd >= 0 and nbf.write_fd >= 0]
    if not (wait_read or wait_write):
      Log('no more files open, end of main loop')
      break
      
    # TODO(pts): Use epoll(2) instead.
    timeout = None
    while True:
      if VERBOSE:
        Log('select mainc=%d nbfs=%r read=%r write=%r timeout=%r' % (
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
      Log('select ret=%r' % (got,))
    for nbf in nbfs:
      # TODO(pts): Allow one tasklet to wait for multiple events.
      if nbf.write_fd in got[1]:
        nbf.write_channel.send(None)
      if nbf.read_fd in got[0]:
        nbf.read_channel.send(None)


# ---

def ChatWorker(nbf):
  # TODO(pts): Let's select this from the command line.
  try:
    nbf.Write('Type something!\n')  # TODO(pts): Handle EPIPE.
    while True:
      nbf.Flush()
      try:
        s = nbf.Read(128)  # TODO(pts): Do line buffering.
      except EOFError:
        break
      nbf.Write('You typed %r, keep typing.\n' % s)
      # TODO(pts): Add feature to give up control during long computations.
    nbf.Write('Bye!\n')
    nbf.Flush()
  finally:
    nbf.Close()

def Worker(nbf):
  import time
  try:
    # Read HTTP/1.x request.
    req_buf = ''
    while True:
      req_buf += nbf.Read(4096)
      i = req_buf.find('\n\n')
      j = req_buf.find('\n\r\n')
      if i >= 0 and i < j:
        req_head = req_buf[:i]
        break
      elif j >= 0:
        req_head = req_buf[:j]
        break
    req_buf = None  # TODO(pts): Read POST body.

    # Write response.
    nbf.Write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n'
              'Hello, <i>World</i> @ %s!\n' % time.time())
    nbf.Flush()
  finally:
    nbf.Close()


def Listener(nbf):
  try:
    while True:
      accepted_nbf, peer_name = nbf.Accept()
      stackless.tasklet(Worker)(accepted_nbf)
    Log('accept got=%r' % (nbf.Accept(),))
  finally:
    nbf.Close()


if __name__ == '__main__':
  if len(sys.argv) > 1:
    VERBOSE = True
  try:
    import psyco
    psyco.full()
  except ImportError:
    pass
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sock.bind(('127.0.0.1', 6666))
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  sock.listen(100)
  Log('listening on %r' % (sock.getsockname(),))
  new_nbfs = []
  listener_nbf = NonBlockingFile(sock, sock, new_nbfs)
  stackless.tasklet(Listener)(listener_nbf)
  std_nbf = NonBlockingFile(sys.stdin, sys.stdout, new_nbfs)
  stackless.tasklet(ChatWorker)(std_nbf)  # Don't run it right now.
  MainLoop(new_nbfs)
  assert 0, 'unexpected end of main loop'
