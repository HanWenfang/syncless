#! /usr/local/bin/stackless2.6
#
# demo.py: demo for syncless WSGI and async DNS
# by pts@fazekas.hu at Sun Dec 20 21:49:16 CET 2009
#

# This import is not necessary, we just demonstrate that we can load stackless
# earlier than coio.
from syncless.best_stackless import stackless

import cgi
import logging
import socket
import sys
import time
import os

import demo_wsgiapp
from syncless import coio
from syncless import patch
from syncless import wsgi


def ChatWorker(nbf, nbf_to_close):
  # TODO(pts): Let's select this from the command line.
  try:
    nbf.write('resolving\n')
    nbf.flush()
    rdata = coio.gethostbyname_ex('www.yahoo.com')
    nbf.write('resolved to %r\n' % (rdata,))
    nbf.write('Type something!\n')  # TODO(pts): Handle EPIPE.
    while True:
      nbf.flush()
      if not nbf.wait_for_readable(3.5):  # 3.5 second
        nbf.write('Come on, type something, I\'m getting bored.\n')
        continue
      s = nbf.read_at_most(128)  # TODO(pts): Do line buffering.
      if not s:
        break
      nbf.write('You typed %r, keep typing.\n' % s)
      # TODO(pts): Add feature to give up control during long computations.
    nbf.write('Bye!\n')
    nbf.flush()
    if nbf_to_close:
      nbf_to_close.close()
  finally:
    nbf.close()


if __name__ == '__main__':
  logging.BASIC_FORMAT = '[%(created)f] %(levelname)s %(message)s'
  logging.root.setLevel(logging.INFO)
  wsgi_listener = wsgi.WsgiListener
  use_psyco = False
  do_verbose = False
  use_https = False
  use_cherrypy = False
  for arg in sys.argv[1:]:
    if arg in ('--cherrypy-wsgi', '--cherrypy', '-c'):
      wsgi_listener = wsgi.CherryPyWsgiListener
      use_cherrypy = True
    elif arg in ('--https', '-s'):
      use_https  = True
    elif arg in ('--verbose', '-v'):
      do_verbose = True
    elif arg in ('--psyco', '-p'):
      use_psyco = True
    elif arg in ('--no-psyco', '+p'):
      use_psyco = False
    else:
      assert 0, 'invalid arg: %s' % arg

  if do_verbose:
    logging.root.setLevel(logging.DEBUG)

  if use_psyco:
    try:
      import psyco
      psyco.full()
      logging.info('using psyco')
    except ImportError:
      logging.info('psyco not available')
      pass
  else:
    logging.info('not using psyco')

  rdata = coio.gethostbyname_ex('en.wikipedia.org')
  logging.info(repr(rdata))
  logging.info('Query2 done.')
  listener_nbs = coio.new_realsocket(socket.AF_INET, socket.SOCK_STREAM)
  listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  listener_nbs.bind(('127.0.0.1', 6666))
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  listener_nbs.listen(100)
  logging.info('visit http://%s:%s/' % listener_nbs.getsockname())
  if use_https:
    sslsock_kwargs = {
        # Parallelize handshakes by moving them to a tasklet.
        'do_handshake_on_connect': False,
        'certfile': os.path.join(os.path.dirname(__file__), 'ssl_cert.pem'),
        'keyfile':  os.path.join(os.path.dirname(__file__), 'ssl_key.pem'),
    }
    # Make sure that the keyfile and certfile exist and they are valid etc.
    patch.validate_new_sslsock(**sslsock_kwargs)
    ssl_listener_nbs = coio.nbsslsocket(
        socket.socket(socket.AF_INET, socket.SOCK_STREAM), **sslsock_kwargs)
    ssl_listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ssl_listener_nbs.bind(('127.0.0.1', 4443))
    ssl_listener_nbs.listen(100)
    logging.info('visit https://%s:%s/' % ssl_listener_nbs.getsockname())
    coio.stackless.tasklet(wsgi_listener)(
        ssl_listener_nbs, demo_wsgiapp.WsgiApp)
  coio.stackless.tasklet(wsgi_listener)(listener_nbs, demo_wsgiapp.WsgiApp)
  std_nbf = coio.nbfile(0, 1, write_buffer_limit=2)
  ChatWorker(std_nbf, nbf_to_close=listener_nbs)
