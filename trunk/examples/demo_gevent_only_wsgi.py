#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Fri Jun 17 19:16:01 CEST 2011

"""Short demo for a gevent WSGI server in Stackless, without Syncless."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys

# Import best_greenlet before gevent to add greenlet emulation for Stackless
# if necessary.
import syncless.best_greenlet
import gevent.hub
import gevent.wsgi

def WsgiApp(env, start_response):
  return ['Hello, <b>World</b>!']

if __name__ == '__main__':
  server = gevent.wsgi.WSGIServer(('127.0.0.1', 8080), WsgiApp)
  print >>sys.stderr, 'info: binding to TCP %r' % (server.address,)
  if len(sys.argv) > 1:
    server.serve_forever()
  else:
    server.start()  # This does the bind(2).
    print >>sys.stderr, 'info: listening on HTTP %r' % (server.address,)
    gevent.hub.get_hub().switch()  # Run forever.
