#! /usr/local/bin/stackless2.6
#
# demo_syncless_web_py.py: running a BaseHTTPRequestHandler under Syncless WSGI
# by pts@fazekas.hu at Tue Dec 22 12:16:22 CET 2009
#

import cgi
import BaseHTTPServer

class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):
  def do_HEAD(self):
    self.send_response(200)
    self.send_header("Content-type", "text/html")
    self.end_headers()

  def do_GET(self):
    """Respond to a GET request."""
    self.send_response(200)
    self.send_header('Content-type', 'text/html')
    self.end_headers()
    self.wfile.write('<html><head><title>Title goes here.</title></head>\n')
    self.wfile.write('<body><p>This is a test orig.</p>\n')
    # If someone went to 'http://something.somewhere.net/foo/bar/',
    # then self.path equals '/foo/bar/'.
    self.wfile.write('<p>You accessed path: %s</p>\n' % cgi.escape(self.path))
    if self.command in ('POST', 'PUT'):
      self.wfile.write(
          '<p>You submitted: %s</p>\n' %
          cgi.escape(repr(self.rfile.read(int(
              self.headers['Content-Length'])))))
    self.wfile.write('<form method=post><input name=q><input type=submit>')
    self.wfile.write('</form>\n')
    self.wfile.write('</body></html>\n')

  do_POST = do_GET
  do_PUT = do_GET

if __name__ == '__main__':
  import logging
  import sys
  from syncless import wsgi
  if len(sys.argv) > 1:
    logging.root.setLevel(logging.DEBUG)
  else:
    logging.root.setLevel(logging.INFO)
  wsgi.RunHttpServer(MyHandler)
