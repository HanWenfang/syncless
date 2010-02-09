#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 15:28:10 CET 2010

import sys

import lprng

from greenlet_fix import greenlet

import eventlet.api
import eventlet.wsgi

def WsgiApplication(env, start_response):
  # No need to log the connection, eventlet.wsgi does that.
  start_response("200 OK", [('Content-Type', 'text/html')])
  if env['PATH_INFO'] in ('', '/'):
    return ['<a href="/0">start at 0</a><p>Hello, World!\n']
  else:
    num = int(env['PATH_INFO'][1:])
    next_num = lprng.Lprng(num).next()
    return ['<a href="/%d">continue with %d</a>\n' % (next_num, next_num)]

if __name__ == '__main__':
  server = eventlet.api.tcp_listener(('127.0.0.1', 8080), backlog=128)
  eventlet.wsgi.server(server, WsgiApplication)
