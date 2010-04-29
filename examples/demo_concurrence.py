#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Apr 29 19:20:58 CEST 2010

"""Demo for hosting a Concurrence application within a Syncless process."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'


import sys
import socket

from concurrence import dispatch, Tasklet
from concurrence.io import BufferedStream, Socket

class Lprng(object):
  __slots__ = ['seed']
  def __init__(self, seed=0):
    self.seed = int(seed) & 0xffffffff
  def next(self):
    """Generate a 32-bit unsigned random number."""
    # http://en.wikipedia.org/wiki/Linear_congruential_generator
    self.seed = (
        ((1664525 * self.seed) & 0xffffffff) + 1013904223) & 0xffffffff
    return self.seed
  def __iter__(self):
    return self

def handler(client_socket):
  print >>sys.stderr, 'info: connection from %r' % (
      client_socket.socket.getpeername(),)
  stream = BufferedStream(client_socket)
  reader = stream.reader  # Strips \r\n and \n from the end.
  writer = stream.writer

  # Read HTTP request.
  line1 = None
  try:
    while True:
      line = reader.read_line()
      if not line:  # Empty line, end of HTTP request.
        break
      if line1 is None:
        line1 = line
  except EOFError:
    pass

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
    writer.write_bytes('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    writer.write_bytes('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = Lprng(num).next()
    writer.write_bytes('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    writer.write_bytes('<a href="/%d">continue with %d</a>\n' %
                       (next_num, next_num))
  writer.flush()
  stream.close()

def server():
  server_socket = Socket.new()
  server_socket.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server_socket.bind(('127.0.0.1', 8080))
  server_socket.listen(128)

  print >>sys.stderr, 'info: listening on: %r' % (
      server_socket.socket.getsockname(),)
  while True:
    client_socket = server_socket.accept()
    Tasklet.new(handler)(client_socket)

def ProgressReporter(delta_sec):
  from syncless import coio
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)

if __name__ == '__main__':
  import stackless
  from syncless import coio
  from syncless import patch
  patch.patch_concurrence()
  stackless.tasklet(ProgressReporter)(0.2)
  dispatch(server)
