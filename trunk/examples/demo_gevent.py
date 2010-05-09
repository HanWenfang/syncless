#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat May  8 18:47:38 CEST 2010

"""Demo for hosting a gevent application within a Syncless process."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys

# Import best_greenlet before gevent to add greenlet emulation for Stackless
# if necessary.
from syncless.best_greenlet.greenlet import greenlet
from syncless import patch
import gevent
import gevent.hub
import gevent.socket

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

def Worker(client_socket, addr):
  print >>sys.stderr, 'info: connection from %r, handled by %r' % (
      addr, greenlet.getcurrent())
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
  # This is to demonstrate the error reporting and recovery behavior of gevent:
  # We get an error message like this, and the process execution continues:
  #
  #   Traceback (most recent call last):
  #     File "/usr/local/lib/python2.6/site-packages/gevent/greenlet.py", line 388, in run
  #       result = self._run(*self.args, **self.kwargs)
  #     File "./s2.py", line 137, in Worker
  #       assert 'bad' not in items[1]
  #   AssertionError
  #   <Greenlet at 0xb71acbecL: Worker(<socket at 0xb747668cL fileno=10 sock=127.0.0.1:80, ('127.0.0.1', 55196))> failed with AssertionError
  assert 'bad' not in items[1]
  if 'sysexit' in items[1]:
    print >>sys.stderr, 'info: exiting with SystemExit'
    #sys.exit()  # Doesn't work, gevent.core.__event_handler catches it.
    gevent.hub.MAIN.throw(SystemExit)
  if 'exit' in items[1]:
    print >>sys.stderr, 'info: exiting with throw'
    gevent.hub.MAIN.throw()
  try:
    num = int(items[1][1:])
  except ValueError:
    num = None

  if 'slow' in items[1]:
    gevent.hub.sleep(5)

  # Write HTTP response.
  if num is None:
    f.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    f.write('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = Lprng(num).next()
    f.write('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    f.write('<a href="/%d">continue with %d</a>\n' %
            (next_num, next_num))
  #f.flush()  # Not needed here.

def GeventListener(server_socket):
  # Please note that exceptions raised here will be printed and then ignored
  # by the gevent.hub main loop.
  print >>sys.stderr, (
      'info: accepting connections in %r' % greenlet.getcurrent())
  while True:
    client_socket, addr = server_socket.accept()
    gevent.spawn(Worker, client_socket, addr)
    # Equally good:
    #gevent.hub.spawn_raw(Worker, client_socket, addr)
    client_socket = addr = None  # Save memory.

def SetupSyncless():
  from syncless import coio
  def ProgressReporter(delta_sec):
    while True:
      sys.stderr.write('.')
      coio.sleep(delta_sec)
  coio.stackless.tasklet(ProgressReporter)(0.05)

if __name__ == '__main__':
  server_socket = gevent.socket.socket()
  # Old:
  #   gevent.socket.set_reuse_addr(server_socket)
  #   server_socket.bind(('127.0.0.1', 8080))
  #   server_socket.listen(128)
  gevent.socket.bind_and_listen(server_socket, ('127.0.0.1', 8080), 128,
                                reuse_addr=True)
  print >>sys.stderr, 'listening on %r' % (server_socket.getsockname(),)
  # All non-blocking gevent operations must be initiated from a greenlet
  # invoked by the gevent hub. The easiest way to ensure that is to move these
  # operations to a function (GeventListener), and call this function with
  # gevent.hub.spawn_raw. (As a side effect, if an exception happens in that
  # function, the process will continue running.)
  gevent.hub.spawn_raw(GeventListener, server_socket)
  if len(sys.argv) <= 1:
    SetupSyncless()  # It's OK import syncless.coio only this late.
  # Run the gevent main loop indefinitely. This is not a requirement, we
  # could to non-blocking Syncless operations instead right here for a long
  # time.
  patch.gevent_hub_main()
  assert 0, 'unreached'
