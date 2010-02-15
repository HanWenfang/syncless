README for Syncless: asynchronous client and server library using
Stackless Python
""""""""""""""""
by pts@fazekas.hu at Sun Dec 20 22:47:13 CET 2009
-- Fri Jan  8 03:06:58 CET 2010
-- Tue Feb  9 19:02:52 CET 2010

Syncless is an experimental, lightweight, non-blocking (asynchronous) client
and server socket network communication library for Stackless Python 2.6.
For high speed, Syncless uses libevent, and parts of Syncless' code is
implemented in C (Pyrex). Thus Syncless can be faster than many other
non-blocking Python communication libraries. Syncless contains an
asynchronous DNS resolver (using evdns) and a HTTP server capable of serving
WSGI applications. Syncless aims to be a coroutine-based alternative of
event-driven networking engines (such as Twisted and FriendFeed's Tornado),
and it's a competitor of gevent, pyevent, eventlet and Concurrence.

Features
~~~~~~~~
* handling multiple TCP connections concurrently in a single Python process,
  using cooperative multitasking provided by Stackless Python (without
  the need for callbacks, threads, subprocesses or locking)
* non-intruisive I/O multiplexing, easy to integrate with existing code
  (with a non-blocking, monkey-patchable, almost faithful reimplementation
  of the socket.socket classes and time.sleep)
* compatible timeout handling on individual socket operations
* I/O event detection using libevent, which can use epoll(7) or kqueue
  (if available)
* built-in WSGI server, but can use CherryPy's WSGI server as well
* non-blocking DNS resolver using evdns
* TODO(pts): Remimplement this
  non-blocking stdin/stdout support (can be useful for implementing an
  interactive server console)
* fast (comparable and sometimes faster than Concurrency, eventlet, node.js
  and eventlet), see benchmark/README.txt

Requirements
~~~~~~~~~~~~
* A recent Unix system. Tested on Linux 2.6, should work on FreeBSD. Testers
  for other Unix variants are welcome. It won't work on Win32 or Win64.
* Stackless Python (recommended) or normal (C)Python with greenlet (slow,
  may leak memory, not recommended).
* Python 2.6 (recommended, for epoll(7) support) or Python 2.5.
* A C compiler and the Python development package (.h files) for
  compilation.
* TODO(pts): Reimplement this: SSL client sockets.

How to use
~~~~~~~~~~
1. Download and install Stackless Python 2.6.x from http://stackless.com/
   For convenience, rename the executable to /usr/local/bin/stackless2.6

2. Download and extract Syncless.

3. Install Syncless:

     $ stackless2.6 ./setup.py build
     $ sudo stackless2.6 ./setup.py install

4. In the Syncless directory, run

     $ stackless2.6 ./demo.py

6. Have a look at examples/demo_*.py in the source directory to study the
   examples.

The original blog announcement of Syncless' precedessor:
http://ptspts.blogspot.com/2009/12/experimental-http-server-using.html

Example code
~~~~~~~~~~~~
See examples/demo_*.py in the Syncless source directory.

Author
~~~~~~
with accents in UTF-8: Péter Szabó <pts@fazekas.hu>
without accents: Peter Szabo <pts@fazekas.hu>

Using Syncless with web frameworks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The WSGI-capable HTTP server in Syncless can run any framework with WSGI
support. Examples:

* pure WSGI application, without a framework: see SimpleWsgiApp in demo.py
  and examples/demo_wsgiapp.py
* (web.py): see examples/demo_syncless_web_py.py
* CherryPy: see examples/demo_syncless_cherrypy.py
* Google AppEngine webapp: see examples/demo_syncless_webapp.py
* Python built-in BaseHTTPRequestHandler: see
  examples/demo_syncless_basehttp.py

Please note that Syncless is not a web framework.

Please note that Syncless is not ready yet for production (e.g. TCP
communication error handling and robust recovery from exceptions are not
written). Feel free to try it, however, with your web application (using any
framework), and report problems.

Related projects
~~~~~~~~~~~~~~~~
* Spawning (WSGI server) http://pypi.python.org/pypi/Spawning
* Concurrence
* gevent
* node.js (in Javascript)
* Eventlet (instead of Stackless Python) http://eventlet.net/
  slides http://soundfarmer.com/content/slides/coroutines-nonblocking-io-eventlet-spawning/coros,%20nonblocking%20i:o,%20eventlet,%20spawning.pdf
* stacklessocket
  http://code.google.com/p/stacklessexamples/wiki/StacklessNetworking
* stacklesswsgi
  http://code.google.com/p/stacklessexamples/wiki/StacklessWSGI
* pyevent (uses callbacks instead of coroutines)
* Twisted (uses callbacks instead of coroutines)
* Tornado (uses callbacks instead of coroutines)

Feature design of the new event loop (syncless.coio)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
My conclusion was that in order to get the fastest coroutine-based,
non-blocking, line-buffering-capable I/O library for Python, I should wrap
libevent (including event registration and I/O buffering) and Stackless and
the WSGI server in hand-optimized Pyrex, manually checking the .c file Pyrex
generates for inefficiencies. I'll be doing so soon.

syncless.coio will provide the following features:

* drop-in non-blocking replacements so pure Python network libraries
  (such as urllib2, dnspython and BaseHTTPServer) can be used unmodified:
** syncless.coio.gethostbyname for socket.gethostbyname
** syncless.coio.gethostbyaddr for socket.gethostbyaddr
** syncless.coio.getaddrinfo for socket.getaddrinfo
** syncless.coio.pipe for os.pipe
** syncless.coio.socket_compat for socket.socket
** syncless.coio.socketfile_compat for socket._fileobject
** syncless.coio.realsocket_compat for socket._realsocket
** syncless.coio.socket_fromfd for socket.fromfd
** syncless.coio.socketpair for socket.socketpair
** syncless.coio.open for open (nonblock for pipes, sockets and char devices)
** syncless.coio.file_compat for file (nonblock for pipes, sockets and char devices)
** syncless.coio.sslsocket_compat for ssl.SSLSocket
** syncless.coio.sslsocketfile_compat for ssl._fileobject
** syncless.coio.select for select.select (initial implementation works only with
   1 input filehandle)
** (None for socket._socket)
** (None for ssl._ssl)
** (None for select.poll)
** (None for select.epoll)
** (TODO(pts): Which of these is high speed?)
* function to monkey-patch the replacements above
* syncless.coio.fastsocket without timeout (only SO_RECVTIMEO) and makefile
  returning self
* built-in high performance WSGI server
* can use CherryPy's WSGI server as well

Features removed from old Syncless:

* credit system for fair scheduling
* edge-triggered epoll operation
* ability to use greenlet instead of Stackless (may be added later)

Code used for syncless.io
~~~~~~~~~~~~~~~~~~~~~~~~~
Copied files from the BSD-licensed pyevent (libevent Python bindings),
revision 60 from
svn checkout http://pyevent.googlecode.com/svn/trunk/ pyevent-read-only
* Makefile
* evdns.pxi
* event.pyx
* setup.py
* test.py

Limitations
~~~~~~~~~~~
1. The DNS looup functions (even the emulated syncless.coio.gethostbyname) read
   /etc/hosts (and /etc/resolve.conf) only at startup.

2. For hostname lookups, Linux libc6 NSS mechanisms (such as
   /etc/nsswitch.conf and etc/host.conf) are ignored: /etc/hosts is used
   first, then a DNS lookup is done.

3. The reverse DNS lookup functions fail on a host with multiple PTR records:

$ host 202.92.65.220 
;; Truncated, retrying in TCP mode.
220.65.92.202.in-addr.arpa domain name pointer pop.cbdcorp.com.au.
220.65.92.202.in-addr.arpa domain name pointer pop.stanicharding.com.au.
220.65.92.202.in-addr.arpa domain name pointer webmail.stanicharding.com.au.
220.65.92.202.in-addr.arpa domain name pointer webmail.cbdcorp.com.au.
220.65.92.202.in-addr.arpa domain name pointer webmail.viewhotels.com.au.
220.65.92.202.in-addr.arpa domain name pointer pop.migrationlawforum.com.au.
220.65.92.202.in-addr.arpa domain name pointer sydmail01.powertel.net.au.
220.65.92.202.in-addr.arpa domain name pointer mail.viewhotels.com.au.
220.65.92.202.in-addr.arpa domain name pointer mail.migrationlawforum.com.au.
220.65.92.202.in-addr.arpa domain name pointer webmail.migrationlawforum.com.au.
220.65.92.202.in-addr.arpa domain name pointer mail.c2cextreme.net.
220.65.92.202.in-addr.arpa domain name pointer mail.cbdcorp.com.au.
220.65.92.202.in-addr.arpa domain name pointer mail.stanicharding.com.au
$ stackless2.6 -c 'import syncless.coio;
print syncless.coio.dns_resolve_reverse("202.92.65.220")'
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "evdns.pxi", line 344, in syncless.coio.dns_resolve_reverse
  File "evdns.pxi", line 278, in syncless.coio.dns_call
syncless.coio.DnsLookupError: [Errno -65] reply truncated or ill-formed

4. syncless.coio.gethostbyname_ex is slower (does 2 DNS lookups) and only
   approximates the answer of socket.gethostbyname_ex, because evdns doesn't
   support CNAME lookups.

Planned features
~~~~~~~~~~~~~~~~
* TODO(pts): Document the side effect of import syncless.coio on Ctrl-<C>.
* TODO(pts): TCP communication error handling in the WSGI server
* TODO(pts): HTTP client library (making urllib non-blocking?)
* TODO(pts): Twisted integration
* TODO(pts): support webob as a web framework
* TODO(pts): productionization
* TODO(pts): timeout on socket and SSLSocket operations
* TODO(pts): monkey-patching socket and SSLSocket
* TODO(pts): setsockopt TCP_DEFER_ACCEPT
* TODO(pts): setsockopt SO_LINGER non-immediate close() for writing
* TODO(pts): use SO_RCVTIMEO and SO_SNDTIMEO for timeout
* TODO(pts): is it smaller or faste in Cython?
* TODO(pts): measure if evhttp is faster for WSGI than in pure Python
* !! TODO(pts): Handle starving (when one worker is very fast, even Ctrl-<C>
  is delayed)

__EOF__
