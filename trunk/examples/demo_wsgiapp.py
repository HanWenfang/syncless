#! /usr/local/bin/stackless2.6

"""Simple demo WSGI application code."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import cgi
import time

try:
  from syncless import coio
except ImportError:  # Don't ignore inner ImportError{}s.
  coio = None
def WsgiApp(env, start_response):
  """A simple demo WSGI application function."""
  error_stream = env['wsgi.errors']
  error_stream.write('Got env=%r\n' % env)
  status = '200 OK'
  assert env['PATH_INFO'] != '/badhead', 'bad head'
  response_headers = [('Content-type', 'text/html')]
  if env['PATH_INFO'] == '/badsize':
    response_headers.append(('Content-Length', 6))
  if env['PATH_INFO'] == '/parsesize':
    response_headers.append(('Content-Length', '--'))
  write = start_response(status, response_headers)
  assert env['PATH_INFO'] != '/badresp', 'bad resp'
  #from syncless import wsgi; raise wsgi.WsgiReadError('zzz')
  if env['REQUEST_METHOD'] in ('POST', 'PUT'):
    #print env['wsgi.input']
    return ['Posted/put %r.' % env['wsgi.input'].read(10)]
  elif env['PATH_INFO'] == '/hello':
    return ['Hello, <i>World</i> @ %s!\n' % time.time()]
  elif env['PATH_INFO'] == '/foobar':
    return iter(['foo', 'bar'])
  elif env['PATH_INFO'] == '/foobarbaz':
    write('foo')
    write('bar')
    return 'baz'
  elif env['PATH_INFO'] == '/infinite':
    s = 'x' * 99998 + '\n'
    def InfiniteYield():
      while True:
        yield s
    return InfiniteYield()
  elif env['PATH_INFO'] == '/badbody':
    def BadBodyYield():
      yield 'before bad body'
      assert 0, 'bad body'
    return BadBodyYield()
  elif env['PATH_INFO'] == '/badsize':
    return 'blah'
  elif env['PATH_INFO'] == '/a':
    if '=' not in env['QUERY_STRING']:
      return 'Missing hostname!'
    key, hostname = env['QUERY_STRING'].split('=', 2)
    if not hostname:
      return 'Empty hostname!'
    if not coio:
      return 'Missing DNS resolver!'
    try:
      result = coio.dns_resolve_ipv4(hostname, 0).values
    except coio.DnsLookupError, e:
      # Example e.__class__.__name__: 'NXDOMAIN', 'Timeout' (after >20 sec).
      return 'Resolve error: %s' % e.__class__.__name__
    return '\n<br>'.join(map(cgi.escape, map(repr, result)))
  else:
    if coio:
      dns_html = ('<form action="/a">Hostname: <input name=hostname>'
                  '<input type=submit value=Resolve></form>')
    else:
      dns_html = '<p>Missing DNS resolver.'
    # cherrypy.wsgiserver doesn't add REMOTE_HOST.
    remote_host = env.get('REMOTE_HOST', 'REMOTE_ADDR')
    return ['<a href="/hello">hello</a>, %s\n' % env['wsgi.url_scheme'],
            dns_html,
            '<p>%s</p>' % cgi.escape(env.get('HTTP_IF_NONE_MATCH', '')),
            '<form method="post"><input name=foo><input name=bar>'
            '<input type=submit></form>\n', remote_host]
