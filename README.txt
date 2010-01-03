README for Syncless
~~~~~~~~~~~~~~~~~~~
by pts@fazekas.hu at Sun Dec 20 22:47:13 CET 2009
-- Mon Dec 28 00:40:30 CET 2009

Syncless is an experimental, lightweight, non-blocking (asynchronous) client
and server socket network communication library implemented in Stackless
Python 2.6. Syncless contains an asynchronous DNS resolver (using dnspython)
and a HTTP server capable of serving WSGI applications. Syncless aims to be
a coroutine-based alternative of event-driven networking engines (such as
Twisted and FriendFeed's Tornado). Syncless is already about that fast, but
it has less features and it's less stable now.

Features
~~~~~~~~
* handling multiple TCP connections concurrently in a single Python process,
  using cooperative multitasking provided by Stackless Python (without
  the need for callbacks, threads, subprocesses or locking)
* non-intruisive I/O multiplexing, easy to integrate with existing code (can
  be as easy as changing the socket constructor socket.socket to
  syncless.NonBlockingSocket)
* timeout on individual socket operation (needs changing existing code)
* I/O event detection using epoll() (if available) or select()
* built-in WSGI server, but can use CherryPy's WSGI server as well
* non-blocking DNS resolver using dnspython
* non-blocking stdin/stdout support (can be useful for implementing an
  interactive server console)
* pure Python implementation, requires Stackless Python 2.6 only

Requirements
~~~~~~~~~~~~
* A recent Unix system. Tested on Linux 2.6, should work on FreeBSD. Testers
  for other Unix variants are welcome.

How to use
~~~~~~~~~~
1. Download and install Stackless Python 2.6.x from http://stackless.com/
   For convenience, name the executable /usr/local/bin/stackless 

2. Download and install dnspython from http://www.dnspython.org/
   Example compilation and installation:

     $ stackless2.6 ./setup.py build
     $ sudo stackless2.6 ./setup.py install

3. Download and extract Syncless.

4. In the Syncless directory, run

     $ stackless2.6 ./demo.py

The original blog announcement of Syncless' precedessor:
http://ptspts.blogspot.com/2009/12/experimental-http-server-using.html

Using Syncless with web frameworks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The WSGI-capable HTTP server in Syncless can run any framework with WSGI
support. Examples:

* pure WSGI application, without a framework: see SimpleWsgiApp in demo.py
  and demo_wsgiapp.py
* (web.py): see demo_syncless_web_py.py
* CherryPy: see demo_syncless_cherrypy.py
* Google AppEngine webapp: see demo_syncless_webapp.py
* Python built-in BaseHTTPRequestHandler: see demo_syncless_basehttp.py

Please note that Syncless is not a web framework.

Please note that Syncless is not ready yet for production (e.g. TCP
communication error handling and robust recovery from exceptions are not
written). Feel free to try it, however, with your web application (using any
framework), and report problems.

Related projects
~~~~~~~~~~~~~~~~
* Spawning (WSGI server) http://pypi.python.org/pypi/Spawning
* Eventlet (instead of Stackless Python) http://eventlet.net/
  slides http://soundfarmer.com/content/slides/coroutines-nonblocking-io-eventlet-spawning/coros,%20nonblocking%20i:o,%20eventlet,%20spawning.pdf
* stacklessocket
  http://code.google.com/p/stacklessexamples/wiki/StacklessNetworking
* stacklesswsgi
  http://code.google.com/p/stacklessexamples/wiki/StacklessWSGI

Planned features
~~~~~~~~~~~~~~~~
* TCP communication error handling in the WSGI server
* HTTP client library (making urllib non-blocking?)
* Twisted integration
* support webob as a web framework
* productionization
* http://pypi.python.org/ and easy_install integration

__EOF__
