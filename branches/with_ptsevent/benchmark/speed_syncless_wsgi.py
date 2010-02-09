#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 15:53:22 CET 2010

import logging
import socket
import stackless
import sys
from syncless import coio
from syncless import wsgi

import lprng


def WsgiApplication(env, start_response):
  print >>sys.stderr, 'connection from %(REMOTE_ADDR)s:%(REMOTE_PORT)s' % env
  start_response("200 OK", [('Content-Type', 'text/html')])
  if env['PATH_INFO'] in ('', '/'):
    return ['<a href="/0">start at 0</a><p>Hello, World!\n']
  else:
    num = int(env['PATH_INFO'][1:])
    next_num = lprng.Lprng(num).next()
    return ['<a href="/%d">continue with %d</a>\n' % (next_num, next_num)]


if __name__ == '__main__':
  logging.root.level = logging.DEBUG
  ss = coio.new_realsocket(socket.AF_INET, socket.SOCK_STREAM)
  ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  ss.bind(('127.0.0.1', 8080))
  ss.listen(100)
  logging.info('listening on %r' % (ss.getsockname(),))
  wsgi.WsgiListener(ss, WsgiApplication)
