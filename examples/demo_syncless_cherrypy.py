#! /usr/local/bin/stackless2.6
#
# demo for running a CherryPy application under Syncless WSGI.
# by pts@fazekas.hu at Tue Dec 22 12:15:58 CET 2009
#

import cherrypy

class HelloWorld(object):
  def index(self, name='World'):
    return 'Hello, <b>%s</b>!' % name
  index.exposed = True

if __name__ == '__main__':
  import logging
  import sys
  from syncless import wsgi
  if len(sys.argv) > 1:
    logging.root.setLevel(logging.DEBUG)
  else:
    logging.root.setLevel(logging.INFO)
  wsgi.RunHttpServer(HelloWorld)
