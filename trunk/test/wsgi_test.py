#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sat Apr 24 00:25:31 CEST 2010

import logging
import socket
import sys
import unittest
from syncless import coio
from syncless import wsgi


def TestApplication(env, start_response):
  if env['PATH_INFO'] == '/answer':
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return ('Forty-two.',)
  if env['PATH_INFO'] == '/':
    start_response('200 OK', [('Content-Type', 'text/html')])
    return ['Hello, World!']
  if env['PATH_INFO'] == '/save':
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [env['wsgi.input'].readline().upper()]
  # A run-time error caught by the wsgi moduel if this is reached.


TEST_DATE = wsgi.GetHttpDate(1234567890)  # 2009-02-13


def CallWsgiWorker(accepted_socket, do_multirequest=True):
  env = {}
  wsgi.PopulateDefaultWsgiEnv(env, ('127.0.0.1', 80))
  peer_name = ('127.0.0.1', 2)
  wsgi.WsgiWorker(accepted_socket, peer_name, TestApplication, env, TEST_DATE,
                  do_multirequest)

def ParseHttpResponse(data):
  head = 'Status: '
  i = data.find('\n\n')
  j = data.find('\n\r\n')
  if i >= 0 and i < j:
    head += data[:i]
    body = data[i + 2:]
  elif j >= 0:
    head += data[:j]
    body = data[j + 3:]
  else:
    raise ValueError('missing HTTP response headers: %r' % data)
  # TODO(pts): Don't parse line continuations.
  head = dict(line.split(': ', 1) for line in
              head.rstrip('\r').replace('\r\n', '\n').split('\n'))
  return head, body


def SplitHttpResponses(data):
  """Split a string containing multiple HTTP responses.
  
  Returns:
    List of strings (individual HTTP responses).
  """
  return ['HTTP/1.' + item for item in data.split('HTTP/1.')[1:]]


class WsgiTest(unittest.TestCase):
  # TODO(pts): Write more tests, especially for error responses.
  # TODO(pts): Test HEAD requests.

  def testDate(self):
    self.assertEqual('Fri, 13 Feb 2009 23:31:30 GMT', TEST_DATE)

  def AssertHelloResponse(self, head, body, http_version='1.0'):
    self.assertEqual('Hello, World!', body)
    self.assertEqual('HTTP/%s 200 OK' % http_version, head['Status'])
    self.assertEqual('13', head['Content-Length'])
    self.assertTrue('syncless' in head['Server'].lower(), head['Server'])
    self.assertEqual(TEST_DATE, head['Date'])
    self.assertEqual('text/html', head['Content-Type'])

  def AssertAnswerResponse(self, head, body, http_version='1.0',
                           is_new_date=False):
    self.assertEqual('Forty-two.', body)
    self.assertEqual('HTTP/%s 200 OK' % http_version, head['Status'])
    self.assertEqual('10', head['Content-Length'])
    self.assertTrue('syncless' in head['Server'].lower(), head['Server'])
    if is_new_date:
      self.assertNotEqual(TEST_DATE, head['Date'])
      self.assertTrue(head['Date'].endswith(' GMT'), head['Date'])
    else:
      self.assertEqual(TEST_DATE, head['Date'])
    
    self.assertEqual('text/plain', head['Content-Type'])

  def AssertSaveResponse(self, head, body, http_version='1.0',
                         is_new_date=False, msg='FOO\n'):
    self.assertEqual(msg, body)
    self.assertEqual('HTTP/%s 200 OK' % http_version, head['Status'])
    self.assertEqual(str(len(msg)), head['Content-Length'])
    self.assertTrue('syncless' in head['Server'].lower(), head['Server'])
    if is_new_date:
      self.assertNotEqual(TEST_DATE, head['Date'])
      self.assertTrue(head['Date'].endswith(' GMT'), head['Date'])
    else:
      self.assertEqual(TEST_DATE, head['Date'])
    
    self.assertEqual('text/plain', head['Content-Type'])

  def testSingleRequestWithoutCr(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('GET / HTTP/1.0\n\n')
    b.shutdown(1)
    CallWsgiWorker(a)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('close', head['Connection'])
    self.AssertHelloResponse(head, body)

  def testSingleGetRequest(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('GET / HTTP/1.0\r\n\r\n')
    b.shutdown(1)
    CallWsgiWorker(a)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('close', head['Connection'])
    self.AssertHelloResponse(head, body)

  def testSinglePostRequest(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('POST /save HTTP/1.0\r\nContent-Length: 7\r\n\r\nfoo\nbar')
    b.shutdown(1)
    CallWsgiWorker(a)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('close', head['Connection'])
    self.AssertSaveResponse(head, body)

  def testContinuableHTTP10Request(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('GET / HTTP/1.0\r\nConnection: keep-alive\r\n\r\n')
    b.shutdown(1)
    CallWsgiWorker(a)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertHelloResponse(head, body)

  def testContinuableHTTP11Request(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('GET /?foo=bar HTTP/1.1\r\n\r\n')
    b.shutdown(1)
    CallWsgiWorker(a)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertHelloResponse(head, body, http_version='1.1')

  def testTwoSequentialHTTP11GetFirstRequests(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('GET / HTTP/1.1\r\n\r\n')
    CallWsgiWorker(a, do_multirequest=False)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertHelloResponse(head, body, http_version='1.1')
    b.sendall('GET /answer?foo=bar HTTP/1.1\r\n\r\n')
    b.shutdown(1)
    CallWsgiWorker(a)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertAnswerResponse(head, body, http_version='1.1')

  def testTwoSequentialHTTP11PostFirstRequests(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('POST /save HTTP/1.1\r\nContent-Length: 7\r\n\r\nfoo\nbar')
    CallWsgiWorker(a, do_multirequest=False)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertSaveResponse(head, body, http_version='1.1')
    b.sendall('GET /answer?foo=bar HTTP/1.1\r\n\r\n')
    b.shutdown(1)
    CallWsgiWorker(a)
    head, body = ParseHttpResponse(b.recv(8192))
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertAnswerResponse(head, body, http_version='1.1')

  def testThreePipelinedHTTP11GetRequests(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('GET / HTTP/1.1\r\n\r\n'
              'GET /answer?foo=x+y&bar= HTTP/1.0\r\n\r\n'
              'GET /unreached... HTTP/1.1\r\n\r\n')
    CallWsgiWorker(a)
    responses = SplitHttpResponses(b.recv(8192))
    # The WsgiWorker doesn't respond to request 2 (/unreached...), because
    # the previous request was a HTTP/1.0 request with default Connection:
    # close (so keep-alive is false).
    self.assertEqual(2, len(responses))
    head, body = ParseHttpResponse(responses[0])
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertHelloResponse(head, body, http_version='1.1')
    head, body = ParseHttpResponse(responses[1])
    self.assertEqual('close', head['Connection'])
    self.AssertAnswerResponse(head, body, http_version='1.0',
                              is_new_date=True)

  def testFourPipelinedHTTP11PostFirstRequests(self):
    a, b = coio.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    b.sendall('POST /save HTTP/1.1\r\nContent-Length: 7\r\n\r\nfoo\nbar'
              'POST /save HTTP/1.1\r\nContent-Length: 10\r\n\r\nNice!\ngood'
              'GET /answer?foo=x+y&bar= HTTP/1.0\r\n\r\n'
              'GET /unreached... HTTP/1.1\r\n\r\n')
    CallWsgiWorker(a)
    responses = SplitHttpResponses(b.recv(8192))
    self.assertEqual(3, len(responses))
    head, body = ParseHttpResponse(responses[0])
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertSaveResponse(head, body, http_version='1.1')
    head, body = ParseHttpResponse(responses[1])
    self.assertEqual('Keep-Alive', head['Connection'])
    self.AssertSaveResponse(head, body, http_version='1.1',
                            msg='NICE!\n', is_new_date=True)
    head, body = ParseHttpResponse(responses[2])
    self.assertEqual('close', head['Connection'])
    self.AssertAnswerResponse(head, body, http_version='1.0',
                              is_new_date=True)


if __name__ == '__main__':
  if '-v' in sys.argv[1:]:
    logging.BASIC_FORMAT = '[%(created)f] %(levelname)s %(message)s'
    logging.root.setLevel(logging.DEBUG)
  unittest.main()
