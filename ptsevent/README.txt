README for ptsevent: a high performance Stackless Python binding for libevent
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
ptsevent is a high performance Stackless Python binding for libevent
implemented as a C extension for Python in Pyrex. ptsevent intends to be the
high speed backend of a future rewrite of Syncless (a lightweight,
non-blocking (asynchronous) client and server socket network communication
library for Stackless Python).

ptsevent is currently experimental. It is tested on Linux with Stackless
2.6.4.

My conclusion was that in order to get the fastest coroutine-based,
non-blocking, line-buffering-capable I/O library for Python, I should wrap
libevent (including event registration and I/O buffering) and Stackless and
the WSGI server in hand-optimized Pyrex, manually checking the .c file Pyrex
generates for inefficiencies. I'll be doing so soon.

Feature design
~~~~~~~~~~~~~~
ptsevent, and the new Syncless will provide the following features:

* drop-in non-blocking replacements so pure Python network libraries
  (such as urllib2, dnspython and BaseHTTPServer) can be used unmodified:
** ptsevent.gethostbyname for socket.gethostbyname
** ptsevent.gethostbyaddr for socket.gethostbyaddr
** ptsevent.getaddrinfo for socket.getaddrinfo
** ptsevent.pipe for os.pipe
** ptsevent.socket_compat for socket.socket
** ptsevent.socketfile_compat for socket._fileobject
** ptsevent.realsocket_compat for socket._realsocket
** ptsevent.socket_fromfd for socket.fromfd
** ptsevent.socketpair for socket.socketpair
** ptsevent.open for open (nonblock for pipes, sockets and char devices)
** ptsevent.file_compat for file (nonblock for pipes, sockets and char devices)
** ptsevent.sslsocket_compat for ssl.SSLSocket
** ptsevent.sslsocketfile_compat for ssl._fileobject
** ptsevent.select for select.select (initial implementation works only with
   1 input filehandle)
** (None for socket._socket)
** (None for ssl._ssl)
** (None for select.poll)
** (None for select.epoll)
** (TODO(pts): Which of these is high speed?)
* function to monkey-patch the replacements above
* ptsevent.fastsocket without timeout (only SO_RECVTIMEO) and makefile
  returning self
* built-in high performance WSGI server
* can use CherryPy's WSGI server as well

Features removed from old Syncless:

* credit system for fair scheduling
* edge-triggered epoll operation
* ability to use greenlet instead of Stackless (may be added later)

Author
~~~~~~
with accents in UTF-8: Péter Szabó <pts@fazekas.hu>
without accents: Peter Szabo <pts@fazekas.hu>

Code used
~~~~~~~~~
Copied files from the BSD-licensed pyevent (libevent Python bindings),
revision 60 from
svn checkout http://pyevent.googlecode.com/svn/trunk/ pyevent-read-only
* Makefile
* evdns.pxi
* event.pyx
* setup.py
* test.py

---

TODO(pts): setsockopt TCP_DEFER_ACCEPT
TODO(pts): setsockopt SO_LINGER non-immediate close() for writing
TODO(pts: use SO_RCVTIMEO and SO_SNDTIMEO for timeout
