#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Tue Apr 20 17:55:48 CEST 2010

"""A demo showing how to use Syncless and Twisted in the same process.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.


To use Syncless and Twisted in the same process:

* Make sure that the Syncless reactor is installed
  (syncless.reactor.install()).
* Make sure the reactor main loop is run (e.g. by calling reactor.run() at
  the end of your main script).
* You can create any number of tasklets any time, and your tasklets can use
  Syncless' non-blocking I/O operations.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import os
import sys
from syncless.best_stackless import stackless

import syncless.reactor
# It has to be installed before `twisted.internet.reactor' is imported.
# (This is by design in Twisted.)
syncless.reactor.install()

from twisted.internet import reactor
from twisted.internet import task
from twisted.python import log
from twisted.web import resource
from twisted.web import server

from syncless import coio

STDOUT_FILENO = 1
STDERR_FILENO = 2

def ShowTwistedProgress():
  os.write(STDOUT_FILENO, 'T')  # Twisted captures sys.stdout and sys.stderr.

def ProgressWorker(sleep_amount):
  while True:
    os.write(STDOUT_FILENO, 'W')
    coio.sleep(sleep_amount)

class Simple(resource.Resource):
  isLeaf = True
  def render_GET(self, request):
    return 'Hello, <b>World</b>!'

log.startLogging(sys.stdout)
site = server.Site(Simple())
reactor.listenTCP(8080, site)
task.LoopingCall(ShowTwistedProgress).start(0.1)
stackless.tasklet(ProgressWorker)(0.1)
reactor.run()
