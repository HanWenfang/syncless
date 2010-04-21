#! /usr/local/bin/stackless2.6

"""Generally useful, non-performance-critical Syncless functions.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import stackless
import sys

from syncless import coio


def run_in_tasklet_with_timeout(function, timeout, default_value=None,
                                args=(), kwargs={}):
  """Run function in sepearte tasklet, kill when timeout elapsed.
  
  Create a new tasklet, run function(*args, **kwargs) in it, and once done,
  return its return value or raise the exception it has raised. If function
  is not done within `timeout' seconds, send TaskletExit to its tasklet
  (switching to it so it can handle it, then proceeding with scheduling the
  caller tasklet), and return default_value.

  This method is safe when exceptions are raised (or forced) in any of its
  two tasklets. For example, when TaskletExit is raised in any of the
  tasklets, it's immediately propagated to the other tasklet.
  """
  results = []
  def Worker(sleeper_tasklet, function, args, kwargs):
    try:
      results.append(function(*args, **kwargs))
    except:
      # We do this for TaskletExit as well.
      results.extend(sys.exc_info())
    if sleeper_tasklet.alive:
      sleeper_tasklet.insert()  # Interrupt coio.sleep().
  worker_tasklet = stackless.tasklet(Worker)(
      stackless.current, function, args, kwargs)
  try:
    coio.sleep(timeout)
  finally:
    if worker_tasklet.alive:
      worker_tasklet.remove()
      # This raises TaskletExit in Worker, so it might further extend results
      # as a side effect. We don't care about that.
      worker_tasklet.kill()
      return default_value
    else:
      if len(results) > 1:  # Propagate exception.
        raise results[0], results[1], results[2]
      return results[0]
