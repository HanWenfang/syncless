#! /usr/local/bin/stackless2.6

"""Generally useful, non-performance-critical Syncless functions."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys
from collections import deque

from syncless.best_stackless import stackless
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
  worker_tasklet = coio.stackless.tasklet(Worker)(
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


class Queue(object):
  """Like stackless.channel, but messages queue up if there is no receiver.

  Typical use: to send data, use the append() method. To receive data in FIFO
  (queue) order, use the popleft() method. To receive data in LIFO (stack,
  reverse) order, use the pop() method.

  There is no upper limit on the number of items in the queue.
  """

  def __init__(self, items=(), preference=1):
    self.deque = deque(items)
    self.channel = stackless.channel()
    self.channel.preference = preference  # preference=1: prefer the sender.

  def __len__(self):
    """Number of items appended but not popped."""
    return len(self.deque)

  @property
  def pending_receiver_count(self):
    return -self.channel.balance

  def append(self, item):
    self.deque.append(item)
    if self.channel.balance < 0:
      self.channel.send(None)

  def appendleft(self, item):
    self.deque.appendleft(item)
    if self.channel.balance < 0:
      self.channel.send(item)

  def popleft(self):
    while not self.deque:
      self.channel.receive()
    return self.deque.popleft()

  def pop(self):
    while not self.deque:
      self.channel.receive()
    return self.deque.pop()

  def __iter__(self):
    return iter(self.deque)


class TimeoutException(Exception):
  """Raised when the timeout has been reached."""


class Timeout(object):
  """Timeout context manager.
  
  Example (needs Python 2.6):

    with Timeout(1.5):
      ... # Do work here.

  If the timeout is reached, the work is silently terminated, and execution
  resumes at after the `while' block. This is implemented by creating a
  timeout tasklet, which raises TimeoutException (configurable), which gets
  caught and ignored in self.__exit__ in the current (busy) tasklet.

  If the busy tasklet is not scheduled or it's blocked on a channel, the
  TimeoutException gets delivered anyway, inserting back the busy tasklet to
  the runnables list.

  Please note that multitasking with Syncless is still cooperative:
  TimeoutException won't be delivered until the Syncless main loop tasklet
  is scheduled, and for that, all busy tasklets has to give up control (by
  running a coio.sleep, a Syncless non-blocking I/O operation, or a
  stackless.schedule() or stackless.schedule_remove().
  """
  __slots__ = ['timeout', 'sleeper_tasklet', 'busy_tasklet', 'exc']
  def __init__(self, timeout, exc=TimeoutException):
    self.timeout = timeout
    self.busy_tasklet = self.sleeper_tasklet = None
    self.exc = exc

  def __enter__(self):
    self.busy_tasklet = stackless.current
    if self.timeout is not None:
      self.sleeper_tasklet = stackless.tasklet(self.Sleeper)()
    return self

  def __exit__(self, typ, val, tb):
    self.busy_tasklet = None
    if self.sleeper_tasklet:
      # Let's continue with us after the kill().
      self.sleeper_tasklet.remove().kill()
      self.sleeper_tasklet = None
    if typ:
      if isinstance(self.exc, BaseException):
        return issubclass(typ, type(self.exc))
      else:
        return issubclass(typ, self.exc)

  def cancel(self):
    """Cancel the timeout, let it run indefinitely.
    
    self.cancel() is equivalent to self.change(None).
    """
    if self.sleeper_tasklet:
      self.sleeper_tasklet.remove().kill()
      self.sleeper_tasklet = None

  def change(self, timeout):
    """Change the timeout (restarting from 0)."""
    if self.sleeper_tasklet:
      self.sleeper_tasklet.remove().kill()
      self.sleeper_tasklet = None
    self.timeout = timeout
    if timeout is not None:
      # TODO(pts): speed: Do this without creating a new tasklet. Would this
      # improve speed?
      self.sleeper_tasklet = stackless.tasklet(self.Sleeper)()

  def Sleeper(self):
    coio.sleep(self.timeout)
    if self.busy_tasklet:
      if isinstance(self.exc, BaseException):
        self.busy_tasklet.raise_exception(type(self.exc), *self.exc.args)
      else:
        self.busy_tasklet.raise_exception(self.exc)
