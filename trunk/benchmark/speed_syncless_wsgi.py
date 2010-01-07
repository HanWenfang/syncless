#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 15:53:22 CET 2010

import socket
import stackless

import lprng

from syncless import nbio
from syncless import wsgi

def WsgiApplication(env, start_response):
  nbio.LogInfo('connection from %(REMOTE_ADDR)s:%(REMOTE_PORT)s' % env)
  start_response("200 OK", [('Content-Type', 'text/html')])
  if env['PATH_INFO'] in ('', '/'):
    return ['<a href="/0">start at 0</a><p>Hello, World!\n']
  else:
    num = int(env['PATH_INFO'][1:])
    next_num = lprng.Lprng(num).next()
    return ['<a href="/%d">continue with %d</a>\n' % (next_num, next_num)]

if __name__ == '__main__':
  listener_nbs = nbio.NonBlockingSocket(socket.AF_INET, socket.SOCK_STREAM)
  listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  listener_nbs.bind(('127.0.0.1', 8080))
  listener_nbs.listen(100)
  nbio.LogInfo('listening on %r' % (listener_nbs.getsockname(),))
  stackless.tasklet(wsgi.WsgiListener)(listener_nbs, WsgiApplication)
  nbio.RunMainLoop()
