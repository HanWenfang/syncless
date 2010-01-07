#! /usr/local/bin/stackless2.6

import sys

import lprng

import eventlet.api

def Worker(connection):
  reader = connection.makefile('r')
  writer = connection.makefile('w')

  # Read HTTP request.
  line1 = None
  while True:
    line = reader.readline().rstrip('\r\n')
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
    writer.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    writer.write('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = lprng.Lprng(num).next()
    writer.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    writer.write('<a href="/%d">continue with %d</a>\n' %
                 (next_num, next_num))


def read_chat_forever(writer, reader):
    line = reader.readline()
    while line:
        print "Chat:", line.strip()
        for p in participants:
            if p is not writer: # Don't echo
                p.write(line)
        line = reader.readline()
    participants.remove(writer)
    print "Participant left chat."

if __name__ == '__main__':
  server = eventlet.api.tcp_listener(('127.0.0.1', 8080), backlog=128)
  print >>sys.stderr, 'info: listening on %r' % (server.getsockname(),)
  while True:
    new_connection, peer_name = server.accept()
    print >>sys.stderr, 'info: connection from %r' % (peer_name,)
    eventlet.api.spawn(Worker, new_connection)
    new_connection = None
