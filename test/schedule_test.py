#! /usr/local/bin/stackless2.6

"""Test for the Syncless scheduler.

!! make this test work with coio instead of nbio.
"""

import os
import stackless
import sys
import unittest

from syncless import nbio

class ScheduleTest(unittest.TestCase):

  def setUp(self):
    # TODO(pts): Detect self.verbosity in one of the unittest.py callers.
    nbio.VERBOSE = '-v' in sys.argv[1:]
    self.assertEqual(1, stackless.runcount)

  def tearDown(self):
    if nbio.HasCurrentMainLoop():
      main_loop = nbio.CurrentMainLoop()
      self.assertEqual(1 + int(main_loop.run_tasklet != stackless.current),
                       stackless.runcount)
      main_loop.Run()
      #self.assertEqual(0, len(main_loop.nbfs))
    self.assertEqual(1, stackless.runcount)

  def testFairAAANothing(self):
    pass

  def testFairZZZNothing(self):
    pass

  def testEmptyMainLoop(self):
    nbio.RunMainLoop()

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
    nbio.RunMainLoop()

    self.assertEqual('ABCABCABCABCABCBCBCBB', ''.join(events))

  def testFairSchedulingWithFile(self):
    events = []
    def Worker(name, count):
      while count > 0:
        events.append(name)
        stackless.schedule()
        count -= 1

    nbf = nbio.NonBlockingFile(*os.pipe())
    try:
      stackless.tasklet(Worker)('A', 5)
      stackless.tasklet(Worker)('B', 9)
      stackless.tasklet(Worker)('C', 7)
      nbio.RunMainLoop()

      self.assertEqual('ABCABCABCABCABCBCBCBB', ''.join(events))
      #self.assertEqual([nbf], nbio.CurrentMainLoop().nbfs)
    finally:
      nbf.close()
    #self.assertEqual([nbf], nbio.CurrentMainLoop().nbfs)
    nbio.RunMainLoop()
    #self.assertEqual([], nbio.CurrentMainLoop().nbfs)

  def testFairSchedulingBlockedOnFile(self):
    events = []

    def Worker(name, count):
      while count > 0:
        events.append(name)
        count -= 1
        if count > 0:
          stackless.schedule()

    nbf = nbio.NonBlockingFile(*os.pipe())

    try:
      def SenderWorker(name, count):
        while count > 0:
          events.append(name)
          count -= 1
          if count > 0:
            stackless.schedule()
        events.append('R')
        nbf.Write('S')
        nbf.Flush()
        events.append('T')

      def ReceiverWorker(name):
        events.append(name)
        nbf.ReadAtMost(1)
        events.append(name.lower())

      stackless.tasklet(SenderWorker)('A', 3)
      stackless.tasklet(Worker)('B', 6)
      stackless.tasklet(ReceiverWorker)('W')
      stackless.tasklet(Worker)('C', 9)
      nbio.RunMainLoop()

      self.assertEqual(
          'ABWC'  # First iteration, in tasklet clreation order.
          'ABC'  # W is blocked on reading now.
          'ARTBC'  # A sends 'S' to wake up W.
          'wBC'  # W woken up, inserted to the beginning of the chain.
          'BC'
          'BC'
          'C'  # B's counter has expired.
          'C'
          'C',
          ''.join(events))
      #self.assertEqual([nbf], nbio.CurrentMainLoop().nbfs)
      nbf.close()
      #self.assertEqual([nbf], nbio.CurrentMainLoop().nbfs)
      nbio.RunMainLoop()
      #self.assertEqual([], nbio.CurrentMainLoop().nbfs)
    finally:
      nbf.close()


if __name__ == '__main__':
  unittest.main()
