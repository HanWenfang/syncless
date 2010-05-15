README for Syncless: asynchronous client and server library using
Stackless Python
""""""""""""""""
by pts@fazekas.hu at Sun Dec 20 22:47:13 CET 2009
-- Fri Jan  8 03:06:58 CET 2010
-- Tue Feb  9 19:02:52 CET 2010
-- Mon Apr 19 02:54:24 CEST 2010

Syncless is a non-blocking (asynchronous) concurrent client and server
socket network communication library for Stackless Python 2.6 (and also for
regular Python with greenlet). For high speed, Syncless uses libev (and
libevent) for event notification, and parts of Syncless' code is implemented
in Pyrex/Cython and C. This alone makes Syncless faster than many of its
non-blocking network libraries for Python. Syncless contains an asynchronous
DNS resolver (using evdns) and a HTTP server capable of serving WSGI
applications. Syncless aims to be a coroutine-based alternative of
event-driven networking engines (such as Twisted, asyncore, pyevent,
python-libevent and FriendFeed's Tornado), and it's a competitor of gevent,
Eventlet and Concurrence.

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
  smtplib, ftplib, imaplib, poplib, asyncore, popen2, subprocess etc. modules
* special monkey-patching for pure Python MySQL client libraries
  mysql.connector and pymysql
* compatible timeout handling on individual socket operations
* I/O event detection using libev, which can use Linux epoll(7) or BSD
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
* combination of Syncless and (Twisted, Tornado (fast), Concurrence, gevent
  and/or asyncore) in the same process

Requirements
~~~~~~~~~~~~
* A recent Unix system. Tested on Linux 2.6, should work on FreeBSD. Testers
  for other Unix variants are welcome. It won't work on Win32 or Win64.
* Stackless Python 2.6.x (recommended, especially for production use) or
  normal (C)Python 2.5 or 2.6 with greenlet (slow, may leak memory,
  not recommended in general, but it's easy to install and try).
* Python 2.6 (recommended, for epoll(7) support) or Python 2.5.
* A C compiler (gcc) and the Python development package (.h files) for
  compilation.
* Various development packages such as python2.5-dev and libssl-dev already
  installed.

Installation (the fast and easy way)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
You need a Unix system with Python 2.5 or 2.6. Stackless Python is
recommended, but not necessary.

To install syncless, run this as root (without the # sign):

  # easy_install syncless

Be patient, compilation may take up to 60 seconds.

As an alterative, if you have already downloaded and extracted Syncless, you
can install it with:

  # python setup.py install

To verify that Syncless got properly installed, run this command (without
the leading $):

  $ python -c 'from syncless.coio import sleep; sleep(1e-5); print "OK"'
  OK

You can also try if your Syncless works using the interactive console. See
http://code.google.com/p/syncless/wiki/Console for details . Example
invocation:

  $ python -m syncless.console

If you want to install syncless to a specific Pyton version on your system,
run the following instead (without python substituted properly):

  # python -c'from setuptools.command.easy_install import main;main()' syncless

If you don't have the easy_install command installed, do this:

  $ wget http://peak.telecommunity.com/dist/ez_setup.py
  $ python ez_setup.py syncless

If installation fails, or you want to reinstall syncless to get the highest
performance, please follow the next Installation section.

Installation (the hard way)
~~~~~~~~~~~~~~~~~~~~~~~~~~~
For a Python with coroutine support, you have these options (pick one):

* Python 2.6 with greenlet  (easy to install, slow, may leak memory, not
  recommended in general, but recommended if you want to try Syncless
  quickly without bothering to install Stackless Python)
* Python 2.5 with greenlet  (like Python2.6, but without SSL support)
* Stackless Python >= 2.6.4  (recommended for production use)

For an asynchronous event notification library with DNS support, you have
these options (pick one):

* minievent  (very simple to install, bundled with Syncless, ideal for
  trying and learning Syncless, but has poor performance with >10 TCP
  connections)
* libev >= 3.9 + minihdns  (recommended, fastest, minihdns bundled with
  Syncless)
* libev >= 3.9 + evhdns (like with minihdns, but more work to install)
* libevent2 >= 2.0.4  (recommended if you don't like libev)
* libevent1 >= 1.4.13  (not recommended, because it can register only a single
  event on the same filehandle with the same purpose at a time)

Remember your picks above.

0. Install a C compiler (e.g. $ apt-get install gcc).

1. If you have picked Python 2.5 or Python 2.6 (non-Stackless), install it
   either from source or from binary package. When installing from binary
   package, please install the headers as well. For example, on Debian and
   Ubuntu, run one of:

     $ sudo apt-get install python2.5 python2.5-dev
     $ sudo apt-get install python2.6 python2.6-dev
   
2. If you have picked Stackless, most probably you have to download it and
   install it from source. Download and install Stackless Python 2.6.x (not
   3.x) from http://stackless.com/

   For convenience, rename the installed executable or make a symlink to
   /usr/local/bin/stackless2.6:

     $ sudo ln -s python2.6 stackless2.6

3. If you have picked greenlet, download and install it from source.
   Syncless needs a recent version of greenlet (>= 0.3.1, >= 2010-04-06).
   Older versions lack the `throw' method. Get it from
   http://pypi.python.org/pypi/greenlet  (pip and easy_install also work).

   You can also check it out from the SVN repository with:

     $ svn co http://codespeak.net/svn/py/release/0.9.x/py/c-extension/greenlet

   Please note that http://www.undefined.org/python/#greenlet contains an old
   version (without greenlet.greenlet.throw).

   Install it as usual:

     $ $PYTHON setup.py build
     $ sudo $PYTHON setup.py install

   , where $PYTHON is your choice of Python above: stackless2.6, python2.5,
   python2.6.

4. If you have picked libev, download and install libev from
   http://software.schmorp.de/pkg/libev.html

   Syncless has been tested on Linux with libev-3.9. The version shipped
   with your Linux distribution will probably also be OK if it's new enough.

5. If you have picked libev, you also have to install libevhdns. Download
   the libevhdns sources from http://code.google.com/p/libevhdns/ , and
   install them. The minimum version required is 1.4.13.4.

   Most probably your Linux distribution doesn't have libevhdns, so you should
   install libevhdns from source.

6. If you have picked libevent1, download the libevent1 sources from
   http://www.monkey.org/~provos/libevent/ , and install them. The minimum
   version required is 1.4.13. Make sure you don't download version 2.x.

   Most probably your Linux distribution has a libevent1, but it's too old
   (like 1.3). If it's at least 1.4, you can try that one instead of
   installing from source. You don't have to install the development
   package, Syncless works without it.

7. If you have picked libevent2, download the libevent2 sources from
   http://www.monkey.org/~provos/libevent/ , and install them. The minimum
   version required is 2.0.4. Make sure you don't download version 1.x.

   Most probably your Linux distribution doesn't have libevent2, so you should
   install libevent2 from source.

8. Download the newest version of Syncless. Get the .tar.gz file from here:
   http://pypi.python.org/pypi/syncless  or from here:
   http://code.google.com/p/syncless/ . Extract the .tar.gz file and cd into
   the directory.

   Alteratively, you may check out the trunk from the SVN repository:

     svn checkout http://syncless.googlecode.com/svn/trunk/ syncless-read-only

9. Compile Syncless. Make sure you are in the directory
   containing setup.py and syncless/patch.py . Then run

     $ $PYTHON setup.py build

   , where $PYTHON is your choice of Python above: stackless2.6, python2.5,
   python2.6.

   You may want to make sure that Syncless has picked up its right
   dependencies. The `setup.py build' commands displays dependency and
   configuration information before compilation, and it also saves that to
   the setup.cenv file:

   * COIO_USE_CO_STACKLESS: Stackless Python is used for coroutines.
   * COIO_USE_CO_GREENLET: greenlet is used for coroutines.
   * COIO_USE_LIBEVHDNS: libevhdns is used for DNS resolution.
   * COIO_USE_MINIHDNS: minihdns is used for DNS resolution.
   * COIO_USE_MINIEVENT: libev is used for notification.
   * COIO_USE_LIBEV: libev is used for notification.
   * COIO_USE_LIBEVENT1: libevent1 is used for DNS resolution and notification.
   * COIO_USE_LIBEVENT2: libevent2 is used for DNS resolution and notification.

   Before running `setup.py build', you can set one or more of the following
   environment variables to force Syncless use a specific dependency instead
   of autodetection:

   * export SYNCLESS_USE_LIBEV=1
   * export SYNCLESS_USE_LIBEVENT1=1
   * export SYNCLESS_USE_LIBEVENT2=1
   * export SYNCLESS_USE_MINIEVENT=1
   * export SYNCLESS_USE_LIBEVHDNS=1
   * export SYNCLESS_ALLOW_MINIEVENT=1 (is 1 by default, set to '' to disable)


    Please note that you don't have to run the `install' step to experiment
    with syncless: after the `build' step, you can run the demos in the
    `examples' directory, and you can also run the tests in the `test'
    directory.

How to use (with example code)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Follow the steps in `Installation'.

2. In the Syncless directory, run

     $ stackless2.6 ./examples/demo.py

3. Have a look at examples/demo_*.py in the source directory to study the
   examples.

Author
~~~~~~
with accents in UTF-8: Péter Szabó <pts@fazekas.hu>
without accents: Peter Szabo <pts@fazekas.hu>

License
~~~~~~~
Syncless is licensed under the GNU GPL v2.

If you need other licensing options, please contact the author.

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
FYI This has already been implemented.

My conclusion was that in order to get the fastest coroutine-based,
non-blocking, line-buffering-capable I/O library for Python, I should wrap
something like libevent (including event registration and I/O buffering) and Stackless and
the WSGI server in hand-optimized Pyrex, manually checking the .c file Pyrex
generates for inefficiencies.

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

5. Socket timeouts are not enforced on file objects created by
   nbsocket.makefile().

FAQ
~~~
Q1. I have created quite a few tasklets, put them into the runnables list.
    How do I make my program run until there are no tasklets? Currently my
    the process exists as soon as the main tasklet returns.

A1. It's impossible to do that since Syncless has migrated from libevent to
    libev. The rest of the answer documents the old, now obsolete behavior.

    OBSOLETE. Call `stackless.schedule_remove()' at the end of your main tasklet code.

    OBSOLETE. This would make your program run while there are tasklets on
    the runnables list, or some tasklets are blocked on Syncless I/O.

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

A3. Yes. If you have a reference to the sleeping tasklet, just insert the
    tasklet back to the runnables list (or send an exception to it in a
    stackless.bomb, and then insert it back), and the sleep will be
    interrupted.

    For example, the following program finishes immediately (not needing 5
    seconds).

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

    Same example with a bomb (not recommended):

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
     python-libevent, Tornado, Twisted or another event-driven network
     library with Syncless?

A12. Tornado (with its own main loop) is already supported with
     patch.patch_tornado(). See also examples/demo_tornado.py . Please note
     that the speed would be slower than native Tornado because of the
     select(2) emulation with coio.select.

     asyncore (with its own main loop) is already supported with
     patch.patch_asyncore(). See also examples/demo_asyncore.py . But, if
     possible, please don't use asyncore in production (but write your
     application using a modern framework like Syncless, Tornado, Twisted or
     Concurrence), because asyncore lacks core functionality like proper
     timed event handling, some developers don't like its error handling
     design, and it's slow.

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

A13. Concurrence works with patch.patch_concurrence(). See also
     examples/demo_concurrence.py . The speed should be the same as with
     regular Concurrence, there is no Syncless-specific overhead. Please
     note that native Syncless is faster than native Concurrence, because
     Syncless provides sockets and buffered files as a C (Pyrex) extension.

     Eventlet works with patch.patch_eventlet(). See also
     examples/demo_eventlet.py . The speed should be the same as with
     regular Eventlet (with any of its faster hubs like
     eventlet.hubs.pyevent and eventlet.hubs.epoll), there is no
     Syncless-specific overhead. Please note that native Syncless is faster
     than native Eventlet, not only because Syncless provides sockets and
     buffered files as a C (Pyrex) extension, but also because the overhead
     of waiting for I/O is much smaller in Syncless. Please expect low
     performance if you are using Stackless Python, because Eventlet uses
     greenlet, so it has to be emulated with the syncless.best_greenlet
     emulatior, which is slow.

     gevent works with patch.patch_gevent() with some limitations, see the
     docstring of patch_gevent() for more details. See also
     examples/demo_gevent.py . Please expect low performance, because gevent
     uses greenlet, so either greenlet or Stackless has to be emulated (with
     syncless.best_greenlet or syncless.best_syncless) so that Syncless and
     gevent can work in the same process. The emulation is at least 20%
     slower, but it can be much slower. (Speed measurements needed.)

     Please note that Syncless, gevent, Eventlet and Concurrence use
     libevent (with Syncless being able to use libev and minievent, and
     Eventlet being able to support many other methods, including
     pure-Python implementations in eventlet.hubs.*), so techincally it's
     possible to unify the event loops. This has been done with Syncless +
     gevent (where the Syncless main loop processes both Syncless and gevent
     notifications). For Concurrence and Eventlet this was not needed,
     because the event notification abstractions of Concurrence and Eventlet
     were so clean that they could be efficiently emulated by Syncless (no
     matter libev or libevent).

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

Q15. Is it OK to close() an nbfile or an nbsocket while other tasklets are
     reading from it?

A15. No. You must ensure that there are no other tasklets using the filehandle
     in any way by the time you close(). Otherwise you may get a
     segmentation fault.

     (Please note that in some systems and some libevent drivers it might be
     safe -- try it for yourself.)

Q16. Can multiple tasklets wait on the same file descriptor at the same time?
     Will all of them get notified?

A16. Yes and yes, this is fully supported by libev-3.9, see the
     testTwoReaders method in test/nbfile_test.py.

     Before syncless-0.06 this was not possible, because libevent-1.4.13
     doesn't support this. If you attempted it with libevent, only the last
     tasklet would get notified and the others would be discarded (never
     woken up).

Q17. Can I start subprocesses and communicate with them in a non-blocking
     way with Syncless?

A17. Yes, by monkey-patching any of these methds: subprocess, popen2,
     os.popen. There is no support yet for more sophisticated mechanisms
     (such as the multiprocessing module).

     There is an important limitation so far: waiting for a subprocess to exit
     (e.g. with os.wait and os.waitpid without WNOHANG) is a blocking
     operation: all tasklets in the process would get blocked.

     Code examples:

       # See longer example in examples/demo_subprocess.py.
       import subprocess
       from syncless import patch
       patch.patch_subprocess()  # or, worse, patch.patch_os()
       ...
       subprocess.popen3(...)  # or any other method

       # See longer example in examples/demo_popen2.py .
       import popen2
       from syncless import patch
       patch.patch_popen2()  # or patch.patch_os()
       ...
       popen2.popen2(...)  # or any other method

       # See longer example in examples/demo_popen.py .
       import os
       from syncless import patch
       patch.patch_os()  # or os.popen = coio.popen
       ...
       os.popen(...)  # or any other method

Q18. Can I link Syncless aganst libevent instead of libev?

A18. Please try Syncless with libevent2 (libevent-2.0.4 or later) by
     compiling it with

       $ SYNCLESS_USE_LIBEVENT2=true stackless2.6 ./setup.py build
       $ sudo stackless2.6 ./setup.py install

     Also the primary focus is to make Syncless work with libev, it should
     also work with libevent2. Please report any libevent2 issues to the
     author of Syncless.

     Currently Syncless works only partially with libevent1 (i.e.
     libevent-1.4 and earlier), because libevent1 has the inherent limitation
     that it silently starts behaving unpredictably and unreliably if
     multiple events are registered on the same filehandle. You can try
     nevertheless:

       $ SYNCLESS_USE_LIBEVENT1=true stackless2.6 ./setup.py build
       $ sudo stackless2.6 ./setup.py install

Q19. Is Syncless faster than Concurrence, gevent, Eventlet, asyncore,
     pyevent and python-libevent?

A19. It was designed to be faster, and it should be faster. But benchmarks
     haven't been run recently, the files in the benchmark directory are
     obsolete (i.e. they have been run in a faster but buggy old version of
     Syncless).

     The only exception from the rule that Syncless is the fastest may be
     Concurrence, because Syncless uses hard switching (i.e. C stack
     copying) of tasklets, which is a bit slower than the soft switching
     used by Concurrence.

Q20. Should I use stackless.schedule() or stackless.schedule(None)?

     If you are not interested in stackless.current.tempval, then use
     stackless.schedule(None) (and stackless.schedule_remove(None)) rather
     than without None, to save memory.

     That's because stackless.schedule() is equivalent to
     stackless.schedule(stackless.current), which sets
     stackless.current.tempval = stackless.current, creating a circular
     reference, which can lead to memory leaks if garbage collection is
     disabled. Example (this raises MemoryError, reaching 200 MB):

       import gc
       import resource
       import stackless
       gc.disable()
       resource.setrlimit(resource.RLIMIT_AS, (200 << 20, 200 << 20))  # 200 MB
       while True:
         t = stackless.tasklet(stackless.schedule)()
         assert t.alive
         stackless.schedule()
         assert t.alive
         assert t is t.tempval  # Circular reference: t --> t.tempval --> t
         t.remove()

Q21. Can I register my signal handlers?

A21. Yes, use coio.signal. Example:

       import signal
       from syncless import coio
       def MyHandler(signum): print 'signal %d received' % signum
       h = coio.signal(signal.SIGINT, MyHandler)
       coio.signal(signal.SIGHUP, MyHandler)
       ...
       coio.signal(signal.SIGHUP, None)   # Delete it.
       h.delete()   # Delete SIGINT.

     All signal handlers are persistent.

     Uncaught exceptions raised in signal handlers are reported (without a
     traceback), and then they get ignored.

Q22. Does Syncles provide a way to parse the bytes read from a socket?

A22. You should call nbsocket.makefile('r') to create nbfile, which has a
     read buffer. The basic idea for parsing is that nbfile.read_upto and
     nbfile.read_more can be used to read more bytes from the file
     descriptor to the read buffer, the methods nbfile.get_string,
     nbfile.get_read_buffer, nbfile.find and nbfile.rfind can be used to
     find out if enough data is available, and whether it is parseable, and
     finally nbfile.discard can be used the remove the parsed message from
     the beginning of the read buffer. nbfile.read_buffer_len contains the
     current byte size of the read buffer.

     You can also parse with regular expressions, e.g.
     re.search(r'...', nbfile_obj.get_read_buffer()), but you should make
     your regexp aware that the read buffer may contain only a prefix of the
     full message you want to parse. In that case, you should call
     nbfile.read_more to read more bytes, and then retry the re.search.

Q23. Does Syncless work on Microsoft Windows?

A23. As of now, Windows support is not implemented. Since that would be
     a considerably large piece of work, and it has low priority for the
     Syncless developers, Windows support probably never be implemented.

     Currently you need a recent Unix system to run Syncless. It should work
     on Linux, FreeBSD, NetBSD, OpenBSD, Mac OS X and Solaris. If you have a
     desktop or server Unix system on which Syncless doesn't compile or work
     properly, please let us know, so we can fix it.

Q24. What are the dependencies of Syncless?

A24. To run Syncless, you need a recent Unix system with Python 2.5 or 2.6.
     You also need Stackless Python or the greenlet (>= 0.3.1) Python package.
     Syncless is distributed in source form, so you should compile
     it before you can run it. To compile Syncless, you need the Python headers
     (the python-dev package) and GCC on your system.

     There are many optional dependencies, including libevent1, libevent2,
     libev and libevhdns. Syncless detects them at compilation time. Without
     these, Syncless is fully functional, but it's less efficient,
     especially at higher loads (>10 concurrent TCP connections). See the
     Installation section in the README for more details.

Q25. Does Syncless have an interactive Python console?

A25. Yes, it's in the syncless.console module. You can start it using:

       $ python -m syncless.console

     Run the ``help'' command to find out some examples.

     See http://code.google.com/p/syncless/wiki/Console for more details.

     syncless.console is like the regular interactive Python interpreter
     except that it has some useful global variables preloaded (such as
     help, syncless and ticker), and it supports running coroutines
     (tasklets) in the background while the user can issue Python commands.
     It's an easy-to-use environment to learn Syncless and to experiment with
     tasklets.

     The interactive console displays a prompt. At this point all tasklets
     are running and scheduled until you press the first key to type an
     interactive command. While you are typing the command (after the 1st
     key), other tasklets are suspended. They remain suspended until you
     press <Enter> (to finish the command or to start a multiline command).

     Please note that if an uncaught exception is raised in tasklet, the
     whole process exits. You can prevent that in interactive sessions by
     creating your tasklets with `wrap_tasklet(Function)' instead of
     `stackless.tasklet(Function)'. If you do so, the exception will be
     printed, but the interactive console resumes afterwards.

Q26. Can I use other non-blocking network libraries in the same process
     which runs Syncless?

A26. Syncless supports the following libraries out-of-the-box with monkey
     patching: gevent, Eventlet, Concurrence, Twisted, Tornado and asyncore.
     See Q12 and Q13 for more details how to enable them. Please note that
     there is no direct synchronization support between Syncless and the
     other library, i.e. there is no way for a tasklet managed by a library
     to notify a tasklet managed by another library that computation results
     are available.

     If you want to run a web framework supporting WSGI, run its WSGI
     application function/class directly with syncless.wsgi instead.

     If your pure Python network library uses select.select() for event
     notification, then see Q14.

     Otherwise, the library most probably won't work with Syncless in the
     same process. Most probably either Syncless I/O will make progress, and
     the other library's I/O will be stalled, or the other way round.

Links
~~~~~
* doc: related: eventlet vs gevent:
  http://blog.gevent.org/2010/02/27/why-gevent/
* doc: http://www.disinterest.org/resource/stackless/2.6.4-docs-html/library/stackless/channels.html
* doc: http://wiki.netbsd.se/kqueue_tutorial
* doc: http://stackoverflow.com/questions/554805/stackless-python-network-performance-degrading-over-time
* doc: speed benchmark: http://muharem.wordpress.com/2007/07/31/erlang-vs-stackless-python-a-first-benchmark/
* doc: gevent and gtk: http://groups.google.com/group/gevent/browse_thread/thread/36f8dd594b5e2c06

Asynchronous DNS for Python:

* twisted.names.client from http://twistedmatrix.com
* dnspython: http://glyphy.com/asynchronous-dns-queries-python-2008-02-09
             http://www.dnspython.org/
* adns-python: http://code.google.com/p/adns/python
*              http://michael.susens-schurter.com/blog/2007/09/18/a-lesson-on-python-dns-and-threads/comment-page-1/

Info: In interactive stackless, repeated invocations of stackless.current may
  return different objects.
Info: LIBEV_FLAGS=1 use select(); LIBEV_FLAGS=2 use poll()
Info: gevent.backdoor doesn't support line editing with libreadline
      python2.5 -m gevent.backdoor 1234

Release procedure
~~~~~~~~~~~~~~~~~
This section describes how to create a new source distribution release of
Syncless. The intended audience is Syncless developers.

1. Run

     $ make -C coio_src coio.c

2. Make sure it works in your SVN local directory (e.g. run the tests).

3. Bump the version number in syncless/version.py .

4. Commit your changes, e.g.

     $ svn ci -m 'bumped version number, creating release X.YZ'

5. Run

     $ stackless2.6 setup.py sdist upload register

Planned features
~~~~~~~~~~~~~~~~
* TODO(pts): Wrap / monkey-patch the multiprocessing module (and its C code in
  _multiprocessing). The _multiprocessing module implemented in C doesn't
  seem to support non-blocking operation.
* TODO(pts): Report libevent bug that evdns events are not EVLIST_INTERNAL.
* TODO(pts): Document the side effect of import syncless.coio on Ctrl-<C>.
* TODO(pts): HTTP client library (making urllib non-blocking?)
* TODO(pts): support webob as a web framework
* TODO(pts): productionization
* TODO(pts): setsockopt TCP_DEFER_ACCEPT
* TODO(pts): setsockopt SO_LINGER non-immediate close() for writing
* TODO(pts): use SO_RCVTIMEO and SO_SNDTIMEO for timeout
* TODO(pts): is it faster in Cython than in Pyrex? (it's not smaller though)
* TODO(pts): Strip the coio.so files upon installation? It seems to be still
             importable. Some Python installations autostrip. Why not ours?
* TODO(pts): Fix the AttributeError in socket.socket.close().
* TODO(pts): channel.send_exception() with a traceback. (Wait for receiver?)
* TODO(pts): Handle starving (when one worker is very busy, even Ctrl-<C>
  is delayed) This is hard to achieve (but the main tasklet can be given
  priority on Ctrl-<C>, so it would be the next to be scheduled).
# TODO(pts): Evaluate how fast stack copying (Stackless hard switching) is.
* TODO(pts): Monkey-patch signal.signal(...).
* TODO(pts): Automatic install script for Linux.
* TODO(pts): Add SSL support for Python2.5 (it already has socket._ssl.ssl).
* TODO(pts): Document Pyrex vs Cython
* !! SUXX: why can't we connect() with O_NONBLOCK at a very high rate (just
  as with normal sockets?)
* TODO(pts): Specify TCP socket timeout. Verify it.
* TODO(pts): Specify total HTTP write timeout.
* TODO(pts): Move the main loop to another tasklet (?) so async operations can
  work even at initialization.
* TODO(pts): Implement an async DNS resolver HTTP interface.
  (This will demonstrate asynchronous socket creation.)
* TODO(pts): Document that scheduling is not fair if there are multiple readers
  on the same fd.
* TODO(pts): Close connection on 413 Request Entity Too Large.
* TODO(pts): Prove that there is no memory leak over a long running time.
* TODO(pts): Use socket.recv_into() for buffering.
* TODO(pts): Handle signals (at least KeyboardInterrupt).
* TODO(pts): Handle errno.EPIPE.
* TODO(pts): Handle errno.EINTR. (Do we need this in Python?)
* TODO(pts): /infinite 100K buffer on localhost is much faster than 10K.
* TODO(pts): Consider alternative implementation with eventlet.
* TODO(pts): Implement an SSL-capable HTTP proxy as a reference.
* TODO(pts): doc: signal.alarm doesn't work (the SIGALRM will get ignored?)
* TODO(pts): Make os.waitpid non-blocking by installing a SIGCHLD handler.
* TODO(pts): Add interactive console like gevent.backdoor with line editing
  and history.
* TODO(pts): Fix very small float sleep value for libev.
* TODO(pts): Add proper nbfile buffering (with read_upto) for nbsslsocket.
* TODO(pts): Add more protocol parsing examples.

__EOF__
