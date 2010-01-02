#! /usr/local/bin/stackless2.6

import web

urls = (
    '/(.*)', 'hello'
)
app = web.application(urls, globals())

class hello:        
    def GET(self, name):
        if not name: 
            name = 'world'
        web.header('Content-Type', 'text/html; charset=UTF-8')
        return 'Hello, <b>' + name + '</b>!'

if __name__ == "__main__":
  app.run()
