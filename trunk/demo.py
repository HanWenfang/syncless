#! /usr/local/bin/stackless2.6
#
# demo.py: demo for syncless WSGI and async DNS
# by pts@fazekas.hu at Sun Dec 20 21:49:16 CET 2009
#

import stackless
import socket
import sys
import time

import syncless
import wsgi


def ChatWorker(nbf, nbf_to_close):
  # TODO(pts): Let's select this from the command line.
  try:
    nbf.Write('Type something!\n')  # TODO(pts): Handle EPIPE.
    while True:
      nbf.Flush()
      if not nbf.WaitForReadableTimeout(3.5):  # 3.5 second
        nbf.Write('Come on, type something, I\'m getting bored.\n')
        continue
      s = nbf.ReadAtMost(128)  # TODO(pts): Do line buffering.
      if not s:
        break
      nbf.Write('You typed %r, keep typing.\n' % s)
      # TODO(pts): Add feature to give up control during long computations.
    nbf.Write('Bye!\n')
    nbf.Flush()
    if nbf_to_close:
      nbf_to_close.close()
  finally:
    nbf.close()

if __name__ == '__main__':
  if len(sys.argv) > 1:
    syncless.VERBOSE = True
  try:
    import psyco
    psyco.full()
  except ImportError:
    pass
  listener_nbs = syncless.NonBlockingSocket(socket.AF_INET, socket.SOCK_STREAM)
  listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  listener_nbs.bind(('127.0.0.1', 6666))
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  listener_nbs.listen(100)

  def SimpleWsgiApp(env, start_response):
    """Simplest possible application object"""
    error_stream = env['wsgi.errors']
    error_stream.write('Got env=%r\n' % env)
    status = '200 OK'
    response_headers = [('Content-type', 'text/html')]
    start_response(status, response_headers)
    if env['REQUEST_METHOD'] in ('POST', 'PUT'):
      return ['Posted/put %s.' % env['wsgi.input'].read(10)]
    elif env['PATH_INFO'] == '/hello':
      return ['Hello, <i>World</i> @ %s!\n' % time.time()]
    elif env['PATH_INFO'] == '/foobar':
      return iter(['foo', 'bar'])
    else:
      return ['<a href="/hello">hello</a>\n',
              '<form method="post"><input name=foo><input name=bar>'
              '<input type=submit></form>\n']

  syncless.LogInfo('listening on %r' % (listener_nbs.getsockname(),))
  stackless.tasklet(wsgi.WsgiListener)(listener_nbs, SimpleWsgiApp)
  std_nbf = syncless.NonBlockingFile(sys.stdin, sys.stdout)
  stackless.tasklet(ChatWorker)(std_nbf, nbf_to_close=listener_nbs)
  syncless.RunMainLoop()
  # We reach this after 'Bye!' in ChatWorker.
