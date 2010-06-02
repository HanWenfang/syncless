#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Wed Jun  2 01:00:36 CEST 2010

"""Demo for fetching a https:// page using Syncless coio.sslwrap_simple.

This needs Python 2.6 because of the SSL support.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import socket
import ssl
import sys

from syncless import coio
from syncless import patch


def ProgressReporter(delta_sec):
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)


if __name__ == '__main__':
  coio.stackless.tasklet(ProgressReporter)(0.02)
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
  sock.connect(('www.facebook.com', 443))
  patch.patch_socket()
  # coio.sslwrap_simple() is a non-blocking drop-in replacement for
  # ssl.sslwrap_simple() and socket.ssl(). We've patched socket.ssl() above.
  sslsock = socket.ssl(sock)
  req = 'GET / HTTP/1.0\r\n\r\n'
  while req:
    got = sslsock.write(req)
    if got >= len(req):
      break
    req = buffer(req, got)
  head = sslsock.read(512)
  sys.stdout.write('\n%r\n' % head)
  sys.stdout.flush()
  try:
    while 1:  # Reat till EOF
      assert sslsock.read()
  except ssl.SSLError, e:
    if e.errno != ssl.SSL_ERROR_EOF:
      raise
