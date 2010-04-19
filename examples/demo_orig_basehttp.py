#! /usr/local/bin/stackless2.6

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
  import time
  HOST_NAME = '127.0.0.1'
  PORT_NUMBER = 8080
  server_class = BaseHTTPServer.HTTPServer
  httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
  print time.asctime(), "Server Starts - %s:%s" % (HOST_NAME, PORT_NUMBER)
  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    pass
  httpd.server_close()
  print time.asctime(), "Server Stops - %s:%s" % (HOST_NAME, PORT_NUMBER)
