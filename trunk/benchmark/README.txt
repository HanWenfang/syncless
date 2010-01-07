Benchmarks for Syncless and other coroutine-based non-blocking I/O libraries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Speed results
~~~~~~~~~~~~~
All items in the table below are requests per second. The larger the better.

Implementation benchmarked  Parallel  Sequential
------------------------------------------------
concurrence                 3446.41   2777.78
concurrence_greenlet        2855.61   2517.62
concurrence_wsgi            1591.80   1234.72
concurrence_wsgi_greenlet   1019.02    963.39
eventlet                    4385.39   2787.06
eventlet_wsgi               1857.89   1442.58   
node_js                     4370.64   3450.65
syncless                    8313.59   4249.89
syncless_wsgi               4281.65   2836.07
tornado                     3228.51   2287.28

Conclusions and remarks
~~~~~~~~~~~~~~~~~~~~~~~
* The parallel benchmark issued 100 concurrent connections. This load might
  not be relevant in some workflows. To get a better insight, it would be
  worthwhile to do the benchmark for 1, 2, 4, 8, ..., 65536, ... concurrent
  connections, and draw a graph. That graph would show if there is an
  inherent limitation in an I/O library that prevents it from scaling up.
* See a similar, but more comprehensive benchmark with graphs at
  http://nichol.as/asynchronous-servers-in-python .
* Syncless is the clear winner for the non-WSGI parallel case, it also wins
  (although by only a little) in the sequential case, and it is good at the
  parallell WSGI case as well.
* As expected, Stackless Python is faster than greenlet, especially when
  there are lots of parallel requests.
* The huge difference between syncless and syncless_wsgi suggests that the
  WSGI server of Syncless is a good candidate for optimization (possibly in
  Cython and Pyrex, because the Python code already looks optimized).
* node.js has a very fast HTTP server protocol implementation (partially in
  C).

Environment
~~~~~~~~~~~
Various implementations were tested in the following environment:

* 2200MHz dual-core AMD Opteron CPU
* 8GB of RAM
* Ubuntu Hardy 64-bit (amd64)
* no swap
* Linux 2.6 (with epoll(7) support)
* Stackless 2.6.4 (or non-Stackless Python 2.5.2 where indicated)

Web servers
~~~~~~~~~~~
The characteristics of the web servers benchmarked:

* web server being the WSGI server of the I/O library, or implemented
  minimally from scratch using the I/O library's TCP socket readline() and
  write() methods
* pure Python code, except possibly the I/O library and its dependencies
* web server listening on the local interface: http://127.0.0.1:8080/
* very simple web application returning a HTML page of 40 bytes
  (see the source code of the application e.g. in speed_eventlet_wsgi.py)
* listen(2) backlog queue size of 128 items
* web server logging the client IP of each request to stderr
* stderr redirected to /dev/null
* otherwise using the default settings of each library

The following I/O libraries were tested:

* speed_concurrence.py: Concurrence-0.3.1 TCP (with Stackless Python and with
  greenlet)
* speed_concurrence_wsgi.py: Concurrence-0.3.1 WSGI server (with Stackless
  Python and with greenlet)
* speed_eventlet.py: eventlet-0.9.2 TCP
* speed_eventlet_wsgi.py: eventlet-0.9.2 WSGI server
* speed_node_js.js: node.js-0.1.24 custome web server
* speed_syncless.py: Syncless-v42 TCP
* speed_syncless_wsgi.py: Syncless-v42 WSGI server
* speed_tornado.py: Tornado-0.2 custom web server

(Please note that Tornado is not a coroutine, but an event-based web server
and I/O library, but it was included in the benchmarks for speed
comparison.)

Sequential benchmarks
~~~~~~~~~~~~~~~~~~~~~
See the results (time measurements) in sequential_benchmark_results.txt .

The characteristics of the bechmarks:

* client_seq.py (a custom HTTP client) used as a client
* 10000 different URLs were fetched sequentially (one HTTP request at a time)
* a new TCP connection created for each request (no keep-alive)

Parallel benchmarks
~~~~~~~~~~~~~~~~~~~
See the results (time measurements) in *.ab.txt .

The characteristics of the benchmarks:

* ApacheBench (ab) used as a HTTP client
* the main page fetched 100000 times
* 100 concurrect requests
* a new TCP connection created for each request (no keep-alive)
