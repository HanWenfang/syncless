#! /usr/bin/python
# by pts@fazekas.hu at Fri Aug  6 15:37:26 CEST 2010

"""Pure Python client for backdoor interpreters, e.g. Syncless RemoteConsole.

This client supports command editing (with the readline module) if connecting
to a RemoteConsole server. This is the most important feature over pure
telnet(1).

Example startup of the RemoteConsole server:

  $ python -m syncless.remote_console 5454
  (keep it running)

Example connecting with line editing:

  $ python -m syncless.backdoor_client 127.0.0.1 5454

Example connecting without line editing:

  $ telnet 127.0.0.1 5454

TODO(pts): See more on http://code.google.com/p/syncless/wiki/Console .
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import os
import select
import socket
import sys
import types

class ReadBuffer(object):
  """A read buffer for newline-terminated and other terminated reads."""

  # TODO(pts): Speed up this class, possibly with Syncles nbfile.

  def __init__(self):
    self.buf = ''
    self.bufb = 0

  def ReadUpTo(self, sock, c):
    """Reads from socket up to the first occurrence of string c."""
    buf = self.buf
    bufb = self.bufb
    if bufb < 0:  # EOF
      return ''
    while 1:
      i = buf.find(c, bufb)
      if i >= 0:
        i += len(c)
        if i == len(buf):
          retval = buf[bufb:]
          self.buf = ''
          self.bufb = 0
        else:
          retval = buf[bufb : i]
          self.bufb = i
        return retval
      try:
        newdata = sock.recv(8192)
      except socket.error, e:
        # Typical: errno.EPIPE, errno.ECONNRESET.
        print >>sys.stderr, 'error: reading from RemoteConsole: %s' % e
        self.bufb = -1
        return ''
      if not newdata:  # Got EOF.
        self.bufb = -1
        retval = buf
        self.buf = ''
        return retval
      if bufb > 0 and bufb + len(newdata) >= 8192:
        self.buf = buf[bufb:]
        bufb = self.bufb = 0
      self.buf = None
      buf += newdata
      self.buf = buf

  def ReadRest(self):
    if not self.buf:
      return ''
    retval = self.buf[self.bufb:]
    if self.bufb > 0:
      self.bufb = 0
    self.buf = ''
    return retval


def CopyBetweenSocketAndStdinAndStdout(sock):
  stdin = sys.stdin
  stdout = sys.stdout
  rin = [stdin, sock]
  while sock in rin:
    # TODO(pts): Handle I/O exceptions.
    # TODO(pts): Don't assume that sock and stdout are always writable.
    rout, _, _ = select.select(rin, (), ())
    if sock in rout:
      try:
        data = sock.recv(8192)
      except socket.error, e:
        print >>sys.stderr, '\nerror: from RemoteConsole: %s' % e
        data = None
      if data:
        stdout.write(data)
        stdout.flush()
      else:
        rin.remove(sock)
    if stdin in rout:
      data = os.read(stdin.fileno(), 8192)
      if data:
        try:
          sock.sendall(data)
        except socket.error, e:
          print >>sys.stderr, '\nerror: to RemoteConsole: %s' % e
          rin.remove(sock)
          sock.shutdown(0)
      else:
        rin.remove(stdin)
        sock.shutdown(0)
  if stdin in rin:
    print >>sys.stderr, '\nerror: unexpected EOF from RemoteConsole'
    return 3
  return 0

def BackdoorClient(sock):
  """Runs the backdoor client, returns on EOF, doesn't close sock."""

  read_buffer = ReadBuffer()
  line = read_buffer.ReadUpTo(sock, '\n')
  # TODO(pts): Distinguish between RemoteConsole.
  if line.startswith('\0\0\rPython 2.') or line.startswith('\0\0\rPython 3.'):
    # Connected to a Syncless RemoteConsole, with advanced indication for
    # prompts.
    try:
      import readline  # Changes raw_input().
    except ImportError:
      readline = None
    if readline:
      print >>sys.stderr, 'info: local line editing enabled for RemoteConsole'
      has_line_editing = True
    else:
      print >>sys.stderr, 'info: local readline missing, no line editing'
      has_line_editing = False
  elif line.startswith('Python 2.') or line.startswith('Python 3.'):
    print >>sys.stderr, (
        'info: remote backdoor not a RemoteConsole, so no line editing')
    has_line_editing = False
  else:
    print >>sys.stderr, 'error: not a RemoteConsole server, got %r' % (
        line[:32])
    return 4
  sys.stdout.write(line)
  if not has_line_editing:
    sys.stdout.write(read_buffer.ReadRest())
    sys.stdout.flush()
    try:
      exit_code = CopyBetweenSocketAndStdinAndStdout(sock)
    except KeyboardInterrupt:
      pass
    sys.stdout.write('\n')  # TODO(pts): Only if Ctrl-<D> on prompt etc.
    sys.stdout.flush()
    return exit_code
  sys.stdout.flush()
  while True:
    # We don't wait for '\n' in front of '\0\r\0\r\r', because it is not sent
    # after the first command (it is sent before any command).
    more = read_buffer.ReadUpTo(sock, '\0\r\0\r\r')
    if not more.endswith('\0\r\0\r\r'):
      if not more:
        print >>sys.stderr, 'error: unexpected EOF from RemoteConsole'
        return 3
      sys.stdout.write(more)
      break
    sys.stdout.write(more[:-4])
    prompt = read_buffer.ReadUpTo(sock, '\0')
    if not prompt.endswith('\0'):
      sys.stdout.write(prompt)
      break
    try:
      prompt_reply = raw_input(prompt)
    except (EOFError, IOError, KeyboardInterrupt):
      prompt_reply = None
    if prompt_reply is None:
      print >>sys.stderr, (
          '\ninfo: EOF from user, closing connection to RemoteConsole')
      break
    # As documented, raw_input returns a string without a trailing '\n'.
    line = prompt_reply.replace('\n', ' ').rstrip('\r\n') + '\n'
    # TODO(pts): Do error handling.
    try:
      sock.sendall(line)
    except socket.error, e:
      print >>sys.stderr, 'error: reading from RemoteConsole: %s' % e
      return 3
    if line in ('quit()\n', 'exit()\n'):
      break
  return 0


def main(argv):
  if not (1 <= len(argv) <= 3) or (len(argv) > 1 and
                                       argv[1] == '--help'):
    print >>sys.stderr, (
        'Usage: %s [[<host>] <tcp-port>]\n'
        'Default <host> is 127.0.0.1, other useful: 0.0.0.0.\n'
        'Default <tcp-port> is 5454.' % argv[0])
    sys.exit(1)
  if len(argv) > 2:
    host = argv[1]
  else:
    host = '127.0.0.1'
  if len(argv) > 1:
    port = int(argv[-1])
  else:
    port = 5454
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  print >>sys.stderr, 'info: connecting to backdoor %r' % ((host, port),)
  try:
    sock.connect((host, port))
  except socket.error, e:
    print >>sys.stderr, 'info: cannot connect to backdoor: %s' % e
    sys.exit(2)
  print >>sys.stderr, 'info: connected to backdoor %r' % (
      sock.getpeername(),)
  sys.exit(BackdoorClient(sock))


if __name__ == '__main__':
  sys.exit(main(sys.argv) or 0)
