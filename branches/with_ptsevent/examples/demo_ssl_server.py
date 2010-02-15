#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Feb 14 12:12:38 CET 2010
#
# TODO(pts): Add a proper test, with our custom (blocking) SSL server.
# TODO(pts): Add a proper test for a non-blocking SSL server and its client.

import socket
import ssl
import stackless
import sys
from syncless import coio
from syncless import patch

# sudo apt-get install openssl
#openssl genrsa -out example-rsa.pem 2048
#yes '' | openssl req -new -key example-rsa.pem -out example-cert.csr
#yes '' | openssl req -new -x509 -key example-rsa.pem -out example-cert.pem

def HandleRequest(csslsock, addr):
  print >>sys.stderr, 'info: accepted %s from %s' % (csslsock, addr)
  f = None
  try:
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
  finally:  # TODO(pts): Make sure this is automatic, and drop it.
    if f and f._sock:
      f.close()
    csslsock.close()

if __name__ == '__main__':
  use_ssl = True
  if len(sys.argv) > 1:
    sslsocket_impl = coio.nbsslsocket  # Non-blocking.
  else:
    sslsocket_impl = ssl.SSLSocket     # Blocking.
    patch.fix_ssl_makefile()
  print >>sys.stderr, 'info: testing with %s' % sslsocket_impl
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  if use_ssl:
    # TODO(pts): use resource.py to find example-cert.pem?
    #sslsock = sslsocket_impl(sock, keyfile='example-rsa.pem',
    #                         certfile='example-cert.pem')
    sslsock = sslsocket_impl(
      sock,
      certfile='/usr/local/lib/python2.6/test/ssl_cert.pem',
      keyfile='/usr/local/lib/python2.6/test/ssl_key.pem')
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
      # !! TODO(pts): SUXX: Move the SSL handshake to the new tasklet.
      # Sometimes the SSL handshake takes infinite time because a HTTP request
      # is issued instead of a HTTPS request.
      csslsock, addr = sslsock.accept()
    except socket.error, e:  # This includes ssl.SSLError.
      # We may get an ssl.SSLError or a socket.socketerror in a failed
      # handshake.
      continue
    stackless.tasklet(HandleRequest)(csslsock, addr)
    # !! SUXX: segfault within the first 3 connections, both with wget(1) and
    # links(1). Works perfectly with ssl.SSLSocket, segfaults with nbsslsocket.
    # ssl_cert.pem doesn't help.
    stackless.schedule()  # Give a chance for HandleRequest.
    csslsock = addr = None  # Free memory early.
