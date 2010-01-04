"""Syncless: asynchronous client and server library using Stackless Python.

started by pts@fazekas.hu at Sat Dec 19 18:09:16 CET 2009

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

Please import submodules to get the actual functionality. Example:

  import socket
  from syncless import nbio
  s = nbio.NonBlockingSocket(socket.AF_INET, socket.SOCK_STREAM)
  addr = ('www.google.com', 80)
  s.connect(addr)
  s.sendall('GET / HTTP/1.0\r\nHost: %s\r\n\r\n' % addr[0])
  print s.recv(4096)

See more examples in the demo_*.py files in the Syncless source distribution.

Doc: http://www.disinterest.org/resource/stackless/2.6.4-docs-html/library/stackless/channels.html
Doc: http://wiki.netbsd.se/kqueue_tutorial
Doc: http://stackoverflow.com/questions/554805/stackless-python-network-performance-degrading-over-time
Doc: speed benchmark: http://muharem.wordpress.com/2007/07/31/erlang-vs-stackless-python-a-first-benchmark/

Asynchronous DNS for Python:

* twisted.names.client from http://twistedmatrix.com
* dnspython: http://glyphy.com/asynchronous-dns-queries-python-2008-02-09
             http://www.dnspython.org/
* adns-python: http://code.google.com/p/adns/python
*              http://michael.susens-schurter.com/blog/2007/09/18/a-lesson-on-python-dns-and-threads/comment-page-1/

Info: In interactive stackless, repeated invocations of stackless.current may
  return different objects.

TODO(pts): Specify TCP socket timeout. Verify it.
TODO(pts): Specify total HTTP write timeout.
TODO(pts): Move the main loop to another tasklet (?) so async operations can
           work even at initialization.
TODO(pts): Implement an async DNS resolver HTTP interface.
           (This will demonstrate asynchronous socket creation.)
TODO(pts): Document that scheduling is not fair if there are multiple readers
           on the same fd.
TODO(pts): Implement broadcasting chatbot.
TODO(pts): Close connection on 413 Request Entity Too Large.
TODO(pts): Prove that there is no memory leak over a long running time.
TODO(pts): Use socket.recv_into() for buffering.
TODO(pts): Handle signals (at least KeyboardInterrupt).
TODO(pts): Handle errno.EPIPE.
TODO(pts): Handle errno.EINTR. (Do we need this in Python?)
TODO(pts): /infinite 100K buffer on localhost is much faster than 10K.
TODO(pts): Consider alternative implementation with eventlet.
TODO(pts): Implement an SSL-capable HTTP proxy as a referenc
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'
