#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat Jan  9 15:42:59 CET 2010

import socket
import sys

from greenlet_fix import greenlet
import lprng

import gevent
import gevent.wsgi

def WsgiApplication(env, start_response):
  # Concurrence WSGIServer SUXX: no env['REMOTE_ADDR'] or env['REMOTE_HOST']
  start_response("200 OK", [('Content-Type', 'text/html')])
  if env['PATH_INFO'] in ('', '/'):
    return ['<a href="/0">start at 0</a><p>Hello, World!\n']
  else:
    num = int(env['PATH_INFO'][1:])
    next_num = lprng.Lprng(num).next()
    return ['<a href="/%d">continue with %d</a>\n' % (next_num, next_num)]

if __name__ == '__main__':
  wsgiserver = gevent.wsgi.WSGIServer(('127.0.0.1', 8080), WsgiApplication)
  print >>sys.stderr, 'listening on %r' % (wsgiserver.address,)
  wsgiserver.backlog = 128
  wsgiserver.serve_forever()
