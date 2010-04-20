#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Tue Apr 20 17:52:02 CEST 2010

import os
import sys

import syncless.reactor
# It has to be installed before `twisted.internet.reactor' is imported.
# (This is by design in Twisted.)
syncless.reactor.install()

from twisted.internet import reactor
from twisted.internet import task
from twisted.python import log
from twisted.web import resource
from twisted.web import server

STDOUT_FILENO = 1
STDERR_FILENO = 2

def ShowTwistedProgress():
  os.write(STDOUT_FILENO, 'T')  # Twisted captures sys.stdout and sys.stderr.

class Simple(resource.Resource):
  isLeaf = True
  def render_GET(self, request):
    return 'Hello, <b>World</b>!'

log.startLogging(sys.stdout)
site = server.Site(Simple())
reactor.listenTCP(8080, site)
task.LoopingCall(ShowTwistedProgress).start(0.1)
reactor.run()
