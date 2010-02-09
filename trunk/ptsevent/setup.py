#!/usr/bin/env python
#
# by pts@fazekas.hu at Tue Feb  9 18:42:57 CET 2010

import glob
import os
import os.path
import sys
from distutils.core import setup, Extension

try:
  import stackless
except ImportError:
  print >>sys.stderr, (
      'This Python extension needs Stackless Python.\n'
      'Please run setup.py with the Stackless Python interpreter.')
  sys.exit(2)

# TODO(pts): Run this autodetection only for build_ext (just like in
# pysqlite).

# We could add more directories (e.g. those in /etc/ld.so.conf), but that's
# system-specific, see http://stackoverflow.com/questions/2230467 .
# !! command-line flags
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
event = Extension(name='ptsevent',
                  sources=['ptsevent.c'],
                  include_dirs=include_dirs,
                  library_dirs=library_dirs,
                  libraries=['event'])

setup(name='ptsevent',
      version='0.4',
      author='Peter Szabo',
      author_email='pts@fazekas.hu',
      url='http://ptsevent/',  # !!
      description='An event library with buffering and Stackless coroutines.',
      #long_description="""This module provides a mechanism to execute a function when a specific event on a file handle, file descriptor, or signal occurs, or after a given time has passed.""",
      license='BSD',
      #download_url='http://monkey.org/~dugsong/pyevent/',
      ext_modules = [ event ])
