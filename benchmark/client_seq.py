#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Thu Jan  7 14:45:06 CET 2010

import re
import socket
import sys

RESPONSE_RE = re.compile(r'(?s)\AHTTP\/1[.][01] 200 OK(?=\r\n).*?\n\r?\n')
NEXT_RE = re.compile(r'<a\s+href="/(\d+)"')

def DoRequest(sub_url='/'):
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  try:
    s.connect(('127.0.0.1', 8080))
    s.sendall('GET %s HTTP/1.0\r\n\r\n' % sub_url)
    response = []
    while True:
      block = s.recv(32768)
      if not block:
        break
      response.append(block)
    return ''.join(response)
  finally:
    s.close()

if __name__ == '__main__':
  res = DoRequest('/')
  assert RESPONSE_RE.match(res), repr(res)
  if len(sys.argv) > 1:
    c = int(sys.argv[1:])
  else:
    c = 10000
  print >>sys.stderr, 'doing %d fetches' % c
  num = 0
  for i in xrange(c):
    res = DoRequest('/%s' % num)
    match = RESPONSE_RE.match(res)
    assert match
    match = NEXT_RE.search(res[match.end(0):])
    assert match, res
    num = int(match.group(1))
  print >>sys.stderr, 'final num=%d' % num
