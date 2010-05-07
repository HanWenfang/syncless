#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Feb 14 12:12:38 CET 2010
#
# TODO(pts): Add a proper test, with our custom (blocking) SSL server.
# TODO(pts): Add a proper test for a non-blocking SSL server and its client.

"""Demo for implementing a HTTPS server by hand using Syncless coio.

Please note that syncless.wsgi also supports SSL (see examples/demo.py),
please use that in production instead of writing your own HTTP(S) server.

This needs Python 2.6 because of the SSL support.
"""

import errno
import gc
import os
import os.path
import socket
import ssl
import sys
from syncless import coio
from syncless import patch

# Here is how to create the SSL certificates:
# sudo apt-get install openssl
#openssl genrsa -out example-rsa.pem 2048
#yes '' | openssl req -new -key example-rsa.pem -out example-cert.csr
#yes '' | openssl req -new -x509 -key example-rsa.pem -out example-cert.pem

def HandleRequest(csslsock, addr):
  f = None
  try:
    print >>sys.stderr, 'info: accepted %s from %s' % (csslsock, addr)
    # TODO(pts): Impose a timeout on the SSL handshake. Sometimes the SSL
    # handshake takes infinite time because a HTTP request is issued instead
    # of a HTTPS request.
    if hasattr(csslsock, 'do_handshake_on_connect'):
      print >>sys.stderr, 'info: doing SSL handshake'
      csslsock.do_handshake()
      print >>sys.stderr, 'info: SSL handshake completed'
    f = csslsock.makefile()
    # Read the HTTP request header.
    request_lines = []
    while True:
      line = f.readline()
      if not line:
        return
      line = line.rstrip('\r\n')
      if not line:
        break
      request_lines.append(line)
    if not request_lines:
      request_lines.append('No request.')
    # Write the HTTP response.
    body = 'Hello, World!\n%s\n' % request_lines[0]
    http_response = (
        'HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n'
        'Content-Length: %d\r\n\r\n%s' % (len(body), body))
    f.write(http_response)
    f.close()  # Flush before closing.
  except IOError, e:
    print >>sys.stderr, 'error: %s.%s: %s' % (
        e.__class__.__module__, e.__class__.__name__, e)
  finally:  # TODO(pts): Make sure this is automatic, and drop it.
    if f and f._sock:
      f.close()
    csslsock.close()

if __name__ == '__main__':
  #gc.disable()
  use_ssl = True
  if len(sys.argv) == 1:
    sslsocket_impl = coio.nbsslsocket  # Non-blocking (by default).
  else:
    sslsocket_impl = ssl.SSLSocket     # Blocking (1 connection at a time).
    patch.fix_ssl_makefile()
    patch.fix_ssl_init_memory_leak()
  print >>sys.stderr, 'info: testing with %s' % sslsocket_impl
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  if use_ssl:
    sslsock_kwargs = {
        # Parallelize handshakes by moving them to a tasklet.
        'do_handshake_on_connect': False,
        'certfile': os.path.join(os.path.dirname(__file__), 'ssl_cert.pem'),
        'keyfile':  os.path.join(os.path.dirname(__file__), 'ssl_key.pem'),
    }
    # Make sure that the keyfile and certfile exist and they are valid etc.
    patch.validate_new_sslsock(**sslsock_kwargs)
    sslsock = sslsocket_impl(sock, **sslsock_kwargs)
  else:
    sslsock = sock
  sslsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sslsock.bind(('127.0.0.1', 44433))
  sslsock.listen(128)
  print >>sys.stderr, 'info: visit http%s://%s:%s/' % (
      's' * bool(use_ssl),
      sslsock.getsockname()[0], sslsock.getsockname()[1])
  print >>sys.stderr, 'info: listening on %s' % (sslsock.getsockname(),)
  while True:
    try:
      csslsock, addr = sslsock.accept()
    except socket.error, e:  # This includes ssl.SSLError.
      # We may get an ssl.SSLError or a socket.socketerror in a failed
      # handshake.
      print >>sys.stderr, 'error: %s' % e  # !!
      continue
    coio.stackless.tasklet(HandleRequest)(csslsock, addr)
    csslsock = addr = None  # Free memory early.
    coio.stackless.schedule(None)  # Give a chance for HandleRequest.
