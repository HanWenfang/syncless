#! /usr/local/bin/stackless2.6

import gc
import socket
import ssl
import types
import unittest
from syncless import coio
from syncless import patch

orig_sslsocket_init = ssl.SSLSocket.__init__

class SslInitMemoryLeakTest(unittest.TestCase):
  def testPatchedSslSocket(self):
    patch.fix_ssl_init_memory_leak()
    self.assertFalse(self.IsLeaking(ssl.SSLSocket))

  def testOrigSslSocket(self):
    ssl.SSLSocket.__init__ = orig_sslsocket_init
    print '(orig SSLSocket leaking: %r)' % self.IsLeaking(ssl.SSLSocket)

  def testNbSslSocket(self):
    ssl.SSLSocket.__init__ = orig_sslsocket_init
    self.assertFalse(self.IsLeaking(coio.nbsslsocket))
  
  def IsLeaking(self, sslsocket_impl):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    gc.disable()
    gc.collect()
    count0 = gc.get_count()[0]
    for i in xrange(1000):
      sslsocket_impl(sock)
    count1 = gc.get_count()[0]
    self.assertTrue(count1 >= count0)
    return count1 - count0 >= 1000

if __name__ == '__main__':
  unittest.main()
