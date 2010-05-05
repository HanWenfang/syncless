#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Apr 18 16:02:32 CEST 2010

import stackless
import socket

from syncless import coio

if __name__ == '__main__':
  sock = coio.nbsocket(socket.AF_INET, socket.SOCK_STREAM, 0)
  #sock.connect(('gmail-smtp-in.l.google.com', 25))
  sock.connect(('209.85.218.52', 25))
  print repr(sock.recv(256))  # '220 mx.google.com ESMTP 20si15803912bwz.24'
  print 'Exiting.'
  # Won't exit because we did DNS lookups with coio (evdns).
  #stackless.schedule_remove(None)
