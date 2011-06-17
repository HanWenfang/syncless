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

# We introduce one namespace layer (named Template) so unittest.main() won't
# find GreenletTestTemplate as a class to run tests methods of.
class Template(object):
  class GreenletTestTemplate(unittest.TestCase):
    greenlet = None
    """greenlet class, will be overridden by subclasses."""

    def setUp(self):
      self.assertEqual(1, self.getruncount())

    def tearDown(self):
      self.assertEqual(1, self.getruncount())

    def getruncount(self):  # Dummy.
      return 1

    def testGreenlet(self):
      events = []

      m = self.greenlet.getcurrent()
      assert m.parent is None
      assert m
      assert not m.dead

      def A(x, y, z):
        events.append('%s/%s/%s' % (x, y, z))
        events.append(m.switch('C'))

      g = self.greenlet(A)
      assert not g.dead
      assert not g
      assert self.greenlet.getcurrent() is m
      events.append(str(g.switch(3, 4, 5)))
      assert self.greenlet.getcurrent() is m
      assert not g.dead
      assert g
      events.append(str(g.switch('D')))
      #print ' '.join(events)
      assert ' '.join(events) == '3/4/5 C D None'
      assert g.dead
      assert not g

      def B():
        1 / 0

      g = self.greenlet(B)
      assert self.greenlet.getcurrent() is m
      assert g.parent is m
      assert not g
      assert not g.dead
      try:
        g.switch()
        assert 0, 'not reached'
      except ZeroDivisionError:
        pass
      assert self.greenlet.getcurrent() in (g, m)
      assert self.greenlet.getcurrent() is m

      gc = []

      def C():
        events.append('C')

      def D():
        events.append('D1')
        gc.append(self.greenlet(C))
        events.append('D2')
        events.append(m.switch('D3'))
        events.append('D4')

      assert self.greenlet.getcurrent() is m
      del events[:]
      g = self.greenlet(D)
      events.append('M')
      events.append(g.switch())
      assert ' '.join(events) == 'M D1 D2 D3'
      assert gc[0] is not self.greenlet.getcurrent()
      try:
        gc[0].throw(ValueError, 'VE')
      except ValueError, e:
        events.append(str(e))
      assert ' '.join(events) == 'M D1 D2 D3 VE'

    def testSwitchValue(self):
      gc = self.greenlet.getcurrent()
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
      g1 = self.greenlet(lambda: Switcher('g1'))
      g2 = self.greenlet(lambda: Switcher('g2'))
      g3 = self.greenlet(lambda: Switcher('g3'))
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
      self.assertRaises(ValueError,
                        self.greenlet.getcurrent().throw, ValueError)
      items = []
      gc = self.greenlet.getcurrent()

      def Catcher(do_switch):
        assert do_switch is True
        try:
          gc.switch('catcher')
          items.append('ok')
        except BaseException, e:
          items.append(type(e))

      gp = self.greenlet(Catcher)
      self.assertEqual('catcher', gp.switch(True))
      ge = self.greenlet(lambda: 1 / 0, gp)
      # The Catcher (gp) catches this ValueError, because it is the parent of ge.
      ge.throw(ValueError)
      self.assertEqual([ValueError], items)

      del items[:]
      gp = self.greenlet(Catcher)
      ge = self.greenlet(lambda: 1 / 0, gp)
      assert not (gp or gp.dead)
      # The Catcher can't catch this ValueError, because it's not running yet.
      self.assertRaises(ValueError, ge.throw, ValueError)
      assert not gp
      assert gp.dead
      assert not ge
      assert ge.dead
      self.assertEqual([], items)

      del items[:]
      gp = self.greenlet(Catcher)
      self.assertEqual('catcher', gp.switch(True))
      ge = self.greenlet(lambda: 42, gp)
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

    def testSwitchToParent(self):
      greenlet1 = self.greenlet(lambda x=None: 'P:' + repr(x))
      greenlet2 = self.greenlet(lambda x: x * 10, parent=greenlet1)
      self.assertEqual('P:210', greenlet2.switch(21))

      def Raiser(x):
        raise self.greenlet.GreenletExit(x)
      greenlet3 = self.greenlet(Raiser)
      try:
        # The exception is returned to the parent, not raised.
        self.assertEqual('42', str(greenlet3.switch(42)))
      except self.greenlet.GreenletExit, e:
        self.assertFalse('unexpected GreenletExit: %s', e)

      greenlet4 = self.greenlet(lambda x: 1 / x)
      self.assertRaises(ZeroDivisionError, greenlet4.switch, 0)

      greenlet5 = self.greenlet(lambda: 42)
      greenlet6 = self.greenlet(lambda x: 1 / x, parent=greenlet5)
      self.assertRaises(ZeroDivisionError, greenlet6.switch, 0)

    def testGreenletExitOnDelete(self):
      exits = []
      def Reporter():
        exits.append('HI')
        try:
          self.greenlet.getcurrent().parent.switch()
        except BaseException, e:
          exits.append(isinstance(e, self.greenlet.GreenletExit))
      greenlets = [self.greenlet(Reporter)]
      self.assertEqual([], exits)
      greenlets[-1].switch()
      self.assertEqual(['HI'], exits)
      greenlets.pop()
      # GreenletExit is raised when all references to the greenlet go aways.
      self.assertEqual(['HI', True], exits)

    def testParentChangeOnDelete(self):
      x = []

      def Work():
        g1 = self.greenlet(x.append)
        g2 = self.greenlet(lambda: 1 / 0, parent=g1)
        del g2  #  This updates the parent of g2 to the current greenlet.
        self.assertFalse(g1)
        self.assertFalse(g1.dead)
        self.assertEqual([], x)
        x[:] = [()]

      self.greenlet(Work).switch()
      self.assertEqual([()], x)

    def testParentOnKill(self):
      x = []

      def Work():
        g1 = self.greenlet(lambda value: x.append(type(value)))
        g2 = self.greenlet(lambda: 1 / 0, parent=g1)
        g2.throw()
        self.assertTrue(g1.dead)
        self.assertEqual([self.greenlet.GreenletExit], x)
        x[:] = [()]

      self.greenlet(Work).switch()
      self.assertEqual([()], x)

    def testParentOnKillWithGreenletExit(self):
      x = []

      def Work():
        g1 = self.greenlet(lambda value: x.append(type(value)))
        g2 = self.greenlet(lambda: 1 / 0, parent=g1)
        g2.throw(self.greenlet.GreenletExit)
        self.assertTrue(g1.dead)
        self.assertEqual([self.greenlet.GreenletExit], x)
        x[:] = [()]

      self.greenlet(Work).switch()
      self.assertEqual([()], x)

    def testParentOnKillWithGreenletExitSubclass(self):
      x = []

      class MyGreenletExit(self.greenlet.GreenletExit):
        pass

      def Work():
        g1 = self.greenlet(lambda value: x.append(type(value)))
        g2 = self.greenlet(lambda: 1 / 0, parent=g1)
        g2.throw(MyGreenletExit)
        self.assertTrue(g1.dead)
        self.assertEqual([MyGreenletExit], x)
        x[:] = [()]

      self.greenlet(Work).switch()
      self.assertEqual([()], x)

    def testParentOnKillWithOtherError(self):
      x = []

      def Work():
        g1 = self.greenlet(lambda: ()[0])
        g2 = self.greenlet(lambda: 1 / 0, parent=g1)
        e = None
        try:
          g2.throw(ValueError, 42)
        except ValueError, e:
          e = e.args
        self.assertEqual((42,), e)
        self.assertTrue(g1.dead)
        self.assertEqual([], x)
        x[:] = [()]

      self.greenlet(Work).switch()
      self.assertEqual([()], x)

    def testParentCatchOnKill(self):
      x = []

      def Work():
        gw = self.greenlet.getcurrent()
        g1 = self.greenlet(lambda value: x.append(type(value)))
        def F2():
          try:
            x.append('A')
            x.append(self.greenlet.getcurrent().parent is g1)
            gw.switch()
          except self.greenlet.GreenletExit:
            # For `del g2', parent becomes gw (who deleted it),
            # for normal throw(), parent remains.
            x.append('B')
            x.append(self.greenlet.getcurrent().parent is gw)
            x.append(self.greenlet.getcurrent().parent is g1)
            x.append('C')
            raise
        g2 = self.greenlet(F2, parent=g1)
        self.assertEqual([], x)
        g2.switch()
        self.assertEqual(['A', True], x)
        g2.throw()
        self.assertEqual(['A', True, 'B', False, True, 'C',
                          self.greenlet.GreenletExit], x)
        self.assertTrue(g1.dead)
        self.assertTrue(g2.dead)
        x[:] = [()]

      self.greenlet(Work).switch()
      self.assertEqual([()], x)

    def testParentCatchOnDelete(self):
      x = []

      def Work():
        gw = self.greenlet.getcurrent()
        g1 = self.greenlet(lambda value: x.append(type(value)))
        def F2():
          try:
            x.append('A')
            x.append(self.greenlet.getcurrent().parent is g1)
            gw.switch()
          except self.greenlet.GreenletExit:
            # For `del g2', parent becomes gw (who deleted it),
            # for normal throw(), parent remains.
            x.append('B')
            x.append(self.greenlet.getcurrent().parent is gw)
            x.append(self.greenlet.getcurrent().parent is g1)
            x.append('C')
            raise
        g2 = self.greenlet(F2, parent=g1)
        self.assertEqual([], x)
        g2.switch()
        self.assertEqual(['A', True], x)
        del g2
        self.assertEqual(['A', True, 'B', True, False, 'C'], x)
        self.assertFalse(g1)
        self.assertFalse(g1.dead)
        x[:] = [()]

      self.greenlet(Work).switch()
      self.assertEqual([()], x)



if __name__ == '__main__':
  class GreenletTest(Template.GreenletTestTemplate):
    from syncless.best_greenlet.greenlet import greenlet
    if hasattr(greenlet, 'is_pts_greenlet_emulated'):
      print >>sys.stderr, 'info: using stackless with greenlet emulation'
      from stackless import getruncount
      getruncount = staticmethod(getruncount)  # Extra check.
    else:
      print >>sys.stderr, 'info: using greenlet'

    assert isinstance(greenlet.GreenletExit(), BaseException)

    def testGreenletModule(self):
      self.assertTrue('greenlet' in sys.modules)
      self.assertEqual(self.greenlet, sys.modules['greenlet'].greenlet)

  unittest.main()
