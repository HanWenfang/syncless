#! /usr/local/bin/stackless2.6

"""Tests for Greenlet and its emulator greenlet_fix.

by pts@fazekas.hu at Sat Jan  9 03:10:51 CET 2010
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import unittest

from greenlet_fix import greenlet

class GreenletTest(unittest.TestCase):
  def testGreenlet(self):
    events = []

    m = greenlet.getcurrent()

    def A(x, y, z):
      events.append('%s/%s/%s' % (x, y, z))
      events.append(m.switch('C'))

    g = greenlet.greenlet(A)
    assert not g.dead
    assert not g
    assert greenlet.getcurrent() is m
    events.append(str(g.switch(3, 4, 5)))
    assert greenlet.getcurrent() is m
    assert not g.dead
    assert g
    events.append(str(g.switch('D')))
    #print ' '.join(events)
    assert ' '.join(events) == '3/4/5 C D None'
    assert g.dead
    assert not g

    def B():
      1 / 0

    g = greenlet.greenlet(B)
    assert greenlet.getcurrent() is m
    try:
      g.switch()
      assert 0, 'not reached'
    except ZeroDivisionError:
      pass
    assert greenlet.getcurrent() in (g, m)
    assert greenlet.getcurrent() is m

    gc = []

    def C():
      events.append('C')

    def D():
      events.append('D1')
      gc.append(greenlet.greenlet(C))
      events.append('D2')
      events.append(m.switch('D3'))
      events.append('D4')

    assert greenlet.getcurrent() is m
    del events[:]
    g = greenlet.greenlet(D)
    events.append('M')
    events.append(g.switch())
    assert ' '.join(events) == 'M D1 D2 D3'
    try:
      gc[0].throw(ValueError, 'VE')
    except ValueError, e:
      events.append(str(e))
    assert ' '.join(events) == 'M D1 D2 D3 VE'

if __name__ == '__main__':
  unittest.main()
