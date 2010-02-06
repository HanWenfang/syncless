#
# evdns.pxi: Non-blocking DNS lookup routines
# by pts@fazekas.hu at Sat Feb  6 20:04:13 CET 2010
# ### pts #### This file has been entirely written by pts@fazekas.hu.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
#
# TODO(pts): Have a look at Concurrence (or others) for patching everything.

def patch_socket():
    """Monkey-patch the socket module for non-blocking I/O."""
    import socket
    socket.socket = nbsocket
    # TODO(pts): Maybe make this a class?
    socket._realsocket = new_realsocket
    socket._socket.socket = new_realsocket
    socket.gethostbyname = gethostbyname
    socket.gethostbyname_ex = gethostbyname_ex
    socket.gethostbyaddr = gethostbyaddr
    socket.getfqdn = getfqdn
    # TODO(pts): Better indicate NotImplementedError
    socket.getaddrinfo = None
    socket.getnameinfo = None

def patch_time():
    import time
    time.sleep = sleep

def patch_all():
    patch_socket()
    patch_time()
