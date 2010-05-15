#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat May 15 15:22:26 CEST 2010

"""Demo for hosting an Eventlet application within a Syncless process."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys

# Load greenlet emulation to stackless before loading eventlet.
import syncless.best_greenlet
import eventlet

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
  assert 'bad' not in items[1]
  try:
    num = int(items[1][1:])
  except ValueError:
    num = None

  # Write HTTP response.
  if num is None:
    writer.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    writer.write('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = Lprng(num).next()
    writer.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    writer.write('<a href="/%d">continue with %d</a>\n' %
                 (next_num, next_num))

def SetupSyncless():
  from syncless import coio
  def ProgressReporter(delta_sec):
    while True:
      sys.stderr.write('.')
      coio.sleep(delta_sec)
  coio.stackless.tasklet(ProgressReporter)(0.05)


if __name__ == '__main__':
  from syncless import patch
  patch.patch_eventlet()
  SetupSyncless()
  server = eventlet.listen(('127.0.0.1', 8080), backlog=128)
  print >>sys.stderr, 'info: listening on %r' % (server.getsockname(),)
  patch.patch_eventlet()  # Doing it again doesn't hurt.
  while True:
    new_connection, peer_name = server.accept()
    patch.patch_eventlet()  # Doing it again doesn't hurt.
    print >>sys.stderr, 'info: connection from %r' % (peer_name,)
    eventlet.spawn(Worker, new_connection)
    new_connection = None
