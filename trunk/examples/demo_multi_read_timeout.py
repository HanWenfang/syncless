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

def RunInTaskletWithTimeout(function, timeout, default_value=None,
                            args=(), kwargs={}):
  # TODO(pts): Productionize this.
  # !! TODO(pts): Kill the Worker if TaskletExit (or something else) is sent
  # to us.
  results = []
  def Worker(sleeper_tasklet, function, args, kwargs):
    try:
      results.append(function(*args, **kwargs))
    except TaskletExit:
      raise
    except:
      results.extend(sys.exc_info())
    if sleeper_tasklet.alive:
      sleeper_tasklet.insert()  # Interrupt coio.sleep().
  worker_tasklet = stackless.tasklet(Worker)(
      stackless.current, function, args, kwargs)
  if coio.sleep(timeout) and worker_tasklet.alive:
    worker_tasklet.kill()
    return default_value
  else:
    if len(results) > 1:  # Propagate exception.
      raise results[0], results[1], results[2]
    return results[0]

if __name__ == '__main__':
  patch.patch_stdin_and_stdout()  # sets sys.stdin = sys.stdout = ...
  patch.patch_stderr()  # For fair exeption reporting.
  age_answer_channel = stackless.channel()
  age_answer_channel.preference = 1  # Prefer the sender.
  timeout = 3
  age = RunInTaskletWithTimeout(Asker, timeout, None, (timeout,))
  if age is None:  # Timed out.
    print 'You were too slow entering your age.'
  else:
    print 'Got age: %r.' % age
  stackless.schedule_remove()  # Run until all tasklets exit.
