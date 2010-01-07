#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 15:19:07 CET 2010

import socket
import stackless

import lprng

from syncless import nbio

def Worker(nbs):
  # Read HTTP request.
  request = ''
  while True:
    got = nbs.recv(32768)
    assert got
    request += got
    i = request.find('\n\r\n')
    if i >= 0:
      j = request.find('\n\n')
      if j >= 0 and j < i:
        i = j + 2
      else:
        i += 3
      break
    else:
      i = request.find('\n\n')
      if i >= 0:
        i + 2
        break
  head = request[:i]
  body = request[i:]

  # Parse HTTP request.
  # Please note that an assertion here aborts the server.
  i = head.find('\n')
  assert i > 0, (head,)
  if head[i - 1] == '\r':
    line1 = head[:i - 1]
  else:
    line1 = head[:i]
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
    nbs.Write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    nbs.Write('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = lprng.Lprng(num).next()
    nbs.Write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    nbs.Write('<a href="/%d">continue with %d</a>\n' %
              (next_num, next_num))
  nbs.Flush()
  nbs.close()

def Listener(listener_nbs):
  while True:
    nbs, peer_name = listener_nbs.accept()
    nbio.LogInfo('connection from %r' % (peer_name,))
    stackless.tasklet(Worker)(nbs)
    nbs = None

listener_nbs = nbio.NonBlockingSocket(socket.AF_INET, socket.SOCK_STREAM)
listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener_nbs.bind(('127.0.0.1', 8080))
listener_nbs.listen(128)
nbio.LogInfo('listening on %r' % (listener_nbs.getsockname(),))
stackless.tasklet(Listener)(listener_nbs)
nbio.RunMainLoop()
                