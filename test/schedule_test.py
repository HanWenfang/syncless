#! /usr/local/bin/stackless2.6

"""Test for the Syncless scheduler."""

import os
import sys
import unittest

from syncless.best_stackless import stackless
from syncless import coio

class ScheduleTest(unittest.TestCase):

  def setUp(self):
    self.assertEqual(2, stackless.getruncount())

  def tearDown(self):
    self.assertEqual(2, stackless.getruncount())

  def testFairAAANothing(self):
    pass

  def testFairZZZNothing(self):
    pass

  def testFairSchedulingWithoutFile(self):
    events = []
    def Worker(name, count):
      while count > 0:
        events.append(name)
        stackless.schedule()
        count -= 1

    stackless.tasklet(Worker)('A', 5)
    stackless.tasklet(Worker)('B', 9)
    stackless.tasklet(Worker)('C', 7)
    for i in xrange(10):
      stackless.schedule()

    self.assertEqual('ABCABCABCABCABCBCBCBB', ''.join(events))

  def testFairSchedulingWithFile(self):
    events = []
    def Worker(name, count):
      while count > 0:
        events.append(name)
        stackless.schedule()
        count -= 1

    nbf = coio.nbfile(*os.pipe())
    try:
      stackless.tasklet(Worker)('A', 5)
      stackless.tasklet(Worker)('B', 9)
      stackless.tasklet(Worker)('C', 7)
      for i in xrange(10):
        stackless.schedule()

      self.assertEqual('ABCABCABCABCABCBCBCBB', ''.join(events))
      #self.assertEqual([nbf], coio.CurrentMainLoop().nbfs)
    finally:
      nbf.close()

  def testFairSchedulingBlockedOnFile(self):
    events = []

    def Worker(name, count):
      while count > 0:
        events.append(name)
        count -= 1
        if count > 0:
          stackless.schedule()

    nbf = coio.nbfile(*os.pipe())

    try:
      def SenderWorker(name, count):
        while count > 0:
          events.append(name)
          count -= 1
          if count > 0:
            stackless.schedule()
        events.append('R')
        nbf.write('S')
        nbf.flush()
        events.append('T')

      def ReceiverWorker(name):
        events.append(name)
        nbf.read_at_most(1)
        events.append(name.lower())

      stackless.tasklet(SenderWorker)('A', 3)
      stackless.tasklet(Worker)('B', 6)
      stackless.tasklet(ReceiverWorker)('W')
      stackless.tasklet(Worker)('C', 9)
      for i in xrange(32):
        stackless.schedule()

      self.assertEqual(
          'ABWC'  # First iteration, in tasklet creation order.
          'ABC'  # W is blocked on reading now.
          'ARTBC'  # A sends 'S' to wake up W.
          'wBC'  # W woken up, inserted to the beginning of the chain.
          'BC'
          'BC'
          'C'  # B's counter has expired.
          'C'
          'C',
          ''.join(events))
      nbf.close()
    finally:
      nbf.close()


if __name__ == '__main__':
  unittest.main()
