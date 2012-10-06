#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat Apr 24 00:25:31 CEST 2010

import errno
import os
import socket
import unittest

from syncless import coio


class NbfileTest(unittest.TestCase):
  # TODO(pts): Write more tests.

  def setUp(self):
    self.assertEqual(2, coio.stackless.getruncount())
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
    self.assertEqual(2, coio.stackless.getruncount())

  def assertRaisesErrno(self, exc_type, exc_errno, function, *args, **kwargs):
    try:
      function(*args, **kwargs)
      e = None
    except exc_type, e:
      self.assertEqual(exc_errno, e.args[0])
    if e is None:
      self.fail('not raised: %s(%r)' % (exc_type.__name__, exc_str))

  def assertRaisesStr(self, exc_type, exc_str, function, *args, **kwargs):
    try:
      function(*args, **kwargs)
      e = None
    except exc_type, e:
      self.assertEqual(exc_str, str(e))
    if e is None:
      self.fail('not raised: %s(%r)' % (exc_type.__name__, exc_str))

  def testReadLine(self):
    # This doesn't test blocking reads.
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
    reader_tasklet = coio.stackless.current
    def Appender():
      appender_calls.append(10)
      self.f.write(to_write)
      if to_write and limit:
        appender_calls.append(20)
        coio.stackless.schedule()
      else:
        appender_calls.append(20)
      if reader_tasklet.scheduled and not reader_tasklet.blocked:
        appender_calls.append(30)
      else:
        appender_calls.append(31)
        self.f.write('\n')
    coio.stackless.tasklet(Appender)()
    if to_write and limit:
      expected_calls = [10, 20]
    else:
      expected_calls = []
    self.assertEqual([expected_read, expected_calls],
                     [self.f.readline(limit), appender_calls])
    coio.stackless.schedule()
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
    # SUXX: TODO(pts): Why does this fall to an infinite loop with
    # libevent-1.4.13? It works with libev-3.9.
    # Other tests also fail on Hardy.

    # Almost 1 MB. Since Linux usually sends at most 64 kB over a pipe at a
    # time, sending and receiving 1 MB needs multiple EAGAIN for write(2),
    # thus doing a complex tasklet and libevent interaction.
    ks = 'ABCDEFGHI' * 111111
    self.AssertReadLineWait(ks, ks, len(ks))
    self.AssertReadLineWait('\n', '\n')
    ksn = ks + '\n'
    self.AssertReadLineWait(ksn, ksn + 'foo')
    self.AssertReadLineWait('foo', '', 3)

  def testTwoReaders(self):
    # libevent-1.4.13 doesn't support multiple events on the same handle,
    # libev-3.9 does support this.
    read_chars = []
    def Reader():
      read_chars.append(self.f.read(1))
    reader1_tasklet = coio.stackless.tasklet(Reader)()
    reader2_tasklet = coio.stackless.tasklet(Reader)()
    coio.stackless.schedule()
    assert not reader1_tasklet.scheduled
    assert not reader2_tasklet.scheduled
    self.f.write('ab')
    self.f.flush()
    self.assertEqual([], read_chars)
    coio.stackless.schedule()
    if coio.has_feature_multiple_events_on_same_fd():
      self.assertEqual(['a', 'b'], read_chars)
      assert not reader1_tasklet.alive
    else:
      self.assertEqual(['a'], read_chars)
      assert reader1_tasklet.alive
    assert not reader2_tasklet.alive

  def testBuffer(self):
    self.assertEqual(0, self.f.read_buffer_len)
    self.f.unread('barb')
    self.assertEqual(4, self.f.read_buffer_len)
    self.f.unread('FOO')
    self.assertEqual(7, self.f.read_buffer_len)
    self.f.unread_append('az')
    self.assertEqual(9, self.f.read_buffer_len)
    data = self.f.get_string()
    self.assertTrue(str, type(data))
    self.assertEqual('FOObarbaz', data)
    buf = self.f.get_read_buffer()
    self.assertTrue(buffer, type(buf))
    self.assertEqual('FOObarbaz', str(buf))
    buf[3 : -3] = 'BAR'
    self.assertEqual('FOOBARbaz', str(buf))
    self.assertEqual('FOObarbaz', data)
    self.assertEqual('FOOBARbaz', str(self.f.get_read_buffer()))
    self.assertEqual('OOBARbaz', str(self.f.get_read_buffer(1)))
    self.assertEqual('', str(self.f.get_read_buffer(10)))
    self.assertEqual('', str(self.f.get_read_buffer(9)))
    self.assertEqual('az', str(self.f.get_read_buffer(-2)))
    self.assertEqual('FOOBARbaz', str(self.f.get_read_buffer(-9)))
    self.assertEqual('FOOBARbaz', str(self.f.get_read_buffer(-10)))
    self.assertEqual('', str(self.f.get_read_buffer(0, -9)))
    self.assertEqual('', str(self.f.get_read_buffer(0, -10)))
    self.assertEqual('', str(self.f.get_read_buffer(5, -4)))
    self.assertEqual('R', str(self.f.get_read_buffer(5, -3)))
    self.assertEqual('R', str(self.f.get_read_buffer(-4, 6)))
    self.assertEqual('FOOBARbaz', self.f.get_string())
    self.assertEqual('OOBARbaz', self.f.get_string(1))
    self.assertEqual('', self.f.get_string(10))
    self.assertEqual('', self.f.get_string(9))
    self.assertEqual('az', self.f.get_string(-2))
    self.assertEqual('FOOBARbaz', self.f.get_string(-9))
    self.assertEqual('FOOBARbaz', self.f.get_string(-10))
    self.assertEqual('', self.f.get_string(0, -9))
    self.assertEqual('', self.f.get_string(0, -10))
    self.assertEqual('', self.f.get_string(5, -4))
    self.assertEqual('R', self.f.get_string(5, -3))
    self.assertEqual('R', self.f.get_string(-4, 6))
    self.assertEqual(-1, self.f.find('ax'))
    self.assertEqual(-1, self.f.find('ax', 10))
    self.assertEqual(-1, self.f.find('ax', 10, 20))
    self.assertEqual(-1, self.f.rfind('ax'))
    self.assertEqual(-1, self.f.rfind('ax', 10))
    self.assertEqual(-1, self.f.rfind('ax', 10, 20))
    self.assertEqual(4, self.f.find('AR'))
    self.assertEqual(1, self.f.find('O'))
    self.assertEqual(1, self.f.find('O', 1))
    self.assertEqual(2, self.f.find('O', 2))
    self.assertEqual(-1, self.f.find('O', 3))
    self.assertEqual(-1, self.f.find('AR', 10))
    self.assertEqual(-1, self.f.find('AR', 10, 20))
    self.assertEqual(4, self.f.rfind('AR'))
    self.assertEqual(4, self.f.rfind('AR', 3))
    self.assertEqual(4, self.f.rfind('AR', 4))
    self.assertEqual(-1, self.f.rfind('AR', 5))
    self.assertEqual(4, self.f.rfind('AR', 4, 6))
    self.assertEqual(-1, self.f.rfind('AR', 4, 5))
    self.assertEqual(4, self.f.rfind('AR', 4, -3))
    self.assertEqual(4, self.f.rfind('AR', -5, -3))
    self.assertEqual(4, self.f.rfind('AR', -6))
    self.assertEqual(4, self.f.rfind('AR', -5))
    self.assertEqual(-1, self.f.rfind('AR', -4))
    self.assertEqual(-1, self.f.rfind('AR', 10, 20))
    self.assertEqual(2, self.f.rfind('O'))
    self.assertEqual(2, self.f.rfind('O', 1))
    self.assertEqual(2, self.f.rfind('O', 2))
    self.assertEqual(2, self.f.rfind('O', 2))
    self.assertEqual(-1, self.f.rfind('O', 3))
    self.assertEqual(2, self.f.rfind('O', 0, 3))
    self.assertEqual(1, self.f.rfind('O', 0, 2))
    self.assertEqual(1, self.f.rfind('O', -8, -7))
    self.assertEqual(2, self.f.rfind('O', -8, -6))

  def testLongReadAll(self):
    # 200K, most Unix systems don't buffer that much on a pipe, so sending
    # this forces EAGAIN and back-and-forth switching between the writer and
    # the reader.
    data = 'FooBarBaz' * 22222

    def Writer():
      self.f.write(data)
      os.close(self.f.forget_write_fd())  # Send EOF.

    coio.stackless.tasklet(Writer)()
    self.assertEqual(data, self.f.read())
    coio.stackless.schedule()  # Make sure the reader exits.

  def testReadMoreAndReadUpto(self):
    self.f.write('foobar')
    # Reading more than requested.
    self.assertEqual(6, self.f.read_upto(2))
    self.assertEqual('foobar', self.f.get_string())
    self.assertEqual(6, self.f.read_upto(-1))
    self.assertEqual('foobar', self.f.get_string())
    self.f.write('baz')
    self.assertEqual(6, self.f.read_upto(5))
    self.assertEqual('foobar', self.f.get_string())
    self.assertEqual(6, self.f.read_upto(6))
    self.assertEqual('foobar', self.f.get_string())
    self.assertEqual(9, self.f.read_upto(7))
    self.assertEqual('foobarbaz', self.f.get_string())
    self.f.write('hi')
    self.assertEqual(0, self.f.read_more(-1))
    self.assertEqual('foobarbaz', self.f.get_string())
    self.assertEqual(2, self.f.read_more(1))
    self.assertEqual('foobarbazhi', self.f.get_string())

    def Writer():
      self.f.write('HEL')
      # This forces the loop in nbfile.read_more to run twice.
      coio.stackless.schedule()
      self.f.write('LO!')

    coio.stackless.tasklet(Writer)()
    self.assertEqual(6, self.f.read_more(5))
    self.assertEqual('foobarbazhiHELLO!', self.f.get_string())

    def EofWriter():
      self.f.write('end')
      os.close(self.f.forget_write_fd())  # Send EOF.

    coio.stackless.tasklet(EofWriter)()
    self.assertEqual(3, self.f.read_more(5))
    self.assertEqual('foobarbazhiHELLO!end', self.f.get_string())


class NbfileSocketPairTest(NbfileTest):
  def setUp(self):
    import socket
    sock1, sock2 = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    self.sock1 = sock1
    self.f = coio.nbfile(sock1.fileno(), sock2.fileno(),
                         write_buffer_limit=0, do_close=0,
                         close_ref=(sock1, sock2))

  def testClose(self):
    f = self.sock1.makefile('r')
    self.assertNotEqual(self.sock1.fileno(), f.fileno())
    f.close()
    self.sock1.getsockname()  # Must not be closed for this.
    f = self.sock1.makefile_samefd('r')
    self.assertEqual(self.sock1.fileno(), f.fileno())
    f.close()
    del f
    self.sock1.getsockname()  # Must not be closed for this.
    self.sock1.makefile('r').close()
    self.sock1.getsockname()  # Must not be closed for this.
    self.sock1.makefile_samefd('r').close()
    self.sock1.getsockname()  # Must not be closed for this.

  def testTimeout(self):
    self.sock1.settimeout(0.0)
    self.assertRaisesErrno(socket.error, errno.EAGAIN, self.sock1.recv, 1)
    self.sock1.settimeout(0.000002)
    self.assertRaisesStr(socket.timeout, 'timed out', self.sock1.recv, 1)
    sock1, sock2 = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    self.DoTestTimeout(sock1, sock1.makefile)
    self.DoTestTimeout(sock1, sock1.makefile_samefd)

  def DoTestTimeout(self, sock1, makefile_function):
    sock1.settimeout(2.5)
    f = makefile_function('r')
    self.assertEqual(2.5, f.timeout)
    f.settimeout(3.25)
    self.assertEqual(3.25, f.timeout)
    self.assertEqual(2.5, sock1.timeout)
    sock1.settimeout(4.0)
    self.assertEqual(3.25, f.timeout)
    f.settimeout(None)
    self.assertEqual(None, f.timeout)
    sock1.settimeout(None)
    self.assertEqual(None, sock1.timeout)
    
    sock1.settimeout(0.0)
    self.assertRaisesErrno(socket.error, errno.EAGAIN, sock1.recv, 1)
    f.settimeout(0)
    self.assertRaisesErrno(IOError, errno.EAGAIN, f.read, 1)
    sock1.settimeout(0.000002)
    self.assertRaisesStr(socket.timeout, 'timed out', sock1.recv, 1)
    f.settimeout(0.000002)
    self.assertRaisesStr(socket.timeout, 'timed out', f.read, 1)

  def testReadlineWithBadDelimLen(self):
    rfd, wfd = os.pipe()
    os.close(wfd)
    f = coio.fdopen(rfd)
    # Multicharacter string delimiters not allowed.
    self.assertRaises(TypeError, f.readline, delim='fo')
    # Empty string delimiters not allowed.
    self.assertRaises(TypeError, f.readline, delim='')

  def testReadlineWithDelim(self):
    self.DoTestReadlineWithDelim(False)

  def testNblimitreaderReadlineWithDelim(self):
    self.DoTestReadlineWithDelim(True)

  def DoTestReadlineWithDelim(self, use_nblimitreader):
    if use_nblimitreader:
      fdopen = lambda fd: coio.nblimitreader(coio.fdopen(fd), 654321)
    else:
      fdopen = coio.fdopen
  
    rfd, wfd = os.pipe()
    try:
      os.write(wfd, 'brakadabra')
      os.close(wfd)
      wfd = None
      f = fdopen(rfd)
      rfd = None
      self.assertEqual(('bra', 'ka', 'da', 'bra'),
                       tuple(iter(lambda: f.readline(delim='a'), '')))
    finally:
      if rfd is not None:
        os.close(rfd)
      if wfd is not None:
        os.close(wfd)

    rfd, wfd = os.pipe()
    try:
      os.write(wfd, 'abrakadabra!')
      os.close(wfd)
      wfd = None
      f = fdopen(rfd)
      rfd = None
      self.assertEqual(('a', 'bra', 'ka', 'da', 'bra', '!'),
                       tuple(iter(lambda: f.readline(delim='a'), '')))
    finally:
      if rfd is not None:
        os.close(rfd)
      if wfd is not None:
        os.close(wfd)

    rfd, wfd = os.pipe()
    try:
      os.write(wfd, 'br\xFFk\xFFd\xFFbr\xFF')
      os.close(wfd)
      wfd = None
      f = fdopen(rfd)
      rfd = None
      self.assertEqual(('br\xFF', 'k\xFF', 'd\xFF', 'br\xFF'),
                       tuple(iter(lambda: f.readline(delim='\xFF'), '')))
    finally:
      if rfd is not None:
        os.close(rfd)
      if wfd is not None:
        os.close(wfd)

    rfd, wfd = os.pipe()
    try:
      os.write(wfd, 'br\xFFk\xFFd\xFFbr\xFF')
      os.close(wfd)
      wfd = None
      f = fdopen(rfd)
      rfd = None
      self.assertEqual(
          ('br\xFF', 'k\xFF', 'd\xFF', 'br\xFF'),
          tuple(iter(lambda: f.readline(limit=3, delim='\xFF'), '')))
    finally:
      if rfd is not None:
        os.close(rfd)
      if wfd is not None:
        os.close(wfd)

    rfd, wfd = os.pipe()
    try:
      os.write(wfd, 'br\xFFk\xFFd\xFFbr\xFF')
      os.close(wfd)
      wfd = None
      f = fdopen(rfd)
      rfd = None
      self.assertEqual(
          ('br', '\xFF', 'k\xFF', 'd\xFF', 'br', '\xFF'),
          tuple(iter(lambda: f.readline(limit=2, delim='\xFF'), '')))
    finally:
      if rfd is not None:
        os.close(rfd)
      if wfd is not None:
        os.close(wfd)


if __name__ == '__main__':
  unittest.main()
