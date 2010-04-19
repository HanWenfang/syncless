#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon Apr 19 02:16:27 CEST 2010

"""Demo for hosting a Tornado webserver within a Syncless process."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import stackless
import sys

import tornado.httpserver
import tornado.ioloop
import tornado.web
from syncless import coio
from syncless import patch

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

class MainHandler(tornado.web.RequestHandler):
  def get(self):
    print >>sys.stderr, 'info: connection from %s' % self.request.remote_ip
    self.write('<a href="/0">start at 0</a><p>Hello, World!\n')

class NumberHandler(tornado.web.RequestHandler):
  def get(self):
    num = int(self.request.uri[1:])
    next_num = Lprng(num).next()
    self.write('<a href="/%d">continue with %d</a>\n' %
               (next_num, next_num))

application = tornado.web.Application([
    (r'/', MainHandler),
    (r'/\d+\Z', NumberHandler),
])

def ProgressReporter(delta_sec):
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)

if __name__ == "__main__":
  # Without this line ProgressReporter wouldn't be scheduled, and thus the
  # progress dots wouldn't be printed. Also, as a side effect,
  # patch.patch_tornado() makes Ctrl-<C> work to exit from the process.
  # (Otherwise Tornado's IOLoop catches and ignores EINTR in select(), so
  # sometimes it's not possible to exit.)
  patch.patch_tornado()
  http_server = tornado.httpserver.HTTPServer(application)
  # SUXX: No way to listen to 127.0.0.1 only.
  http_server.listen(6666)  # listen queue is forced to be 128
  print >>sys.stderr, 'info: listening on %r' % (
      http_server._socket.getsockname(),)
  stackless.tasklet(ProgressReporter)(0.05)
  tornado.ioloop.IOLoop.instance().start()
