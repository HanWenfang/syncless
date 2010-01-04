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
  import wsgiref.simple_server
  server = wsgiref.simple_server.make_server('', 8080, application)
  print 'Serving on port 8080...'
  server.serve_forever()
