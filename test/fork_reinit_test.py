#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon May 10 16:02:46 CEST 2010

"""Test for calling coio.reinit() after a os.fork().

This test demonstrates that coio.reinit() has to be called after a
os.fork(), otherwise some notifications may get lost because both the child
and the parent process use the same shared file descriptor for notification.

This script runs two instances of RunWorker (one in the parent process, and
one in the child process). An instance of RunWorker sends lines of linearly
increasing size on a pipe (or socketpair), and reads lines from another
pipe, and finally it verifies that it got the same number of bytes and lines
as expected.

See also examples/demo_fork_reinit.py .

If coio.reinit() is not called properly, this test hangs indefinitely or the
child segfaults.

Unfortunately this test is a bit slow (takes 0.3 second).
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import os
import socket
import sys
import unittest

unpatched_fork = os.fork

from syncless import coio
from syncless import patch

def RunWorker(sock_in, sock_out, max_size):
  #f_in = sock_in.makefile('r+')
  f_out = sock_out.makefile('r+')
  byte_count = 0
  line_count = 0
  min_size = max(max_size - 1000, 1)
  expected_line_count = max_size - min_size + 1
  expected_byte_count = (max_size + min_size) * (max_size - min_size + 1) / 2
  for i in xrange(min_size, max_size + 1):
    data = '*' * (i - 1) + '\n'
    f_out.write(data)
    f_out.flush()
    while sock_in and coio.select([sock_in], (), (), 0)[0]:
      data = sock_in.recv(8192)
      if data:
        byte_count += len(data)
        line_count += data.count('\n')
      else:
        sock_in = None
  sock_out.shutdown(1)  # Shut down for writing.
  if sock_in:  # Read the rest.
    while True:
      data = sock_in.recv(8192)
      if not data:
        break
      byte_count += len(data)
      line_count += data.count('\n')
  assert byte_count == expected_byte_count
  assert line_count == expected_line_count

class ForkReinitTest(unittest.TestCase):

  MAX_SIZE = 20000
  """Maximum line length in bytes to send up to."""

  def testWithoutPatch(self):
    a, b = coio.socketpair()
    pid = unpatched_fork()
    if pid:  # Parent.
      try:
        a = a.dup()
        b = b.dup()
        RunWorker(b, a, self.MAX_SIZE)
      finally:
        got_pid, status = os.waitpid(pid, 0)
        assert got_pid == pid
      assert status == 0, 'child exited with status 0x%x' % status
    else:
      try:
        # Without coio.reinit() this the child may crash (segfault) or time
        # out.
        coio.reinit()
        RunWorker(a, b, self.MAX_SIZE)
        os._exit(0)
      except:
        sys.stderr.write(sys.exc_info())
        os._exit(1)

  def testWithPatch(self):
    patch.patch_os()
    assert os.fork is not unpatched_fork
    a, b = coio.socketpair()
    pid = os.fork()
    if pid:  # Parent.
      try:
        a = a.dup()
        b = b.dup()
        RunWorker(b, a, self.MAX_SIZE)
      finally:
        got_pid, status = os.waitpid(pid, 0)
        assert got_pid == pid
      assert status == 0, 'child exited with status 0x%x' % status
    else:
      try:
        # No need for coio.reinit(), our patched fork does that.
        RunWorker(a, b, self.MAX_SIZE)
        os._exit(0)
      except:
        sys.stderr.write(sys.exc_info())
        os._exit(1)
    

if __name__ == '__main__':
  unittest.main()
