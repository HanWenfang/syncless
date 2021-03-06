#! /usr/local/bin/stackless2.6

"""A demo for enforcing a timeout on multiple read operations."""

import sys

from syncless import coio
from syncless import util
from syncless import patch


def Asker(timeout_arg):
  print 'You have %s seconds altogether to tell me your age.' % timeout_arg
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
    return age

if __name__ == '__main__':
  patch.patch_stdin_and_stdout()  # sets sys.stdin = sys.stdout = ...
  patch.patch_stderr()  # For fair exeption reporting.
  timeout = 3
  age = util.run_in_tasklet_with_timeout(Asker, timeout, None, (timeout,))
  if age is None:  # Timed out.
    print 'You were too slow entering your age.'
  else:
    print 'Got age: %r.' % age
  if len(sys.argv) > 1:
    # Run until all tasklets exit. This doesn't work anymore with libev.
    stackless.schedule_remove(None)
