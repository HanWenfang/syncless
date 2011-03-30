#! /usr/local/bin/stackless2.6

import os
import signal
import sys
import unittest

from syncless import coio


class SignalTest(unittest.TestCase):
  def testSignalHandlerEvent(self):
    got = []
    s1 = coio.signal_handler_event(signal.SIGUSR2, lambda *args: got.append(1))
    s2 = coio.signal_handler_event(signal.SIGUSR2, lambda *args: got.append(2))
    try:
      t = coio.stackless.tasklet(coio.sleep)(999999)  # A non-internal event.
      try:
        coio.stackless.schedule()  # Start the sleeping.
        self.assertEqual([], got)
        os.kill(os.getpid(), signal.SIGUSR2)
        self.assertEqual([], got)
        coio.stackless.schedule()
        # The order doesn't matter.
        self.assertEqual([1, 2], sorted(got))
        coio.stackless.schedule()
        # The order doesn't matter.
        self.assertEqual([1, 2], sorted(got))
      finally:
        t.insert()  # Cancel the sleep.
        coio.stackless.schedule()
    finally:
      s1.delete()
      s2.delete()


if __name__ == '__main__':
  unittest.main()
