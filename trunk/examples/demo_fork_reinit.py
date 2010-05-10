#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon May 10 15:18:13 CEST 2010

"""Demonstration that coio.reinit() has to be called after a os.fork().

This script demonstrates that coio.reinit() has to be called after a
os.fork(), otherwise some notifications may get lost because both the child
and the parent process use the same shared file descriptor for notification.
The result is: the process waits forever for a notification which it never
receives.

This script runs two instances of RunWorker (one in the parent process, and
one in the child process). An instance of RunWorker sends lines of linearly
increasing size on a pipe (or socketpair), and reads lines from another
pipe, and finally it verifies that it got the same number of bytes and lines
as expected.

Try this with libevent1 or libevent2, with epoll as the notification method
(don't use select(), it will not fail) without command-line arguments.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import fcntl
import os
import select
import signal
import socket
import sys

from syncless import coio
from syncless import patch

def EnableAppendMode(fd):
  if not isinstance(fd, int):
    fd = fd.fileno()
  fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_APPEND)

def RunWorker(sock_in, sock_out, max_size, progress_str, select_function):
  #f_in = sock_in.makefile('r+')
  f_out = sock_out.makefile('r+')
  byte_count = 0
  line_count = 0
  expected_line_count = max_size
  expected_byte_count = (max_size + 1) * max_size / 2
  for i in xrange(1, max_size + 1):
    data = '*' * (i - 1) + '\n'
    f_out.write(data)
    f_out.flush()
    while sock_in and select_function([sock_in], (), (), 0)[0]:
      data = sock_in.recv(8192)
      if data:
        byte_count += len(data)
        line_count += data.count('\n')
      else:
        sock_in = None
    sys.stdout.write(progress_str)
    sys.stdout.flush()
  sock_out.shutdown(1)  # Shut down for writing.
  sys.stdout.write('/' + progress_str)
  sys.stdout.flush()
  if sock_in:  # Read the rest.
    while True:
      data = sock_in.recv(8192)
      if not data:
        break
      byte_count += len(data)
      line_count += data.count('\n')
  assert byte_count == expected_byte_count
  assert line_count == expected_line_count
  sys.stdout.write('$' + progress_str)
  sys.stdout.flush()

if __name__ == '__main__':
  a, b = coio.socketpair()
  select_function = coio.select
  #a, b = socket.socketpair()
  #select_function = select.select

  #a, b = socket.socketpair()
  max_size = 20000
  # So we don't lose characters when writing the output to a file.
  EnableAppendMode(sys.stdout)
  EnableAppendMode(sys.stderr)
  pid = os.fork()
  # signal.alarm(10) won't help here.
  if pid:  # Parent.
    try:
      a = a.dup()
      b = b.dup()
      RunWorker(b, a, max_size, 'P', select_function)
    finally:
      got_pid, status = os.waitpid(pid, 0)
      assert got_pid == pid
    assert status == 0, 'child exited with status 0x%x' % status
    print >>sys.stderr, 'ok'
  else:
    if len(sys.argv) > 1:
      coio.reinit()
    RunWorker(a, b, max_size, 'C', select_function)
    raise SystemExit
