#! /usr/local/bin/stackless2.6

"""WSGI server library for the Syncless server framework.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

Doc: WSGI: http://www.python.org/dev/peps/pep-0333/
Doc: WSGI server in stackless: http://stacklessexamples.googlecode.com/svn/trunk/examples/networking/wsgi/stacklesswsgi.py

TODO(pts): Validate this implementation with wsgiref.validate.
TODO(pts): Write access.log like BaseHTTPServer and CherryPy
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import errno
import re
import sys
import socket
import time
import types

from syncless import nbio


# TODO(pts): Use this.
ERRLIST_REQHEAD_RAISE = [
    errno.EBADF, errno.EINVAL, errno.EFAULT]
"""Errnos to be raised when reading the HTTP request headers."""

# TODO(pts): Use this.
ERRLIST_REQBODY_RAISE = [
    errno.EBADF, errno.EINVAL, errno.EFAULT]
"""Errnos to be raised when reading the HTTP request headers."""


HTTP_REQUEST_METHODS_WITH_BODY = ['POST', 'PUT', 'OPTIONS', 'TRACE']
"""HTTP request methods which can have a body (Content-Length)."""

COMMA_SEPARATED_REQHEAD = set(['ACCEPT', 'ACCEPT-CHARSET', 'ACCEPT-ENCODING',
    'ACCEPT-LANGUAGE', 'ACCEPT-RANGES', 'ALLOW', 'CACHE-CONTROL',
    'CONNECTION', 'CONTENT-ENCODING', 'CONTENT-LANGUAGE', 'EXPECT',
    'IF-MATCH', 'IF-NONE-MATCH', 'PRAGMA', 'PROXY-AUTHENTICATE', 'TE',
    'TRAILER', 'TRANSFER-ENCODING', 'UPGRADE', 'VARY', 'VIA', 'WARNING',
    'WWW-AUTHENTICATE'])
"""HTTP request headers which will be joined by comma + space.

The list was taken from cherrypy.wsgiserver.comma_separated_headers.
"""

REQHEAD_CONTINUATION_RE = re.compile(r'\n[ \t]+')
"""Matches HTTP request header line continuation."""


class WsgiErrorsStream(object):
  @classmethod
  def flush(cls):
    pass

  @classmethod
  def write(cls, msg):
    # TODO(pts): Buffer on newline.
    nbio.LogDebug(msg)

  @classmethod
  def writelines(cls, msgs):
    for msg in msgs:
      cls.write(msg)

# TODO(pts): Replace the read buffering here with a faster `file' object in
# non-blocking mode. We may have to use an extra file descriptor for that,
# because of closing issues (_socket.socket.makefile() does this).
class WsgiInputStream(object):
  """POST data input stream sent to the WSGI application as env['wsgi.input'].

  The methods read, readline, readlines and __iter__ correspond to the WSGI
  specification.
  """

  # TODO(pts): Add a faster implementation if readline() is not needed.
  # TODO(pts): Handle read errors without dying. (Ignore errors? The WSGI
  #            application would notice that env['CONTENT_LENGTH'] is larger.
  # TODO(pts): Make the buffering faster.

  def __init__(self, nbf, content_length):
    if not isinstance(nbf, nbio.NonBlockingFile):
      raise TypeError
    if type(content_length) not in (int, long) or content_length < 0:
      raise TypeError
    self.nbf = nbf
    self.bytes_remaining = content_length
    # This includes data in buffers (self.half_line and self.lines_rev).
    self.bytes_read = 0
    # Buffers strings ending with a \n (except possibly at EOF), in reverse
    # order.
    self.lines_rev = []
    # Buffers strings read without a newline (coming after self.lines_rev).
    self.half_line = []

  def SetContentLength(self, content_length):
    assert self.bytes_remaining == 0
    del self.lines_rev[:]
    del self.half_line[:]
    if type(content_length) not in (int, long) or content_length < 0:
      raise TypeError
    self.bytes_remaining = content_length
    self.bytes_read = 0

  def ReadAndDiscardRemaining(self):
    del self.lines_rev[:]
    del self.half_line[:]
    while self.bytes_remaining > 0:
      n = min(self.bytes_remaining, 4096)
      got = len(self.nbf.ReadAtMost(n))
      if got:
        self.bytes_remaining -= got
      else:
        self.bytes_remaining = 0
        break
      self.bytes_read += got

  def AppendToReadBuffer(self, data):
    if data:
      assert len(data) <= self.bytes_remaining
      self.bytes_remaining -= len(data)
      self.bytes_read += len(data)
      # TODO(pts): Support a read buffer which is not split yet.
      half_line = self.half_line
      lines_rev = self.lines_rev
      i = data.rfind('\n')
      if i < 0:
        half_line.append(data)
      else:
        if i != len(data) - 1:
          half_line.append(data[i + 1:])
        data = data[:i]
        data = [item + '\n' for item in data.split('\n')]
        data.reverse()
        lines_rev[:0] = data

  def read(self, size):
    """Read and return a string of at most size bytes."""
    if size <= 0:
      return ''
    lines_rev = self.lines_rev

    # Read from self.lines_rev.
    if lines_rev:
      data = lines_rev.pop()
      if len(data) <= size:
        return data
      # TODO(pts): Make this faster (O(n)) if the buffer is large and size is
      # small.
      lines_rev.append(data[size:])
      return data[:size]

    # Read from self.half_line if available.
    half_line = self.half_line
    if half_line:
      data = ''.join(half_line)
      assert data
      del half_line[:]
      if len(data) <= size:
        return data
      # TODO(pts): Make this faster (O(n)) if the buffer is large and size is
      # small.
      half_line.append(data[size:])
      return data[:size]

    # TODO(pts): Can we return less than size bytes? (WSGI doesn't say.)
    data = self.nbf.ReadAtMost(min(size, self.bytes_remaining))
    if data:
      self.bytes_remaining -= len(data)
    else:
      self.bytes_remaining = 0
    self.bytes_read += len(data)
    return data

  def readline(self):
    # TODO(pts): Create NonBlockingLineBufferedFile and move code there.
    lines_rev = self.lines_rev
    if lines_rev:
      return lines_rev.pop()
    half_line = self.half_line
    while True:
      n = min(4096, self.bytes_remaining)
      if n <= 0:
        if half_line:
          data = ''.join(half_line)
          del half_line[:]
          return data
        else:
          return ''
      data = nbf.ReadAtMost(n)
      if not data:
        self.bytes_remaining = 0
        if half_line:
          data = ''.join(half_line)
          del half_line[:]
          return data
        else:
          return ''
      self.bytes_read += len(data)
      self.bytes_remaining -= len(data)
      i = data.find('\n')
      if i >= 0:
        break
      half_line.append(data)
    if i == len(data) - 1:  # Fisrt newline at the end of the buffer.
      if half_line:
        half_line.append(data)
        data = ''.join(half_line)
        del half_line[:]
      return data
    half_line.append(data)
    lines_rev = ''.join(half_line).split('\n')
    del half_line[:]
    if lines_rev[-1]:
      half_line.append(lines_rev.pop())
    else:
      lines_rev.pop()
    for i in xrange(len(lines_rev)):
      lines_rev[i] += '\n'  # TODO(pts): Optimize this.
    lines_rev.reverse()
    return lines_rev.pop()

  def readlines(self, hint=None):
    lines = []
    while True:
      line = self.readline()
      if not line:
        break
      lines.append(line)
    return lines

  def __iter__(self):
    while True:
      line = self.readline()
      if not line:
        break
      yield line


class WsgiEmptyInputStream(object):
  """Empty POST data input stream sent to the WSGI application as
  env['wsgi.input'].

  The methods read, readline, readlines and __iter__ correspond to the WSGI
  specification.
  """

  bytes_read = 0
  bytes_remaining = 0

  @classmethod
  def read(cls, size):
    return ''

  @classmethod
  def readline(cls):
    return ''

  @classmethod
  def readlines(cls, hint=None):
    return []

  @classmethod
  def __iter__(cls):
    return iter(())


class FixedReadLineInputStream(object):
  def __init__(self, lines):
    self.lines_rev = list(lines)
    self.lines_rev.reverse()

  def readline(self):
    if self.lines_rev:
      return self.lines_rev.pop()
    else:
      return ''


HEADER_WORD_LOWER_LETTER_RE = re.compile(r'(?:\A|-)[a-z]')

# TODO(pts): Get it form the HTTP RFC.

SUB_URL_RE = re.compile(r'\A/[-A-Za-z0-9_./,~!@$*()\[\]\';:?&%+=]*\Z')
"""Matches a HTTP sub-URL, as appearing in line 1 of a HTTP request."""

HTTP_1_1_METHODS = ('GET', 'HEAD', 'POST', 'PUT', 'DELETE',
                    'OPTIONS', 'TRACE', 'CONNECT')

HTTP_VERSIONS = ('HTTP/1.0', 'HTTP/1.1')

KEEP_ALIVE_RESPONSES = (
    'Connection: close\r\n',
    'Connection: Keep-Alive\r\n')

WDAY = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
MON = ('', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
       'Oct', 'Nov', 'Dec')

def GetHttpDate(at):
  now = time.gmtime(at)
  return '%s, %02d %s %4d %02d:%02d:%02d GMT' % (
      WDAY[now[6]], now[2], MON[now[1]], now[0], now[3], now[4], now[5])
      
def RespondWithBadRequest(date, server_software, nbf, reason):
  msg = 'Bad request: ' + str(reason)
  # TODO(pts): Add Server: and Date:
  nbf.Write('HTTP/1.0 400 Bad Request\r\n'
            'Server: %s\r\n'
            'Date: %s\r\n'
            'Connection: close\r\n'
            'Content-Type: text/plain\r\n'
            'Content-Length: %d\r\n\r\n%s\n' %
            (server_software, date, len(msg) + 1, msg))
  nbf.Flush()

def WsgiWorker(nbf, peer_name, wsgi_application, default_env, date):
  # TODO(pts): Implement the full WSGI spec
  # http://www.python.org/dev/peps/pep-0333/
  if not isinstance(date, str):
    raise TypeError
  req_buf = ''
  do_keep_alive_ary = [True]
  headers_sent_ary = [False]
  server_software = default_env['SERVER_SOFTWARE']
  full_input = WsgiInputStream(nbf, content_length=0)
  reqhead_continuation_re = REQHEAD_CONTINUATION_RE
  try:
    while do_keep_alive_ary[0]:
      do_keep_alive_ary[0] = False
      env = dict(default_env)
      env['REMOTE_HOST'] = env['REMOTE_ADDR'] = peer_name[0]
      env['REMOTE_PORT'] = str(peer_name[1])
      env['wsgi.errors'] = WsgiErrorsStream
      if date is None:  # Reusing a keep-alive socket.
        items = data = input
        # For efficiency reasons, we don't check now whether the child has
        # already closed the connection. If so, we'll be notified next time.

        # Let other tasklets make some progress before we serve our next
        # request.
        nbio.stackless.schedule()
        
      # Read HTTP/1.0 or HTTP/1.1 request. (HTTP/0.9 is not supported.)
      # req_buf may contain some bytes after the previous request.
      nbio.LogDebug('reading HTTP request on nbf=%x' % id(nbf))
      while True:
        if req_buf:
          # TODO(pts): Support HTTP/0.9 requests without headers.
          i = req_buf.find('\n\n')
          j = req_buf.find('\n\r\n')
          if i >= 0 and i < j:
            req_head = req_buf[:i]
            req_buf = req_buf[i + 2:]
            break
          elif j >= 0:
            req_head = req_buf[:j]
            req_buf = req_buf[j + 3:]
            break
          if len(req_buf) > 32767:
            # Request too long. Just abort the connection since it's too late to
            # notify receiver.
            return
        # TODO(pts): Handle read errors (such as ECONNRESET etc.).
        # TODO(pts): Better buffering than += (do we need that?)
        req_new = nbf.ReadAtMost(4096)
        if not req_new:
          # The HTTP client has closed the connection before sending the headers.
          return
        if date is None:
          date = GetHttpDate(time.time())
        # TODO(pts): Ensure that refcount(req_buf) == 1 -- do the string
        # reference counters increase by slicing?
        req_buf += req_new  # Fast string append if refcount(req_buf) == 1.
        req_new = None

      # TODO(pts): Speed up this splitting?
      req_head = reqhead_continuation_re.sub(
          ', ', req_head.rstrip('\r').replace('\r\n', '\n'))
      req_lines = req_head.split('\n')
      req_line1_items = req_lines.pop(0).split(' ', 2)
      if len(req_line1_items) != 3:
        RespondWithBadRequest(date, server_software, nbf, 'bad line1')
        return  # Don't reuse the connection.
      method, suburl, http_version = req_line1_items
      if http_version not in HTTP_VERSIONS:
        RespondWithBadRequest(date, 
            server_software, nbf, 'bad HTTP version: %r' % http_version)
        return  # Don't reuse the connection.
      # TODO(pts): Support more methods for WebDAV.
      if method not in HTTP_1_1_METHODS:
        RespondWithBadRequest(date, server_software, nbf, 'bad method')
        return  # Don't reuse the connection.
      if not SUB_URL_RE.match(suburl):
        # This also fails for HTTP proxy URLS http://...
        RespondWithBadRequest(date, server_software, nbf, 'bad suburl')
        return  # Don't reuse the connection.
      env['REQUEST_METHOD'] = method
      env['SERVER_PROTOCOL'] = http_version
      # TODO(pts): What does appengine set here? wsgiref.validate recommends
      # the empty string (not starting with '.').
      env['SCRIPT_NAME'] = ''
      i = suburl.find('?')
      if i >= 0:
        env['PATH_INFO'] = suburl[:i]
        env['QUERY_STRING'] = suburl[i + 1:]
      else:
        env['PATH_INFO'] = suburl
        env['QUERY_STRING'] = ''

      content_length = None
      do_req_keep_alive = http_version == 'HTTP/1.1'  # False for HTTP/1.0
      for line in req_lines:
        i = line.find(':')
        if i < 0:
          RespondWithBadRequest(date, server_software, nbf, 'bad header line')
          return
        j = line.find(': ', i)
        if j >= 0:
          value = line[i + 2:]
        else:
          value = line[i + 1:]
        name = line[:i].lower()
        if name == 'connection':
          do_req_keep_alive = value.lower() == 'keep-alive'
        elif name == 'keep-alive':
          pass  # TODO(pts): Implement keep-alive timeout.
        elif name == 'content-length':
          try:
            content_length = int(value)
          except ValueError:
            RespondWithBadRequest(date, server_software, nbf, 'bad content-length')
            return
          env['CONTENT_LENGTH'] = value
        elif name == 'content-type':
          env['CONTENT_TYPE'] = value
        elif not name.startswith('proxy-'):
          name_upper = name.upper()
          key = 'HTTP_' + name_upper.replace('-', '_')
          if key in env and name_upper in COMMA_SEPARATED_REQHEAD:
            # Fast (linear) version of the quadratic env[key] += ', ' + value.
            s = env[key]
            env[key] = ''
            s += ', '
            s += value
            env[key] = s
          else:
            env[key] = value
          # TODO(pts): Maybe override SERVER_NAME and SERVER_PORT from HTTP_HOST?
          # Does Apache do this?

      if content_length is None:
        if method in ('POST', 'PUT'):
          RespondWithBadRequest(date, server_software, nbf, 'missing content')
          return
        env['wsgi.input'] = input = WsgiEmptyInputStream
      else:
        if method not in ('POST', 'PUT'):
          if content_length:
            RespondWithBadRequest(
                date, server_software, nbf, 'unexpected content')
            return
          content_length = None
          del env['CONTENT_LENGTH']
        if content_length:
          full_input.SetContentLength(content_length)
          env['wsgi.input'] = input = full_input
          if len(req_buf) > content_length:
            input.AppendToReadBuffer(req_buf[:content_length])
            req_buf = req_buf[content_length:]
          elif req_buf:
            input.AppendToReadBuffer(req_buf)
            req_buf = ''
        else:
          env['wsgi.input'] = input = WsgiEmptyInputStream

      is_not_head = method != 'HEAD'
      res_content_length = None
      headers_sent_ary[0] = False
      assert not nbf.write_buf

      def WriteHead(data):
        """HEAD callback returned by StartResponse, the app may call it."""
        data = str(data)
        if not data:
          return
        data = None  # Save memory.
        if not headers_sent_ary[0]:
          do_keep_alive_ary[0] = do_req_keep_alive
          nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
          nbf.Write('\r\n')
          nbf.Flush()
          if not do_keep_alive_ary[0]:
            nbf.close()
          headers_sent_ary[0] = True
          if input.bytes_remaining:
            input.ReadAndDiscardRemaining()

      def WriteNotHead(data):
        """Non-HEAD callback returned by StartResponse, the app may call it."""
        data = str(data)
        if not data:
          return
        if headers_sent_ary[0]:
          nbf.Write(data)
          nbf.Flush()
        else:
          do_keep_alive_ary[0] = (
              do_req_keep_alive and res_content_length is not None)
          nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
          nbf.Write('\r\n')
          nbf.Write(data)
          nbf.Flush()
          headers_sent_ary[0] = True
          if input.bytes_remaining:
            input.ReadAndDiscardRemaining()

      def StartResponse(status, response_headers, exc_info=None):
        """Callback called by wsgi_application."""
        # Just set it to None, because we don't have to re-raise it since we
        # haven't sent any headers yet.
        exc_info = None
        if nbf.write_buf:  # StartResponse called again by an error handler.
          del nbf.write_buf[:]
          res_content_length = None

        # TODO(pts): Send `Date:' header: Date: Sun, 20 Dec 2009 12:48:56 GMT
        nbf.Write('%s %s\r\n' % (http_version, status))  # HTTP/1.0
        nbf.Write('Server: %s\r\n' % server_software)
        nbf.Write('Date: %s\r\n' % date)
        for key, value in response_headers:
          key_lower = key.lower()
          if (key not in ('status', 'server', 'date', 'connection') and
              not key.startswith('proxy-') and
              # Apache responds with content-type for HEAD requests.
              (is_not_head or key not in ('content-length',
                                          'content-transfer-encoding'))):
            if key == 'content-length':
              # !! TODO(pts): Cut or pad the output below at content-length.
              # TODO(pts): Handle parsing error here.
              res_content_length = int(value)
            key_capitalized = re.sub(
                HEADER_WORD_LOWER_LETTER_RE,
                lambda match: match.group(0).upper(), key_lower)
            # TODO(pts): Eliminate duplicate keys (except for set-cookie).
            nbf.Write('%s: %s\r\n' % (key_capitalized, value))
        # Don't flush yet.
        if is_not_head:
          return WriteNotHead
        else:
          return WriteHead

      # TODO(pts): Handle application-level exceptions here.
      items = wsgi_application(env, StartResponse)
      # TODO(pts): Handle this error robustly.
      assert nbf.write_buf or headers_sent_ary[0], (
          'WSGI app must have called start_response by now')
      date = None
      if (isinstance(items, list) or isinstance(items, tuple) or
          isinstance(items, str)):
        if is_not_head:
          if isinstance(items, str):
            data = items
          else:
            data = ''.join(map(str, items))
        else:
          data = ''
        items = None
        if not headers_sent_ary[0]:
          if input.bytes_remaining:
            input.ReadAndDiscardRemaining()
          if res_content_length is not None:
            # TODO(pts): Pad or truncate.
            assert len(data) == res_content_length
          if is_not_head:
            nbf.Write('Content-Length: %d\r\n' % len(data))
          do_keep_alive_ary[0] = do_req_keep_alive
          nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
          nbf.Write('\r\n')
        nbf.Write(data)
        nbf.Flush()
      elif is_not_head:
        if not headers_sent_ary[0]:
          do_keep_alive_ary[0] = (
              do_req_keep_alive and res_content_length is not None)
          nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
          nbf.Write('\r\n')
        for data in items:
          if input.bytes_remaining:  # TODO(pts): Check only once.
            input.ReadAndDiscardRemaining()
          nbf.Write(data)
          nbf.Flush()
        if input.bytes_remaining:
          input.ReadAndDiscardRemaining()
      else:  # HTTP HEAD request.
        if not headers_sent_ary[0]:
          do_keep_alive_ary[0] = do_req_keep_alive
          nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
          nbf.Write('\r\n')
          nbf.Flush()
          if not do_keep_alive_ary[0]:
            nbf.close()
        # If tasklets could run in parellel, we could iterate over `items'
        # below in another tasklet,, so the HTTP client could reuse the
        # connection for another request before the iteration finishes.
        for data in items:  # Run the generator function through.
          if input.bytes_remaining:  # TODO(pts): Check only once.
            input.ReadAndDiscardRemaining()
        if input.bytes_remaining:
          input.ReadAndDiscardRemaining()
      # TODO(pts): Call close() in a finally block.
      # TODO(pts): Look up the WSGI specification again. What should we be
      # closing?
      if hasattr(items, 'close'):  # CherryPyWSGIServer does this.
        items.close()
  finally:
    nbf.close()
    nbio.LogDebug('connection closed nbf=%x' % id(nbf))


def WsgiListener(nbs, wsgi_application):
  """HTTP server serving WSGI, listing on nbs, to be run in a tasklet."""
  if not isinstance(nbs, nbio.NonBlockingSocket):
    raise TypeError
  if not callable(wsgi_application):
    raise TypeError
  env = {}
  env['wsgi.version']      = (1, 0)
  env['wsgi.multithread']  = True
  env['wsgi.multiprocess'] = False
  env['wsgi.run_once']     = False
  env['wsgi.url_scheme']   = 'http'  # could be 'https'
  env['HTTPS']             = 'off'  # could be 'on'; Apache sets this
  server_ipaddr, server_port = nbs.getsockname()
  env['SERVER_PORT'] = str(server_port)
  env['SERVER_SOFTWARE'] = 'pts-syncless-wsgi'
  if server_ipaddr:
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = server_ipaddr
  else:
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = nbs.getsockname()

  try:
    while True:
      accepted_nbs, peer_name = nbs.accept()
      date = GetHttpDate(time.time())
      if nbio.VERBOSE:
        nbio.LogDebug('connection accepted from=%r nbf=%x' %
                 (peer_name, id(accepted_nbs)))
      nbio.stackless.tasklet(WsgiWorker)(
          accepted_nbs, peer_name, wsgi_application, env, date)
      accepted_nbs = peer_name = None  # Help the garbage collector.
  finally:
    nbs.close()

class FakeServerSocket(object):
  """A fake TCP server socket, used as CherryPyWSGIServer.socket."""

  __attrs__ = ['accepted_nbs', 'accepted_addr']

  def __init__(self):
    self.accepted_nbs = None
    self.accepted_addr = None

  def accept(self):
    """Return and clear self.accepted_nbs.

    This method is called by CherryPyWSGIServer.tick().
    """
    accepted_nbs = self.accepted_nbs
    assert accepted_nbs
    accepted_addr = self.accepted_addr
    self.accepted_nbs = None
    self.accepted_addr = None
    return accepted_nbs, accepted_addr

  def ProcessAccept(self, accepted_nbs, accepted_addr):
    assert accepted_nbs
    assert self.accepted_nbs is None
    self.accepted_nbs = accepted_nbs
    self.accepted_addr = accepted_addr


class FakeRequests(object):
  """A list of HTTPConnection objects, for CherryPyWSGIServer.requests."""

  __slots__ = 'requests'

  def __init__(self):
    self.requests = []

  def put(self, request):
    # Called by CherryPyWSGIServer.tick().
    self.requests.append(request)


def CherryPyWsgiListener(nbs, wsgi_application):
  """HTTP server serving WSGI, using CherryPy's implementation."""
  # TODO(pts): Why is CherryPy's /infinite twice as fast as ours?
  # Only sometimes.
  if not isinstance(nbs, nbio.NonBlockingSocket):
    raise TypeError
  if not callable(wsgi_application):
    raise TypeError
  try:
    from cherrypy import wsgiserver
  except ImportError:
    from web import wsgiserver  # Another implementation in (web.py).
  wsgi_server = wsgiserver.CherryPyWSGIServer(
      nbs.getsockname(), wsgi_application)
  wsgi_server.ready = True
  wsgi_server.socket = FakeServerSocket()
  wsgi_server.requests = FakeRequests()
  wsgi_server.timeout = None  # TODO(pts): Fix once implemented.

  try:
    while True:
      accepted_nbs, peer_name = nbs.accept()
      if nbio.VERBOSE:
        nbio.LogDebug('cpw connection accepted from=%r nbf=%x' %
                 (peer_name, id(accepted_nbs)))
      wsgi_server.socket.ProcessAccept(accepted_nbs, peer_name)
      assert not wsgi_server.requests.requests
      wsgi_server.tick()
      assert len(wsgi_server.requests.requests) == 1
      http_connection = wsgi_server.requests.requests.pop()
      nbio.stackless.tasklet(http_connection.communicate)()
      # Help the garbage collector.
      http_connection = accepted_nbs = peer_name = None
  finally:
    nbf.close()


class FakeBaseHttpWFile(object):
  def __init__(self, env, start_response):
    self.env = env
    self.start_response = start_response
    self.wsgi_write_callback = None
    self.write_buf = []
    self.closed = False

  def write(self, data):
    data = str(data)
    if not data:
      return
    write_buf = self.write_buf
    if self.wsgi_write_callback:
      write_buf.append(data)
    else:
      assert data.endswith('\r\n')
      data = data.rstrip('\n\r')
      if data:
        write_buf.append(data)  # Buffer status and headers.
      else:
        assert len(write_buf) > 2  # HTTP/..., Server:, Date:
        assert write_buf[0].startswith('HTTP/')
        status = write_buf[0][write_buf[0].find(' ') + 1:]
        write_buf.pop(0)
        response_headers = [
            tuple(header_line.split(': ', 1)) for header_line in write_buf]
        self.wsgi_write_callback = self.start_response(
            status, response_headers)
        assert callable(self.wsgi_write_callback)
        del self.write_buf[:]

  def close(self):
    if not self.closed:
      self.flush()
    self.closed = True

  def flush(self):
    if self.wsgi_write_callback:
      if self.write_buf:
        data = ''.join(self.write_buf)
        del self.write_buf[:]
        if data:
          self.wsgi_write_callback(data)


def CloseMethod(self):
  self.closed = True


class ConstantReadLineInputStream(object):
  def __init__(self, lines):
    self.lines_rev = list(lines)
    self.lines_rev.reverse()
    self.closed = False

  def readline(self):
    if self.lines_rev:
      return self.lines_rev.pop()
    else:
      return ''

  def read(self, size):
    assert not self.lines_rev
    return ''  

  def close(self):
    # We don't clear self.lines_rev[:], the hacked
    # WsgiInputStream doesn't do that eiter.
    self.closed = True


class FakeBaseHttpConnection(object):
  def __init__(self, env, start_response, request_lines):
    self.env = env
    self.start_response = start_response
    self.request_lines = request_lines

  def makefile(self, mode, bufsize):
    if mode.startswith('r'):
      rfile = self.env['wsgi.input']
      if isinstance(rfile, WsgiInputStream):
        rfile.close = types.MethodType(CloseMethod, rfile)
        if rfile.lines_rev:
          rfile.lines_rev.extend(reversed(self.request_lines))
        else:
          rfile.lines_rev = list(self.request_lines)
          rfile.lines_rev.reverse()
      elif rfile is WsgiEmptyInputStream:
        rfile = ConstantReadLineInputStream(self.request_lines)
      else:
        assert 0, rfile
      self.request_lines = None  # Save memory.
      return rfile
    elif mode.startswith('w'):
      return FakeBaseHttpWFile(self.env, self.start_response)


class FakeBaseHttpServer(object):
  pass


def HttpRequestFromEnv(env, connection=None):
  """Convert a CGI or WSGI environment to a HTTP request header.

  Returns:
    A list of lines, all ending with '\r\n', the last being '\r\n' for
    HTTP/1.x.
  """
  # TODO(pts): Add unit test.
  if not isinstance(env, dict):
    raise TypeError
  output = []
  path = (env['SCRIPT_NAME'] + env['PATH_INFO']) or '/'
  if env['QUERY_STRING']:
    path += '?'
    path += env['QUERY_STRING']
  if env['SERVER_PROTOCOL'] == 'HTTP/0.9':
    output.append('%s %s\r\n' % (env['REQUEST_METHOD'], path))
  else:
    output.append(
        '%s %s %s\r\n' %
        (env['REQUEST_METHOD'], path, env['SERVER_PROTOCOL']))
    for key in sorted(env):
      if key.startswith('HTTP_') and key not in (
          'HTTP_CONTENT_TYPE', 'HTTP_CONTENT_LENGTH', 'HTTP_CONNECTION'):
        name = re.sub(
            r'[a-z0-9]+', lambda match: match.group(0).capitalize(),
            key[5:].lower().replace('_', '-'))
        output.append('%s: %s\r\n' % (name, env[key]))
    if env['REQUEST_METHOD'] in HTTP_REQUEST_METHODS_WITH_BODY:
      # It should be CONTENT_LENGTH, not HTTP_CONTENT_LENGTH.
      content_length = env.get(
          'CONTENT_LENGTH', env.get('HTTP_CONTENT_LENGTH'))
      if content_length is not None:
        output.append('Content-Length: %s\r\n' % content_length)
      # It should be CONTENT_TYPE, not HTTP_CONTENT_TYPE.
      content_type = env.get('CONTENT_TYPE', env.get('HTTP_CONTENT_TYPE'))
      if content_type:
        output.append('Content-Type: %s\r\n' % content_type)
    if connection is not None:
      output.append('Connection: %s\r\n' % connection)
    output.append('\r\n')
  return output


def BaseHttpWsgiWrapper(bhrh_class):
  """Return a WSGI application running a BaseHttpRequestHandler."""
  BaseHTTPServer = sys.modules['BaseHTTPServer']
  if not ((isinstance(bhrh_class, type) or
           isinstance(bhrh_class, types.ClassType)) and
          issubclass(bhrh_class, BaseHTTPServer.BaseHTTPRequestHandler)):
    raise TypeError

  def WsgiApplication(env, start_response):
    request_lines = HttpRequestFromEnv(env, connection='close')
    connection = FakeBaseHttpConnection(env, start_response, request_lines)
    server = FakeBaseHttpServer(env, start_response)
    client_address = (env['REMOTE_ADDR'], int(env['REMOTE_PORT']))
    # The constructor calls bhrh.handle_one_request() automatically.
    bhrh = bhrh_class(connection, client_address, server)
    # If there is an exception in the bhrh_class creation above, then these
    # assertions are not reached, and bhrh.wfile and bhrh.rfile remain
    # unclosed, but that's OK.
    assert bhrh.wfile.wsgi_write_callback
    assert not bhrh.wfile.write_buf
    return ''

  return WsgiApplication


def CanBeCherryPyApp(app):
  """Return True if app is a CherryPy app class or object."""
  # Since CherryPy applications can be of any type, the only way for us to
  # detect such an application is to look for an exposed method (or class?).
  if isinstance(app, type) or isinstance(app, types.ClassType):
    pass
  elif isinstance(app, object) or isinstance(app, types.InstanceType):
    app = type(app)
  else:
    return False
  for name in dir(app):
    value = getattr(app, name)
    if callable(value) and getattr(value, 'exposed', False):
      return True
  return False


def RunHttpServer(app, server_address=None):
  """Listen as a HTTP server, and run the specified application forever.

  Args:
    app: A WSGI application function, or a (web.py) web.application object.
    server_address: TCP address to bind to, e.g. ('', 8080), or None to use
      the default.
  """
  try:
    import psyco
    psyco.full()  # TODO(pts): Measure the speed in Stackless Python.
  except ImportError:
    pass
  if len(sys.argv) > 1:  # TODO(pts): Use getopt.
    nbio.VERBOSE = True
  webapp = (sys.modules.get('google.appengine.ext.webapp') or
            sys.modules.get('webapp'))
  # Use if already loaded.
  BaseHTTPServer = sys.modules.get('BaseHTTPServer')
  if webapp and isinstance(app, type) and issubclass(
      app, webapp.RequestHandler):
    nbio.LogInfo('running webapp RequestHandler')
    wsgi_application = webapp.WSGIApplication(
        [('/', app)], debug=bool(nbio.VERBOSE))
    assert callable(wsgi_application)
    if server_address is None:
      server_address = ('127.0.0.1', 6666)
  elif (not callable(app) and
      hasattr(app, 'handle') and hasattr(app, 'request') and
      hasattr(app, 'run') and hasattr(app, 'wsgifunc') and
      hasattr(app, 'cgirun') and hasattr(app, 'handle')):
    nbio.LogInfo('running (web.py) web.application')
    wsgi_application = app.wsgifunc()
    if server_address is None:
      server_address = ('0.0.0.0', 8080)  # (web.py) default
  elif CanBeCherryPyApp(app):
    nbio.LogInfo('running CherryPy application')
    if isinstance(app, type) or isinstance(app, types.ClassType):
      app = app()
    import cherrypy
    # See http://www.cherrypy.org/wiki/WSGI
    wsgi_application = cherrypy.tree.mount(app, '/')
    if server_address is None:
      server_address = ('127.0.0.1', 8080)  # CherryPy default
    # TODO(pts): Use CherryPy config files.
  elif (BaseHTTPServer and
        (isinstance(app, type) or isinstance(app, types.ClassType)) and
        issubclass(app, BaseHTTPServer.BaseHTTPRequestHandler)):
    nbio.LogInfo('running BaseHTTPRequestHandler application')
    wsgi_application = BaseHttpWsgiWrapper(app)
    if server_address is None:
      server_address = ('127.0.0.1', 6666)
  elif callable(app):
    if webapp and isinstance(app, webapp.WSGIApplication):
      nbio.LogInfo('running webapp WSGI application')
    else:
      nbio.LogInfo('running WSGI application')

    # Check that app accepts the proper number of arguments.
    has_self = False
    if isinstance(app, type) or isinstance(app, types.ClassType):
      func = getattr(app, '__init__', None)
      assert isinstance(func, types.UnboundMethodType)
      func = func.im_func
      has_self = True
    elif isinstance(app, object) or isinstance(app, types.InstanceType):
      func = getattr(app, '__call__', None)
      assert isinstance(func, types.MethodType)
      func = func.im_func
      has_self = True
    else:
      func = app
    expected_argcount = int(has_self) + 2  # self, env, start_response
    assert func.func_code.co_argcount == expected_argcount, (
        'invalid argument count -- maybe not a WSGI application: %r' % app)
    func = None

    wsgi_application = app
    if server_address is None:
      server_address = ('127.0.0.1', 6666)
  else:
    print type(app)
    assert 0, 'unsupported application type for %r' % (app,)
    
  listener_nbs = nbio.NonBlockingSocket(socket.AF_INET, socket.SOCK_STREAM)
  listener_nbs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  listener_nbs.bind(server_address)
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  listener_nbs.listen(100)
  nbio.LogInfo('listening on %r' % (listener_nbs.getsockname(),))
  # From http://webpy.org/install (using with mod_wsgi).
  nbio.stackless.tasklet(WsgiListener)(listener_nbs, wsgi_application)
  nbio.RunMainLoop()
