#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat Jan 23 20:15:51 CET 2010

import time
import ptsevent  # libevent creates an epoll fd and 2 socket FDs.
import socket
import stackless
import sys

import lprng

def Handler(cs, csaddr):
  print >>sys.stderr, 'info: connection from %r' % (
      cs.getpeername(),)
  f = cs.makefile('r+')

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

  if num is None:
    f.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    f.write('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = lprng.Lprng(num).next()
    f.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    f.write('<a href="/%d">continue with %d</a>\n' %
            (next_num, next_num))
  f.flush()
  cs.close()  # No need for event_del, nothing listening.

if __name__ == '__main__':
  ss = ptsevent.evsocket(socket.AF_INET, socket.SOCK_STREAM)
  #ss.settimeout(1)
  ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  # TODO(pts): Use ss._sock.
  ss.bind(('127.0.0.1', 8080))
  ss.listen(2280)
  print >>sys.stderr, 'info: listening on: %r' % (
      ss.getsockname(),)
  while True:
    cs, csaddr = ss.accept()
    stackless.tasklet(Handler)(cs, csaddr)
    cs = None  # Save memory.
