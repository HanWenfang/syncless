#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 15:28:10 CET 2010

import logging
import socket
import sys

import lprng

import concurrence
import concurrence.http.server
import concurrence.io.socket

def WsgiApplication(env, start_response):
  # Concurrence WSGIServer SUXX: no env['REMOTE_ADDR'] or env['REMOTE_HOST']
  print >>sys.stderr, 'info: got WSGI connection'
  start_response("200 OK", [('Content-Type', 'text/html')])
  if env['PATH_INFO'] in ('', '/'):
    return ['<a href="/0">start at 0</a><p>Hello, World!\n']
  else:
    num = int(env['PATH_INFO'][1:])
    next_num = lprng.Lprng(num).next()
    return ['<a href="/%d">continue with %d</a>\n' % (next_num, next_num)]

if __name__ == '__main__':
  logging.basicConfig()  # log errors to stderr.
  concurrence.io.socket.DEFAULT_BACKLOG = 128  # listen queue size
  server = concurrence.http.server.WSGIServer(WsgiApplication)
  server.serve(('127.0.0.1', 8080))
  concurrence.dispatch()
