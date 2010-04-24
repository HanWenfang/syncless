#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat Apr 24 00:25:31 CEST 2010

import stackless
import os
import unittest

from syncless import coio


class NbfileTest(unittest.TestCase):
  # TODO(pts): Write more tests.

  def setUp(self):
    try:
      read_fd, write_fd = os.pipe()
      self.f = coio.nbfile(read_fd, write_fd, write_buffer_limit=0,
                           do_close=1)
      read_fd = None
    finally:
      if read_fd is not None:  # Construction failed.
        os.close(read_fd)
        os.close(write_fd)

  def tearDown(self):
    self.f.close()

  def testReadLine(self):
    # TODO(pts): Add tests for the tasklet waiting in I/O.
    self.assertEqual('', self.f.readline(0))
    self.f.write('foobarbaz')
    self.assertEqual('', self.f.readline(0))
    self.assertEqual('fo', self.f.readline(2))
    self.assertEqual('oba', self.f.readline(3))
    self.f.write('X\n\nYZ\n')
    self.assertEqual('r', self.f.readline(1))
    self.assertEqual('', self.f.readline(0))
    self.assertEqual('bazX\n', self.f.readline())
    self.assertEqual('', self.f.readline(0))
    self.assertEqual('\n', self.f.readline())
    self.assertEqual('YZ\n', self.f.readline())
    self.f.write('\nABC')
    self.assertEqual('\n', self.f.readline(1))
    self.assertEqual('ABC', self.f.readline(3))

  def AssertReadLineWait(self, expected_read, to_write, limit=-1):
    appender_calls = []
    reader_tasklet = stackless.current
    def Appender():
      appender_calls.append(10)
      self.f.write(to_write)
      if to_write and limit:
        appender_calls.append(20)
        stackless.schedule()
      else:
        appender_calls.append(20)
      if reader_tasklet.scheduled and not reader_tasklet.blocked:
        appender_calls.append(30)
      else:
        appender_calls.append(31)
        self.f.write('\n')
    stackless.tasklet(Appender)()
    if to_write and limit:
      expected_calls = [10, 20]
    else:
      expected_calls = []
    self.assertEqual([expected_read, expected_calls],
                     [self.f.readline(limit), appender_calls])
    stackless.schedule()
    self.assertEqual([10, 20, 30], appender_calls)

  def testReadLineWait(self):
    self.AssertReadLineWait('foo', 'foo\nbar\nbaz\n', 3)
    self.AssertReadLineWait('\n', '')
    self.AssertReadLineWait('bar\n', '')
    self.AssertReadLineWait('baz\n', '')
    self.AssertReadLineWait('', '', 0)
    self.AssertReadLineWait('', 'foo', 0)
    self.AssertReadLineWait('foo', '', 3)

  def testReadLineLongLine(self):
    # Almost 1 MB. Since Linux usually sends at most 64 kB over a pipe at a
    # time, sending and receiving 1 MB needs multiple EAGAIN for write(2),
    # thus doing a complex tasklet and libevent interaction.
    ks = 'ABCDEFGHI' * 111111
    self.AssertReadLineWait(ks, ks, len(ks))
    self.AssertReadLineWait('\n', '\n')
    ksn = ks + '\n'
    self.AssertReadLineWait(ksn, ksn + 'foo')
    self.AssertReadLineWait('foo', '', 3)

  def ZZZtestTwoReaders(self):
    # !!! SUXX: libevent-1.4.13 doesn't support this.
    read_chars = []
    def Reader():
      read_chars.append(self.f.read(1))
    reader1_tasklet = stackless.tasklet(Reader)()
    reader2_tasklet = stackless.tasklet(Reader)()
    stackless.schedule()
    assert not reader1_tasklet.scheduled
    assert not reader2_tasklet.scheduled
    self.f.write('ab')
    self.f.flush()
    stackless.schedule()
    stackless.schedule()
    stackless.schedule()
    print read_chars


class NbfileSocketPairTest(NbfileTest):
  def setUp(self):
    import socket
    sock1, sock2 = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    self.f = coio.nbfile(sock1.fileno(), sock2.fileno(),
                         write_buffer_limit=0, do_close=0,
                         close_ref=(sock1, sock2))

if __name__ == '__main__':
  unittest.main()
