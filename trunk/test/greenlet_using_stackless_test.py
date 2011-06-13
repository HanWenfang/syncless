#! /usr/local/bin/stackless2.6

"""Tests for Greenlet emulator (which uses Stackless)."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys
import unittest

import greenlet_test  # test/greenlet_test.py in Syncless.

if __name__ == '__main__':
  try:
    import stackless
  except ImportError:
    stackless = None

  if stackless:
    print >>sys.stderr, 'info: using stackless'
    class GreenletUsingStacklessTest(
        greenlet_test.Template.GreenletTestTemplate):
      from syncless.greenlet_using_stackless import greenlet

    unittest.main()
  else:
    print >>sys.stderr, 'info: stackless not found, skipping'
