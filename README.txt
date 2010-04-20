README for Syncless: asynchronous client and server library using
Stackless Python
""""""""""""""""
by pts@fazekas.hu at Sun Dec 20 22:47:13 CET 2009
-- Fri Jan  8 03:06:58 CET 2010
-- Tue Feb  9 19:02:52 CET 2010
-- Mon Apr 19 02:54:24 CEST 2010

Syncless is an experimental, lightweight, non-blocking (asynchronous) client
and server socket network communication library for Stackless Python 2.6.
For high speed, Syncless uses libevent, and parts of Syncless' code is
implemented in C (Pyrex). Thus Syncless can be faster than many other
non-blocking Python communication libraries. Syncless contains an
asynchronous DNS resolver (using evdns) and a HTTP server capable of serving
WSGI applications. Syncless aims to be a coroutine-based alternative of
event-driven networking engines (such as Twisted and FriendFeed's Tornado),
and it's a competitor of gevent, pyevent, python-libevent, Eventlet and
Concurrence.

Features
~~~~~~~~
* handling multiple TCP connections concurrently in a single Python process,
  using cooperative multitasking provided by Stackless Python (without
  the need for callbacks, threads, subprocesses or locking)
* non-intruisive I/O multiplexing, easy to integrate with existing code
  because locking is not needed and it's monkey-patchable
* monkey-patchable, almost faithful non-blocking reimplementation of
  socket.socket, socket.gethostbyname (etc.), ssl.SSLSocket, time.sleep
  and select.select
* non-blocking support added by monkey-patching to built-in urllib, urllib2,
  smtplib, ftplib, imaplib, poplib etc. modules
* special monkey-patching for pure Python MySQL client libraries
  mysql.connector and pymysql
* special monkey-patching for the Tornado web server (slow)
* compatible timeout handling on individual socket operations
* I/O event detection using libevent, which can use Linux epoll(7) or BSD
  kqueue (if available)
* built-in (non-blocking) WSGI server, but can use CherryPy's WSGI server as
  well in non-blocking mode
* non-blocking DNS resolver using evdns
* non-blocking stdin/stdout support (can be useful for implementing an
  interactive server console)
* built-in WSGI server capable of running not only WSGI applications, but
  BaseHTTPRequestHandler + BaseHTTPServer applications, CherryPy
  applications, web.py applications, and Google webapp applications (not
  supporting most other Google AppEngine technologies) as well

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
* python-libevent (uses callbacks instead of coroutines)
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

External code used
~~~~~~~~~~~~~~~~~~
Code used for syncless.coio
"""""""""""""""""""""""""""
Copied files from the BSD-licensed pyevent (libevent Python bindings),
revision 60 from
svn checkout http://pyevent.googlecode.com/svn/trunk/ pyevent-read-only
* Makefile
* evdns.pxi
* event.pyx
* setup.py
* test.py

Code used for the Twisted reactor
"""""""""""""""""""""""""""""""""
libevent.reactor v0.3 (2008-11-22), available from
http://launchpad.net/python-libevent (simple BSD license).


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

5. Don't use non-blocking I/O on the same filehandle from multiple
   coroutines (tasklets): there may be race conditions.

FAQ
~~~
Q1. I have created quite a few tasklets, put them into the runnables list.
    How do I make my program run until there are no tasklets? Currently my
    the process exists as soon as the main tasklet returns.

A1. Call `stackless.schedule_remove()' at the end of your main tasklet code.

    This would make your program run while there are tasklets on the
    runnables list, or some tasklets are blocked on Syncless I/O.

    Unfortunately this doesn't work (your program will run forever) if it
    has done any DNS lookups (like with coio.gethostbyname), because evdns
    registers and keeps additional event handlers.

Q2. What is the `.scheduled' value for tasklets blocked on Syncless I/O?

A2. The value is False, since they are not on the runnables list, and they
    are not waiting in a channel.

    After I/O is available, and the Syncless event wakeup tasklet gets
    scheduled, the wakeup tasklet puts back the blocked tasklet to the
    runnables list, so blocked_tasklet.scheduled becomes True.

Q3. Is it possible to cancel (interrupt) a coio.sleep()?

A3. Yes. If you have a reference to the sleeping tasklet, just send an
    exception to it in a stackless.bomb, and then insert the tasklet back to
    the runnables list, and the sleep will be interrupted.

    For example, the following program finishes immediately (not needing 5
    seconds).

      import stackless
      from syncless import coio
      sleep_done_channel = stackless.channel()
      def Sleeper():
        try:
          coio.sleep(5)
        except AssertionError:
          sleep_done_channel.send(None)
      tasklet_obj = stackless.tasklet(Sleeper)()
      stackless.schedule()  # Start Sleeper and start sleeping.
      # ...
      tasklet_obj.tempval = stackless.bomb(AssertionError)
      tasklet_obj.insert()  # Interrupt the sleep.
      sleep_done_channel.receive()

    Please note that interrupting can be dangerous if you are not excatly
    sure that the other tasklet is doing a blocking Syncless I/O operation
    (such as coio.sleep). Please use synchronization mechanisms (such as
    channels) to make sure that a sleep is going on in the tasklet.

    Even simpler: it is possible to interrupt a sleep just without sending a
    bomb. Example (doesn't need 5 seconds):

      import stackless
      from syncless import coio
      sleep_done_channel = stackless.channel()
      def Sleeper():
        coio.sleep(5)
      tasklet_obj = stackless.tasklet(Sleeper)()
      stackless.schedule()  # Start Sleeper and start sleeping.
      # ...
      tasklet_obj.insert()  # Interrupt the sleep.
      sleep_done_channel.receive()

Q4. Is it possible to cancel (interrupt) a blocking Syncless I/O operation?

A4. Yes, by sending an exception wrapped to a stackless.bomb to the tasklet,
    and reinserting it to the runnables list. See A3 for more details.
    (Please note that coio.sleep is one of the blocking Syncless I/O
    operations.)

Q5. Is it possible to insert a tasklet which is blocked on a Syncless I/O
    operation back to the runnables list?

A5. Yes, you can use tasklet_obj.insert(), tasklet_obj.run() (or any other
    means to insert the tasklet to the runnables list). But you are not
    allowed to change the tempval (None by default) of a tasklet blocked on
    a Syncless I/O operation. If you do so, event_del() won't be called, and
    you'll get spurious events later (with exceptions caused by spurious
    tasklet_obj.insert()).

    Please note, however, that for non-sleep I/O operations the tasklet
    would retry the I/O operation (with the timeout period restarted), so it
    will most probably become blocked again (and thus removed from the
    runnables list). To prevent that, send an exception wrapped to a
    stackless.bomb to the tasklet by setting its tempval before reinserting
    it to the runnables list. See A3 and examples/demo_multi_read_timeout.py
    for more examples.

Q6. How do I receive on a channel with a timeout?

    Call coio.receive_with_timeout.
    
    But please consider that cleaning up after a timeout is cumbersome. How
    do you tell the other tasklets to stop generating data on the channel?
    You'd better create dedicated tasklets for tasks you want to time out.

Q7. Can I use my existing DNS, TCP, HTTP, HTTPS, FTP, urllib, urllib2, MySQL,
    memcached, Redis, Tokyo Tyrant etc. client with Syncless?

A7. If your client software is written in pure Python, and it uses the
    standard Python `socket' module to connect to the server, then you only
    have to call

      from syncless import patch
      patch.patch_socket()
      patch.patch_ssl()  # Only if SSL (e.g. HTTPS) support is needed.

    somewhere in your script initialization. This makes all DNS queries,
    TCP-based and other socket-based clients non-blocking.

    If your client software is non-pure Python (such as a Python extension
    written in C, Pyrex or Cython), then non-blocking functionality will
    most probably not work. Porting such client software is possible, but
    it's usually cumbersome and needs lots of work. However, if the client
    is written in Pyrex or Cython, you get non-blocking functionality by
    calling patch.patch_socket() as early as possible.

Q8. How do I connect to a MySQL database with Syncless?

    Use ``MySQL Connector/Python'' (https://launchpad.net/myconnpy), which
    is dbapi2-compatible pure Python MySQL client implementation, and call
    patch.patch_socket() or patch.patch_mysql_connector(). See
    examples/demo_mysql_client.py for an example. Please note that myconnpy
    might be slower than other clients, because it's implemented in pure
    Python -- but non-blocking functionality is much harder to patch into
    other clients.

    If you want to use pymysql instead, then see
    examples/demo_mysql_client_pymysql.py .

    See also Q7.

    A more detailed analysis:

    * ``MySQL Connector/Python'' (myconnpy) is a pure Python MySQL client, and
      it works with patch.patch_socket() and patch.patch_mysql_connector(). The
      disadvantage is that it's slower than C extensions (which don't work).
      https://launchpad.net/myconnpy
    * libmysqlclient is inherently blocking, so it wouldn't work
      http://mysql-python.blogspot.com/
    * oursql uses libmysqlclient
    * Concurrence has a non-blocking MySQL client implemented in Pyrex/Cython,
      but it's quite hard to abstract away the networking part to make it work
      with Syncless.
    * The client ``MySQL for Python''
      (http://sourceforge.net/projects/mysql-python/files/) is implemented
      as a C extension using the official C client (libmysqlclient), so it's
      inherently blocking.
    * There is also the pure Python client ``pymysql''
      (http://code.google.com/p/pymysql/), but it seems to be less
      maintained than myconnpy. It also seems a bit immature and not used in
      production because of trivial escaping bugs and a nonfunctional
      encoding (UTF-8) support. pymysql seems to be a bit faster (with less
      overhead) than myconnpy.

Q9. How do I make my SSL connections (client and server) non-blocking?

A9. Use the coio.nbsslsocket class as a drop-in non-blocking replacement for
    ssl.SSLSocket. If you don't want to modify your source code, call this
    somewhere the beginning in your script:
    
      from syncless import patch
      patch.patch_socket()  # DNS lookups and socket.socket() non-blocking.
      patch.patch_ssl()     # Make ssl.SSLSocket non-blocking.

    This makes both the connecting handshake operation and the data
    transfers (reads and writes) non-blocking.

    Patching affects only Python code using the standard `ssl' Python
    module. Patching doesn't affect the non-standard `openssl' Python module
    or C extensions using libssl directly. Maybe in the future Syncless will
    have a patch.patch_openssl(), but C extensions will never be patched, so
    please make sure that you create all your SSL sockets in Python code.

Q10. Does SQLite3 work with Syncless?

A10. The standard `import sqlite3' works (just like any Python module with C
     extensions), but it blocks: so if a tasklet is busy running a long
     SQLite3 query, no other tasklets get scheduled at that time. This is
     unacceptable in most latency-sensitive situations.

     While it is possible to read (SELECT) from an SQLite3 database in
     parallel from multiple processes or threads (by connecting to it once
     per thread), this kind of parallelism is impossible to implement with
     coroutines (thus with Syncless).

     It is also impossible to make the database file read or write locking
     fcntl operation non-blocking, e.g. if tasklet A is holding a write lock
     (for a long-running transaction with thousands of INSERT), and tasklet
     B wants to acquire a read lock (for a SELECT), then it's impossible to
     schedule tasklet C (which doesn't need access to the SQLite3 database)
     while tasklet B is waiting for its lock. Threads or processing would be
     needed for this kind of parallelism.

     If you really must use SQLite3, then you may consider setting up an
     sqlite3.connection.set_progress_handler and call stackless.schedule()
     from there to improve the latency. But this can be become very tricky,
     because according to http://www.sqlite.org/c3ref/progress_handler.html
     you have to ensure that you don't use the database connection while a
     progress handler is running. See
     examples/demo_sqlite_progress_handler.py for some experiments.

     For real concurrency, you should create one thread per SQLite3
     connection, and communicate with those threads and the tasklets in your
     main thread. This is complicated, tiresome and tricky to implement.

Q11. Is it possible to scheduler background work with Syncless for GTK,
     TCL/Tk or Qt applications?

A11. Not at the moment, since the main event loop of these GUI frameworks doesn't
     support coroutines. It would be an interesting and complicated project
     to make Syncless support these main event loops instead of libevent.

Q12. Is it possible to use stacklessocket, asyncore, pyevent,
     python-libevent, Tornado, Twisted or another event-driven communication
     library with Syncless?

A12. Tornado (with its own main loop) is already supported with
     patch.patch_tornado(). See also examples/demo_tornado.py . Please note
     that the speed would be slower than native Tornado because of the
     select(2) emulation with coio.select.

     Twisted (with a Syncless-specific reactor as its main loop) is already
     supported. See examples/demo_twisted.py .

     Adding support for Twisted would be possible, fun and interesting.
     Adding asyncore would be possible and fun.

     Adding pyevent or python-libevent may become complicated because of the
     multiple libevent-based I/O loops. (Most importantly: the Syncless main
     loop adds EVLOOP_NONBLOCK if more tasklets are in the runnables list
     (stackless.runcount > 1). Thus EVLOOP_NONBLOCK would always be
     specified with multiple main loops, which would result in busy waiting.

     Adding stacklessocket wouldn't give us too much benefit, because
     stacklessocket is not for production use.

Q13. Is it possible to use gevent, Eventlet, Concurrence or another
     coroutine-based event communication framwork with Syncless?

A13. No, but it might be fun to add support for one of them. gevent,
     Eventlet and Concurrence use libevent, so techincally it wouldn't be
     too much work to unify the event loops. For Eventlet and gevent, one
     would have to emulate greenlet using Stackless Python. There is emulation
     code in the Syncless codebase, but it's 20% or even more slower than
     greenlet.

Q14. Is it possible to use select(2) (select.select) with Syncless?

A14. Yes, either as coio.select, or as select.select after
     patch.patch_select():

       from coio import patch
       patch.patch_select()
       ...
       import select
       print select.select(...)

     Limitation: Exceptional filehandles (non-empty xlist) are not
     supported.

     Please note that select(2) is inherently slow compared to libevent or the
     combination of Syncless and tasklets. That's because libevent uses
     faster polling mechanisms such as Linux epoll or BSD kqueue. If your
     speed-critical program uses select(2), please consider redesigning it
     so it would use Sycnless non-blocking communication classes and tasklets.

Planned features
~~~~~~~~~~~~~~~~
* TODO(pts): Report libevent bug that evdns events are not EVLIST_INTERNAL.
* TODO(pts): mksleep(secs) and cancel_sleep()
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
* TODO(pts): Strip the coio.so files upon installation? It seems to be still
             importable. Some Python installations autostrip. Why not ours?
* TODO(pts): Fix the AttributeError in socket.socket.close().
* TODO(pts): channel.send_exception() with a traceback. (Wait for receiver?)
* !! TODO(pts): Handle starving (when one worker is very fast, even Ctrl-<C>
  is delayed)

__EOF__
