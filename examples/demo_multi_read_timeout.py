#! /usr/local/bin/stackless2.6

"""A demo for enforcing a timeout on multiple read operations.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
"""

import stackless
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
