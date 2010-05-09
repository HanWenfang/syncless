#! /usr/local/bin/stackless2.6

"""Tests for Greenlet and its emulator.

by pts@fazekas.hu at Sat Jan  9 03:10:51 CET 2010
--- Sun May  9 20:05:50 CEST 2010

Stackless python 2.6.5 sometimes segfaults on this (if the .pyc file doesn't
exist) with greenlet_test.py, with cryptic error messages like:
Python 2.6.5 Stackless 3.1b3 060516 (python-2.65:81025M, May  9 2010, 14:53:06) 
[GCC 4.4.1] on linux2.

  AttributeError: 'greenlet' object has no attribute 'parent'

This seems to be related of lots of non-cleaned-up tasklets. It hasn't been
happening recently.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys
import unittest

from syncless.best_greenlet.greenlet import greenlet

if hasattr(greenlet, 'is_pts_greenlet_emulated'):
  print >>sys.stderr, 'info: using stackless with greenlet emulation'
  from stackless import getruncount
else:
  print >>sys.stderr, 'info: using greenlet'
  def getruncount():
    return 1

class GreenletTest(unittest.TestCase):
  def setUp(self):
    self.assertEqual(1, getruncount())

  def tearDown(self):
    self.assertEqual(1, getruncount())

  def testGreenlet(self):
    events = []

    m = greenlet.getcurrent()
    assert m.parent is None
    assert m
    assert not m.dead

    def A(x, y, z):
      events.append('%s/%s/%s' % (x, y, z))
      events.append(m.switch('C'))

    g = greenlet(A)
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

    g = greenlet(B)
    assert greenlet.getcurrent() is m
    assert g.parent is m
    assert not g
    assert not g.dead
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
      gc.append(greenlet(C))
      events.append('D2')
      events.append(m.switch('D3'))
      events.append('D4')

    assert greenlet.getcurrent() is m
    del events[:]
    g = greenlet(D)
    events.append('M')
    events.append(g.switch())
    assert ' '.join(events) == 'M D1 D2 D3'
    assert gc[0] is not greenlet.getcurrent()
    try:
      gc[0].throw(ValueError, 'VE')
    except ValueError, e:
      events.append(str(e))
    assert ' '.join(events) == 'M D1 D2 D3 VE'

  def testSwitchValue(self):
    gc = greenlet.getcurrent()
    self.assertEqual('self0', gc.switch('self0'))
    self.assertEqual((), gc.switch())  # The default is the empty tuple.
    next = {}
    items = []
    def Switcher(name):
      if name == 'g2':
        items.append(gc.switch())
      else:
        items.append(gc.switch(name))
      items.append(next[name].switch('+' + name))
    g1 = greenlet(lambda: Switcher('g1'))
    g2 = greenlet(lambda: Switcher('g2'))
    g3 = greenlet(lambda: Switcher('g3'))
    next['g1'] = g2
    next['g2'] = g3
    next['g3'] = gc
    assert not (g1 or g1.dead)
    assert not (g2 or g2.dead)
    assert not (g3 or g3.dead)
    self.assertEqual('self1', gc.switch('self1'))
    self.assertEqual('g1', g1.switch())
    self.assertEqual((),   g2.switch())
    self.assertEqual('g3', g3.switch())
    self.assertEqual('self2', gc.switch('self2'))
    self.assertEqual([], items)
    assert g1 and not g1.dead
    assert g2 and not g2.dead
    assert g3 and not g3.dead
    self.assertEqual('+g3', g1.switch('base'))
    self.assertEqual(['base', '+g1', '+g2'], items)
    assert g1 and not g1.dead
    assert g2 and not g2.dead
    assert g3 and not g3.dead
    self.assertEqual(None, g3.switch('d3'))
    assert not g3 and g3.dead
    self.assertEqual(['base', '+g1', '+g2', 'd3'], items)
    self.assertEqual(None, g2.switch('d2'))
    assert not g2 and g2.dead
    self.assertEqual(['base', '+g1', '+g2', 'd3', 'd2'], items)
    self.assertEqual(None, g1.switch('d1'))
    assert not g1 and g1.dead
    self.assertEqual(['base', '+g1', '+g2', 'd3', 'd2', 'd1'], items)

  def testThrow(self):
    self.assertRaises(ValueError, greenlet.getcurrent().throw, ValueError)
    items = []
    gc = greenlet.getcurrent()

    def Catcher(do_switch):
      assert do_switch is True
      try:
        gc.switch('catcher')
        items.append('ok')
      except BaseException, e:
        items.append(type(e))

    gp = greenlet(Catcher)
    self.assertEqual('catcher', gp.switch(True))
    ge = greenlet(lambda: 1 / 0, gp)
    # The Catcher (gp) catches this ValueError, because it is the parent of ge.
    ge.throw(ValueError)
    self.assertEqual([ValueError], items)

    del items[:]
    gp = greenlet(Catcher)
    ge = greenlet(lambda: 1 / 0, gp)
    assert not (gp or gp.dead)
    # The Catcher can't catch this ValueError, because it's not running yet.
    self.assertRaises(ValueError, ge.throw, ValueError)
    assert not gp
    assert gp.dead
    assert not ge
    assert ge.dead
    self.assertEqual([], items)

    del items[:]
    gp = greenlet(Catcher)
    self.assertEqual('catcher', gp.switch(True))
    ge = greenlet(lambda: 42, gp)
    self.assertEqual(None, ge.switch())
    assert gp.dead
    assert ge.dead
    self.assertEqual(['ok'], items)

  def testThrowWithDummyTasklet(self):
    if 'stackless' not in sys.modules:
      return
    import stackless
    def DummyWorker():
      while True:
        stackless.schedule()
    dummy_tasklet = stackless.tasklet(DummyWorker)()
    try:
      self.testThrow()
    finally:
      dummy_tasklet.kill()


if __name__ == '__main__':
  unittest.main()
