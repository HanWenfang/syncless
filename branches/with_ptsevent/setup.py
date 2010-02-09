#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Tue Feb  9 18:42:57 CET 2010

import glob
import os
import os.path
import sys
from distutils.core import Extension
from distutils.core import setup

# TODO(pts): Run this autodetection only for build_ext (just like in
# pysqlite).
# TODO(pts): Parse command-line flags (like include etc.)
# We could add more directories (e.g. those in /etc/ld.so.conf), but that's
# system-specific, see http://stackoverflow.com/questions/2230467 .
include_dirs = []
library_dirs = []
event = None
for prefix in os.getenv('LD_LIBRARY_PATH', '').split(':') + [
              sys.prefix, '/usr']:
  if (prefix and
      os.path.isfile(prefix + '/include/event.h') and
      os.path.isfile(prefix + '/include/evdns.h') and
      glob.glob(prefix + '/lib/libevent.*')):
    print 'found libevent in', prefix
    include_dirs =['%s/include' % prefix]
    library_dirs =['%s/lib' % prefix]    
if not include_dirs:
  print 'libevent not found, may be present anyway, going on'
event = Extension(name='syncless.coio',
                  sources=['coio_src/coio.c'],
                  include_dirs=include_dirs,
                  library_dirs=library_dirs,
                  libraries=['event'])

setup(name='syncless',
      version='0.02',
      description='Syncless: asynchronous client and server library using Stackless Python',
      author='Peter Szabo',
      author_email='pts@fazekas.hu',
      maintainer='Peter Szabo',
      maintainer_email='pts@fazekas.hu',
      url='http://code.google.com/p/syncless/',
      download_url='http://syncless.googlecode.com/files/syncless-0.01.tar.gz',
      packages=['syncless'],
      long_description=
          "Syncless is an experimental, lightweight, non-blocking "
          "(asynchronous) client and server socket network communication "
          "library for Stackless Python 2.6. For high speed, Syncless uses "
          "libevent, and parts of Syncless' code is implemented in C (Pyrex). "
          "Thus Syncless can be faster than many other non-blocking Python "
          "communication libraries. Syncless contains an asynchronous DNS "
          "resolver (using evdns) and a HTTP server capable of serving WSGI "
          "applications. Syncless aims to be a coroutine-based alternative of "
          "event-driven networking engines (such as Twisted and FriendFeed's "
          "Tornado), and it's a competitor of gevent, pyevent, eventlet and "
          "Concurrence.",
      license="GPL v2",
      platforms=["Unix"],
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Environment :: Console",
          "Environment :: No Input/Output (Daemon)",
          "Environment :: Other Environment",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: GNU General Public License (GPL)",
          "Operating System :: POSIX :: Linux",
          "Operating System :: Unix",
          "Programming Language :: Python :: 2.6",
          "Topic :: Internet",
          "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries",
          "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Server",
          "Topic :: Software Development :: Libraries :: Application Frameworks",
          "Topic :: Software Development :: Libraries :: Python Modules",
      ],
      requires=['stackless'],
      ext_modules = [ event ],
     )
