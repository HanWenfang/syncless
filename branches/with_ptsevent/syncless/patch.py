#! /usr/local/bin/stackless2.6

"""Functions for monkey-patching Python libraries to use Syncless.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys
import types
from syncless import coio

# TODO(pts): Have a look at Concurrence (or others) for patching everything.

def patch_socket():
  """Monkey-patch the socket module for non-blocking I/O."""
  import socket
  socket.socket = nbsocket
  # TODO(pts): Maybe make this a class?
  socket._realsocket = new_realsocket
  socket._socket.socket = new_realsocket
  socket.gethostbyname = gethostbyname
  socket.gethostbyname_ex = gethostbyname_ex
  socket.gethostbyaddr = gethostbyaddr
  socket.getfqdn = getfqdn
  # TODO(pts): Better indicate NotImplementedError
  socket.getaddrinfo = None
  socket.getnameinfo = None

def patch_time():
  import time
  time.sleep = sleep

def ExceptHook(orig_excepthook, *args):
  try:
    old_blocking = coio.set_fd_blocking(2, True)
    orig_excepthook(*args)
  finally:
    coio.set_fd_blocking(2, old_blocking)

def patch_stderr():
  # !! add line buffering (or copy it)
  if not isinstance(sys.stderr, coio.nbfile):
    new_stderr = coio.fdopen(sys.stderr.fileno(), 'w', bufsize=0, do_close=0)
    logging = sys.modules.get('logging')
    if logging:
      for handler in logging.root.handlers:
        stream = getattr(handler, 'stream', None)
        if stream is sys.stderr:
          handler.stream = new_stderr
    sys.stderr = new_stderr
    # Make sure we can print the final exception which causes the death of the
    # program.
    orig_excepthook = sys.excepthook
    sys.excepthook = lambda *args: ExceptHook(orig_excepthook, *args)

def patch_stdin_and_stdout():
  # !! patch stdin and stdout separately (for sys.stdout.fileno())
  if (not isinstance(sys.stdin,  coio.nbfile) or
      not isinstance(sys.stdout, coio.nbfile)):
    # Unfortunately it's not possible to get the current buffer size from a
    # Python file object, so we just set up the defaults here.
    write_buffer_limit = 8192
    import os
    if os.isatty(sys.stdout.fileno()):
      write_buffer_limit = 1  # Set up line buffering.
    new_stdinout = coio.nbfile(sys.stdin.fileno(), sys.stdout.fileno(),
                               write_buffer_limit=write_buffer_limit,
                               do_close=0)
    sys.stdin = sys.stdout = new_stdinout

def fix_ssl_makefile():
  """Fix the reference counting in ssl.SSLSocket.makefile().
  
  This is the reference counting bugfix (close=True) for Stackless 2.6.4.
  """
  try:
    import ssl
  except ImportError:
    ssl = None
  if ssl:
    import socket
    def SslMakeFileFix(self, mode='r', bufsize=-1):
      self._makefile_refs += 1
      return socket._fileobject(self, mode, bufsize, close=True)
    ssl.SSLSocket.makefile = types.MethodType(
        SslMakeFileFix, None, ssl.SSLSocket)

def fix_ssl_init_memory_leak():
  """Fix the memory leak in ssl.SSLSocket.__init__ in Python 2.6.4.

  ssl.SSLSocket.__init__ has code like this:

    self.send = lambda data, flags=0: SSLSocket.send(self, data, flags)

  It could have been this simple, and it would still produce a memory leak:
  
    self.foo = lambda: self

  This creates a circular reference (self -> __init__ -> lambda -> self),
  which prevents self._sock from being automatically closed when self goes out
  of scope.

  The fix just removes those lambdas (and function attributes created by
  socket.socket.__init__ as well). This fixes the memory leak, and provides
  correct behavior.
  """
  try:
    import ssl
  except ImportError:
    return
  import socket
  import types
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  if ssl.SSLSocket(sock).recv is sock._sock.recv:
    del sock
    # TODO(pts): Don't create a socket.socket just for the detection above.
    old_init = ssl.SSLSocket.__init__.im_func
    def SslInitFix(*args, **kwargs):
      self = args[0]
      try:
        old_init(*args, **kwargs)
      finally:
        if self.recv.func_name == '<lambda>':
          for attr in socket._delegate_methods:
            delattr(self, attr)
    ssl.SSLSocket.__init__ = types.MethodType(SslInitFix, None, ssl.SSLSocket)


def validate_new_sslsock(**kwargs):
  """Validate contructor arguments of ssl.SSLSocket.

  Validate SSL parameter constructor arguments of ssl.SSLSocket. This is useful
  to check if the specified keyfile= and certfile= exist and have a valid
  format etc.

  Normal ssl.SSLSocket does the validation only upon connect() or accept().

  Args:
    kwargs: keyfile=, certfile=, cert_reqs=, ssl_version=, ca_certs=
      (some of them can be missing)
  """
  import errno
  import ssl
  import socket
  nsock = socket._realsocket(socket.AF_INET, socket.SOCK_STREAM)
  try:
    nsslobj = ssl._ssl.sslwrap(
        nsock, False,
        kwargs.get('keyfile'),
        kwargs.get('certfile'),
        kwargs.get('cert_reqs', ssl.CERT_NONE),
        kwargs.get('ssl_version', ssl.PROTOCOL_SSLv23),
        kwargs.get('ca_certs'))
    try:
      nsslobj.do_handshake()
    except socket.error, e:
      if e.errno not in (errno.EPIPE, errno.ENOTCONN):
        raise
  finally:
    nsock.close()


def fix_all():
  fix_ssl_makefile()
  fix_ssl_init_memory_leak()


def patch_all():
  fix_all()
  patch_socket()
  patch_time()
  patch_stdin_and_stdout()
  patch_stderr()
