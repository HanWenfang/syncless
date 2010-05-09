#! /usr/bin/python2.5
# by pts@fazekas.hu at Sat Jan 23 20:39:53 CET 2010

import sys

try:
  from greenlet_fix import greenlet
except ImportError:
  import greenlet
import lprng

import gevent
import gevent.socket

def Handle(client_socket, addr):
  print >>sys.stderr, 'connection from %r' % (addr,)
  f = client_socket.makefile()

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
  #f.flush()  # Not needed here.

if __name__ == '__main__':
  server_socket = gevent.socket.socket()
  gevent.socket.set_reuse_addr(server_socket)
  server_socket.bind(('127.0.0.1', 8080))
  server_socket.listen(128)
  print >>sys.stderr, 'listening on %r' % (server_socket.getsockname(),)
  while True:
    client_socket, addr = server_socket.accept()
    gevent.spawn(Handle, client_socket, addr)
    client_socket = addr =None  # Save memory.
