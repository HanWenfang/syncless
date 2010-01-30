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
