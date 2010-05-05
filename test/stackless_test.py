#! /usr/local/bin/stackless2.6

"""Tests for Stackless features used by Syncless.

These tests also test the syncless.greenstackless emulation module if run
under non-Stackless Python.
"""

import sys
import unittest

try:
  import stackless
  print >>sys.stderr, 'info: using stackless'
except ImportError:
  #import syncless.greenstackless as stackless
  import greenstackless as stackless
  assert 'greenlet' in sys.modules
  print >>sys.stderr, 'info: using greenlet'


class StacklessTest(unittest.TestCase):
  def setUp(self):
    # This is ignored by Stackless, but used by greenstackless.
    stackless.is_slow_prev_next_ok = False
    self.assertEqual(1, stackless.getruncount())

  def tearDown(self):
    self.assertEqual(stackless.main, stackless.getcurrent())
    main_tasklet = stackless.main
    try:
      self.assertEqual(1, stackless.getruncount())
    finally:
      while main_tasklet is not main_tasklet.prev:
        main_tasklet.prev.kill()

  def testStackless(self):
    events = []

    def Divide(a, b):
      return a / b

    def Worker(name, c):
      while True:
        events.append(name + '.wait')
        events.append('%s/%s' % (name, c.receive()))

    def Single(name):
      events.append(name + '.single')

    def Cooperative(name):
      while True:
        events.append(name + '.coop')
        stackless.schedule()

    def CooperativeRemove(name):
      while True:
        events.append(name + '.corm')
        stackless.schedule_remove()

    def Run():
      while True:
        events.append('schedule')
        i = len(events)
        stackless.schedule()
        if i == len(events):
          break
      events.append('done')


    c = stackless.channel()

    self.assertTrue(stackless.getcurrent() is stackless.getmain())
    self.assertTrue(stackless.getcurrent() is stackless.main)
    self.assertEqual(1, stackless.getruncount())
    self.assertTrue(stackless.getcurrent() is stackless.getcurrent().next)
    self.assertTrue(stackless.getcurrent() is stackless.getcurrent().prev)
    ta = stackless.tasklet(Worker)('A', c)
    tb = stackless.tasklet(Worker)('B', c)
    tc = stackless.tasklet(Worker)('C', c)
    td = stackless.tasklet(Worker)('D', c)
    self.assertEqual(5, stackless.getruncount())
    self.assertTrue(td is stackless.getcurrent().prev)
    self.assertTrue(ta is stackless.getcurrent().next)
    self.assertTrue(td.next is stackless.getcurrent())
    self.assertTrue(td.prev is tc)

    self.assertEqual(c.preference, -1)
    self.assertEqual(c.balance, 0)
    del events[:]
    events.append('send')
    self.assertEqual(5, stackless.getruncount())
    c.send('msg')
    self.assertEqual(1, stackless.getruncount())
    Run()
    self.assertEqual(' '.join(events), 'send A.wait A/msg A.wait B.wait C.wait D.wait schedule done')

    self.assertEqual(c.preference, -1)
    self.assertEqual(c.balance, -4)
    del events[:]
    events.append('send')
    c.preference = 0  # same as c.preference = 1
    self.assertEqual(1, stackless.getruncount())
    c.send('msg')
    self.assertEqual(2, stackless.getruncount())
    Run()
    #print ' '.join(events)
    self.assertEqual(' '.join(events), 'send schedule A/msg A.wait schedule done')

    self.assertEqual(c.preference, 0)
    self.assertEqual(c.balance, -4)
    del events[:]
    c.preference = 1
    events.append('send')
    self.assertEqual(1, stackless.getruncount())
    c.send('msg')
    self.assertEqual(2, stackless.getruncount())
    Run()
    self.assertEqual(' '.join(events), 'send schedule B/msg B.wait schedule done')

    self.assertEqual(c.preference, 1)
    del events[:]
    c.preference = 2  # same as c.preference = 1
    events.append('send')
    self.assertEqual(1, stackless.getruncount())
    c.send('msg')
    c.send('msg')
    self.assertEqual(3, stackless.getruncount())
    Run()
    self.assertEqual(' '.join(events), 'send schedule C/msg C.wait D/msg D.wait schedule done')
    # Now the doubly-linked list is (d, main, a, b, c) !! why?

    self.assertEqual(c.balance, -4)
    del events[:]
    c.preference = 5
    events.append('send')
    self.assertEqual(c.balance, -4)
    self.assertEqual(1, stackless.getruncount())
    t = stackless.tasklet(Single)
    self.assertEqual(1, stackless.getruncount())
    self.assertTrue(t is t('T'))
    self.assertEqual(2, stackless.getruncount())
    t.remove()
    self.assertEqual(1, stackless.getruncount())
    t.insert()
    self.assertEqual(2, stackless.getruncount())
    c.send('msg1')
    self.assertEqual(c.balance, -3)
    c.send('msg2')
    c.send('msg3')
    c.send('msg4')
    self.assertEqual(6, stackless.getruncount())
    events.append('a4')
    self.assertEqual(c.balance, 0)
    #t.run()
    #stackless.schedule()
    c.send('msg5')
    self.assertEqual(5, stackless.getruncount())
    events.append('a5')
    c.send('msg6')
    self.assertEqual(5, stackless.getruncount())
    Run()
    #print  ' '.join(events)
    self.assertEqual(' '.join(events), 'send a4 T.single A/msg1 A.wait a5 B/msg2 B.wait schedule C/msg3 C.wait D/msg4 D.wait A/msg5 A.wait B/msg6 B.wait schedule done')

    self.assertTrue(stackless.getcurrent() is stackless.getcurrent().next)
    self.assertTrue(stackless.getcurrent() is stackless.getcurrent().prev)

    del events[:]
    self.assertEqual(c.balance, -4)
    c.preference = 42
    c.send('msg1')
    self.assertEqual(c.balance, -3)
    self.assertTrue(tc is stackless.getcurrent().next)
    self.assertTrue(tc is stackless.getcurrent().prev)
    self.assertTrue(tc.prev is stackless.getcurrent())
    self.assertTrue(tc.next is stackless.getcurrent())
    c.send('msg2')
    self.assertEqual(c.balance, -2)
    self.assertTrue(tc is stackless.getcurrent().next)
    self.assertTrue(td is stackless.getcurrent().prev)
    self.assertTrue(td.next is stackless.getcurrent())
    self.assertTrue(td.prev is tc)
    c.send('msg3')
    self.assertEqual(c.balance, -1)
    self.assertTrue(tc is stackless.getcurrent().next)
    self.assertTrue(ta is stackless.getcurrent().prev)
    self.assertTrue(ta.next is stackless.getcurrent())
    self.assertTrue(ta.prev is td)
    self.assertEqual(' '.join(events), '')
    self.assertEqual(4, stackless.getruncount())
    t = stackless.tasklet(Single)('T')
    self.assertTrue(t is stackless.getcurrent().prev)
    self.assertTrue(ta is t.prev)
    self.assertTrue(t.alive)
    self.assertEqual(5, stackless.getruncount())
    t.remove()
    #self.assertTrue(t.next is None  # NotImplementedError in greenstackless)
    self.assertTrue(ta is stackless.getcurrent().prev)
    self.assertTrue(t.alive)
    self.assertEqual(4, stackless.getruncount())
    t.run()
    self.assertEqual(4, stackless.getruncount())
    self.assertTrue(not t.alive)
    self.assertEqual(' '.join(events), 'T.single')
    del events[:]
    td.run()
    self.assertEqual(' '.join(events), 'D/msg2 D.wait A/msg3 A.wait')
    del events[:]
    self.assertEqual(c.balance, -3)
    self.assertTrue(tc is stackless.getcurrent().next)
    self.assertTrue(tc is stackless.getcurrent().prev)
    self.assertTrue(tc.prev is stackless.getcurrent())
    self.assertTrue(tc.next is stackless.getcurrent())
    tc.run()
    self.assertEqual(' '.join(events), 'C/msg1 C.wait')
    del events[:]
    self.assertEqual(c.balance, -4)
    self.assertTrue(stackless.getcurrent() is stackless.getcurrent().next)
    self.assertTrue(stackless.getcurrent() is stackless.getcurrent().prev)

    t = stackless.tasklet(Cooperative)('T')
    r = stackless.tasklet(CooperativeRemove)('R')
    u = stackless.tasklet(Cooperative)('U')
    self.assertEqual(4, stackless.getruncount())
    del events[:]
    stackless.schedule()
    self.assertEqual(' '.join(events), 'T.coop R.corm U.coop')
    self.assertEqual(3, stackless.getruncount())
    del events[:]
    stackless.schedule()
    self.assertEqual(' '.join(events), 'T.coop U.coop')
    self.assertEqual(3, stackless.getruncount())
    del events[:]
    t.kill()  # This involves t.run(), so u gets run as well. 
    self.assertEqual(' '.join(events), 'U.coop')
    self.assertEqual(2, stackless.getruncount())
    r.kill()
    self.assertEqual(2, stackless.getruncount())
    r.kill()
    self.assertEqual(2, stackless.getruncount())
    u.kill()
    self.assertEqual(1, stackless.getruncount())

    typ, val, tb1 = None, None, None
    try:
      Divide(42, 0)
    except ZeroDivisionError:
      typ, val, tb1 = sys.exc_info()
    self.assertTrue(typ is ZeroDivisionError)

    tb2 = None
    try:
      if hasattr(stackless.getcurrent(), 'throw'):  # greenstackless
        stackless.getcurrent().throw(typ, val, tb1)
      else:  # Stackless
        stackless.getcurrent().tempval = stackless.bomb(typ, val, tb1)
        stackless.getcurrent().run()
    except:
      self.assertTrue(sys.exc_info()[0] is typ)
      self.assertTrue(sys.exc_info()[1] is val)
      tb2 = sys.exc_info()[2]
      tb3 = tb2 and tb2.tb_next
      tb4 = tb3 and tb3.tb_next
      # greenstackless adds 2 frames.
      self.assertTrue(tb1 in (tb2, tb3, tb4) )
    self.assertTrue(tb2)

    self.assertEqual(-4, c.balance)
    ta.kill()
    self.assertEqual(-3, c.balance)
    td.kill()
    self.assertEqual(-2, c.balance)
    tc.kill()
    self.assertEqual(-1, c.balance)
    tb.kill()
    self.assertEqual(0, c.balance)

    tb2 = None
    self.assertEqual(0, c.balance)
    c.preference = 1
    def SendBomb():
      c.send(stackless.bomb(typ, val, tb1))
    stackless.tasklet(SendBomb)()
    try:
      c.receive()
    except:
      self.assertTrue(sys.exc_info()[0] is typ)
      self.assertTrue(sys.exc_info()[1] is val)
      tb2 = sys.exc_info()[2]
      tb3 = tb2 and tb2.tb_next
      tb4 = tb3 and tb3.tb_next
      tb5 = tb4 and tb4.tb_next
      # greenstackless adds 3 frames (including c.receive() etc.)
      self.assertTrue(tb1 in (tb2, tb3, tb4, tb5))
    self.assertTrue(tb2)

    tb2 = None
    self.assertEqual(0, c.balance)
    c.preference = 1
    def SendBomb():
      c.send(stackless.bomb(typ, val, tb1))
    stackless.tasklet(SendBomb)()
    try:
      c.receive()
    except:
      self.assertTrue(sys.exc_info()[0] is typ)
      self.assertTrue(sys.exc_info()[1] is val)
      tb2 = sys.exc_info()[2]
      tb3 = tb2 and tb2.tb_next
      tb4 = tb3 and tb3.tb_next
      tb5 = tb4 and tb4.tb_next
      # greenstackless adds 3 frames (including c.receive() etc.)
      self.assertTrue(tb1 in (tb2, tb3, tb4, tb5))
    self.assertTrue(tb2)

    tb2 = None
    def RaiseException(task):
      task.raise_exception(ValueError, 42)
    stackless.tasklet(RaiseException)(stackless.getcurrent())
    try:
      stackless.schedule()
    except:
      self.assertTrue(sys.exc_info()[0] is ValueError)
      self.assertEqual(str(sys.exc_info()[1]), '42')
      tb2 = sys.exc_info()[2]
      # Don't check the traceback (tb2), should be in stackless.schedule().
    self.assertTrue(tb2)

    tb2 = None
    self.assertEqual(0, c.balance)
    c.preference = 1
    def SendException(task):
      c.send_exception(ValueError, 43)
    stackless.tasklet(SendException)(stackless.getcurrent())
    try:
      c.receive()
    except:
      self.assertTrue(sys.exc_info()[0] is ValueError)
      self.assertEqual(str(sys.exc_info()[1]), '43')
      tb2 = sys.exc_info()[2]
      # Don't check the traceback (tb2), should be in stackless.schedule().
    self.assertTrue(tb2)

  def testKillJumpsInRunnablesList(self):
    items = []

    def Worker():
      items.append('worker')

    def Dead():
      items.append('dead')

    dead_tasklet = stackless.tasklet(Dead)()
    worker_tasklet = stackless.tasklet(Worker)()
    items.append('before')
    dead_tasklet.kill()
    items.append('after')
    self.assertEqual('before,worker,after', ','.join(items))

  def testChannelReceiveLinkedList(self):
    """Test how the linked lists are formed when blocked on a channel."""
    stackless.is_slow_prev_next_ok = True
    channel_obj = stackless.channel()
    tasklet1 = stackless.tasklet(channel_obj.receive)()
    #tasklet2 = stackless.tasklet(channel_obj.receive)()
    #tasklet3 = stackless.tasklet(channel_obj.receive)()
    assert tasklet1.next is stackless.getcurrent()

    stackless.schedule()
    assert tasklet1.next is None
    assert tasklet1.prev is None

    tasklet2 = stackless.tasklet(channel_obj.receive)()
    stackless.schedule()
    assert tasklet1.next is tasklet2
    assert tasklet1.prev is None

    tasklet3 = stackless.tasklet(channel_obj.receive)()
    stackless.schedule()
    assert tasklet1.next is tasklet2
    assert tasklet2.next is tasklet3
    assert tasklet3.next is None
    assert tasklet1.prev is None
    assert tasklet2.prev is tasklet1
    assert tasklet3.prev is tasklet2

  def testRunBlockedTasklet(self):
    def Worker(channel_obj):
      print repr(channel_obj.receive())

    channel_obj = stackless.channel()
    tasklet1 = stackless.tasklet(Worker)(channel_obj)
    assert not tasklet1.blocked
    stackless.schedule()
    assert tasklet1.blocked
    # RuntimeError('You cannot run a blocked tasklet')
    self.assertRaises(RuntimeError, tasklet1.insert)

  def testRunnablesOrderAtKill(self):
    def Safe(items):
      try:
        items.append('start')
        stackless.schedule()
      except ValueError:
        items.append('caught')

    stackless.schedule()
    tasklet1 = stackless.tasklet(lambda: 1 / 0)()
    items = []
    tasklet2 = stackless.tasklet(Safe)(items)
    tasklet2.run()
    assert 'start' == ','.join(items)
    tasklet3 = stackless.tasklet(lambda: 1 / 0)()
    tasklet2.remove()
    tasklet2.remove()
    tasklet2.raise_exception(ValueError)
    assert 'start,caught' == ','.join(items)
    assert tasklet1.alive
    assert not tasklet2.alive
    assert tasklet3.alive
    tasklet1.remove()
    tasklet1.kill()  # Don't run tasklet3.
    tasklet3.kill()
    tasklet2.kill()

  def testTempval(self):
    def Worker(items):
        items.append(stackless.schedule())
        items.append(stackless.schedule(None))
        items.append(stackless.schedule('foo'))
        items.append(stackless.schedule(42))
  
    items = []
    tasklet_obj = stackless.tasklet(Worker)(items)
    self.assertEqual(None, tasklet_obj.tempval)
    self.assertEqual([], items)
    stackless.schedule()
    self.assertEqual(tasklet_obj, tasklet_obj.tempval)
    self.assertEqual([], items)
    stackless.schedule()
    self.assertEqual(None, tasklet_obj.tempval)
    self.assertEqual([tasklet_obj], items)
    stackless.schedule()
    self.assertEqual('foo', tasklet_obj.tempval)
    self.assertEqual([tasklet_obj, None], items)
    tasklet_obj.tempval = False
    stackless.schedule()
    self.assertEqual([tasklet_obj, None, False], items)
    self.assertEqual(42, tasklet_obj.tempval)
    stackless.schedule()
    self.assertEqual([tasklet_obj, None, False, 42], items)
    # Upon TaskletExit.
    self.assertEqual(None, tasklet_obj.tempval)

if __name__ == '__main__':
  unittest.main()
