#! /usr/local/bin/stackless2.6
# Example invocation: PYTHONPATH="$HOME/prg/google_appengine/google/appengine/ext:$HOME/prg/google_appengine/lib/webob" ./examples/demo_orig_webapp.py

try:
  from google.appengine.ext import webapp
except ImportError:
  import webapp

class MainPage(webapp.RequestHandler):
  def get(self):
    self.response.out.write(
      '<html><body><form action="/hello" method="post">'
      'Name: <input name="name" type="text" size="20"> '
      '<input type="submit" value="Say Hello"></form></body></html>')

class HelloPage(webapp.RequestHandler):
  def post(self):
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.out.write('Hello, %s' % self.request.get('name'))

application = webapp.WSGIApplication([
  ('/', MainPage),
  ('/hello', HelloPage)
], debug=True)

if __name__ == '__main__':
  import wsgiref.simple_server
  server_host = ''
  server_port = 8080
  server = wsgiref.simple_server.make_server(
      server_host, server_port, application)
  print 'Serving on %s:%s' % (server_host, server_port)
  server.serve_forever()
