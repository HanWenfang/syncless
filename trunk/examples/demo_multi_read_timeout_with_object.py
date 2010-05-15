#! /usr/local/bin/stackless2.6

"""A demo for enforcing a timeout on multiple read operations."""

import sys

import stackless
from syncless import coio
from syncless import patch
from syncless import util

if __name__ == '__main__':
  patch.patch_stdin_and_stdout()  # sets sys.stdin = sys.stdout = ...
  patch.patch_stderr()  # For fair exeption reporting.
  timeout = 3
  final_age = None
  print 'You have %s seconds altogether to tell me your age.' % timeout
  with util.Timeout(timeout) as timeout_obj:
    while True:
      sys.stdout.write('How old are you? ')
      sys.stdout.flush()
      answer = sys.stdin.readline()
      assert answer
      answer = answer.strip()
      try:
        age = int(answer)
      except ValueError:
        print 'Please enter an integer.'
        continue
      if age < 3:
        print 'That would be too young. Please enter a valid age.'
        continue
      assert age != 111, 'simulated bug'
      if age == 222:
        print 'Canceling the timeout.'
        timeout_obj.cancel()
      elif age == 333:
        print 'Canceling the timeout to 1 second, starting from now.'
        timeout_obj.change(1)
      else:
        final_age = age
        break
  assert 2 == stackless.getruncount()
  if final_age is None:  # Timed out.
    print 'You were too slow entering your age.'
  else:
    print 'Got age: %r.' % final_age
  if len(sys.argv) > 1:
    # Run until all tasklets exit. This doesn't work anymore with libev.
    stackless.schedule_remove(None)
