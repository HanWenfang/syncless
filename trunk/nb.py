#! /usr/local/bin/stackless2.6
#
# example nonblocking HTTP server in Python + Stackless
# by pts@fazekas.hu at Sat Dec 19 18:09:16 CET 2009
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# Doc: http://www.disinterest.org/resource/stackless/2.6.4-docs-html/library/stackless/channels.html
# Doc: http://wiki.netbsd.se/kqueue_tutorial
# Doc: http://stackoverflow.com/questions/554805/stackless-python-network-performance-degrading-over-time
# Doc: WSGI: http://www.python.org/dev/peps/pep-0333/
#
# Asynchronous DNS for Python:
#
# * twisted.names.client from http://twistedmatrix.com
# * dnspython: http://glyphy.com/asynchronous-dns-queries-python-2008-02-09 + http://www.dnspython.org/
# * 
#
# TODO(pts): Use epoll (as in tornado--twisted).
# TODO(pts): 
# TODO(pts): Document that scheduling is not fair if there are multiple readers
#            on the same fd.
# TODO(pts): Implement broadcasting chatbot.

import errno
import fcntl
import os
import re
import select
import socket
import stackless
import sys

VERBOSE = False

def SetFdBlocking(fd, is_blocking):
  """Set a file descriptor blocking or nonblocking.

  Please note that this may affect more than expected, for example it may
  affect sys.stderr when called for sys.stdout.

  Returns:
    The old blocking value (True or False).
  """
  if hasattr(fd, 'fileno'):
    fd = fd.fileno()
  old = fcntl.fcntl(fd, fcntl.F_GETFL)
  if is_blocking:
    value = old & ~os.O_NONBLOCK
  else:
    value = old | os.O_NONBLOCK
  if old != value:
    fcntl.fcntl(fd, fcntl.F_SETFL, value)
  return bool(old & os.O_NONBLOCK)


class NonBlockingFile(object):
  def __init__(self, read_fh, write_fh, new_nbfs):
    self.write_buf = []
    self.read_fh = read_fh
    self.write_fh = write_fh
    self.read_fd = read_fh.fileno()
    assert self.read_fd >= 0
    self.write_fd = write_fh.fileno()
    assert self.write_fd >= 0
    if not isinstance(new_nbfs, list):
      raise TypeError
    self.new_nbfs = new_nbfs
    self.read_channel = stackless.channel()
    self.read_channel.preference = 1  # Prefer the sender (main task).
    self.write_channel = stackless.channel()
    self.write_channel.preference = 1  # Prefer the sender (main task).
    SetFdBlocking(self.read_fd, False)
    if self.read_fd != self.write_fd:
      SetFdBlocking(self.write_fd, False)
    # Create a circular reference which lasts until the MainLoop resolves it.
    # This should be the last operation in __init__ in case others raise an
    # exception.
    self.new_nbfs.append(self)

  def Write(self, data):
    self.write_buf.append(str(data))

  def Flush(self):
    while self.write_buf:
      # TODO(pts): Measure special-casing of len(self.write_buf) == 1.
      data = ''.join(self.write_buf)
      del self.write_buf[:]
      if data:
        try:
          written = os.write(self.write_fd, data)
        except OSError, e:
          if e.errno == errno.EAGAIN:
            written = 0
          else:
            raise
        if written == len(data):  # Everything flushed.
          break
        elif written == 0:  # Nothing flushed.
          self.write_buf.append(data)
          self.write_channel.receive()
        else:  # Partially flushed.
          # TODO(pts): Do less string copying.
          data = data[written:]
          self.write_buf.append(data)
          self.write_channel.receive()

  def Read(self, size):
    """Read at most size bytes."""
    if size <= 0:
      return ''
    # TODO(pts): Implement reading exacly `size' bytes.
    while True:
      try:
        got = os.read(self.read_fd, size)
        break
      except OSError, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_channel.receive()
    # Don't raise EOFError, sys.stdin.read() doesn't raise that either.
    #if not got:
    #  raise EOFError('end-of-file on fd %d' % self.read_fd)
    return got

  def Close(self):
    # TODO(pts): Don't close stdout or stderr.
    # TODO(pts): Assert that there is no unflushed data in the buffer.
    # TODO(pts): Add unregister functionality without closing.
    # TODO(pts): Can an os.close() block on Linux (on the handshake)?
    if self.read_fd != -1:
      # The contract is that self.read_fh.close() must call
      # os.close(self.read_fd) -- otherwise the fd wouldn't be removed from the
      # epoll set.
      self.read_fh.close()
      self.read_fd = -1
    if self.write_fd != -1:
      self.write_fh.close()
      self.write_fd = -1
    if self in self.new_nbfs:
      # TODO(pts): Faster remove.
      self.new_nbfs[:] = [nbf for nbf in self.new_nbfs if nbf is not self]

  def Accept(self):
    """Non-blocking version of socket self.read_fh.accept().

    Return:
      (accepted_nbf, peer_name)
    """
    while True:
      try:
        accepted_socket, peer_name = self.read_fh.accept()
        break
      except socket.error, e:
        if e.errno != errno.EAGAIN:
          raise
      self.read_channel.receive()
    return (NonBlockingFile(accepted_socket, accepted_socket, self.new_nbfs),
            peer_name)


def LogInfo(msg):
  Log('info: ' + str(msg))


def LogDebug(msg):
  if VERBOSE:
    Log('debug: ' + str(msg))


def Log(msg):
  """Write blockingly to stderr."""
  msg = str(msg)
  if msg and msg != '\n':
    if msg[-1] != '\n':
      msg += '\n'
    while True:
      try:
        written = os.write(2, msg)
      except OSError, e:
        if e.errno == errno.EAGAIN:
          written = 0
        else:
          raise
      if written == len(msg):
        break
      elif written != 0:
        msg = msg[written:]


# Make sure we can print the final exception which causes the death of the
# program.
orig_excepthook = sys.excepthook
def ExceptHook(*args):
  SetFdBlocking(1, True)
  SetFdBlocking(2, True)
  orig_excepthook(*args)
sys.excepthook = ExceptHook


def MainLoop(new_nbfs):
  nbfs = []
  wait_read = []
  wait_write = []
  mainc = 0
  while True:
    mainc += 1
    stackless.run()  # Until all others are blocked.
    del wait_read[:]
    del wait_write[:]
    if new_nbfs:
      nbfs.extend(new_nbfs)
      del new_nbfs[:]
    need_rebuild_nbfs = False
    for nbf in nbfs:
      if nbf.read_fd < 0 and nbf.write_fd < 0:
        need_rebuild_nbfs = True
      if nbf.read_channel.balance < 0 and nbf.read_fd >= 0:
        wait_read.append(nbf.read_fd)
      if nbf.write_channel.balance < 0 and nbf.write_fd >= 0:
        wait_write.append(nbf.write_fd)
    if need_rebuild_nbfs:
      nbfs[:] = [nbf for nbf in nbfs
                 if nbf.read_fd >= 0 and nbf.write_fd >= 0]
    if not (wait_read or wait_write):
      LogDebug('no more files open, end of main loop')
      break
      
    # TODO(pts): Use epoll(2) instead of select(2).
    timeout = None
    while True:
      if VERBOSE:
        LogDebug('select mainc=%d nbfs=%r read=%r write=%r timeout=%r' % (
            mainc,
            [(nbf.read_fd, nbf.write_fd) for nbf in nbfs],
            wait_read, wait_write, timeout))
      try:
        got = select.select(wait_read, wait_write, (), timeout)
        break
      except select.error, e:
        if e.errno != errno.EAGAIN:
          raise
    if VERBOSE:
      LogDebug('select ret=%r' % (got,))
    for nbf in nbfs:
      # TODO(pts): Allow one tasklet to wait for multiple events.
      if nbf.write_fd in got[1]:
        nbf.write_channel.send(None)
      if nbf.read_fd in got[0]:
        nbf.read_channel.send(None)


# ---

def ChatWorker(nbf):
  # TODO(pts): Let's select this from the command line.
  try:
    nbf.Write('Type something!\n')  # TODO(pts): Handle EPIPE.
    while True:
      nbf.Flush()
      s = nbf.Read(128)  # TODO(pts): Do line buffering.
      if not s:
        break
      nbf.Write('You typed %r, keep typing.\n' % s)
      # TODO(pts): Add feature to give up control during long computations.
    nbf.Write('Bye!\n')
    nbf.Flush()
  finally:
    nbf.Close()

class WsgiErrorsStream(object):
  @classmethod
  def flush(cls):
    pass

  @classmethod
  def write(cls, msg):
    # TODO(pts): Buffer on newline.
    LogDebug(msg)

  @classmethod
  def writelines(cls, msgs):
    for msg in msgs:
      cls.write(msg)

class WsgiInputStream(object):
  """POST data input stream sent to the WSGI application as env['input'].

  The methods read, readline, readlines and __iter__ correspond to the WSGI
  specification.
  """

  # TODO(pts): Add a faster implementation if readline() is not needed.
  # TODO(pts): Handle read errors without dying. (Ignore errors? The WSGI
  #            application would notice that env['CONTENT_LENGTH'] is larger.
  # TODO(pts): Make the buffering faster.

  def __init__(self, nbf, content_length):
    if not isinstance(nbf, NonBlockingFile):
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

  def ReadAndDiscardRemaining(self):
    del self.lines_rev[:]
    del self.half_line[:]
    while self.bytes_remaining > 0:
      n = min(self.bytes_remaining, 4096)
      got = len(self.nbf.Read(n))
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
    data = self.nbf.Read(min(size, self.bytes_remaining))
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
      data = nbf.Read(n)
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
  """Empty POST data input stream sent to the WSGI application as env['input'].

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


def RespondWithBadRequest(nbf, reason):
  msg = 'Bad request: ' + str(reason)
  # TODO(pts): Add Server: and Date:
  nbf.Write('HTTP/1.0 400 Bad Request\r\n'
            'Connection: close\r\n'
            'Content-Type: text/plain\r\n'
            'Content-Length: %d\r\n\r\n%s\n' % (len(msg) + 1, msg))
  nbf.Flush()

def WsgiWorker(nbf, wsgi_application, default_env):
  # TODO(pts): Implement the full WSGI spec
  # http://www.python.org/dev/peps/pep-0333/
  env = dict(default_env)
  env['wsgi.errors'] = WsgiErrorsStream
  req_buf = ''
  do_keep_alive = True
  try:
    while do_keep_alive:
      do_keep_alive = False
      # Read HTTP/1.0 or HTTP/1.1 request. (HTTP/0.9 is not supported.)
      # req_buf may contain some bytes after the previous request.
      LogDebug('reading HTTP request on nbf=%x' % id(nbf))
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
        req_new = nbf.Read(4096)
        if not req_new:
          # The HTTP client has closed the connection before sending the headers.
          return
        # TODO(pts): Ensure that refcount(req_buf) == 1 -- do the string
        # reference counters increase by slicing?
        req_buf += req_new  # Fast string append if refcount(req_buf) == 1.
        req_new = None

      # TODO(pts): Speed up this splitting?
      req_lines = req_head.rstrip('\r').replace('\r\n', '\n').split('\n')
      req_line1_items = req_lines.pop(0).split(' ', 2)
      if len(req_line1_items) != 3:
        RespondWithBadRequest(nbf, 'bad line1')
        return  # Don't reuse the connection.
      method, suburl, http_version = req_line1_items
      if http_version not in HTTP_VERSIONS:
        RespondWithBadRequest(nbf, 'bad HTTP version: %r' % http_version)
        return  # Don't reuse the connection.
      # TODO(pts): Support more methods for WebDAV.
      if method not in HTTP_1_1_METHODS:
        RespondWithBadRequest(nbf, 'bad method')
        return  # Don't reuse the connection.
      if not SUB_URL_RE.match(suburl):
        # This also fails for HTTP proxy URLS http://...
        RespondWithBadRequest(nbf, 'bad suburl')
        return  # Don't reuse the connection.
      env['REQUEST_METHOD'] = method
      env['SERVER_PROTOCOL'] = http_version
      # TODO(pts): What does appengine set here?
      env['SCRIPT_NAME'] = ''
      i = suburl.find('?')
      if i >= 0:
        env['PATH_INFO'] = suburl[:i]
        env['QUERY_STRING'] = suburl[i + 1:]
      else:
        env['PATH_INFO'] = suburl
        env['QUERY_STRING'] = ''

      content_length = None
      do_req_keep_alive = False
      for line in req_lines:
        i = line.find(':')
        if i < 0:
          RespondWithBadRequest(nbf, 'bad header line')
          return
        j = line.find(': ', i)
        if j >= 0:
          value = line[i + 2:]
        else:
          value = line[i + 1:]
        key = line[:i].lower()
        if key == 'connection':
          if value.lower() == 'keep-alive':
            do_req_keep_alive = True
        elif key == 'keep-alive':
          pass  # TODO(pts): Implement keep-alive timeout.
        elif key == 'content-length':
          try:
            content_length = int(value)
          except ValueError:
            RespondWithBadRequest(nbf, 'bad content-length')
            return
          env['CONTENT_LENGTH'] = value
        elif key == 'content-type':
          env['CONTENT_TYPE'] = value
        elif not key.startswith('proxy-'):
          env['HTTP_' + key.upper().replace('-', '_')] = value
          # TODO(pts): Maybe override SERVER_NAME and SERVER_PORT from HTTP_HOST?
          # Does Apache do this?

      if content_length is None:
        if method in ('POST', 'PUT'):
          RespondWithBadRequest(nbf, 'missing content')
          return
        env['wsgi.input'] = input = WsgiEmptyInputStream
      else:
        if method not in ('POST', 'PUT'):
          if content_length:
            RespondWithBadRequest(nbf, 'unexpected content')
            return
          content_length = None
          del env['CONTENT_LENGTH']
        if content_length:
          env['wsgi.input'] = input = WsgiInputStream(nbf, content_length)
          if len(req_buf) > content_length:
            input.AppendToReadBuffer(req_buf[:content_length])
            req_buf = req_buf[content_length:]
          elif req_buf:
            input.AppendToReadBuffer(req_buf)
            req_buf = ''
        else:
          env['wsgi.input'] = input = WsgiEmptyInputStream

      is_not_head = method != 'HEAD'
      do_generate_content_length = is_not_head
      res_content_length = None
      assert not nbf.write_buf

      def StartResponse(status, response_headers, exc_info=None):
        """Callback called by wsgi_application."""
        if nbf.write_buf:  # StartResponse called again by an error handler.
          del nbf.write_buf[:]
          do_generate_content_length = is_not_head
          res_content_length = None

        # TODO(pts): Send `Server:' header: Server: Apache
        # TODO(pts): Send `Date:' header: Date: Sun, 20 Dec 2009 12:48:56 GMT
        nbf.Write('HTTP/1.0 %s\r\n' % status)
        for key, value in response_headers:
          key_lower = key.lower()
          if (key not in ('status', 'server', 'date', 'connection') and
              not key.startswith('proxy-') and
              # Apache responds with content-type for HEAD requests.
              (is_not_head or key not in ('content-length',
                                          'content-transfer-encoding'))):
            if key == 'content-length':
              # !! TODO(pts): Cut or pad the output below at content-length.
              do_generate_content_length = False
              # TODO(pts): Handle parsing error here.
              res_content_length = int(value)
            key_capitalized = re.sub(
                HEADER_WORD_LOWER_LETTER_RE,
                lambda match: match.group(0).upper(), key_lower)
            # TODO(pts): Eliminate duplicate keys (except for set-cookie).
            nbf.Write('%s: %s\r\n' % (key_capitalized, value))
        # Don't flush yet.

      # TODO(pts): Join tuple or list response for automatic content-length
      # generation. (Don't generate it from iterator.)

      # TODO(pts): Handle application-level exceptions here.
      items = wsgi_application(env, StartResponse)
      if do_generate_content_length:
        assert res_content_length is None
        i = 0
        data0 = ''
        for data in items:
          if i > 1:
            nbf.Write(data)
            nbf.Flush()  # TODO(pts): Handle write errors (everywhere).
          elif i:  # i == 1
            nbf.Write('Connection: close\r\n')
            nbf.Write('\r\n')
            nbf.Write(data0)
            nbf.Write(data)
            nbf.Flush()
            data0 = ''
          else:
            #LogDebug('input buffer: %r % (input.half_line, input.lines_rev))
            if input.bytes_remaining:
              input.ReadAndDiscardRemaining()
            # Is this buffering contrary to the WSGI specification?
            data0 = data
          i += 1
        if i <= 1:  # Generate Content-Length if there was only a single string.
          if input.bytes_remaining:
            input.ReadAndDiscardRemaining()
          nbf.Write('Content-Length: %d\r\n' % len(data0))
          do_keep_alive = do_req_keep_alive
          nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive])
          nbf.Write('\r\n')
          nbf.Write(data0)
          nbf.Flush()
      elif is_not_head:
        do_keep_alive = do_req_keep_alive and res_content_length is not None
        nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive])
        nbf.Write('\r\n')
        for data in items:
          if input.bytes_remaining:  # TODO(pts): Check only once.
            input.ReadAndDiscardRemaining()
          nbf.Write(data)  # TODO(pts): Don't write if HEAD request.
          nbf.Flush()
      else:  # HTTP HEAD request.
        do_keep_alive = do_req_keep_alive
        nbf.Write(KEEP_ALIVE_RESPONSES[do_keep_alive])
        nbf.Write('\r\n')
        nbf.Flush()
        if not do_keep_alive:
          nbf.Close()
        for data in items:  # Run the generator function through.
          if input.bytes_remaining:  # TODO(pts): Check only once.
            input.ReadAndDiscardRemaining()

      if input.bytes_remaining:
        input.ReadAndDiscardRemaining()
      # !! TODO(pts): do cooperative scheduling with stackless
      # TODO(pts): Close the connection if the child has already closed.
  finally:
    nbf.Close()
    LogDebug('connection closed nbf=%x' % id(nbf))


def WsgiListener(nbf, wsgi_application):
  env = {}
  env['wsgi.version']      = (1, 0)
  env['wsgi.multithread']  = True
  env['wsgi.multiprocess'] = False
  env['wsgi.run_once']     = False
  env['wsgi.url_scheme']   = 'http'  # could be 'https'
  env['HTTPS']             = 'off'  # could be 'on'; Apache sets this
  server_ipaddr, server_port = nbf.read_fh.getsockname()
  env['SERVER_PORT'] = str(server_port)
  if server_ipaddr:
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = server_ipaddr
  else:
    # TODO(pts): Do a canonical name lookup.
    env['SERVER_ADDR'] = env['SERVER_NAME'] = socket.getsockname()

  try:
    while True:
      accepted_nbf, peer_name = nbf.Accept()
      if VERBOSE:
        LogDebug('connection accepted from=%r nbf=%x' %
                 (peer_name, id(accepted_nbf)))
      stackless.tasklet(WsgiWorker)(accepted_nbf, wsgi_application, env)
  finally:
    nbf.Close()


if __name__ == '__main__':
  if len(sys.argv) > 1:
    VERBOSE = True
  try:
    import psyco
    psyco.full()
  except ImportError:
    pass
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sock.bind(('127.0.0.1', 6666))
  # Reducing this has a strong negative effect on ApacheBench worst-case
  # connection times, as measured with:
  # ab -n 100000 -c 50 http://127.0.0.1:6666/ >ab.stackless3.txt
  # It increases the maximum Connect time from 8 to 9200 milliseconds.
  sock.listen(100)

  def SimpleWsgiApp(env, start_response):
    """Simplest possible application object"""
    error_stream = env['wsgi.errors']
    error_stream.write('Got env=%r\n' % env)
    import time
    status = '200 OK'
    response_headers = [('Content-type', 'text/html')]
    start_response(status, response_headers)
    if env['REQUEST_METHOD'] in ('POST', 'PUT'):
      return ['Posted/put %s.' % env['wsgi.input'].read(10)]
    elif env['PATH_INFO'] == '/hello':
      return ['Hello, <i>World</i> @ %s!\n' % time.time()]
    else:
      return ['<a href="/hello">hello</a>\n',
              '<form method="post"><input name=foo><input name=bar>'
              '<input type=submit></form>\n']

  LogInfo('listening on %r' % (sock.getsockname(),))
  new_nbfs = []
  listener_nbf = NonBlockingFile(sock, sock, new_nbfs)
  stackless.tasklet(WsgiListener)(listener_nbf, SimpleWsgiApp)
  std_nbf = NonBlockingFile(sys.stdin, sys.stdout, new_nbfs)
  stackless.tasklet(ChatWorker)(std_nbf)  # Don't run it right now.
  MainLoop(new_nbfs)
  assert 0, 'unexpected end of main loop'
