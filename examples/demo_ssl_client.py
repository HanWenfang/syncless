#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Feb 14 12:12:38 CET 2010
#
# TODO(pts): Add a proper test, with our custom (blocking) SSL server.
# TODO(pts): Add a proper test for a non-blocking SSL server and its client.

"""Demo for fetching a https:// page using Syncless coio.

This needs Python 2.6 because of the SSL support.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'


import socket
import ssl
import sys
from syncless import coio
from syncless import patch

if __name__ == '__main__':
  if len(sys.argv) > 1:
    sslsocket_impl = coio.nbsslsocket  # Non-blocking.
  else:
    sslsocket_impl = ssl.SSLSocket     # Blocking.
    patch.fix_ssl_makefile()
  print >>sys.stderr, 'info: testing with %s' % sslsocket_impl
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  sslsock = sslsocket_impl(sock)
  d = sslsock.dup()
  assert isinstance(d, socket.socket) or isinstance(d, coio.nbsocket)
  d = None
  assert sslsock._sslobj is None
  sslsock.connect(('www.gmail.com', 443))
  assert isinstance(sslsock._sslobj, socket._ssl.SSLType)
  assert 0 == sslsock._makefile_refs
  sslsock.makefile('r+').close()
  # Without fix_ssl[5~_makefile, this would be 1 instead of 0.
  assert 0 == sslsock._makefile_refs
  assert sslsock._sslobj is not None
  sslsock.close()
  assert sslsock._sslobj is None

  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  sslsock = sslsocket_impl(sock)
  sslsock.connect(('www.apache.org', 443))
  sslsock.send(buffer('GET'))
  sslsock.send(' /')
  f = sslsock.makefile('r+')
  f.write('should_be_not_found HTTP/1.0\r\n\r\n')
  f.flush()
  response = []
  for line in f:
    #print repr(line)
    response.append(line)
  f.close()
  response = ''.join(response)
  assert ('The requested URL /should_be_not_found'
          ' was not found on this server.' in response), repr(response)
  print 'All OK.'
