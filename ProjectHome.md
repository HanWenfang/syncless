Syncless is a non-blocking (asynchronous) concurrent client and server
socket network communication library for Stackless Python 2.6 (and also for
regular Python with greenlet). For high speed, Syncless uses libev (and
libevent) for event notification, and parts of Syncless' code is implemented
in Pyrex/Cython and C. This alone makes Syncless faster than many other
non-blocking network libraries for Python. Syncless contains an asynchronous
DNS resolver (using evdns) and a HTTP server capable of serving WSGI
applications. Syncless aims to be a coroutine-based alternative of
event-driven networking engines (such as Twisted, asyncore, pyevent,
python-libevent and FriendFeed's Tornado), and it's a competitor of gevent,
Eventlet and Concurrence.

```
"
$ sudo easy_install syncless
$ python -c 'if 1:
    from syncless import wsgi; import stackless
    wsgi.simple(8080, lambda *args: ["Hello, <b>World<\/b>!\n"])
    stackless.schedule_remove()'
Ctrl-<Z>
[1] Stopped   python
$ bg
$ wget -q -O - http://127.0.0.1:8080/
Hello, <b>World</b>!
$ kill %1
$ python -m syncless.console
...
>>> help
```

On Linux, it's possible to try Syncless without installation, using the <a href='http://code.google.com/p/pts-mini-gpl/wiki/StaticPython'>StaticPython</a> binary Python distribution, like this:

```
$ wget -O stacklessco2.7-static http://pts-mini-gpl.googlecode.com/svn/trunk/staticpython/release/stacklessco2.7-static
$ chmod +x stacklessco2.7-static
$ ./stacklessco2.7-static
Python 2.7.1 Stackless 3.1b3 060516 (release27-maint, Feb  1 2011, 16:57:16) 
[GCC 4.1.2] on linux2
Type "help", "copyright", "credits" or "license" for more information.
>>> from syncless import coio
>>> coio.sleep(1.5)
(sleeping for 1.5 second)
<object object at 0xf7709490>
>>> 
```

### Features ###

  * handling multiple TCP connections concurrently in a single Python process, using cooperative multitasking based on coroutines, as provided by Stackless Python or greenlet (without the need for callbacks, threads, subprocesses or locking)
  * non-blocking DNS resolver using evdns
  * monkey-patchable, almost faithful non-blocking reimplementation of socket.socket, socket.gethostbyname (etc.), ssl.SSLSocket, time.sleep and select.select
  * compatible timeout handling on individual socket operations
  * I/O event detection with libevent1, libevent2 or libev (fastest) and provides a slow fallback if none of these are available
  * easy to convert existing single-threaded, multi-threaded or multiprocess code to Syncless coroutines (because coroutines work like lightweight threads, Syncless exposes a compatible, monkey-patchable interface for sockets, pipes and buffered I/O, and locking is not needed)
  * non-blocking support added by monkey-patching to built-in urllib, urllib2, smtplib, ftplib, imaplib, poplib, asyncore, popen2, subprocess etc. modules
  * special monkey-patching for pure Python MySQL client libraries mysql.connector and pymysql
  * special monkey-patching for C (Cython) MySQL client library geventmysql
  * I/O event detection using the fastest methods (epoll(7) on Linux, kqueue on BSD etc.) with libev
  * built-in (non-blocking) WSGI server, but can use CherryPy's WSGI server as well in non-blocking mode
  * non-blocking stdin/stdout support
  * built-in WSGI server capable of running not only WSGI applications, but BaseHTTPRequestHandler + BaseHTTPServer applications, CherryPy applications, web.py applications, and Google webapp applications (not supporting most other Google AppEngine technologies) as well
  * combination of Syncless and (Twisted, Tornado (fast), Concurrence, gevent, Eventlet, circuits and/or asyncore) in the same process
  * a thread pool class for wrapping blocking operations
  * an interactive Python console for experimenting with the Syncless library, without having to write a Python script
  * a remote interactive Python console (backdoor) named RemoteConsole for debugging, which accepts TCP (telnet) connections, and supports line editing (readline) if used with the supplied client
  * WebSocket server in the WSGI server module
  * HTTP/1.1 request pipelining


See the <a href='http://ptspts.blogspot.com/2010/05/feature-comparison-of-python-non.html'>feature comparison</a> of Syncless, Twisted, Eventlet, gevent, Concurrence, Tornado and asyncore. See also an <a href='http://nichol.as/asynchronous-servers-in-python'>older feature comparison</a> of 4 Python non-blocking networking I/O libraries, including generator-based ones.

### System requirements ###

  * A recent Unix system. Tested on Linux 2.6 and Mac OS X 10.5, should also work on FreeBSD and others. Testers for other Unix variants are welcome. It won't work on Windows (Win32 or Win64).
  * At runtime, need less than 0.3 MB memory in addition to what Python needs without Syncless. Needs much less memory than the same Python application with threads.
  * (C)Python 2.5, 2.6 or 2.7. Doesn't work with anything earlier than 2.5. Doesn't work with 3.x. There are no plans to add 3.x support, but I'm open to integrate Python 3.x suppport to Syncless if someone volunteers to write it. Doesn't work with PyPy. Python >= 2.6 is needed for SSL support.
  * Stackless Python or normal (C)Python with the greenlet extension. Stackless Python is strongly recommended for production use, because it's faster and doesn't have memory leaks.

See installation instructions in the [README](http://syncless.googlecode.com/svn/trunk/README.txt).

### Documentation ###

See the [README](http://syncless.googlecode.com/svn/trunk/README.txt) for installation instructions and other documentation.

See also the slides about coroutine-based I/O in Python (and other languages): [13371 concurrent TCP connections in Python with coroutines](http://syncless.googlecode.com/svn/trunk/doc/slides_2010-11-29/pts_coro_2010-11-29.html)

### Compatibility matrix ###

The following matrix displays which network libraries can run in the same process.

|              | Syncless | gevent | Concurrence | Eventlet | Tornado | asyncore | circuits | Twisted | GTK+ | Qt  |
|:-------------|:---------|:-------|:------------|:---------|:--------|:---------|:---------|:--------|:-----|:----|
| Syncless     | yes      | yes, 1)| yes         | yes      | yes     | yes      | yes      | yes     |      |     |
| gevent       | yes, 1)  | yes    |             |          |         |          |          |         |      |     |
| Concurrence  | yes      |        | yes         |          |         |          |          |         |      |     |
| Eventlet     | yes      |        |             | yes      |         |          |          |         |      |     |
| Tornado      | yes      |        |             |          | yes     |          |          |         |      |     |
| asyncore     | yes      |        |             |          |         | yes      |          |         |      |     |
| circuits     | yes      |        |             |          |         |          | yes      |         | yes  |     |
| Twisted      | yes      |        |             |          |         |          |          | yes     | yes  | yes |
| GTK+         |          |        |             |          |         |          | yes      | yes     | yes  |     |
| Qt           |          |        |             |          |         |          |          | yes     |      | yes |

1) Limitation between Syncless and gevent: They must be linked to the same libevent version.

Please note that usually there is no direct synchronization support between Syncless and these libraries, i.e. there is no way for a tasklet managed by a library to notify a tasklet managed by another library that computation results are available.

### Software similar to Syncless ###

Similarly to Syncless, the following software also provide coroutine-based asynchronous I/O multiplexing in Python:

  * [Concurrence](http://opensource.hyves.org/concurrence/)
  * [eventlet](http://eventlet.net/) using ([link to old, wrong greenlet](http://undefined.org/python/#greenlet)) [greenlet](http://codespeak.net/py/0.9.2/greenlet.html)
  * [gevent](http://www.gevent.org/) using [greenlet](http://codespeak.net/py/0.9.2/greenlet.html)

Less similar software are:

  * event-based in Python: [Tornado](http://www.tornadoweb.org/), [Twisted](http://twistedmatrix.com/)
  * event-based in JavaScript: [node.js](http://nodejs.org/)

See a benchmark at http://nichol.as/asynchronous-servers-in-python

### Using Syncless with web frameworks ###

The WSGI-capable HTTP server in Syncless can run any framework with WSGI support (and some others as well). Examples:

  * pure WSGI application, without a framework: see `WsgiApp` in [demo.py](http://code.google.com/p/syncless/source/browse/trunk/examples/demo.py) and [demo\_wsgiapp.py](http://code.google.com/p/syncless/source/browse/trunk/examples/demo_wsgiapp.py)
  * (web.py): see [demo\_syncless\_web\_py.py](http://code.google.com/p/syncless/source/browse/trunk/examples/demo_syncless_web_py.py)
  * Google AppEngine webapp: see [demo\_syncless\_webapp.py](http://code.google.com/p/syncless/source/browse/trunk/examples/demo_syncless_webapp.py)
  * Python built-in BaseHTTPRequestHandler: see [demo\_syncless\_basehttp.py](http://code.google.com/p/syncless/source/browse/trunk/examples/demo_syncless_basehttp.py)

Please note that Syncless is not a web framework, but it can work with many frameworks.