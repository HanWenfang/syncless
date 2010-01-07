#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 14:56:22 CET 2010

import sys

import lprng

import tornado.httpserver
import tornado.ioloop
import tornado.web

class MainHandler(tornado.web.RequestHandler):
  def get(self):
    print >>sys.stderr, 'info: connection from %s' % self.request.remote_ip
    self.write('<a href="/0">start at 0</a><p>Hello, World!\n')

class NumberHandler(tornado.web.RequestHandler):
  def get(self):
    num = int(self.request.uri[1:])
    next_num = lprng.Lprng(num).next()
    self.write('<a href="/%d">continue with %d</a>\n' %
               (next_num, next_num))

application = tornado.web.Application([
    (r'/', MainHandler),
    (r'/\d+\Z', NumberHandler),
])

if __name__ == "__main__":
  http_server = tornado.httpserver.HTTPServer(application)
  # SUXX: No way to listen to 127.0.0.1 only.
  http_server.listen(8080)  # listen queue is forced to be 128
  print >>sys.stderr, 'info: listening on %r' % (
      http_server._socket.getsockname(),)
  tornado.ioloop.IOLoop.instance().start()
