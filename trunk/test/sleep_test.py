#! /usr/local/bin/stackless2.6

import unittest

from syncless import coio


SMALL_SLEEP_SEC = 0.02

LOOPRET = int(bool(coio.has_feature_may_loop_return_1()))

class SleepTest(unittest.TestCase):
  def testMainSleep(self):
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.
    coio.sleep(SMALL_SLEEP_SEC)
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.

  def testZeroSleep(self):
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.
    coio.sleep(0)
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.

  def testNegativeSleep(self):
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.
    coio.sleep(-42)
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.

  def testOtherTaskletSleep(self):
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.
    log_items = []
    sleep_done_channel = coio.stackless.channel()
    sleep_done_channel.preference = 1  # Prefer the sender.

    def Sleeper():
      log_items.append('sleeping')
      coio.sleep(SMALL_SLEEP_SEC)
      log_items.append('slept')
      sleep_done_channel.send(None)

    tasklet_obj = coio.stackless.tasklet(Sleeper)()
    assert tasklet_obj.alive
    assert tasklet_obj.scheduled
    coio.stackless.schedule()
    assert ['sleeping'] == log_items
    assert not tasklet_obj.scheduled
    assert tasklet_obj.alive
    sleep_done_channel.receive()
    assert ['sleeping', 'slept'] == log_items
    assert not tasklet_obj.alive
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.

  def testBombInterruptedSleep(self):
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.
    log_items = []

    def Sleeper():
      try:
        coio.sleep(30)  # Half a minute, won't be reached.
      except AssertionError, e:
        log_items.append(str(e))
      log_items.append('slept')

    tasklet_obj = coio.stackless.tasklet(Sleeper)()
    assert tasklet_obj.alive
    assert tasklet_obj.scheduled
    coio.stackless.schedule()
    assert not tasklet_obj.scheduled
    assert tasklet_obj.alive
    assert 0 == coio.nonblocking_loop_for_tests()  # We have registered events.
    tasklet_obj.tempval = coio.stackless.bomb(AssertionError, 'bombed')
    tasklet_obj.run()
    assert ['bombed', 'slept'] == log_items
    assert not tasklet_obj.alive
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.

  def testRunInterruptedSleep(self):
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.
    log_items = []

    def Sleeper():
      coio.sleep(99999999)  # Quite a lot, won't be reached.
      log_items.append('slept')

    tasklet_obj = coio.stackless.tasklet(Sleeper)()
    assert tasklet_obj.alive
    assert tasklet_obj.scheduled
    coio.stackless.schedule()
    assert not tasklet_obj.scheduled
    assert tasklet_obj.alive
    assert 0 == coio.nonblocking_loop_for_tests()  # We have registered events.
    tasklet_obj.run()
    assert ['slept'] == log_items
    assert not tasklet_obj.alive
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.

  def testReinsertInterruptedSleep(self):
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.
    log_items = []

    def Sleeper():
      coio.sleep(99999999)  # Quite a lot, won't be reached.
      log_items.append('slept')

    tasklet_obj = coio.stackless.tasklet(Sleeper)()
    assert tasklet_obj.alive
    assert tasklet_obj.scheduled
    coio.stackless.schedule()
    assert not tasklet_obj.scheduled
    assert tasklet_obj.alive
    assert 0 == coio.nonblocking_loop_for_tests()  # We have registered events.
    tasklet_obj.insert()
    coio.stackless.schedule()
    assert ['slept'] == log_items
    assert not tasklet_obj.alive
    self.assertEqual(LOOPRET, coio.nonblocking_loop_for_tests())  # No registered events.


if __name__ == '__main__':
  unittest.main()
