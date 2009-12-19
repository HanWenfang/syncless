#! /usr/local/bin/stackless2.6
#
# nonblocking HTTP server in Python + Stackless
# by pts@fazekas.hu at Sat Dec 19 18:09:16 CET 2009
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
  def __init__(self, read_fh, write_fh):
    self.write_buf = []
    self.read_fh = read_fh
    self.write_fh = write_fh
    self.read_fd = read_fh.fileno()
    assert self.read_fd >= 0
    self.write_fd = write_fh.fileno()
    assert self.write_fd >= 0
    self.read_channel = stackless.channel()
    self.read_channel.preference = 1  # Prefer the sender (main task).
    self.write_channel = stackless.channel()
    self.write_channel.preference = 1  # Prefer the sender (main task).
    SetFdBlocking(self.read_fd, False)
    if self.read_fd != self.write_fd:
      SetFdBlocking(self.write_fd, False)

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
    if self.read_fd != 1:
      self.read_fh.close()
      self.read_fd = -1
    if self.write_fd != 1:
      self.write_fh.close()
      self.write_fd = -1
    # !! TODO(pts): Remove self from nbfs.

  def Accept(self):
    """Non-blocking version of socket self.read_fh.accept().

    Return:
      (accepted_socket, peer_name)
    """
    while True:
      try:
        return self.read_fh.accept()
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_channel.receive()


def Log(msg):
  """Writes blockingly to stderr."""
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


def MainLoop(nbfs):
  wait_read = []
  wait_write = []
  mainc = 0
  while True:
    mainc += 1
    stackless.run()  # Until all others are blocked.
    del wait_read[:]
    del wait_write[:]
    for nbf in nbfs:
      if nbf.read_channel.balance < 0 and nbf.read_fd >= 0:
        wait_read.append(nbf.read_fd)
      if nbf.write_channel.balance < 0 and nbf.write_fd >= 0:
        wait_write.append(nbf.write_fd)
    if not (wait_read or wait_write):
      Log('no more files open, end of main loop')
      break
      
    # TODO(pts): Use epoll(2) instead.
    timeout = None
    while True:
      Log('select mainc=%d read=%r write=%r timeout=%r' % (
          mainc, wait_read, wait_write, timeout))
      try:
        got = select.select(wait_read, wait_write, (), timeout)
        break
      except select.error, e:
        if e.errno != errno.EAGAIN:
          os.write(2, 'EEE=%d' % e.errno)
          raise
    Log('select ret=%r' % (got,))
    for nbf in nbfs:
      # TODO(pts): Allow one tasklet to wait for multiple events.
      if nbf.write_fd in got[1]:
        nbf.write_channel.send(None)
      if nbf.read_fd in got[0]:
        nbf.read_channel.send(None)


# ---

def Worker(nbf):
  try:
    nbf.Write('Type something!\n')  # TODO(pts): Handle EPIPE.
    while True:
      nbf.Flush()
      try:
        s = nbf.Read(128)  # TODO(pts): Do line buffering.
      except EOFError:
        break
      nbf.Write('You typed %r, keep typing.\n' % s)
      # !! TODO(pts): Give up control during long computations.
    nbf.Write('Bye!\n')
    nbf.Flush()
  finally:
    nbf.Close()

def Listener(nbf, nbfs):
  try:
    while True:
      accepted_socket, peer_name = nbf.Accept()
      accepted_nbf = NonBlockingFile(accepted_socket, accepted_socket)
      # TODO(pts): Autoregister nbf to nbfs.
      nbfs.append(accepted_nbf)
      stackless.tasklet(Worker)(accepted_nbf)
    Log('accept got=%r' % (nbf.Accept(),))
  finally:
    nbf.Close()

if __name__ == '__main__':
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sock.bind(('127.0.0.1', 6666))
  sock.listen(5)
  Log('listening on %r' % (sock.getsockname(),))
  nbfs = []
  listener_nbf = NonBlockingFile(sock, sock)
  stackless.tasklet(Listener)(listener_nbf, nbfs)
  nbfs.append(listener_nbf)
  std_nbf = NonBlockingFile(sys.stdin, sys.stdout)
  stackless.tasklet(Worker)(std_nbf)  # Don't run it right now.
  nbfs.append(std_nbf)
  MainLoop(nbfs)
  assert 0, 'unexpected end of main loop'
