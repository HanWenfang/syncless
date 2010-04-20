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

# TODO(pts): Have a look at Concurrence (or others) for patching everything.

fake_create_connection = None

def get_fake_create_connection():
  global fake_create_connection
  if fake_create_connection is None:
    import socket
    import coio
    fake_create_connection_globals = {
        'getaddrinfo': coio.partial_getaddrinfo,
        'socket': coio.nbsocket,
        'SOCK_STREAM': socket.SOCK_STREAM,
        '_GLOBAL_DEFAULT_TIMEOUT': socket._GLOBAL_DEFAULT_TIMEOUT,
    }
    fake_create_connection = types.FunctionType(
      socket.create_connection.func_code, fake_create_connection_globals,
      None, socket.create_connection.func_defaults)
    fake_create_connection.__doc__ = (
        """Non-blocking drop-in replacement for socket.create_connection.""")
  return fake_create_connection


def _populate_socket_module_with_coio(socket_module):
  """Populate a socket module with coio non-blocking functions and classes."""
  from syncless import coio
  # There is no need to afraid that ssl.SSLSocket would pick up coio.nbsocket
  # as its base class, because when `coio' is loaded above, it loads `ssl' as
  # well, so loading `ssl' happens before the following assignment.
  socket_module.socket = coio.nbsocket
  # TODO(pts): Maybe make this a class?
  socket_module._realsocket = coio.new_realsocket
  if not hasattr(socket_module, '_socket'):
     # Create new module.
    socket_module._socket = type(socket_module)('fake_coio_c_socket')
  socket_module._socket.socket = coio.new_realsocket
  socket_module.gethostbyname = coio.gethostbyname
  socket_module.gethostbyname_ex = coio.gethostbyname_ex
  socket_module.gethostbyaddr = coio.gethostbyaddr
  socket_module.getfqdn = coio.getfqdn
  # TODO(pts): Better indicate NotImplementedError
  socket_module.getaddrinfo = None
  socket_module.getnameinfo = None
  socket_module.create_connection = get_fake_create_connection()
  return socket_module

fake_coio_socket_module = None
"""None or a fake socket module containing constants and some coio values."""

def get_fake_coio_socket_module():
  global fake_coio_socket_module
  if fake_coio_socket_module is None:
    import socket
    fake_coio_socket_module = type(socket)('fake_coio_socket')
    for name in dir(socket):
      if (name[0] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' and
          isinstance(getattr(socket, name), int)):
        setattr(fake_coio_socket_module, name, getattr(socket, name))
    _populate_socket_module_with_coio(fake_coio_socket_module)
  return fake_coio_socket_module


fake_coio_select_module = None
"""None or a fake select module containing select()."""

def get_fake_coio_select_module():
  global fake_coio_select_module
  if fake_coio_select_module is None:
    from syncless import coio
    fake_coio_select_module = type(coio)('fake_coio_select')
    fake_coio_select_module.select = coio.select
  return fake_coio_select_module


def patch_socket():
  """Monkey-patch the socket module for non-blocking I/O."""
  import socket
  _populate_socket_module_with_coio(socket)


def patch_ssl():
  """Monkey-patch the standard ssl module for non-blocking I/O."""
  import ssl
  from syncless import coio
  ssl.SSLSocket = coio.nbsslsocket
  # There is no need to patch ssl.wrap_socket since ssl.SSLSocket is already
  # patched.
  #ssl.wrap_socket = coio.ssl_wrap_socket


def patch_mysql_connector():
  from mysql.connector import connection
  connection.socket = get_fake_coio_socket_module()


def patch_pymysql():
  from pymysql import connections
  connections.socket = get_fake_coio_socket_module()


def patch_time():
  import time
  from syncless import coio
  time.sleep = coio.sleep


def patch_select():
  import select
  from syncless import coio
  select.select = coio.select
  if hasattr(select, 'poll'):
    del select.poll  # So smart libs won't try to use it.
  if hasattr(select, 'epoll'):
    del select.epoll  # So smart libs won't try to use it.


def patch_asyncore():
  import asyncore
  import select
  from syncless import coio
  select_module = type(asyncore)('fake_asyncore_select')
  # Ignore the xlist.
  select_module.select = (lambda rlist, wlist, xlist, timeout = None:
                          coio.select(rlist, wlist, (), timeout))
  select_module.error = select.error
  asyncore.select = select_module


def patch_tornado():
  import tornado.ioloop
  tornado.ioloop.select = get_fake_coio_select_module()
  # TODO(pts): Implement a faster class (similar to tornado.ioloop._EPoll),
  # with less overhead than select(2). Is it possible?
  tornado.ioloop._poll = tornado.ioloop._Select  # Class.
  def register(self, fd, events):
    if events & tornado.ioloop.IOLoop.READ: self.read_fds.add(fd)
    if events & tornado.ioloop.IOLoop.WRITE: self.write_fds.add(fd)
    # Ignore IOLoop.ERROR, since libevent con't listen on that.
  # TODO(pts): Don't we have to wrap this to an instance method?
  tornado.ioloop._Select.register = register


def ExceptHook(orig_excepthook, *args):
  from syncless import coio
  try:
    old_blocking = coio.set_fd_blocking(2, True)
    orig_excepthook(*args)
  finally:
    coio.set_fd_blocking(2, old_blocking)


def patch_stderr():
  from syncless import coio
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
  from syncless import coio
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


def fix_all_std():
  fix_ssl_makefile()
  fix_ssl_init_memory_leak()


def patch_all_std():
  fix_all_std()
  patch_socket()
  patch_ssl()
  patch_mysql_connector()
  patch_pymysql()
  patch_time()
  patch_select()
  #patch_tornado()  # Non-standard module, don't patch.
  patch_stdin_and_stdout()
  patch_stderr()

