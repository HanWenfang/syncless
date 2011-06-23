#! /usr/local/bin/stackless2.6
# original of this code was contributed by Nick Pappas in
# http://code.google.com/p/syncless/issues/detail?id=12

import hashlib
import os
import os.path
import socket
import ssl
import sys
import traceback

def Try(use_syncless, dir_name):
  print 'use_syncless = %r' % use_syncless

  server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sslsock_kwargs = {
    'do_handshake_on_connect': False,
    'certfile': os.path.join(dir_name, 'i12-crt.pem'),
    'keyfile': os.path.join(dir_name, 'i12-rsa.pem'),
    'server_side': True,
    'cert_reqs': ssl.CERT_OPTIONAL,
    'ca_certs': os.path.join(dir_name, 'i12-crt.pem'),
  }
  if use_syncless:
    from syncless import coio
    # It would work equally well with a coio.nbsocket instead of a socket.socket.
    server_socket = coio.ssl_wrap_socket(server_socket, **sslsock_kwargs)
  else:
    server_socket = ssl.wrap_socket(server_socket, **sslsock_kwargs)
  server_socket.bind(('127.0.0.1', 0))  # The OS picks a port.
  server_port = server_socket.getsockname()[1]
  server_socket.listen(128)

  pid = os.fork()
  if not pid:  # Child, client.
    try:
      server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      sslsock_kwargs = {
         'certfile': os.path.join(dir_name, 'i12-crt.pem'),
         'keyfile': os.path.join(dir_name, 'i12-rsa.pem'),
      }
      client_socket = ssl.wrap_socket(server_socket, **sslsock_kwargs)
      client_socket.connect(('127.0.0.1', server_port))
      os._exit(0)
    except:
      traceback.print_exc()
      os._exit(1)

  try:
    client_socket, _ = server_socket.accept()
    client_socket.do_handshake()
    a = hashlib.sha1(client_socket.getpeercert(True)).hexdigest()
    b = client_socket.getpeername()
    c = client_socket.cipher()
    assert ('9672db438ac840b9fe2fc0b244a022056d2cff90', '127.0.0.1',
            ('AES256-SHA', 'TLSv1/SSLv3', 256)) == (a, b[0], c)
  finally:
    pid2, status = os.waitpid(pid, 0)
    assert pid2 == pid
    assert not status, repr(status)


if __name__ == '__main__':
  Try(False, os.path.dirname(__file__))
  Try(True, os.path.dirname(__file__))
  print 'All OK.'
