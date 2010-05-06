#! /usr/bin/python2.5

"""Partial emulation of the Stackless Python API using greenlet.

Limitations of this emulation module over real Stackless:

* both greenlet and the emulation is slower than Stackless
* greenlet has some memory leaks if greenlets reference each other
* no stackless.current support (use stackless.getcurrent())
* no multithreading support (don't use greenstackless in more than one
  thread (not even sequentially) in your application)
* no deadlock detection if the main tasklet gets stuck

Original _syncless.py downloaded from
http://github.com/toymachine/concurrence/raw/master/lib/concurrence/_stackless.py
at Thu Jan  7 22:59:54 CET 2010. Then modified and added unit test
(test/stackless_test.py).
"""

# Copyright (C) 2009, Hyves (Startphone Ltd.)
#
# This module is part of the Concurrence Framework and is released under
# the New BSD License: http://www.opensource.org/licenses/bsd-license.php

"""This module implements the stackless API on top of py.magic greenlet API
This way it is possible to run concurrence applications on top of normal python
using the greenlet module.
Because the greenlet module uses only 'hard' switching as opposed to stackless 'soft' switching
it is a bit slower (about 35%), but very usefull because you don't need to install stackless.
Note that this does not aim to be a complete implementation of stackless on top of greenlets,
just enough of the stackless API to make concurrence run.
This code was inspired by:
http://aigamedev.com/programming-tips/round-robin-multi-tasking and
also by the pypy implementation of the same thing (buggy, not being maintained?) at
https://codespeak.net/viewvc/pypy/dist/pypy/lib/stackless.py?view=markup
"""

try:
  from py.magic import greenlet #as of version 1.0 of py, it does not supply greenlets anymore
except ImportError:
  from greenlet import greenlet #there is an older package containing just the greenlet lib

assert hasattr(greenlet, 'throw'), (
  'wrong version of greenlet loaded; please get greenlet from svn co '
  'http://codespeak.net/svn/py/release/0.9.x/py/c-extension/greenlet')

import sys
import weakref
from collections import deque

class TaskletExit(SystemExit):
  pass

import __builtin__
__builtin__.TaskletExit = TaskletExit


class bomb(object):
  """Used as a result value for sending exceptions trough a channel."""

  __slots__ = ['type', 'value', 'traceback']

  def __init__(self, exc_type = None, exc_value = None, exc_traceback = None):
    self.type = exc_type
    self.value = exc_value
    self.traceback = exc_traceback

class channel(object):
  """Implementation of stackless's channel object."""

  __slots__ = ['balance', 'preference', '_queue', '__weakref__']

  def __init__(self):
    self.balance = 0
    self.preference = -1
    self._queue = deque()

  @property
  def queue(self):
    if self._queue:
      return self._queue[0]
    else:
      return None

  def receive(self):
    return _receive(self, self.preference)

  def send(self, data):
    return _send(self, data, self.preference)

  def send_exception(self, exc_type, *args):
    self.send(bomb(exc_type, exc_type(*args)))

  def send_sequence(self, iterable):
    for item in iterable:
      self.send(item)


def _tasklet_wrapper(tasklet_obj, switch_back_ary, args, kwargs):
  try:
    switch_back_ary.pop().switch()
    tasklet_obj._func(*args, **kwargs)
    assert _runnables.popleft() is tasklet_obj
  except TaskletExit:  # Let it pass silently.
    assert _runnables.popleft() is tasklet_obj
  except:
    exc_info = sys.exc_info()
    assert _runnables.popleft() is tasklet_obj
    assert tasklet_obj is not main
    if _runnables:  # Make main _runnables[0].
      i = 0
      for task in _runnables:
        if task is main:
          if i:
            _runnables.rotate(-i)
          break
        i += 1
      main.tempval = bomb(*exc_info)
      if _runnables[0] is not main:
        _runnables.appendleft(main)
    elif main._channel_weak:
      # If _runnables is empty, let the error be ignored here, and
      # so a StopIteration being raised in the main tasklet, see
      # LazyWorker in StacklessTest.testLastchannel.
      main.tempval = None
  finally:
    if not _runnables:
      _runnables.append(main)
    # This make sure that flow will continue in the correct greenlet,
    # e.g. the next in the runnables list.
    tasklet_obj._greenlet.parent = _runnables[0]._greenlet
    tasklet_obj.alive = False
    tasklet_obj.tempval = None
    del tasklet_obj._greenlet
    del tasklet_obj._func
    del tasklet_obj.data
    # Keeping forever: del tasklet_obj.tempval
    # Keeping forever: del tasklet_obj._channel_weak


is_slow_prev_next_ok = False
"""Bool indicating if emulating tasklet.prev and teasklet.next slowly."""


class tasklet(object):
  """Implementation of stackless's tasklet object.

  TODO(pts): Implement tasklet._channel as a weak reference.
  """

  __slots__ = ['_greenlet', '_func', 'alive', '_channel_weak', 'tempval',
               'data', '__weakref__']

  def __init__(self, f = None, greenlet = None, alive = False):
    self._greenlet = greenlet
    self._func = f
    self.alive = alive
    self.data = None
    self.tempval = None
    self._channel_weak = None

  @property
  def blocked(self):
    return bool(self._channel_weak)

  @property
  def _channel(self):
    # This propery has an odd name (starting with _), to mimic Stackless.
    return self._channel_weak and self._channel_weak()

  def bind(self, func):
    if not callable(func):
      raise TypeError('tasklet function must be a callable')
    if getattr(self, '_greenlet', None):
      raise RuntimeError('tasklet is already bound to a frame')
    self._func = func
    return self

  def __call__(self, *args, **kwargs):
    """this is where the new task starts to run, e.g. it is where the greenlet is created
    and the 'task' is first scheduled to run"""
    if self._func is None:
      raise TypeError('tasklet function must be a callable')
    assert self not in _runnables
    # TODO(pts): Do we properly avoid circular references to self here?
    self._greenlet = greenlet(_tasklet_wrapper)
    # We need this initial switch so the function enters its `try ...
    # finally' block. We get back control very soon after the initial switch.
    self._greenlet.switch(self, [greenlet.getcurrent()], args, kwargs)
    self.alive = True
    _runnables.append(self)
    return self

  def kill(self):
    _throw(self, TaskletExit)

  def raise_exception(self, exc_class, *args):
    _throw(self, exc_class(*args))

  def throw(self, typ, val, tb):
    """Raise the specified exception with the specified traceback.

    Please note there is no such method tasklet.throw in Stackless. In
    stackless, one can use tasklet_obj.tempval = stackless.bomb(...), and
    then tasklet_obj.run() -- or send the bomb in a channel if the
    target tasklet is blocked on receiving from.
    """
    _throw(self, typ, val, tb)

  def __str__(self):
    return repr(self)

  def __repr__(self):
    if hasattr(self, 'name'):
      _id = self.name
    else:
      _id = str(self._func)
    return '<tasklet %s at 0x%0x>' % (_id, id(self))

  def is_main(self):
    return self is main

  def remove(self):
    """Remove self from the main scheduler queue.

    Please note that this implementation has O(r) complexity, where r is
    the number or runnable (non-blocked) tasklets. The implementation in
    Stackless has O(1) complexity.
    """
    if self is _runnables[0]:
      raise RuntimeError('The current tasklet cannot be removed. '
                         'Use t=tasklet().capture()')
    if self._channel_weak:
      raise RuntimeError('You cannot remove a blocked tasklet.')
    i = 0
    for task in _runnables:
      if task is self:
        del _runnables[i]
        return self
      i += 1
    return self

  def insert(self):
    """Add self to the end of the scheduler queue, unless already in.

    Please note that this implementation has O(r) complexity, where r is
    the number or runnable (non-blocked) tasklets. The implementation in
    Stackless has O(1) complexity.
    """
    if not self.alive:
      raise RuntimeError('You cannot run an unbound(dead) tasklet')
    if self._channel_weak:
      raise RuntimeError('You cannot run a blocked tasklet')
    if self not in _runnables:
      _runnables.append(self)

  @property
  def next(self):
    """Return the next tasklet in the doubly-linked list.

    Stackless implements this method for all tasklets. This implementation
    raises a NotImplementedError unless self is stackless.getcurrent() or
    self is the last runnable tasklet.
    """
    if self is _runnables[0]:
      return _runnables[len(_runnables) > 1]
    elif self is _runnables[-1]:
      return _runnables[0]
    elif self._channel_weak:
      channel_obj = self._channel_weak()
      assert channel_obj
      # TODO(pts): Implement this with a linked list.
      queue = channel_obj._queue
      if self is queue[-1]:
        return None
      i = iter(queue)
      for tasklet_obj in i:
        if self is tasklet_obj:
          # No StopIteration because the ifs above.
          return i.next()
      assert 0, 'blocked tasklet missing from its own channel'
    elif is_slow_prev_next_ok:
      i = iter(_runnables)
      for tasklet_obj in i:
        if self is tasklet_obj:
          # No StopIteration because the ifs above.
          return i.next()
    else:
      raise NotImplementedError('tasklet.next for not current or last')

  @property
  def prev(self):
    """Return the next tasklet in the doubly-linked list.

    Stackless implements this method for all tasklets. This implementation
    raises a NotImplementedError unless self is stackless.getcurrent() or
    self is the last runnable tasklet.
    """
    if self is _runnables[0]:
      return _runnables[-1]
    elif self is _runnables[-1]:
      return _runnables[-2]
    elif self._channel_weak:
      channel_obj = self._channel_weak()
      assert channel_obj
      queue = channel_obj._queue
      prev_tasklet_obj = None
      for tasklet_obj in channel_obj._queue:
        if self is tasklet_obj:
          return prev_tasklet_obj
        prev_tasklet_obj = tasklet_obj
      assert 0, 'blocked tasklet missing from its own channel'
    elif is_slow_prev_next_ok:
      prev_tasklet_obj = None
      for tasklet_obj in _runnables:
        if self is tasklet_obj:
          return prev_tasklet_obj
        prev_tasklet_obj = tasklet_obj
    else:
      raise NotImplementedError('tasklet.prev for not current or last')

  def run(self):
    """Switch execution to self, make it stackless.getcurrent().

    Please note that this implementation has O(r) complexity, where r is
    the number or runnable (non-blocked) tasklets. The implementation in
    Stackless has O(1) complexity.
    """
    if self._channel_weak:
      raise RuntimeError('You cannot run a blocked tasklet')
    if not self.alive:
      raise RuntimeError('You cannot run an unbound(dead) tasklet')
    i = 0
    for task in _runnables:
      if task is self:
        if i:
          _runnables.rotate(-i)
          self._greenlet.switch()
        return
      i += 1
    _runnables.appendleft(self)
    self._greenlet.switch()


main = tasklet(greenlet = greenlet.getcurrent(), alive = True)

#all non-blocked tasks are in this queue
#all tasks are only once in this queue
#the current task is the first item in the queue
_runnables = deque([main])

def schedule(*args):
  """Schedule the next tasks and puts the current task back at the queue of _runnables."""
  current_tasklet = _runnables[0]
  if args:
    if len(args) != 1:
      raise TypeError('schedule() takes at most 1 argument (%d given)' %
                      len(args))
    current_tasklet.tempval = args[0]
  else:
    current_tasklet.tempval = current_tasklet
  _runnables.rotate(-1)
  _runnables[0]._greenlet.switch()
  data = current_tasklet.tempval
  current_tasklet.tempval = None
  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data

def schedule_remove(*args):
  """makes stackless.getcurrent() not _runnables, schedules next tasks"""
  current_tasklet = _runnables[0]
  if args:
    if len(args) != 1:
      raise TypeError('schedule() takes at most 1 argument (%d given)' %
                      len(args))
    current_tasklet.tempval = args[0]
  else:
    current_tasklet.tempval = _runnables[0]
  _runnables.popleft()
  if not _runnables:
    _runnables.append(main)
  _runnables[0]._greenlet.switch()
  data = current_tasklet.tempval
  current_tasklet.tempval = None
  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data


def _throw(task, typ, val=None, tb=None):
  """Raise an exception in the tasklet, and run it.

  Please note that this implementation has O(r) complexity, where r is
  the number or runnable (non-blocked) tasklets. The implementation in
  Stackless has O(1) complexity.
  """
  if not task.alive:
    return
  # TODO(pts): Avoid circular parent chain exception here.
  if (task is not _runnables[0] and
      _runnables[0]._greenlet.parent is not task._greenlet):
      task._greenlet.parent = _runnables[0]._greenlet
  if not task._channel_weak:
    i = 0
    for task2 in _runnables:
      if task2 is task:
        if i:  # TODO(pts): Redesign to make these iterations O(1).
          _runnables.rotate(-i)
          task._greenlet.throw(typ, val, tb)
          return
        else:
          raise typ, val, tb
      i += 1
  _runnables.appendleft(task)
  task._greenlet.throw(typ, val, tb)

def _receive(channel_obj, preference):
  #Receiving 1):
  #A tasklet wants to receive and there is
  #a queued sending tasklet. The receiver takes
  #its data from the sender, unblocks it,
  #and inserts it at the end of the _runnabless.
  #The receiver continues with no switch.
  #Receiving 2):
  #A tasklet wants to receive and there is
  #no queued sending tasklet.
  #The receiver will become blocked and inserted
  #into the queue. The next sender will
  #handle the rest through "Sending 1)".
  if channel_obj.balance > 0: #some sender
    channel_obj.balance -= 1
    sender = channel_obj._queue.popleft()
    sender._channel_weak = None
    data, sender.data = sender.data, None
    if preference >= 0:
      #sender preference
      _runnables.rotate(-1)
      _runnables.appendleft(sender)
      _runnables.rotate(1)
      schedule()
    else:
      #receiver preference
      _runnables.append(sender)
  else: #no sender
    if len(_runnables) == 1 and (_runnables[0] is main or main._channel_weak):
      # Strange exception name.
      raise RuntimeError('Deadlock: the last runnable tasklet '
                         'cannot be blocked.')
    current = _runnables.popleft()
    channel_obj._queue.append(current)
    channel_obj.balance -= 1
    current._channel_weak = weakref.ref(channel_obj)
    if not _runnables:
      _runnables.append(main)
    try:
      _runnables[0]._greenlet.switch()
      if current._channel_weak:
        assert current is main
        if isinstance(current.tempval, bomb):
          bomb_obj, current.tempval = current.tempval, None
          raise bomb_obj[0], bomb_obj[1], bomb_obj[2]
        else:
          assert current.tempval is None
          raise StopIteration('the main tasklet is receiving '
                              'without a sender available.')
    except:
      channel_obj._queue.remove(current)
      channel_obj.balance += 1
      current._channel_weak = None
      raise

    data, current.data = current.data, None

  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data

def _send(channel_obj, data, preference):
  #  Sending 1):
  #  A tasklet wants to send and there is
  #  a queued receiving tasklet. The sender puts
  #  its data into the receiver, unblocks it,
  #  and inserts it at the top of the _runnabless.
  #  The receiver is scheduled.
  #  Sending 2):
  #  A tasklet wants to send and there is
  #  no queued receiving tasklet.
  #  The sender will become blocked and inserted
  #  into the queue. The next receiver will
  #  handle the rest through "Receiving 1)".
  if channel_obj.balance < 0: #some receiver
    channel_obj.balance += 1
    receiver = channel_obj._queue.popleft()
    receiver.data = data
    receiver._channel_weak = None
    #put receiver just after current task in _runnables and schedule (which will pick it up)
    if preference < 0: #receiver pref
      _runnables.rotate(-1)
      _runnables.appendleft(receiver)
      _runnables.rotate(1)
      schedule()
    else: #sender pref
      _runnables.append(receiver)
  else: #no receiver
    if len(_runnables) == 1 and (_runnables[0] is main or main._channel_weak):
      raise RuntimeError('Deadlock: the last runnable tasklet '
                         'cannot be blocked.')
    current = _runnables.popleft()
    channel_obj._queue.append(current)
    channel_obj.balance += 1
    current.data = data
    current._channel_weak = weakref.ref(channel_obj)
    if not _runnables:
      _runnables.append(main)
    try:
      _runnables[0]._greenlet.switch()
      if current._channel_weak:
        assert current is main
        if isinstance(current.tempval, bomb):
          bomb_obj, current.tempval = current.tempval, None
          raise bomb_obj[0], bomb_obj[1], bomb_obj[2]
        else:
          assert current.tempval is None
          raise StopIteration('the main tasklet is sending '
                              'without a receiver available.')
    except:
      channel_obj._queue.remove(current)
      channel_obj.balance -= 1
      current.data = None
      current._channel_weak = None
      raise

def getruncount():
  return len(_runnables)

def getcurrent():
  return _runnables[0]

def getmain():
  return main
