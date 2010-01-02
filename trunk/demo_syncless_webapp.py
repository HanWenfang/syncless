#! /usr/local/bin/stackless2.6

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
  import sys
  import wsgi  # from syncless
  if len(sys.argv) > 1 and sys.argv[1] == 'demo':
    del sys.argv[1]
    # self.request.path would be '' or '/' instead of '/hello' in application
    # below.
    wsgi.RunHttpServer(HelloPage)
  else:
    # self.request.path would be '/hello'.
    wsgi.RunHttpServer(application)  # WSGI-compliant.
