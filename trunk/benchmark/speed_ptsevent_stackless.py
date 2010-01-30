#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat Jan 23 20:15:51 CET 2010

import ptsevent
import socket
import stackless
import sys

import lprng

# TODO(pts): Move this code to ptsevent
def SendExceptionAndRun(tasklet, exc_info):
  """Send exception to tasklet, even if it's blocked on a channel.

  To get the tasklet is activated (to handle the exception) after
  SendException, call tasklet.run() after calling SendException.

  tasklet.insert() is called automatically to ensure that it eventually gets
  scheduled.
  """
  if not isinstance(exc_info, list) and not isinstance(exc_info, tuple):
    raise TypeError
  if tasklet == stackless.current:
    if len(exc_info) < 3:
      exc_info = list(exc_info) + [None, None]
    raise exc_info[0], exc_info[1], exc_info[2]
  bomb = stackless.bomb(*exc_info)
  if tasklet.blocked:
    c = tasklet._channel
    old_preference = c.preference
    c.preference = 1  # Prefer the sender.
    for i in xrange(-c.balance):
      c.send(bomb)
    c.preference = old_preference
  else:
    tasklet.tempval = bomb
  tasklet.insert()
  tasklet.run()

def Handler(cs, csaddr):
  print >>sys.stderr, 'info: connection from %r' % (
      cs.getpeername(),)
  csfd = cs.fileno()
  ptsevent.SetFdBlocking(csfd, False)
  csb = ptsevent.evbufferobj()
  csob = ptsevent.evbufferobj()

  # Read HTTP request.
  line1 = None
  while True: 
    line = csb.nb_readline(csfd).rstrip('\r\n')
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
    csob.append('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    csob.append('<a href="/0">start at 0</a><p>Hello, World!\n')
  else:
    next_num = lprng.Lprng(num).next()
    csob.append('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
    csob.append('<a href="/%d">continue with %d</a>\n' %
            (next_num, next_num))
  csob.nb_flush(csfd)
  cs.close()  # No need for event_del, nothing listening.

if __name__ == '__main__':
  ss = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  ptsevent.SetFdBlocking(ss.fileno(), False)
  ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  # TODO(pts): Use ss._sock.
  ss.bind(('127.0.0.1', 8080))
  ss.listen(2280)
  print >>sys.stderr, 'info: listening on: %r' % (
      ss.getsockname(),)
  sb = ptsevent.evbufferobj()
  while True:
    cs, csaddr = sb.nb_accept(ss)
    stackless.tasklet(Handler)(cs, csaddr)
    cs = None  # Save memory.
