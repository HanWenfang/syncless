#! /usr/local/bin/stackless2.6

"""Demo for fetching a https:// page using Syncless' NonBlockingSslSocket.

This needs Python 2.6 because of the SSL support.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import socket

from syncless import coio

sock = coio.nbsocket(socket.AF_INET, socket.SOCK_STREAM)
sslsock = coio.nbsslsocket(sock)
addr = ('mail.google.com', 443)
sslsock.connect(addr)
sslsock.sendall('GET / HTTP/1.0\r\nHost: %s:%s\r\n\r\n' % addr)
print sslsock.recv(4096)  #:
"""HTTP/1.0 200 OK\r
Cache-Control: public, max-age=604800\r
Expires: Mon, 11 Jan 2010 15:56:16 GMT\r
Date: Mon, 04 Jan 2010 15:56:16 GMT\r
Refresh: 0;URL=https://mail.google.com:443/mail/\r
Content-Type: text/html; charset=ISO-8859-1\r
X-Content-Type-Options: nosniff\r
X-XSS-Protection: 0\r
X-Frame-Options: SAMEORIGIN\r
Content-Length: 242\r
Server: GFE/2.0\r
\r\n"""
