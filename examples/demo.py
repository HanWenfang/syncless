#! /usr/local/bin/stackless2.6
#
# demo.py: demo for syncless WSGI and async DNS
# by pts@fazekas.hu at Sun Dec 20 21:49:16 CET 2009
#

import cgi
import socket
import sys
import time

import demo_wsgiapp
from syncless import nbio
from syncless import wsgi

try:
  from syncless import dns
except ImportError:  # Don't ignore inner ImportError{}s.
  dns = None

def ChatWorker(nbf, nbf_to_close):
  # TODO(pts): Let's select this from the command line.
  try:
    if dns:
      nbf.Write('resolving\n')
      nbf.Flush()
      for rdata in dns.resolver.query('www.google.com', 'A'):
        nbf.Write('resolved to %r\n' % (rdata,))
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
  wsgi_listener = wsgi.WsgiListener
  use_psyco = False
  do_verbose = False
  for arg in sys.argv[1:]:
    if arg in ('--cherrypy-wsgi', '-c'):
      wsgi_listener = wsgi.CherryPyWsgiListener
    elif arg in ('--verbose', '-v'):
      do_verbose = True
    elif arg in ('--psyco', '-p'):
      use_psyco = True
    elif arg in ('--no-psyco', '+p'):
      use_psyco = False
    else:
      assert 0, 'invalid arg: %s' % arg
    
  nbio.VERBOSE = do_verbose

  if use_psyco:
    try:
      import psyco
      psyco.full()
      nbio.LogInfo('using psyco')
    except ImportError:
      nbio.LogInfo('psyco not available')
      pass
  else:
    nbio.LogInfo('not using psyco')

  if dns:
    #for rdata in dns.resolver.query('asd', 'A'):
    #  nbio.LogInfo(repr(rdata))
    #nbio.LogInfo('Query1 done.')
    for rdata in dns.resolver.query('en.wikipedia.org', 'A'):
      nbio.LogInfo(repr(rdata))
    nbio.LogInfo('Query2 done.')
    pass
  listener_nbs = nbio.NonBlockingSocket(socket.AF_INET, socket.SOCK_STREAM)
  listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  listener_nbs.bind(('127.0.0.1', 6666))
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  listener_nbs.listen(100)
  nbio.LogInfo('listening on %r' % (listener_nbs.getsockname(),))
  nbio.stackless.tasklet(wsgi_listener)(listener_nbs, demo_wsgiapp.WsgiApp)
  std_nbf = nbio.NonBlockingFile(sys.stdin, sys.stdout)
  nbio.stackless.tasklet(ChatWorker)(std_nbf, nbf_to_close=listener_nbs)
  nbio.RunMainLoop()
  # We reach this after 'Bye!' in ChatWorker.
