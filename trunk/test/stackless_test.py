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
  from syncless.best_stackless import stackless
  assert 'stackless' in sys.modules
  assert 'greenlet' in sys.modules
  print >>sys.stderr, 'info: using greenlet'

assert issubclass(TaskletExit, BaseException)


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

  def assertRaisesStr(self, exc_type, exc_str, function, *args, **kwargs):
    try:
      function(*args, **kwargs)
      e = None
    except exc_type, e:
      self.assertEqual(exc_str, str(e))
    if e is None:
      self.fail('not raised: %s(%r)' % (exc_type.__name__, exc_str))

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

    self.assertTrue(stackless.current is stackless.getmain())
    self.assertTrue(stackless.getcurrent() is stackless.main)
    self.assertEqual(1, stackless.getruncount())
    self.assertTrue(stackless.current is stackless.getcurrent().next)
    self.assertTrue(stackless.current is stackless.getcurrent().prev)
    ta = stackless.tasklet(Worker)('A', c)
    tb = stackless.tasklet(Worker)('B', c)
    tc = stackless.tasklet(Worker)('C', c)
    td = stackless.tasklet().bind(Worker)('D', c)
    self.assertEqual(5, stackless.getruncount())
    self.assertTrue(td is stackless.current.prev)
    self.assertTrue(ta is stackless.getcurrent().next)
    self.assertTrue(td.next is stackless.current)
    self.assertTrue(td.prev is tc)

    self.assertEqual(c.preference, -1)
    self.assertEqual(c.balance, 0)
    del events[:]
    events.append('send')
    self.assertEqual(5, stackless.getruncount())
    self.assertEqual(None, c.send('msg'))
    self.assertEqual(1, stackless.getruncount())
    Run()
    self.assertEqual(' '.join(events), 'send A.wait A/msg A.wait B.wait C.wait D.wait schedule done')

    self.assertEqual(c.preference, -1)
    self.assertEqual(c.balance, -4)
    del events[:]
    events.append('send')
    c.preference = 0  # same as c.preference = 1
    self.assertEqual(1, stackless.getruncount())
    self.assertEqual(None, c.send('msg'))
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
    self.assertEqual(None, c.send('msg'))
    self.assertEqual(2, stackless.getruncount())
    Run()
    self.assertEqual(' '.join(events), 'send schedule B/msg B.wait schedule done')

    self.assertEqual(c.preference, 1)
    del events[:]
    c.preference = 2  # same as c.preference = 1
    events.append('send')
    self.assertEqual(1, stackless.getruncount())
    self.assertEqual(None, c.send('msg'))
    self.assertEqual(None, c.send('msg'))
    self.assertEqual(3, stackless.getruncount())
    Run()
    self.assertEqual(' '.join(events), 'send schedule C/msg C.wait D/msg D.wait schedule done')
    # Now the doubly-linked list is (d, main, a, b, c). Why?

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
    self.assertEqual(t, t.insert())
    self.assertEqual(2, stackless.getruncount())
    self.assertEqual(None, c.send('msg1'))
    self.assertEqual(c.balance, -3)
    self.assertEqual(None, c.send('msg2'))
    self.assertEqual(None, c.send('msg3'))
    self.assertEqual(None, c.send('msg4'))
    self.assertEqual(6, stackless.getruncount())
    events.append('a4')
    self.assertEqual(c.balance, 0)
    self.assertEqual(None, c.send('msg5'))
    self.assertEqual(5, stackless.getruncount())
    events.append('a5')
    self.assertEqual(None, c.send('msg6'))
    self.assertEqual(5, stackless.getruncount())
    Run()
    self.assertEqual(' '.join(events), 'send a4 T.single A/msg1 A.wait a5 B/msg2 B.wait schedule C/msg3 C.wait D/msg4 D.wait A/msg5 A.wait B/msg6 B.wait schedule done')

    self.assertTrue(stackless.getcurrent() is stackless.current.next)
    self.assertTrue(stackless.getcurrent() is stackless.current.prev)

    del events[:]
    self.assertEqual(c.balance, -4)
    c.preference = 42
    self.assertEqual(None, c.send('msg1'))
    self.assertEqual(c.balance, -3)
    self.assertTrue(tc is stackless.getcurrent().next)
    self.assertTrue(tc is stackless.current.prev)
    self.assertTrue(tc.prev is stackless.getcurrent())
    self.assertTrue(tc.next is stackless.current)
    self.assertEqual(None, c.send('msg2'))
    self.assertEqual(c.balance, -2)
    self.assertTrue(tc is stackless.getcurrent().next)
    self.assertTrue(td is stackless.current.prev)
    self.assertTrue(td.next is stackless.getcurrent())
    self.assertTrue(td.prev is tc)
    self.assertEqual(None, c.send('msg3'))
    self.assertEqual(c.balance, -1)
    self.assertTrue(tc is stackless.current.next)
    self.assertTrue(ta is stackless.getcurrent().prev)
    self.assertTrue(ta.next is stackless.current)
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
    self.assertTrue(ta is stackless.current.prev)
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
    self.assertTrue(tc is stackless.current.prev)
    self.assertTrue(tc.prev is stackless.getcurrent())
    self.assertTrue(tc.next is stackless.current)
    tc.run()
    self.assertEqual(' '.join(events), 'C/msg1 C.wait')
    del events[:]
    self.assertEqual(c.balance, -4)
    self.assertTrue(stackless.getcurrent() is stackless.current.next)
    self.assertTrue(stackless.getcurrent() is stackless.current.prev)

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
        stackless.current.throw(typ, val, tb1)
      else:  # Stackless
        stackless.getcurrent().tempval = stackless.bomb(typ, val, tb1)
        stackless.current.run()
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
      assert c.send(stackless.bomb(typ, val, tb1)) is None
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
      assert c.send(stackless.bomb(typ, val, tb1)) is None
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
      assert c.send_exception(ValueError, 43) is None
    stackless.tasklet(SendException)(stackless.current)
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

    self.assertEqual(stackless.main, stackless.current)
    self.assertEqual(stackless.main, stackless.current.next)
    self.assertEqual(stackless.main, stackless.current.prev)
    dead_tasklet = stackless.tasklet(Dead)()
    self.assertEqual(stackless.main, stackless.current)
    self.assertEqual(dead_tasklet, stackless.current.next)
    self.assertEqual(stackless.main, stackless.current.next.next)
    self.assertEqual(dead_tasklet, stackless.current.prev)
    self.assertEqual(stackless.main, stackless.current.prev.prev)
    worker_tasklet = stackless.tasklet(Worker)()
    self.assertEqual(stackless.main, stackless.current)
    self.assertEqual(dead_tasklet, stackless.current.next)
    self.assertEqual(worker_tasklet, stackless.current.next.next)
    self.assertEqual(stackless.main, stackless.current.next.next.next)
    self.assertEqual(worker_tasklet, stackless.current.prev)
    self.assertEqual(dead_tasklet, stackless.current.prev.prev)
    self.assertEqual(stackless.main, stackless.current.prev.prev.prev)
    items.append('before')
    dead_tasklet.kill()
    self.assertEqual(stackless.main, stackless.current)
    self.assertEqual(stackless.main, stackless.current.next)
    self.assertEqual(stackless.main, stackless.current.prev)
    items.append('after')
    self.assertEqual('before,worker,after', ','.join(items))

  def testChannelReceiveLinkedList(self):
    """Test how the linked lists are formed when blocked on a channel."""
    stackless.is_slow_prev_next_ok = True
    channel_obj = stackless.channel()
    self.assertEqual(None, channel_obj.queue)
    tasklet1 = stackless.tasklet(channel_obj.receive)()
    assert tasklet1.next is stackless.getcurrent()

    stackless.schedule()
    self.assertEqual(tasklet1, channel_obj.queue)
    assert tasklet1.next is None
    assert tasklet1.prev is None

    tasklet2 = stackless.tasklet(channel_obj.receive)()
    self.assertEqual(True, tasklet1.blocked)
    self.assertEqual(True, tasklet1.scheduled)
    self.assertEqual(channel_obj, tasklet1._channel)
    self.assertEqual(False, tasklet2.blocked)
    self.assertEqual(True, tasklet2.scheduled)
    self.assertEqual(None, tasklet2._channel)
    stackless.schedule()
    self.assertEqual(channel_obj, tasklet2._channel)
    assert tasklet1.next is tasklet2
    assert tasklet1.prev is None

    tasklet3 = stackless.tasklet(channel_obj.receive)()
    self.assertEqual(tasklet1, channel_obj.queue)
    stackless.schedule()
    self.assertEqual(tasklet1, channel_obj.queue)
    assert tasklet1.next is tasklet2
    assert tasklet2.next is tasklet3
    assert tasklet3.next is None
    assert tasklet1.prev is None
    assert tasklet2.prev is tasklet1
    assert tasklet3.prev is tasklet2

  def testRunBlockedTasklet(self):
    def Worker(channel_obj):
      assert 0, repr(channel_obj.receive())

    channel_obj = stackless.channel()
    tasklet1 = stackless.tasklet(Worker)(channel_obj)
    self.assertEqual(False, tasklet1.blocked)
    self.assertEqual(True, tasklet1.scheduled)
    stackless.schedule()
    self.assertEqual(True, tasklet1.blocked)
    self.assertEqual(True, tasklet1.scheduled)
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
    stackless.current.tempval = 5
    self.assertEqual(stackless.getcurrent(), stackless.schedule())
    self.assertEqual(None, stackless.current.tempval)
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
    self.assertEqual(1, stackless.getruncount())
    self.assertEqual(stackless.getcurrent(), stackless.schedule())
    self.assertEqual(None, stackless.current.tempval)
    self.assertEqual(43, stackless.schedule(43))
    # This seems to be a strange Stackless quirk, this should be 43.
    self.assertEqual(None, stackless.getcurrent().tempval)
    self.assertEqual(54, stackless.schedule_remove(54))
    self.assertEqual(None, stackless.current.tempval)

    def Worker2(items, main_tasklet):
      items.append(stackless.getcurrent().tempval)
      items.append(stackless.schedule(44))
      items.append(stackless.current.tempval)
      main_tasklet.insert()

    del items[:]
    stackless.tasklet(Worker2)(items, stackless.getcurrent())
    self.assertEqual(55, stackless.schedule_remove(55))
    self.assertEqual(None, stackless.current.tempval)
    self.assertEqual([None, 44, None], items)

    self.assertRaisesStr(AssertionError, '', stackless.schedule,
                         stackless.bomb(AssertionError))
    self.assertRaisesStr(AssertionError, 'foo', stackless.schedule,
                         stackless.bomb(AssertionError, 'foo'))

  def testRemoveCurrent(self):
    self.assertRaisesStr(
        RuntimeError, 'The current tasklet cannot be removed. '
        'Use t=tasklet().capture()', stackless.getcurrent().remove)

  def testScheduleRemoveLast(self):
    def Worker1():
      stackless.schedule_remove()
      assert 0

    def Worker2():
      stackless.schedule_remove()
      1 / 0

    stackless.tasklet(Worker1)()
    stackless.tasklet(Worker2)()
    try:
      # In Stackless 2.6.5, stackless.main will be inserted back when the
      # last tasklet gets removed from the runnables list.
      stackless.schedule_remove()
    except ZeroDivisionError:
      # In Stackless 2.6.4, the last tasklet (Worker2) won't be removed (but
      # schedule_remove would be equivalent to schedule).
      assert not hasattr(stackless, '_tasklet_wrapper')  # Not greenstackless.
      assert '2.6.4 ' <= sys.version < '2.6.5 '

  def testHandleExceptionInMainTasklet(self):
    stackless.tasklet(lambda: 1 / 0)()
    stackless.tasklet(lambda: None)()
    self.assertRaises(ZeroDivisionError, stackless.schedule_remove)
    self.assertEqual(2, stackless.getruncount())  # The None tasklet.
    stackless.schedule()
      
  def testLastChannel(self):
    channel_obj = stackless.channel()
    self.assertRaisesStr(
        RuntimeError, 'Deadlock: the last runnable tasklet cannot be blocked.',
        channel_obj.receive)
    self.assertRaisesStr(
        RuntimeError, 'Deadlock: the last runnable tasklet cannot be blocked.',
        channel_obj.send, 55)

    tasklet_obj = stackless.tasklet(channel_obj.receive)()
    self.assertFalse(tasklet_obj.blocked)
    stackless.schedule_remove()  # Blocking re-adds us (stackless.main).
    self.assertTrue(tasklet_obj.blocked)
    self.assertEqual(-1, channel_obj.balance)
    tasklet_obj.kill()
    self.assertEqual(0, channel_obj.balance)
    self.assertFalse(tasklet_obj.blocked)
    self.assertEqual(1, stackless.getruncount())

    stackless.tasklet(lambda: 1 / 0)()
    self.assertRaisesStr(
        StopIteration,
        'the main tasklet is receiving without a sender available.',
        channel_obj.receive)
    self.assertEqual(1, stackless.getruncount())
    self.assertRaisesStr(
        RuntimeError, 'Deadlock: the last runnable tasklet cannot be blocked.',
        channel_obj.send, 55)

    # The AssertionError will get ignored and converted to a StopIteration.
    # (That's a bit odd behavior of Stackless.)
    def LazyWorker():
      stackless.schedule()
      stackless.schedule()
      stackless.schedule()
      assert 0
    tasklet_obj = stackless.tasklet(LazyWorker)()
    stackless.schedule()
    self.assertEqual(2, stackless.getruncount())
    self.assertTrue(tasklet_obj.alive)
    self.assertRaisesStr(
        StopIteration,
        'the main tasklet is receiving without a sender available.',
        channel_obj.receive)
    self.assertFalse(tasklet_obj.alive)
    self.assertEqual(1, stackless.getruncount())
    self.assertRaisesStr(
        RuntimeError, 'Deadlock: the last runnable tasklet cannot be blocked.',
        channel_obj.send, 55)

    def ValueWorker():
      stackless.schedule()
      raise ValueError

    def DivideWorker():
      stackless.schedule()
      1 / 0

    tasklet1 = stackless.tasklet(ValueWorker)()
    tasklet2 = stackless.tasklet(DivideWorker)()
    stackless.schedule()
    self.assertEqual(3, stackless.getruncount())
    self.assertTrue(tasklet1.alive)
    self.assertTrue(tasklet2.alive)
    self.assertRaises(ValueError, channel_obj.receive)
    self.assertFalse(tasklet1.alive)
    self.assertTrue(tasklet2.alive)
    self.assertEqual(2, stackless.getruncount())
    self.assertRaisesStr(
        StopIteration,
        'the main tasklet is sending without a receiver available.',
        channel_obj.send, 55)
    tasklet2.kill()

  def testInsertTooEarly(self):
    tasklet_obj = stackless.tasklet(lambda: 1 / 0)  # No __call__.
    self.assertFalse(tasklet_obj.alive)
    self.assertRaisesStr(
        RuntimeError, 'You cannot run an unbound(dead) tasklet',
        tasklet_obj.insert)

  def testLateBind(self):
    tasklet_obj = stackless.tasklet(lambda: 0)()
    self.assertRaisesStr(RuntimeError, 'tasklet is already bound to a frame',
                         tasklet_obj.bind, lambda: 2 / 0)
    stackless.schedule()
    tasklet_obj.bind(lambda: 3 / 0)

  def testInsertCurrent(self):
    items = []
    stackless.tasklet(items.append)(55)
    stackless.tasklet(items.append)(66)
    stackless.current.insert()
    self.assertEqual([], items)
    stackless.schedule()
    self.assertEqual([55, 66], items)

  def testLateCall(self):
    tasklet_obj = stackless.tasklet(lambda: 0)()
    self.assertRaisesStr(TypeError, 'cframe function must be a callable',
                         tasklet_obj)
    tasklet_obj.remove()
    self.assertRaisesStr(TypeError, 'cframe function must be a callable',
                         tasklet_obj)

  def testRun(self):
    stackless.tasklet(stackless.schedule)(42)
    tasklet_obj = stackless.tasklet(stackless.schedule)(43)
    stackless.tasklet(stackless.schedule)(44)
    self.assertEqual(4, stackless.getruncount())
    self.assertEqual(None, tasklet_obj.run())
    self.assertEqual(4, stackless.getruncount())
    self.assertEqual(50, stackless.schedule(50))
    self.assertEqual(2, stackless.getruncount())
    self.assertEqual(51, stackless.schedule(51))
    self.assertEqual(1, stackless.getruncount())

    def Bomber(tasklet_obj, msg):
      tasklet_obj.tempval = stackless.bomb(AssertionError, msg)

    stackless.tasklet(Bomber)(stackless.current, 'foo')
    stackless.tasklet(Bomber)(stackless.current, 'bar')
    self.assertRaisesStr(AssertionError, 'bar', stackless.schedule)

    def Setter(tasklet_obj, msg):
      tasklet_obj.tempval = msg

    stackless.tasklet(Setter)(stackless.current, 'food')
    stackless.tasklet(Setter)(stackless.current, 'bard')
    self.assertEqual('bard', stackless.schedule())
    self.assertEqual(1, stackless.getruncount())
    
    stackless.tasklet(Setter)(stackless.current, 'fooe')
    tasklet_obj = stackless.tasklet(Setter)(stackless.current, 'bare')
    stackless.tasklet(Setter)(stackless.current, 'baze')
    stackless.current.tempval = 'tv'
    self.assertEqual('tv', stackless.current.run())
    self.assertEqual('baze', tasklet_obj.run())
    self.assertEqual('fooe', stackless.schedule())
    self.assertEqual(1, stackless.getruncount())

    stackless.current.tempval = 50
    tasklet_obj = stackless.tasklet(lambda: 0)()
    self.assertEqual(50, tasklet_obj.run())
    self.assertEqual(None, stackless.current.tempval)
    self.assertEqual(1, stackless.getruncount())

    stackless.current.tempval = 51
    self.assertEqual(51, stackless.current.run())
    self.assertEqual(None, stackless.current.tempval)

  def testRaiseException(self):
    def Ignorer():
      try:
        stackless.schedule()
        1 / 0
      except AssertionError, e:
        assert str(e) == 'ae'

    def Setter(tasklet_obj, msg):
      tasklet_obj.tempval = msg

    tasklet1 = stackless.tasklet(lambda: 0)()
    tasklet2 = stackless.tasklet(Setter)(stackless.current, 'back')
    self.assertEqual('back', tasklet1.kill())
    self.assertEqual(1, stackless.getruncount())

    tasklet1 = stackless.tasklet(Ignorer)()
    stackless.schedule()  # Enter the `try:' block in Ignorer.
    tasklet2 = stackless.tasklet(Setter)(stackless.current, 'back2')
    self.assertEqual('back2', tasklet1.raise_exception(AssertionError, 'ae'))
    self.assertEqual(1, stackless.getruncount())

    channel_obj = stackless.channel()
    tasklet1 = stackless.tasklet(channel_obj.receive)()
    self.assertEqual(0, channel_obj.balance)
    stackless.schedule()
    self.assertEqual(-1, channel_obj.balance)
    tasklet1.kill()
    self.assertEqual(0, channel_obj.balance)
    self.assertEqual(1, stackless.getruncount())

    def ReceiveIgnorer():
      try:
        channel_obj.receive()
        1 / 0
      except AssertionError, e:
        assert str(e) == 'ae'

    tasklet1 = stackless.tasklet(ReceiveIgnorer)()
    self.assertEqual(0, channel_obj.balance)
    stackless.schedule()
    self.assertEqual(-1, channel_obj.balance)
    tasklet1.raise_exception(AssertionError, 'ae')
    self.assertEqual(0, channel_obj.balance)

  def testSendInsert(self):
    channel_obj = stackless.channel()
    self.assertEqual(None, channel_obj.queue)
    tasklet1 = stackless.tasklet(lambda: 1 / 0)()
    tasklet2 = stackless.tasklet(channel_obj.receive)()
    tasklet2.run()
    self.assertRaisesStr(
        RuntimeError, 'You cannot remove a blocked tasklet.',
        tasklet2.remove)
    # channel_obj.send inserts tasklet2 after current, and since tasklet1 was
    # after current, the insertion runs tasklet1 eventually, which triggers
    # the ZeroDivisionError, propagated to current (== main).
    self.assertRaises(ZeroDivisionError, channel_obj.send, 0)
    self.assertEqual(1, stackless.getruncount())
    self.assertEqual(None, channel_obj.queue)

    channel_obj.preference = 1  # Prefer the sender.
    tasklet1 = stackless.tasklet(lambda: 1 / 0)()
    tasklet2 = stackless.tasklet(channel_obj.receive)()
    self.assertEqual(False, tasklet2.blocked)
    self.assertEqual(True, tasklet2.scheduled)
    tasklet2.run()
    self.assertEqual(True, tasklet2.blocked)
    self.assertEqual(True, tasklet2.scheduled)
    self.assertEqual(tasklet1, stackless.getcurrent().next)
    self.assertEqual(None, channel_obj.send(0))
    self.assertEqual(tasklet1, stackless.getcurrent().next)
    self.assertEqual(tasklet2, stackless.current.prev)
    tasklet1.remove()
    stackless.schedule()

  def testIsMain(self):
    self.assertTrue(isinstance(stackless.current, stackless.tasklet))
    self.assertEqual(True, stackless.current.is_main)
    self.assertEqual(stackless.main, stackless.current)


if __name__ == '__main__':
  unittest.main()
