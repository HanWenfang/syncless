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

See the README.txt for more information.

Please import submodules to get the actual functionality. Example:

  import socket
  from syncless import coio
  s = coio.nbsocket(socket.AF_INET, socket.SOCK_STREAM)
  addr = ('www.google.com', 80)
  s.connect(addr)
  s.sendall('GET / HTTP/1.0\r\nHost: %s\r\n\r\n' % addr[0])
  print s.recv(4096)
  coio.sleep(0.5)
  print coio.stackless.current.is_main  # True

The same with monkey-patching:

  import socket
  import time
  from syncless import patch
  patch.patch_socket()
  patch.patch_time()
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  addr = ('www.google.com', 80)
  s.connect(addr)
  s.sendall('GET / HTTP/1.0\r\nHost: %s\r\n\r\n' % addr[0])
  print s.recv(4096)
  time.sleep(0.5)
  print coio.stackless.current.is_main  # True

Syncless provides an emulation of Stackless (the `stackless' module) using
greenlet:

  # Use the emulation if Stackless is not available (recommended).
  from syncless.best_stackless import stackless
  print stackless.__doc__

  # Always use the emulation (not recommended).
  from syncless import greenstackless
  print greenstackless.tasklet

See more examples in examples/demo.py and the examples/demo_*.py files in
the Syncless source distribution.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'
