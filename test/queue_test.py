#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Wed May  5 19:53:45 CEST 2010

import stackless
import unittest

from syncless import coio
from syncless import util


class QueueTest(unittest.TestCase):
  def testEmptyQueue(self):
    q = util.Queue()
    self.assertFalse(q)
    self.assertEqual(0, len(q))

  def testNonBlockingQueue(self):
    q = util.Queue([55, 66])
    self.assertEqual(2, len(q))
    q.append(77)
    self.assertTrue(q)
    self.assertEqual(3, len(q))
    self.assertEqual(77, q.pop())
    self.assertEqual(2, len(q))
    self.assertEqual(55, q.popleft())
    self.assertEqual(1, len(q))
    self.assertTrue(q)
    self.assertEqual(66, q.popleft())
    self.assertEqual(0, len(q))
    self.assertFalse(q)
    q.appendleft(88)
    q.appendleft(99)
    self.assertEqual([99, 88], list(q))

  def testBlockingQueue(self):
    events = []
    q = util.Queue()

    def Worker(prefix):
      while True:
        item = q.popleft()
        events.append((prefix, item))
        if not item:
          return

    stackless.tasklet(Worker)(1)
    stackless.tasklet(Worker)(2)
    self.assertEqual(0, q.pending_receiver_count)
    stackless.schedule()
    self.assertEqual(2, q.pending_receiver_count)
    self.assertEqual([], events)
    q.append('foo')
    self.assertEqual([], events)
    self.assertEqual(1, len(q))
    stackless.schedule()
    self.assertEqual(0, len(q))
    self.assertEqual([(1, 'foo')], events)
    q.append('bar')
    self.assertEqual(1, len(q))
    self.assertEqual([(1, 'foo')], events)
    stackless.schedule()
    self.assertEqual(0, len(q))
    self.assertEqual([(1, 'foo'), (2, 'bar')], events)
    self.assertEqual(2, q.pending_receiver_count)
    q.append(0)
    q.append(None)
    self.assertEqual(2, len(q))
    self.assertEqual(0, q.pending_receiver_count)
    stackless.schedule()
    self.assertEqual([(1, 'foo'), (2, 'bar'), (1, 0), (2, None)], events)
    self.assertEqual(0, len(q))
    self.assertEqual(0, q.pending_receiver_count)

  def testBlockingQueueReverse(self):
    events = []
    q = util.Queue()

    def Worker(prefix):
      while True:
        item = q.pop()
        events.append((prefix, item))
        if not item:
          return

    stackless.tasklet(Worker)(1)
    stackless.tasklet(Worker)(2)
    self.assertEqual(0, q.pending_receiver_count)
    stackless.schedule()
    self.assertEqual(2, q.pending_receiver_count)
    self.assertEqual([], events)
    q.append('foo')
    self.assertEqual([], events)
    self.assertEqual(1, len(q))
    stackless.schedule()
    self.assertEqual(0, len(q))
    self.assertEqual([(1, 'foo')], events)
    q.append('bar')
    self.assertEqual(1, len(q))
    self.assertEqual([(1, 'foo')], events)
    stackless.schedule()
    self.assertEqual(0, len(q))
    self.assertEqual([(1, 'foo'), (2, 'bar')], events)
    self.assertEqual(2, q.pending_receiver_count)
    q.append(0)
    q.append(None)
    self.assertEqual(2, len(q))
    self.assertEqual(0, q.pending_receiver_count)
    stackless.schedule()
    # Only this is different from testBlockingQueue.
    self.assertEqual([(1, 'foo'), (2, 'bar'), (1, None), (2, 0)], events)
    self.assertEqual(0, len(q))
    self.assertEqual(0, q.pending_receiver_count)
    

if __name__ == '__main__':
  unittest.main()
