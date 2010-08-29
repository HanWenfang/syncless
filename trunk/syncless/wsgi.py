#! /usr/local/bin/stackless2.6

"""WSGI server library for Syncless.

This Python module implements a HTTP and HTTPS server which can server WSGI
web applications. Example use:

  from syncless import wsgi
  def WsgiApp(env, start_response):
    start_response('200 OK', [('Content-Type', 'text/html')])
    return ['Hello, World!']
  wsgi.RunHttpServer(WsgiApp)

Example use with yield:

  def WsgiApp(env, start_response):
    start_response('200 OK', [('Content-Type', 'text/html')])
    yield 'Hello, '
    yield 'World!'
  wsgi.RunHttpServer(WsgiApp)

See the following examples uses:

* examples/demo.py (WSGI web app for both HTTP and HTTPS)
* examples/demo_syncless_basehttp.py (BaseHTTPRequestHandler web app)
* examples/demo_syncless_cherrypy.py (CherryPy web app)
* examples/demo_syncless_web_py.py (web.py web app)
* examples/demo_syncless_webapp.py (Google AppEngine ``webapp'' web app)

See http://www.python.org/dev/peps/pep-0333/ for more information about WSGI.

The most important entry point in this module is the WsgiListener method,
which accepts connections and serves HTTP requests on a socket (can be SSL).
There is also CherryPyWsgiListener, which uses the CherryPy's WSGI server
implementation in a Syncless-compatible, non-blocking way to achieve the
same goal as WsgiListener.

The convenience function RunHttpServer can be used in __main__ to run a HTTP
server forever, serving WSGI, BaseHTTPRequestHandler, CherrPy, web.py or
webapp applications.

WsgiListener takes care of error detection and recovery. The details:

* WsgiListener won't crash: it catches, reports and recovers from all I/O
  errors, HTTP request parse errors and also the exceptions raised by the
  WSGI application.
* WsgiListener won't emit an obviously invalid HTTP response (e.g. with
  binary junk in the response status code or in the response headers). It
  will emit a 400 (Bad Request) or an 500 (Internal Server Error) error page
  instead.
* WsgiListener counts the number of bytes sent in a response with
  Content-Length, and it won't ever send more than Content-Length. It also
  closes the TCP connection if too few bytes were sent.
* WsgiListener always calls the close() method of the response body iterable
  returned by the WSGI application, so the application can detect in the
  close method whether all data has been sent.
* WsgiListener prints unbloated exception stack traces when
  logging.root.setLevel(logging.DEBUG) is active.

FYI flush-after-first-body-byte is defined in the WSGI specification. An
excerpt: The start_response callable must not actually transmit the response
headers.  Instead, it must store them for the server or gateway to transmit
only after the first iteration of the application return value that yields a
non-empty string, or upon the application's first invocation of the write()
callable.  In other words, response headers must not be sent until there is
actual body data available, or until the application's returned iterable is
exhausted.  (The only possible exception to this rule is if the response
headers explicitly include a Content-Length of zero.)

Doc: WSGI server in stackless: http://stacklessexamples.googlecode.com/svn/trunk/examples/networking/wsgi/stacklesswsgi.py
Doc: WSGI specification: http://www.python.org/dev/peps/pep-0333/

TODO(pts): Validate this implementation with wsgiref.validate.
TODO(pts): Write access.log like BaseHTTPServer and CherryPy
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import errno
import logging
import re
import sys
import socket
import time
import traceback
import types

from syncless.best_stackless import stackless
from syncless import coio

# TODO(pts): Add tests.

# It would be nice to ignore errno.EBADF, errno.EINVAL and errno.EFAULT, but
# that's a performance overhead.

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

INFO = logging.INFO
DEBUG = logging.DEBUG

HEADER_WORD_LOWER_LETTER_RE = re.compile(r'(?:\A|-)[a-z]')

HEADER_KEY_RE = re.compile(r'[A-Za-z][A-Za-z-]*\Z')

HEADER_VALUE_RE = re.compile(r'[ -~]+\Z')

HTTP_RESPONSE_STATUS_RE = re.compile(r'[2-5]\d\d [A-Z][ -~]*\Z')

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

HTTP_STATUS_STRINGS = {
    400: 'Bad Request',
    500: 'Internal Server Error',
}

if issubclass(socket.error, IOError):
  # Python2.6
  IOError_all = IOError
else:
  # Python2.5
  IOError_all = (IOError, socket.error)
if getattr(socket, '_ssl', None) and getattr(socket._ssl, 'SSLError', None):
  assert issubclass(socket._ssl.SSLError, IOError)

# ---

class WsgiErrorsStream(object):
  @classmethod
  def flush(cls):
    pass

  @classmethod
  def write(cls, msg):
    # TODO(pts): Buffer on newline.
    if logging.root.level <= DEBUG:
      if msg[-1:] == '\n':
        logging.debug(msg[:-1])
      else:
        logging.debug(msg)

  @classmethod
  def writelines(cls, msgs):
    for msg in msgs:
      cls.write(msg)


class WsgiEmptyInputStream(object):
  """Empty POST data input stream sent to the WSGI application as
  env['wsgi.input'].

  The methods read, readline, readlines and __iter__ correspond to the WSGI
  specification.
  """

  bytes_read = 0

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

  @classmethod
  def discard_to_read_limit(cls):
    pass

class WsgiReadError(IOError):
  """Raised when reading the HTTP request."""


class WsgiResponseSyntaxError(IOError):
  """Raised when parsing the HTTP request."""


class WsgiResponseBodyTooLongError(IOError):
  """Raised when the HTTP response body is logner than the Content-Length."""


class WsgiWriteError(IOError):
  """Raised when writing the HTTP response."""


def GetHttpDate(at):
  now = time.gmtime(at)
  return '%s, %02d %s %4d %02d:%02d:%02d GMT' % (
      WDAY[now[6]], now[2], MON[now[1]], now[0], now[3], now[4], now[5])


def RespondWithBad(status, date, server_software, sockfile, reason):
  status_str = HTTP_STATUS_STRINGS[status]
  if reason:
    msg = '%s: %s' % (status_str, reason)
  else:
    msg = status_str
  # TODO(pts): Add Server: and Date:
  sockfile.write('HTTP/1.0 %s %s\r\n'
                 'Server: %s\r\n'
                 'Date: %s\r\n'
                 'Connection: keep-alive\r\n'
                 'Content-Type: text/plain\r\n'
                 'Content-Length: %d\r\n\r\n%s\n' %
                 (status, status_str, server_software, date, len(msg) + 1, msg))
  sockfile.flush()


def ReportAppException(exc_info, which='app'):
  exc = 'error calling WSGI %s: %s.%s: %s' % (
      which, exc_info[1].__class__.__module__, exc_info[1].__class__.__name__,
      exc_info[1])
  if logging.root.level <= DEBUG:
    exc_line1 = exc
    exc = traceback.format_exception(
        exc_info[0], exc_info[1], exc_info[2].tb_next)
    exc[:1] = [exc_line1,
               '\nTraceback of WSGI %s call (most recent call last):\n'
               % which]
    exc = ''.join(exc).rstrip('\n')
  # TODO(pts): Include the connection id in the log message.
  logging.error(exc)


def ConsumerWorker(items, is_debug):
  """Stackless tasklet to consume the rest of a wsgi_application output.

  Args:
    items: Iterable returned by the call to a wsgi_application.
    is_debug: Bool specifying whether debugging is enabled.
  """
  try:
    for data in items:  # This calls the WSGI application.
      pass
  except WsgiWriteError, e:
    if is_debug:
      logging.debug('error writing HTTP body response: %s' % e)
  except Exception, e:
    ReportAppException(sys.exc_info(), which='consume')
  finally:
    if hasattr(items, 'close'):  # According to the WSGI spec.
      try:
        items.close()
      except WsgiWriteError, e:
        if is_debug:
          logging.debug('error writing HTTP body response close: %s' % e)
      except Exception, e:
        ReportAppException(sys.exc_info(), which='consume-close')


def PrependIterator(value, iterator):
  """Iterator which yields value, then all by iterator."""
  yield value
  for item in iterator:
    yield item


def WsgiWorker(sock, peer_name, wsgi_application, default_env, date):
  # TODO(pts): Implement the full WSGI spec
  # http://www.python.org/dev/peps/pep-0333/
  if not isinstance(date, str):
    raise TypeError
  if not hasattr(sock, 'makefile_samefd'):  # isinstance(sock, coio.nbsocket)
    raise TypeError

  loglevel = logging.root.level
  is_debug = loglevel <= DEBUG
  req_buf = ''
  do_keep_alive_ary = [True]
  headers_sent_ary = [False]
  server_software = default_env['SERVER_SOFTWARE']
  if hasattr(sock, 'do_handshake'):
    # Do the SSL handshake in a non-blocking way.
    try:
      sock.do_handshake()
    except IOError_all, e:
      if is_debug:
        logging.debug('https SSL handshake failed: %s' % e)
      return
        
  sockfile = sock.makefile_samefd()
  sockfile.read_exc_class = WsgiReadError
  sockfile.write_exc_class = WsgiWriteError

  reqhead_continuation_re = REQHEAD_CONTINUATION_RE
  try:
    while do_keep_alive_ary[0]:
      do_keep_alive_ary[0] = False

      # This enables the infinite write buffer so we can buffer the HTTP
      # response headers (without a size limit) until the first body byte.
      # Please note that the use of sockfile.write_buffer_len in this
      # function prevents us from using unbuffered output.  But unbuffered
      # output would be silly anyway since we send the HTTP response headers
      # line-by-line.
      sockfile.write_buffer_limit = 2
      # Ensure there is no leftover from the previous request.
      assert not sockfile.write_buffer_len, sockfile.write_buffer_len

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
        stackless.schedule(None)

      # Read HTTP/1.0 or HTTP/1.1 request. (HTTP/0.9 is not supported.)
      # req_buf may contain some bytes after the previous request.
      if is_debug:
        logging.debug('reading HTTP request on sock=%x' % id(sock))
      try:
        while True:  # Read the HTTP request.
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
          req_new = sock.recv(8192)
          
          if not req_new:
            # The HTTP client has closed the connection before sending the headers.
            return
          if date is None:
            date = GetHttpDate(time.time())
          # TODO(pts): Ensure that refcount(req_buf) == 1 -- do the string
          # reference counters increase by slicing?
          req_buf += req_new  # Fast string append if refcount(req_buf) == 1.
          if req_buf[0] not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            if is_debug:
              logging.debug('received non-HTTP request: %r' % req_buf[:64])
            return  # Possibly https request (starts with '\x80')
          req_new = None
      except IOError_all, e:  # Raised in sock.recv above.
        if is_debug and e[0] != errno.ECONNRESET:
          logging.debug('error reading HTTP request headers: %s' % e)
        return
      # TODO(pts): Speed up this splitting?
      req_head = reqhead_continuation_re.sub(
          ', ', req_head.rstrip('\r').replace('\r\n', '\n'))
      req_lines = req_head.split('\n')
      req_line1_items = req_lines.pop(0).split(' ', 2)
      if len(req_line1_items) != 3:
        RespondWithBad(400, date, server_software, sockfile, 'bad line1')
        return  # Don't reuse the connection.
      method, suburl, http_version = req_line1_items
      if http_version not in HTTP_VERSIONS:
        RespondWithBad(400, date,
            server_software, sockfile, 'bad HTTP version: %r' % http_version)
        return  # Don't reuse the connection.
      # TODO(pts): Support more methods for WebDAV.
      if method not in HTTP_1_1_METHODS:
        RespondWithBad(400, date, server_software, sockfile, 'bad method')
        return  # Don't reuse the connection.
      if not SUB_URL_RE.match(suburl):
        # This also fails for HTTP proxy URLS http://...
        RespondWithBad(400, date, server_software, sockfile, 'bad suburl')
        return  # Don't reuse the connection.
      env['REQUEST_METHOD'] = method
      env['SERVER_PROTOCOL'] = http_version
      if is_debug:
        logging.debug(
            'on sock=%x %s %s' %
            (id(sock), method, re.sub(r'(?s)[?].*\Z', '?...', suburl)))
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
          RespondWithBad(400, date, server_software,
                                sockfile, 'bad header line')
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
            RespondWithBad(400,
                date, server_software, sockfile, 'bad content-length')
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
          RespondWithBad(400,
              date, server_software, sockfile, 'missing content')
          return
        env['wsgi.input'] = input = WsgiEmptyInputStream
      else:
        if method not in ('POST', 'PUT'):
          if content_length:
            RespondWithBad(400,
                date, server_software, sockfile, 'unexpected content')
            return
          content_length = None
          del env['CONTENT_LENGTH']
        if content_length:  # TODO(pts): Test this branch.
          # This assertion fails here if the client sends multiple very
          # small HTTP requests without waiting for the first request to be
          # served.
          if content_length < sockfile.read_buffer_len:
            RespondWithBad(400,
                date, server_software, sockfile, 'next request too early')
            return
          env['wsgi.input'] = input = sockfile
          # TODO(pts): Avoid the memcpy() in unread.
          sockfile.unread(req_buf[:content_length])
          sockfile.read_limit = content_length - sockfile.read_buffer_len
        else:
          env['wsgi.input'] = input = WsgiEmptyInputStream

      req_buf = ''  # Save memory.
      is_not_head = method != 'HEAD'
      res_content_length_ary = []
      headers_sent_ary[0] = False

      def WriteHead(data):
        """HEAD write() callback returned by StartResponse to the app."""
        data = str(data)
        if not data:
          return
        data = None  # Save memory.
        if not headers_sent_ary[0]:
          do_keep_alive_ary[0] = do_req_keep_alive
          sockfile.write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
          sockfile.write('\r\n')
          if input.discard_to_read_limit():
            raise WsgiReadError(EISDIR, 'could not discard HTTP request body')
          sockfile.flush()
          if not do_keep_alive_ary[0]:
            try:
              sock.close()
            except IOError_all, e:
              raise WsgiWriteError(*e.args)
          headers_sent_ary[0] = True

      def WriteNotHead(data):
        """Non-HEAD write() callback returned by StartResponse, to the app."""
        data = str(data)
        if not data:
          return
        if headers_sent_ary[0]:
          if res_content_length_ary:
            res_content_length_ary[1] -= len(data)
            if res_content_length_ary[1] < 0:
              sockfile.write(data[:res_content_length_ary[1]])
              raise WsgiResponseBodyTooLongError
          # Autoflush because we've set up sockfile.write_buffer_limit = 0
          # previously.
          sockfile.write(data)
        else:
          do_keep_alive_ary[0] = bool(
              do_req_keep_alive and res_content_length_ary)
          sockfile.write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
          sockfile.write('\r\n')
          if res_content_length_ary:
            res_content_length_ary[1] -= len(data)
            if res_content_length_ary[1] < 0:
              sockfile.flush()
              sockfile.write_buffer_limit = 0
              sockfile.write(data[:res_content_length_ary[1]])
              raise WsgiResponseBodyTooLongError
          if 0 < len(data) <= 65536:
            sockfile.write(data)
            sockfile.flush()
            sockfile.write_buffer_limit = 0  # Unbuffered (autoflush).
          else:
            sockfile.flush()
            sockfile.write_buffer_limit = 0  # Unbuffered (autoflush).
            sockfile.write(data)
          headers_sent_ary[0] = True
          if input.discard_to_read_limit():
            raise WsgiReadError(EISDIR, 'could not discard HTTP request body')

      def StartResponse(status, response_headers, exc_info=None):
        """Callback called by wsgi_application."""
        if not (HTTP_RESPONSE_STATUS_RE.match(status) and status[-1].strip()):
          raise WsgiResponseSyntaxError('bad HTTP response status: %r' % status)

        # Just set it to None, because we don't have to re-raise it since we
        # haven't sent any headers yet.
        exc_info = None
        if sockfile.write_buffer_len:  # StartResponse called again by an error handler.
          sockfile.discard_write_buffer()
          del res_content_length_ary[:]

        sockfile.write('%s %s\r\n' % (http_version, status))  # HTTP/1.0
        sockfile.write('Server: %s\r\n' % server_software)
        sockfile.write('Date: %s\r\n' % date)
        for key, value in response_headers:
          key = key.lower()
          if (key not in ('status', 'server', 'date', 'connection') and
              not key.startswith('proxy-') and
              # Apache responds with content-type for HEAD requests.
              (is_not_head or key not in ('content-length',
                                          'content-transfer-encoding'))):
            if key == 'content-length':
              del res_content_length_ary[:]
              try:
                res_content_length_ary.append(int(str(value)))
                # Number of bytes remaining. Checked and updated only for
                # non-HEAD respones.
                res_content_length_ary.append(res_content_length_ary[-1])
              except ValueError:
                raise WsgiResponseSyntaxError('bad content-length: %r' % value)
            elif not HEADER_KEY_RE.match(key):
              raise WsgiResponseSyntaxError('invalid key: %r' % key)
            key_capitalized = HEADER_WORD_LOWER_LETTER_RE.sub(
                lambda match: match.group(0).upper(), key)
            value = str(value).strip()
            if not HEADER_VALUE_RE.match(value):
              raise WsgiResponseSyntaxError('invalid value for key %r: %r' %
                                            (key_capitalized, value))
            # TODO(pts): Eliminate duplicate keys (except for set-cookie).
            sockfile.write('%s: %s\r\n' % (key_capitalized, value))
        # Don't flush yet.
        if is_not_head:
          return WriteNotHead
        else:
          return WriteHead

      # TODO(pts): Handle application-level exceptions here.
      try:
        items = wsgi_application(env, StartResponse) or ''
        if isinstance(items, types.GeneratorType) and not (
            sockfile.write_buffer_len or headers_sent_ary[0]):
          # Make sure StartResponse gets called now, by forcing the first
          # iteration (yield).
          try:
            item = items.next()  # Only this might raise StopIteration.
            if item:
              items = PrependIterator(item, items)
              item = None
          except StopIteration:
            item = None
      except WsgiReadError, e:
        if is_debug:
          logging.debug('error reading HTTP request body at call: %s' % e)
        return
      except WsgiWriteError, e:
        if is_debug:
          logging.debug('error writing HTTP response at call: %s' % e)
        return
      except Exception, e:
        ReportAppException(sys.exc_info(), which='start')
        if not headers_sent_ary[0]:
          # TODO(pts): Report exc on HTTP in development mode.
          sockfile.discard_write_buffer()
          try:
            RespondWithBad(500, date, server_software, sockfile, '')
          except WsgiWriteError, e:
            if is_debug:
              logging.debug('error writing HTTP response at start-500: %s' % e)
            return
          do_keep_alive_ary[0] = do_req_keep_alive
          continue
        if (do_req_keep_alive and res_content_length_ary and
            not (is_not_head and res_content_length_ary[1])):
          # The whole HTTP response body has been sent.
          do_keep_alive_ary[0] = True
          continue
        return

      try:
        if not (sockfile.write_buffer_len or headers_sent_ary[0]):
          logging.error('app has not called start_response')
          RespondWithBad(500, date, server_software, sockfile, '')
          return
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
          if headers_sent_ary[0]:
            if (res_content_length_ary and
                len(data) != res_content_length_ary[1]):
              if len(data) > res_content_length_ary[1]:
                # SUXX: wget(1) will keep retrying here.
                logging.error(
                    'truncated content: header=%d remaining=%d body=%d'
                    % (res_content_length_ary[0], res_content_length_ary[1],
                       len(data)))
                data = data[:res_content_length_ary[1] - len(data)]
              else:
                logging.error(
                    'content length too large: header=%d remaining=%d body=%d'
                    % (res_content_length_ary[0], res_content_length_ary[1],
                       len(data)))
                do_keep_alive_ary[0] = False
          else:
            if input.discard_to_read_limit():
              raise WsgiReadError(EISDIR, 'could not discard HTTP request body')
            do_keep_alive_ary[0] = do_req_keep_alive
            if res_content_length_ary:
              if len(data) != res_content_length_ary[1]:
                logging.error(
                    'invalid content length: header=%d remaining=%d body=%d' %
                    (res_content_length_ary[0], res_content_length_ary[1],
                     len(data)))
                sockfile.discard_write_buffer()
                RespondWithBad(500, date, server_software, sockfile, '')
                continue
            else:
              if is_not_head:
                sockfile.write('Content-Length: %d\r\n' % len(data))
            sockfile.write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
            sockfile.write('\r\n')
          sockfile.write(data)
          sockfile.flush()
        elif is_not_head:
          if not headers_sent_ary[0]:
            do_keep_alive_ary[0] = bool(
                do_req_keep_alive and res_content_length_ary)
            sockfile.write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
            sockfile.write('\r\n')
          # TODO(pts): Speed: iterate over `items' below in another tasklet
          # as soon as Content-Length has been reached.
          #
          # This loop just waits for the first nonempty data item in the
          # HTTP response body.
          data = ''
          if res_content_length_ary:
            if res_content_length_ary[1]:
              for data in items:
                if data:
                  break
              res_content_length_ary[1] -= len(data)
              if res_content_length_ary[1] < 0:
                logging.error('truncated first yielded content')
                sockfile.flush()
                sockfile.write_buffer_limit = 0
                sockfile.write(data[:res_content_length_ary[1]])
                continue
          else:
            for data in items:
              if data:  # Implement flush-after-first-body-byte.
                break
          if 0 < len(data) <= 65536:
            sockfile.write(data)  # Still buffering it.
            sockfile.flush()
            sockfile.write_buffer_limit = 0  # Unbuffered.
          else:
            sockfile.flush()
            sockfile.write_buffer_limit = 0  # Unbuffered.
            sockfile.write(data)
          if input.discard_to_read_limit():
            raise WsgiReadError(
                EISDIR, 'could not discard HTTP request body')
          try:  # Call the WSGI application by iterating over `items'.
            if res_content_length_ary:
              for data in items:
                sockfile.write(data)
                res_content_length_ary[1] -= len(data)
                if res_content_length_ary[1] < 0:
                  logging.error('truncated yielded content')
                  sockfile.flush()
                  sockfile.write_buffer_limit = 0
                  sockfile.write(data[:res_content_length_ary[1]])
                  break
              if res_content_length_ary[1] > 0:
                logging.error('content length too large for yeald')
                # Ignore the rest in another tasklet.
                stackless.tasklet(ConsumerWorker)(items, is_debug)
                return
            else:
              for data in items:
                sockfile.write(data)
          except (WsgiReadError, WsgiWriteError):
            raise
          except Exception, e:
            ReportAppException(sys.exc_info(), which='yield')
            return
        else:  # HTTP HEAD response.
          if not headers_sent_ary[0]:
            do_keep_alive_ary[0] = do_req_keep_alive
            sockfile.write(KEEP_ALIVE_RESPONSES[do_keep_alive_ary[0]])
            sockfile.write('\r\n')
            if input.discard_to_read_limit():
              raise WsgiReadError(
                  EISDIR, 'could not discard HTTP request body')
            sockfile.flush()
            if not do_keep_alive_ary[0]:
              try:
                sock.close()
              except IOError_all, e:
                raise WsgiWriteError(*e.args)

          # Iterate over `items' below in another tasklet, so we can read
          # the next request asynchronously from the HTTP client while the
          # other tasklet is working.
          # TODO(pts): Is this optimization safe? Limit the number of tasklets
          # to 1 to prevent DoS attacks.
          stackless.tasklet(ConsumerWorker)(items, is_debug)  # Don't run it yet.
          items = None  # Prevent double items.close(), see below.

      except WsgiReadError, e:
        # This should not happen, iteration should not try to read.
        sockfile.discard_write_buffer()
        if is_debug:
          logging.debug('error reading HTTP request at iter: %s' % e)
        return
      except WsgiWriteError, e:
        sockfile.discard_write_buffer()
        if is_debug:
          logging.debug('error writing HTTP response at iter: %s' % e)
        return
      finally:
        if hasattr(items, 'close'):  # According to the WSGI spec.
          try:
            # The close() method defined in the app will be able to detect if
            # `for data in items' has iterated all the way through. For
            # example, when StartResponse was called with a too small
            # Content-Length, some of the items will not be reached, but
            # we call close() here nevertheless.
            items.close()
          except WsgiReadError, e:
            sockfile.discard_write_buffer()
            if is_debug:
              logging.debug('error reading HTTP request at close: %s' % e)
            return
          except WsgiWriteError, e:
            sockfile.discard_write_buffer()
            if is_debug:
              logging.debug('error writing HTTP response at close: %s' % e)
            return
          except Exception, e:
            sockfile.discard_write_buffer()
            ReportAppException(sys.exc_info(), which='close')
            return
  finally:
    # Without this, when the function returns, sockfile.__del__ calls
    # sockfile.close calls sockfile.flush, which raises EBADF.
    sockfile.discard_write_buffer()
    try:
      sock.close()
    except IOError_all:
      pass
    if is_debug:
      logging.debug('connection closed sock=%x' % id(sock))

  # Don't add code here, since we have many ``return'' calls above.


def WsgiListener(server_socket, wsgi_application):
  """HTTP or HTTPS server serving WSGI, listing on server_socket.

  WsgiListener should be run in is own tasklet.

  WsgiListener supports HTTP/1.0 and HTTP/1.1 requests (but not HTTP/0.9).

  WsgiListener is robust: it detects, reports and reports errors (I/O
  errors, request parse errors, invalid HTTP responses, and exceptions
  raised in the WSGI application code).

  WsgiListener supports HTTP Keep-Alive, and it will keep TCP connections
  alive indefinitely. TODO(pts): Specify a timeout.

  Args:
    server_sock: An acceptable coio.nbsocket or coio.nbsslsocket.
  """
  if not hasattr(server_socket, 'getsockname'):
    raise TypeError
  if not callable(wsgi_application):
    raise TypeError
  env = {}
  env['wsgi.version']      = (1, 0)
  env['wsgi.multithread']  = True
  env['wsgi.multiprocess'] = False
  env['wsgi.run_once']     = False
  if hasattr(server_socket, 'do_handshake'):
    env['wsgi.url_scheme']   = 'https'
    env['HTTPS']             = 'on'     # Apache sets this
  else:
    env['wsgi.url_scheme']   = 'http'
    env['HTTPS']             = 'off'
  server_ipaddr, server_port = server_socket.getsockname()
  env['SERVER_PORT'] = str(server_port)
  env['SERVER_SOFTWARE'] = 'pts-syncless-wsgi'
  if server_ipaddr:
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = server_ipaddr
  else:  # Listens on all interfaces.
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = socket.gethostname()

  try:
    while True:
      accepted_socket, peer_name = server_socket.accept()
      date = GetHttpDate(time.time())
      if logging.root.level <= DEBUG:
        logging.debug('connection accepted from=%r' % (peer_name,))
      stackless.tasklet(WsgiWorker)(
          accepted_socket, peer_name, wsgi_application, env, date)
      accepted_socket = peer_name = None  # Help the garbage collector.
  finally:
    server_socket.close()


class FakeServerSocket(object):
  """A fake TCP server socket, used as CherryPyWSGIServer.socket."""

  __attrs__ = ['accepted_sock', 'accepted_addr']

  def __init__(self):
    self.accepted_sock = None
    self.accepted_addr = None

  def accept(self):
    """Return and clear self.accepted_sock.

    This method is called by CherryPyWSGIServer.tick().
    """
    accepted_sock = self.accepted_sock
    assert accepted_sock
    accepted_addr = self.accepted_addr
    self.accepted_sock = None
    self.accepted_addr = None
    return accepted_sock, accepted_addr

  def ProcessAccept(self, accepted_sock, accepted_addr):
    assert accepted_sock
    assert self.accepted_sock is None
    self.accepted_sock = accepted_sock
    self.accepted_addr = accepted_addr


class FakeRequests(object):
  """A list of HTTPConnection objects, for CherryPyWSGIServer.requests."""

  __slots__ = 'requests'

  def __init__(self):
    self.requests = []

  def put(self, request):
    # Called by CherryPyWSGIServer.tick().
    self.requests.append(request)


def CherryPyWsgiListener(server_sock, wsgi_application):
  """HTTP or HTTPS server serving WSGI, using CherryPy's implementation.

  This function should be run in is own tasklet.

  Args:
    server_sock: An acceptable coio.nbsocket or coio.nbsslsocket.
  """
  # !! TODO(pts): Speed: Why is CherryPy's /infinite twice as fast as ours?
  # Only sometimes.
  if not (isinstance(server_socket, coio.nbsocket) or
          isinstance(server_socket, coio.nbsslsocket)):
    raise TypeError
  if not callable(wsgi_application):
    raise TypeError
  try:
    from cherrypy import wsgiserver
  except ImportError:
    from web import wsgiserver  # Another implementation in (web.py).
  wsgi_server = wsgiserver.CherryPyWSGIServer(
      server_socket.getsockname(), wsgi_application)
  wsgi_server.ready = True
  wsgi_server.socket = FakeServerSocket()
  wsgi_server.requests = FakeRequests()
  wsgi_server.timeout = None  # TODO(pts): Fix once implemented.

  def HandshakeAndCommunicate(sock, http_connection):
    sock.do_handshake()
    sock = None
    http_connection.communicate()

  try:
    while True:
      sock, peer_name = server_socket.accept()
      if logging.root.level <= DEBUG:
        logging.debug('cpw connection accepted from=%r sock=%x' %
                      (peer_name, id(sock)))
      wsgi_server.socket.ProcessAccept(sock, peer_name)
      assert not wsgi_server.requests.requests
      wsgi_server.tick()
      assert len(wsgi_server.requests.requests) == 1
      http_connection = wsgi_server.requests.requests.pop()
      if hasattr(sock, 'do_handshake'):
        stackless.tasklet(HandshakeAndCommunicate)(sock, http_connection)
      else:
        stackless.tasklet(http_connection.communicate)()
      # Help the garbage collector free memory early.
      http_connection = sock = peer_name = None
  finally:
    sock.close()


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
    if self.wsgi_write_callback is not None:
      write_buf.append(data)
    else:
      assert data.endswith('\r\n'), [write_buf, data]
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
        # Set to `false' in case self.start_response raises an error.
        self.wsgi_write_callback = False
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


class ConstantReadLineInputStream(object):
  """Used as self.rfile in the BaseHTTPRequestHandler subclass."""

  def __init__(self, lines, body_rfile):
    self.lines_rev = list(lines)
    self.lines_rev.reverse()
    self.closed = False
    self.body_rfile = body_rfile

  def readline(self):
    if self.lines_rev:
      return self.lines_rev.pop()
    elif self.body_rfile:
      return self.body_rfile.readline()
    else:
      return ''

  def read(self, size):
    assert not self.lines_rev
    if self.body_rfile:
      return self.body_rfile.read(size)
    else:
      return ''

  def close(self):
    # We don't clear self.lines_rev[:], the hacked
    # WsgiInputStream doesn't do that eiter.
    # Don't ever close the self.body_rfile.
    self.closed = True


class FakeBaseHttpConnection(object):
  def __init__(self, env, start_response, request_lines):
    self.env = env
    self.start_response = start_response
    self.request_lines = request_lines

  def makefile(self, mode, bufsize):
    if mode.startswith('r'):
      rfile = self.env['wsgi.input']
      assert len(self.request_lines) > 1
      assert self.request_lines[-1] == '\r\n'
      assert self.request_lines[-2].endswith('\r\n')
      if isinstance(rfile, coio.nbfile):
        rfile = ConstantReadLineInputStream(self.request_lines, rfile)
      elif rfile is WsgiEmptyInputStream:
        rfile = ConstantReadLineInputStream(self.request_lines, None)
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
  """Return a WSGI application running a BaseHTTPRequestHandler."""
  BaseHTTPServer = sys.modules['BaseHTTPServer']
  if not ((isinstance(bhrh_class, type) or
           isinstance(bhrh_class, types.ClassType)) and
          issubclass(bhrh_class, BaseHTTPServer.BaseHTTPRequestHandler)):
    raise TypeError

  def WsgiApplication(env, start_response):
    request_lines = HttpRequestFromEnv(env, connection='close')
    connection = FakeBaseHttpConnection(env, start_response, request_lines)
    server = FakeBaseHttpServer()
    client_address = (env['REMOTE_ADDR'], int(env['REMOTE_PORT']))
    # So we'll get a nice HTTP/1.0 answer even for a bad request, and
    # FakeBaseHttpWFile won't complain about the missing '\r\n'. We have
    # to set it early, because th bhrh constructor handles the request.
    bhrh_class.default_request_version = 'HTTP/1.0'
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


def RunHttpServer(app, server_address=None, listen_queue_size=100):
  """Listen as a HTTP server, and run the specified application forever.

  Args:
    app: A WSGI application function, or a (web.py) web.application object.
    server_address: TCP address to bind to, e.g. ('', 8080), or None to use
      the default.
  """
  # TODO(pts): Support HTTPS in this function. See examples/demo.py for
  # HTTPS support.
  try:
    import psyco
    psyco.full()  # TODO(pts): Measure the speed in Stackless Python.
  except ImportError:
    pass
  webapp = (sys.modules.get('google.appengine.ext.webapp') or
            sys.modules.get('webapp'))
  # Use if already loaded.
  BaseHTTPServer = sys.modules.get('BaseHTTPServer')
  if webapp and isinstance(app, type) and issubclass(
      app, webapp.RequestHandler):
    logging.info('running webapp RequestHandler')
    wsgi_application = webapp.WSGIApplication(
        [('/', app)], debug=bool(coio.VERBOSE))
    assert callable(wsgi_application)
    if server_address is None:
      server_address = ('127.0.0.1', 6666)
  elif (not callable(app) and
      hasattr(app, 'handle') and hasattr(app, 'request') and
      hasattr(app, 'run') and hasattr(app, 'wsgifunc') and
      hasattr(app, 'cgirun') and hasattr(app, 'handle')):
    logging.info('running (web.py) web.application')
    wsgi_application = app.wsgifunc()
    if server_address is None:
      server_address = ('0.0.0.0', 8080)  # (web.py) default
  elif CanBeCherryPyApp(app):
    logging.info('running CherryPy application')
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
    logging.info('running BaseHTTPRequestHandler application')
    wsgi_application = BaseHttpWsgiWrapper(app)
    if server_address is None:
      server_address = ('127.0.0.1', 6666)
  elif callable(app):
    if webapp and isinstance(app, webapp.WSGIApplication):
      logging.info('running webapp WSGI application')
    else:
      logging.info('running WSGI application')

    # Check that app accepts the proper number of arguments.
    has_self = False
    if isinstance(app, type) or isinstance(app, types.ClassType):
      func = getattr(app, '__init__', None)
      assert isinstance(func, types.UnboundMethodType)
      func = func.im_func
      has_self = True
    elif isinstance(app, types.FunctionType):
      func = app
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
    assert 0, 'unsupported application type for %r' % (app,)

  server_socket = coio.nbsocket(socket.AF_INET, socket.SOCK_STREAM)
  server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server_socket.bind(server_address)
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  server_socket.listen(listen_queue_size)
  logging.info('listening on %r' % (server_socket.getsockname(),))
  # From http://webpy.org/install (using with mod_wsgi).
  WsgiListener(server_socket, wsgi_application)


def simple(server_port=8080, function=None, server_host='0.0.0.0'):
  """A simple (non-WSGI) HTTP server for demonstration purposes."""
  default_start_response_args = ('200 OK', [('Content-Type', 'text/html')])

  def WsgiApplication(env, start_response):
    is_called_ary = [False]
    def StartResponseWrapper(*args, **kwargs):
      is_called_ary[0] = True
      start_response(*args, **kwargs)
    items = function(env, StartResponseWrapper)
    if is_called_ary[0]:
      return items
    elif (isinstance(items, str) or isinstance(items, list) or
        isinstance(items, tuple)):
      start_response(*default_start_response_args)
      return items
    else:
      items = iter(items)
      for item in items:
        start_response(*default_start_response_args)
        return items

  stackless.tasklet(RunHttpServer)(
      WsgiApplication, (server_host, server_port))
  #return lambda: coio.sleep(100)
  return stackless.schedule_remove
  #RunHttpServer(WsgiApplication, (server_host, server_port))
