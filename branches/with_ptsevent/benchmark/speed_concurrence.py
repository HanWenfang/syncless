#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 14:34:06 CET 2010

import sys
import socket

import lprng

from concurrence import dispatch, Tasklet
from concurrence.io import BufferedStream, Socket

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
    next_num = lprng.Lprng(num).next()
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

if __name__ == '__main__':
  assert ('stackless' in sys.modules) != ('greenlet' in sys.modules)
  dispatch(server)
