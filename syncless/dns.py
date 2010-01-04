#! /usr/local/bin/stackless2.6

"""Asynchronous DNS lookups using dnspython and Syncless.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

Example usage:

  import stackless
  from syncless import nbio
  from syncless import dns

  def MyTasklet():
    ...
    try:
      for rdata dns.resolver.query('www.google.com', 'A'):
        print repr(rdata)
    except dns.DNSException:
      ...
    ...

  ...
  stackless.tasklet(MyTasklet)()
  ...
  nbio.RunMainLoop()

TODO(pts): Create a copy of dns.query (and other dns.* modules), don't
monkeypatch the original.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import os
import socket
import sys
import stackless
import struct

# `import dns' would do a relative import (`from . import dns'), but we want
# an absolute import.
dns = __import__('dns')  # http://www.dnspython.org/

import syncless.nbio as nbio

# Use /dev/urandom for dns.entropy instead of the default /dev/random.
dns.entropy = sys.modules['dns.entropy'] = type(sys)('dns.entropy')
dns.entropy.__builtins__ = __builtins__
dns.entropy.__doc__ = 'Fake dns.entropy module using /dev/urandom'
urandom_fd = os.open('/dev/urandom', os.O_RDONLY)
def Random16():
  s = os.read(urandom_fd, 2)
  assert len(s) == 2
  return struct.unpack('>H', s)[0]
dns.entropy.random_16 = Random16

# Import these after we've faked dns.entropy.
__import__('dns.query')
__import__('dns.resolver')
__import__('dns.exception')

def OurWaitFor(*args):
  raise NotImplementedError

dns.query._wait_for = OurWaitFor

def OurWaitForWritable(s, expiration):
  if not s.WaitForWritableExpiration(expiration):
    raise dns.exception.Timeout

dns.query._wait_for_writable = OurWaitForWritable

def OurWaitForReadable(s, expiration):
  if not s.WaitForReadableExpiration(expiration):
    raise dns.exception.Timeout
        
dns.query._wait_for_readable = OurWaitForReadable

fake_socket = type(sys)('fake_socket')
fake_socket.__builtins__ = __builtins__
fake_socket.__doc__ = 'Fake socket module replacement for dns.query.'
fake_socket.socket = nbio.NonBlockingSocket
for name in dir(socket):
  if (name.startswith('AF_') or
      name.startswith('INADDR_') or
      name.startswith('IPPROTO_') or
      name.startswith('MSG_') or
      name.startswith('PF_') or
      name.startswith('SO_') or
      name.startswith('SOCK_') or
      name.startswith('SOL_') or
      name.startswith('TCP_')):
    value = getattr(socket, name)
    if isinstance(value, int):
      setattr(fake_socket, name, value)

dns.query.socket = fake_socket

resolver = dns.resolver
exception = dns.exception
DNSException = dns.exception.DNSException
