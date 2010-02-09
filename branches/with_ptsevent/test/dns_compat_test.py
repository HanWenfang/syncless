#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Tue Feb  2 21:18:10 CET 2010

import cStringIO
import syncless.coio
import socket
import unittest

# TODO(pts): Test reverse lookup without canonical name.
# TODO(pts): Test for IPv6 addresses:
#    print syncless.coio.dns_resolve_ipv6('www.ipv6.org')
#: <dnsresult code=0, t=3, ttl=2936 value=['2001:6b0:1:ea:202:a5ff:fecd:13a6'] at 0xb7d76d24>
#    print syncless.coio.dns_resolve_reverse('2001:6b0:1:ea:202:a5ff:fecd:13a6')
#: <dnsresult t=2, ttl=3446 values=['igloo.stacken.kth.se'] at 0x824226c>

ERR_NODATA = set([1])
ERR_ADDRFAMILY = set([2])
ERR_HOST_NOT_FOUND = set([3])
ERR_NONAME = set([4])


RESOLVE_IPV4_RESULT = {
    '152.66.84.8':         ['152.66.84.8'],
    '127.5.6.7':           ['127.5.6.7'],
    '74.125.39.106':       ['74.125.39.106'],
    'mail.szit.bme.hu':    ['152.66.84.8'],
    'fourier.szit.bme.hu': ['152.66.84.8'],
    'www.google.com':      ['74.125.39.106', '74.125.39.103',
                            '74.125.39.147', '74.125.39.104',
                            '74.125.39.105', '74.125.39.99'],
    'www.l.google.com':    ['74.125.39.106', '74.125.39.103',
                            '74.125.39.147', '74.125.39.104',
                            '74.125.39.105', '74.125.39.99'],
    'foo.bar.baz':         None,
    'www.ipv6.org':        ['130.237.234.40'],
    'unknown':             None,
}

GETHOSTBYNAME_RESULT = {
    'other':               '1.2.3.5',
    '1.2.3.5':             '1.2.3.5',
    'bogus3':              '1.2.3.4',
    'bogus4.foo.bar':      '1.2.3.4',
    '1.2.3.4':             '1.2.3.4',
    'localhost':           '127.0.0.1',
    '127.0.0.1':           '127.0.0.1',
    '127.5.6.7':           '127.5.6.7',
    '152.66.84.8':         '152.66.84.8',
    '2001:6b0:1:ea:202:a5ff:fecd:13a6': ERR_ADDRFAMILY,
    '74.125.39.106':       '74.125.39.106',
    'foo.bar.baz':         ERR_NODATA,
    'fourier.szit.bme.hu': '152.66.84.8',
    'mail.szit.bme.hu':    '152.66.84.8',
    'www.google.com':      '74.125.39.106',
    'www.l.google.com':    '74.125.39.106',
    'www.ipv6.org':        '130.237.234.40',
}

# Item 1 is usually empty except for hostnames fetched from /etc/hosts.
GETHOSTBYADDR_RESULT = {
    'bogus3': ('bogus1.there',
               ['bogus2', 'bogus3', 'bogus4.foo.bar'], ['1.2.3.4']),
    'bogus4.foo.bar':  ('bogus1.there',
                        ['bogus2', 'bogus3', 'bogus4.foo.bar'], ['1.2.3.4']),
    '1.2.3.4': ('bogus1.there',
                ['bogus2', 'bogus3', 'bogus4.foo.bar'], ['1.2.3.4']),
    'localhost': ('localhost', [], ['127.0.0.1']),
    '127.0.0.1': ('localhost', [], ['127.0.0.1']),
    'other': ('other', ['bogus3'], ['1.2.3.5']),
    '1.2.3.5': ('other', ['bogus3'], ['1.2.3.5']),
    '127.5.6.7': ERR_HOST_NOT_FOUND,
    '152.66.84.8': ('fourier.szit.bme.hu', [], ['152.66.84.8']),
    '2001:6b0:1:ea:202:a5ff:fecd:13a6': (
         'igloo.stacken.kth.se', [], ['2001:6b0:1:ea:202:a5ff:fecd:13a6']),
    '74.125.39.106': ('fx-in-f106.1e100.net', [], ['74.125.39.106']),
    'foo.bar.baz': ERR_NODATA,
    'fourier.szit.bme.hu': ('fourier.szit.bme.hu', [], ['152.66.84.8']),
    'mail.szit.bme.hu': ('fourier.szit.bme.hu', [], ['152.66.84.8']),
    'www.google.com': ('fx-in-f106.1e100.net', [], ['74.125.39.106']),
    'www.l.google.com': ('fx-in-f106.1e100.net', [], ['74.125.39.106']),
    'www.ipv6.org': ('igloo.stacken.kth.se', [], ['130.237.234.40']),
}
GETFQDN_RESULT = {
    '1.2.3.4': 'bogus1.there',
    '1.2.3.5': 'other',
    '127.0.0.1': 'localhost',
    '127.5.6.7': '127.5.6.7',
    '152.66.84.8': 'fourier.szit.bme.hu',
    '2001:6b0:1:ea:202:a5ff:fecd:13a6': 'igloo.stacken.kth.se',
    '74.125.39.106': 'fx-in-f106.1e100.net',
    'bogus3': 'bogus1.there',
    'bogus4.foo.bar': 'bogus1.there',
    'foo.bar.baz': 'foo.bar.baz',
    'fourier.szit.bme.hu': 'fourier.szit.bme.hu',
    'localhost': 'localhost',
    'mail.szit.bme.hu': 'fourier.szit.bme.hu',
    'other': 'other',
    'www.google.com': 'fx-in-f106.1e100.net',
    'www.ipv6.org': 'igloo.stacken.kth.se',
    'www.l.google.com': 'fx-in-f106.1e100.net',
    'unknown': 'unknown',
}

GETHOSTBYNAME_EX_RESULT = {
    '1.2.3.4': ('1.2.3.4', [], ['1.2.3.4']),
    '1.2.3.5': ('1.2.3.5', [], ['1.2.3.5']),
    '127.0.0.1': ('127.0.0.1', [], ['127.0.0.1']),
    '127.5.6.7': ('127.5.6.7', [], ['127.5.6.7']),
    '152.66.84.8': ('152.66.84.8', [], ['152.66.84.8']),
    '2001:6b0:1:ea:202:a5ff:fecd:13a6': ERR_ADDRFAMILY,
    '74.125.39.106': ('74.125.39.106', [], ['74.125.39.106']),
    # Incomplete emulation: socket.gethostbyname_ex would return:
    # 'bogus3': ('bogus1.there',
    #           ['bogus2', 'bogus3', 'bogus4.foo.bar'],
    #           ['1.2.3.4', '1.2.3.5']),  # !! for gethostbyaddr
    'bogus3': ('bogus1.there',
               ['bogus2', 'bogus3', 'bogus4.foo.bar'],
               ['1.2.3.4']),
    'bogus4.foo.bar':  ('bogus1.there',
                        ['bogus2', 'bogus3', 'bogus4.foo.bar'], ['1.2.3.4']),
    'foo.bar.baz': ERR_NODATA,
    'fourier.szit.bme.hu': ('fourier.szit.bme.hu', [], ['152.66.84.8']),
    'localhost': ('localhost', [], ['127.0.0.1']),
    'mail.szit.bme.hu': ('fourier.szit.bme.hu', ['mail.szit.bme.hu'],
                         ['152.66.84.8']),
    'other': ('other', ['bogus3'], ['1.2.3.5']),
    # Incomplete emulation: socket.gethostbyname_ex would return:
    #'www.google.com': ('www.l.google.com', ['www.google.com'],
    #                   ['74.125.39.106', '74.125.39.103',
    #                    '74.125.39.147', '74.125.39.104',
    #                    '74.125.39.105', '74.125.39.99']),
    'www.google.com': ('fx-in-f106.1e100.net', ['www.google.com'],
                       ['74.125.39.106', '74.125.39.103',
                        '74.125.39.147', '74.125.39.104',
                        '74.125.39.105', '74.125.39.99']),
    # Incomplete emulation: socket.gethostbyname_ex would return:
    #'www.l.google.com': ('www.l.google.com', [],
    #                   ['74.125.39.106', '74.125.39.103',
    #                    '74.125.39.147', '74.125.39.104',
    #                    '74.125.39.105', '74.125.39.99']),
    'www.l.google.com': ('fx-in-f106.1e100.net', ['www.l.google.com'],
                       ['74.125.39.106', '74.125.39.103',
                        '74.125.39.147', '74.125.39.104',
                        '74.125.39.105', '74.125.39.99']),
    # Incomplete emulation: socket.gethostbyname_ex would return:
    #'www.ipv6.org': ('shake.stacken.kth.se', ['www.ipv6.org'],
    #                 ['130.237.234.40']),
    'www.ipv6.org': ('igloo.stacken.kth.se', ['www.ipv6.org'],
                     ['130.237.234.40']),
    'unknown': ERR_NODATA,
}


def FakeDnsResolveIpv4(name):
  values = RESOLVE_IPV4_RESULT[name]
  if values is None:
    raise syncless.coio.DnsLookupError(-3, 'fake error')  # name does not exist
  return syncless.coio.dnsresult(1, 1, values)

def Wrap(function, *args):
  try:
    return function(*args)
  except socket.gaierror, e:
    assert type(e.args[1]) == str, repr(e.args)
    if e.args[0] == socket.EAI_NODATA:
      return ERR_NODATA
    elif e.args[0] == socket.EAI_NONAME:
      return ERR_NONAME
    elif e.args[0] == socket.EAI_ADDRFAMILY:
      return ERR_ADDRFAMILY
    else:
      assert 0, repr(e.args)
  except socket.herror, e:
    if e.args[0] == syncless.coio.HERROR_HOST_NOT_FOUND:
      return ERR_HOST_NOT_FOUND
    else:
      assert 0, repr(e.args)

class DnsCompatTest(unittest.TestCase):
  def setUp(self):
    assert callable(getattr(syncless.coio, 'dns_resolve_ipv4', None))
    syncless.coio.dns_resolve_ipv4 = FakeDnsResolveIpv4
    syncless.coio.names_by_ip.clear()
    syncless.coio.names_by_nameip.clear()
    f = cStringIO.StringIO()
    f.write("#127.0.0.1\t \tbad1\n")
    f.write("  127.0.0.1\t \tlocalhost\n")
    f.write("127.0.0.1\t \tbad2\n")
    f.write("\t \t1.2.3.4 bogus1.there\tbogus2 bogus3 bogus4.foo.bar\n")
    f.write("1.2.3.5 other bogus3\n")
    f.reset()
    syncless.coio.read_etc_hosts(f=f)
    # TODO(pts): Cleanup in tearDown.

  def testEtcHostsDicts(self):
    items1 = ['1.2.3.4', 'bogus1.there', 'bogus2', 'bogus3', 'bogus4.foo.bar']
    items2 = ['127.0.0.1', 'localhost']
    items3 = ['1.2.3.5', 'other', 'bogus3']
    items4 = ['127.0.0.1', 'bad2']
    self.assertEqual(
        {'1.2.3.4': items1, '127.0.0.1': items2,
         '1.2.3.5': items3}, syncless.coio.names_by_ip)
    self.assertEqual(
        {'1.2.3.4': items1, 'bogus1.there': items1, 'bogus2': items1,
         'bad2': items4, '1.2.3.5': items3, 'other': items3,
         'bogus3': items1, 'bogus4.foo.bar': items1, 'localhost': items2,
         '127.0.0.1': items2}, syncless.coio.names_by_nameip)

  def testGetHostByName(self):
    for name in sorted(GETHOSTBYNAME_RESULT):
      result = Wrap(syncless.coio.gethostbyname, name)
      self.assertEqual({name: GETHOSTBYNAME_RESULT[name]}, {name: result})

  def testGetHostByNameEx(self):
    for name in sorted(GETHOSTBYNAME_EX_RESULT):
      result = Wrap(syncless.coio.gethostbyname_ex, name)
      self.assertEqual({name: GETHOSTBYNAME_EX_RESULT[name]}, {name: result})

  def testGetHostByAddr(self):
    for name in sorted(GETHOSTBYADDR_RESULT):
      result = Wrap(syncless.coio.gethostbyaddr, name)
      self.assertEqual({name: GETHOSTBYADDR_RESULT[name]}, {name: result})

  def testGetFqdn(self):
    for name in sorted(GETFQDN_RESULT):
      result = syncless.coio.getfqdn(name)  # Never raises an exception.
      self.assertEqual({name: GETFQDN_RESULT[name]}, {name: result})

#  def testZZZGen(self):
#    for name in sorted(GETHOSTBYNAME_EX_RESULT) + ['unknown']:
#      print repr(name), ':', Wrap(socket.gethostbyname_ex, name)


if __name__ == '__main__':
  unittest.main()
