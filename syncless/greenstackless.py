#! /usr/bin/python2.5

"""Partial emulation of the Stackless Python API using greenlet.

The emulation is partial, i.e. it doesn't emulate all Stackless classes or
methods -- but for those it emulates, it aims to be as faithful as possible,
even sacrificing speed. See stackless_test.py for a comprehensive test suite.

Limitations of this emulation module over real Stackless:

* no stackless.runcount (use stackless.getruncount() instead)
* both greenlet and the emulation is slower than Stackless
* greenlet has some memory leaks if greenlets reference each other
* no multithreading support (don't use greenstackless in more than one
  thread (not even sequentially) in your application)

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

#from py.magic import greenlet #as of version 1.0 of py, it does not supply greenlets anymore
from greenlet import greenlet  # Import the greenlet class.

assert hasattr(greenlet, 'throw'), (
  'wrong version of greenlet loaded; please get greenlet from svn co '
  'http://codespeak.net/svn/py/release/0.9.x/py/c-extension/greenlet')

import sys
import weakref

# Unrelated to GreenletExit, SystemExit just like in real stackless.
class TaskletExit(SystemExit):
  pass

__import__('__builtin__').TaskletExit = TaskletExit


def ImportTooLateError(Exception):
  """Raised when syncless.coio is imported too late.

  To solve this problem, either import syncless.greenstackless (or
  syncless.best_stackless) before syncless.coio, or don't create any tasklets
  or bombs before importing syncless.coio.
  """


class NewTooLateError(Exception):
  """Raised when an old-class tasklet or bomb instance is created.

  To solve this problem, create all your tasklets and bombs after importing
  syncless.coio.
  """


def _process_slots(slots, superclass, dict_obj=None):
  """Return __slots__ list without items which conflict with superclass."""
  if not isinstance(superclass, type):
    raise TypeError
  slots = set(slots)
  if dict_obj:
    for name in slots:
      dict_obj.pop(name, None)
  for name in dir(superclass):
    if not name.startswith('__') and name in slots:
      slots.remove(name)
  if '__weakref__' in slots:
    try:
      type('dummy', (superclass,), {'__slots__': ['__weakref__']})
    except TypeError, e:
      if '__weakref__' not in str(e):
        raise
      slots.remove('__weakref__')
  return list(slots)


greenstackless_helper = sys.modules.get('syncless.coio_greenstackless_helper')
if greenstackless_helper:
  bomb = greenstackless_helper.bomb
  _tasklet_base = greenstackless_helper.tasklet
else:
  _tasklet_base = object
  class bomb(object):
    """Result value for sending exceptions trough a channel."""

    __slots__ = ['type', 'value', 'traceback']

    def __init__(self, exc_type=None, exc_value=None, exc_traceback=None):
      self.type = exc_type
      self.value = exc_value
      self.traceback = exc_traceback

class channel(object):
  """Implementation of stackless's channel object."""

  __slots__ = ['balance', 'preference', 'queue', '_queue_last', '__weakref__']

  def __init__(self):
    self.balance = 0
    self.preference = -1
    self.queue = None
    self._queue_last = None

  def receive(self):
    return _receive(self, self.preference)

  def send(self, data):
    return _send(self, data, self.preference)

  def send_exception(self, exc_type, *args):
    self.send(bomb(exc_type, exc_type(*args)))

  def send_sequence(self, iterable):
    for item in iterable:
      self.send(item)

  # TODO(pts): Emulate .close() and .closed.

def _remove(tasklet_obj):
  """Remove the tasklet from the runnables list.

  As a side effect, put `main' back if the list would become empty.
  """
  global current
  if tasklet_obj.next is None:
    pass
  elif tasklet_obj.next is tasklet_obj:  # and tasklet_obj is current
    if tasklet_obj is not main:
      if main._channel_weak:
        _remove_from_channel(main)
      current = main
      main.next = main.prev = main
      tasklet_obj.next = tasklet_obj.prev = None
  else:
    if tasklet_obj is current:
      current = tasklet_obj.next
    tasklet_obj.next.prev = tasklet_obj.prev
    tasklet_obj.prev.next = tasklet_obj.next
    tasklet_obj.next = tasklet_obj.prev = None


def _insert_before_current(tasklet_obj):
  """Insert or move tasklet_obj just before current."""
  global current
  #DEBUG assert not tasklet_obj._channel_weak
  if tasklet_obj.next is not current:
    if tasklet_obj.next:
      tasklet_obj.next.prev = tasklet_obj.prev
      tasklet_obj.prev.next = tasklet_obj.next
    tasklet_obj.next = current
    tasklet_obj.prev = current.prev
    current.prev.next = tasklet_obj
    current.prev = tasklet_obj


def _insert_after_current(tasklet_obj):
  """Insert or move tasklet_obj just after current."""
  global current
  #DEBUG assert not tasklet_obj._channel_weak
  if tasklet_obj.prev is not current:
    if tasklet_obj.next:
      tasklet_obj.next.prev = tasklet_obj.prev
      tasklet_obj.prev.next = tasklet_obj.next
    tasklet_obj.prev = current
    tasklet_obj.next = current.next
    current.next.prev = tasklet_obj
    current.next = tasklet_obj


def _tasklet_wrapper(tasklet_obj, switch_back_ary, args, kwargs):
  """Tasklet wrapper function run in a greenlet."""
  try:
    switch_back_ary.pop().switch()  # Switch back to tasklet.__call__
    tasklet_obj._func(*args, **kwargs)
    assert tasklet_obj is current
    _remove(current)
  except TaskletExit:  # Let it pass silently.
    assert tasklet_obj is current
    _remove(current)
  except:
    exc_info = sys.exc_info()
    assert tasklet_obj is current
    assert tasklet_obj is not main
    if tasklet_obj.next is tasklet_obj:  # Last runnable tasklet.
      if main._channel_weak:
        if main._channel_weak().balance < 0:
          main.tempval = bomb(StopIteration, 'the main tasklet is receiving '
                              'without a sender available.')
        else:
          main.tempval = bomb(StopIteration, 'the main tasklet is sending '
                              'without a receiver available.')
        _remove(current)  # And insert main.
        # If runnables is empty, let the error be ignored here, and
        # so a StopIteration being raised in the main tasklet, see
        # LazyWorker in StacklessTest.testLastchannel.
      else:
        _remove(current)  # And insert main.
        main.tempval = bomb(*exc_info)
    else:  # Make main current.
      if main._channel_weak:
        _remove_from_channel(main)
      _insert_after_current(main)
      _remove(current)
      main.tempval = bomb(*exc_info)
  finally:
    # This make sure that flow will continue in the correct greenlet,
    # e.g. the next in the runnables list.
    tasklet_obj._greenlet.parent = current._greenlet
    tasklet_obj.alive = False
    tasklet_obj.tempval = None
    del tasklet_obj._greenlet
    del tasklet_obj._func
    del tasklet_obj._data
    # Keeping forever: del tasklet_obj.tempval
    # Keeping forever: del tasklet_obj._channel_weak


_tasklets_created = 0


class tasklet(_tasklet_base):
  """Implementation of stackless's tasklet object.

  TODO(pts): Implement tasklet._channel as a weak reference.
  """

  __slots__ = _process_slots(
      ['_greenlet', '_func', 'alive', '_channel_weak',
       '_data', 'next', 'prev', 'tempval', '__weakref__'], _tasklet_base)

  def __init__(self, func=None):
    global _tasklets_created
    _tasklets_created += 1
    self._greenlet = None
    self._func = func
    self.alive = False
    self._data = None
    self.tempval = None
    self._channel_weak = None
    self.prev = None
    self.next = None

  @property
  def blocked(self):
    return bool(self._channel_weak)

  @property
  def scheduled(self):
    return bool(self.next or self._channel_weak)

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
    if getattr(self, '_greenlet', None):
      raise TypeError('cframe function must be a callable')
    #DEBUG assert self.next is None
    # TODO(pts): Do we properly avoid circular references to self here?
    self._greenlet = greenlet(_tasklet_wrapper)
    # We need this initial switch so the function enters its `try ...
    # finally' block. We get back control very soon after the initial switch.
    self._greenlet.switch(self, [greenlet.getcurrent()], args, kwargs)
    self.alive = True
    _insert_before_current(self)
    return self

  def kill(self):
    return _throw(self, TaskletExit)

  def raise_exception(self, exc_class, *args):
    return _throw(self, exc_class(*args))

  def throw(self, typ, val, tb):
    """Raise the specified exception with the specified traceback.

    Please note there is no such method tasklet.throw in Stackless. In
    stackless, one can use tasklet_obj.tempval = stackless.bomb(...), and
    then tasklet_obj.run() -- or send the bomb in a channel if the
    target tasklet is blocked on receiving from.
    """
    return _throw(self, typ, val, tb)

  def __str__(self):
    return repr(self)

  def __repr__(self):
    if not hasattr(self, '_func'):
      _id = 'dead'
    elif getattr(self._func, '__name__', None):
      _id = self._func.__name__
    else:
      _id = self._func
    return '<tasklet %s at 0x%0x>' % (_id, id(self))

  @property
  def is_main(self):
    return self is main

  def remove(self):
    """Remove self from the main scheduler queue.

    Please note that this implementation has O(r) complexity, where r is
    the number or runnable (non-blocked) tasklets. The implementation in
    Stackless has O(1) complexity.
    """
    global current
    if self is current:
      raise RuntimeError('The current tasklet cannot be removed. '
                         'Use t=tasklet().capture()')
    if self._channel_weak:
      raise RuntimeError('You cannot remove a blocked tasklet.')
    if self.next:
      self.next.prev = self.prev
      self.prev.next = self.next
      self.next = self.prev = None
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
    if self.next is None:
      _insert_before_current(self)
    return self

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
    if self.next is None:
      _insert_before_current(self)
    return _schedule_to(self)


def _get_new_main():
  def main():  # Define function with __name__ for tasklet.__repr__.
    assert 0
  main = tasklet(main)
  main._greenlet = greenlet.getcurrent()
  main.alive = True
  main.next = main.prev = main
  return main

def _new_too_late(*args):
  raise NewTooLateError

current = main = _get_new_main()


def schedule(*args):
  """Schedule the next tasks and puts the current task back at the queue of runnables."""
  global current
  if args:
    if len(args) != 1:
      raise TypeError('schedule() takes at most 1 argument (%d given)' %
                      len(args))
    current.tempval = args[0]
  else:
    current.tempval = current
  if current.next is current:
    data = current.tempval
    current.tempval = None
  else:
    tasklet_obj = current
    current = current.next
    current._greenlet.switch()
    data = tasklet_obj.tempval
    tasklet_obj.tempval = None
  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data


def schedule_remove(*args):
  """Remove the current tasklet from the runnables, schedules next tasklet."""
  if args:
    if len(args) != 1:
      raise TypeError('schedule() takes at most 1 argument (%d given)' %
                      len(args))
    current.tempval = args[0]
  else:
    current.tempval = current
  tasklet_obj = current
  _remove(current)
  current._greenlet.switch()
  data = tasklet_obj.tempval
  tasklet_obj.tempval = None
  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data


def _throw(tasklet_obj, typ, val=None, tb=None):
  """Raise an exception in the tasklet, and run it.

  Please note that this implementation has O(r) complexity, where r is
  the number or runnable (non-blocked) tasklets. The implementation in
  Stackless has O(1) complexity.
  """
  global current
  if not tasklet_obj.alive:
    return
  # TODO(pts): Avoid circular parent chain exception here.
  if tasklet_obj is current:
    raise typ, val, tb
  if (current._greenlet.parent is not tasklet_obj._greenlet):
      tasklet_obj._greenlet.parent = current._greenlet
  if tasklet_obj._channel_weak:
    _remove_from_channel(tasklet_obj)
  if tasklet_obj.next is None:
    _insert_before_current(tasklet_obj)
  current, tasklet_obj = tasklet_obj, current
  current._greenlet.throw(typ, val, tb)
  data = tasklet_obj.tempval
  tasklet_obj.tempval = None
  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data


def _schedule_to(tasklet_obj):
  global current
  #DEBUG assert not tasklet_obj._weak_channel
  #DEBUG assert tasklet_obj.next
  if tasklet_obj is not current:
    current, tasklet_obj = tasklet_obj, current
    current._greenlet.switch()
  data = tasklet_obj.tempval
  tasklet_obj.tempval = None
  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data


def _remove_from_channel(tasklet_obj):
  """Remove tasklet_obj from the channel it is waiting on.

  Also set tasklet_obj.next = tasklet_obj.prev = None.
  """
  if tasklet_obj._channel_weak:
    channel_obj = tasklet_obj._channel_weak()
    assert channel_obj
    if tasklet_obj is channel_obj._queue_last:
      channel_obj._queue_last = None
      if tasklet_obj is channel_obj.queue:
        channel_obj.queue = tasklet_obj.next
      else:
        tasklet_obj.prev.next = None
    elif tasklet_obj is channel_obj.queue:
      channel_obj.queue = tasklet_obj.next
      if tasklet_obj.next:
        tasklet_obj.next.prev = None
    else:
      tasklet1 = channel_obj.queue
      assert tasklet1, 'empty channel'
      tasklet2 = tasklet1.next
      while tasklet2:
        if tasklet2 is tasklet_obj:
          break
        tasklet1 = tasklet2
        tasklet2 = tasklet2.next
      assert tasklet2, 'tasklet not found in channel'
      tasklet1.next = tasklet_obj.next
      tasklet_obj.next.prev = tasklet1  # tasklet_obj.next is not None here.
    tasklet_obj.next = tasklet_obj.prev = None
    tasklet_obj._channel_weak = None

    if channel_obj.balance < 0:
      channel_obj.balance += 1
    elif channel_obj.balance > 0:
      channel_obj.balance -= 1
    else: 
      assert 0, 'tasklet on zero-balance channel'


def _receive(channel_obj, preference):
  #Receiving 1):
  #A tasklet wants to receive and there is
  #a queued sending tasklet. The receiver takes
  #its data from the sender, unblocks it,
  #and inserts it at the end of the runnables.
  #The receiver continues with no switch.
  #Receiving 2):
  #A tasklet wants to receive and there is
  #no queued sending tasklet.
  #The receiver will become blocked and inserted
  #into the queue. The next sender will
  #handle the rest through "Sending 1)".
  if channel_obj.balance > 0: #some sender
    channel_obj.balance -= 1
    sender = channel_obj.queue
    channel_obj.queue = sender.next
    if sender.next:
      channel_obj.queue = sender.next
      sender.next = sender.prev = None
    else:
      #DEBUG assert sender is channel_obj._queue_last
      channel_obj._queue_last = None

    sender._channel_weak = None
    data, sender._data = sender._data, None
    if preference >= 0:  # Prefer the sender.
      _insert_after_current(sender)
      _schedule_to(sender)  # TODO(pts): How do we use tempval here?
    else:
      _insert_before_current(sender)
  else: #no sender
    if current.next is current and (current is main or main._channel_weak):
      # Strange exception name.
      raise RuntimeError('Deadlock: the last runnable tasklet '
                         'cannot be blocked.')
    tasklet_obj = current
    _remove(current)
    tasklet_obj.tempval = None
    tasklet_obj._channel_weak = weakref.ref(channel_obj)
    if channel_obj.queue:
      channel_obj._queue_last.next = tasklet_obj
    else:
      channel_obj.queue = tasklet_obj
    tasklet_obj.prev = channel_obj._queue_last
    tasklet_obj.next = None
    channel_obj._queue_last = tasklet_obj
    channel_obj.balance -= 1
    current._greenlet.switch()  # This may raise an exception (from _throw).
    # Whoever has insterted us back is responsible for removing us from the
    # channel by now.
    assert tasklet_obj._channel_weak is None, 'receive still has channel'
    if isinstance(tasklet_obj.tempval, bomb):
      bomb_obj, tasklet_obj.tempval = tasklet_obj.tempval, None
      raise bomb_obj.type, bomb_obj.value, bomb_obj.traceback
    data, current._data = current._data, None

  if isinstance(data, bomb):
    raise data.type, data.value, data.traceback
  else:
    return data


def _send(channel_obj, data, preference):
  #  Sending 1):
  #  A tasklet wants to send and there is
  #  a queued receiving tasklet. The sender puts
  #  its data into the receiver, unblocks it,
  #  and inserts it at the top of the runnables.
  #  The receiver is scheduled.
  #  Sending 2):
  #  A tasklet wants to send and there is
  #  no queued receiving tasklet.
  #  The sender will become blocked and inserted
  #  into the queue. The next receiver will
  #  handle the rest through "Receiving 1)".
  if channel_obj.balance < 0: #some receiver
    channel_obj.balance += 1
    receiver = channel_obj.queue
    channel_obj.queue = receiver.next
    if receiver.next:
      channel_obj.queue = receiver.next
      receiver.next = receiver.prev = None
    else:
      #DEBUG assert receiver is channel_obj._queue_last
      channel_obj._queue_last = None

    receiver._data = data
    receiver._channel_weak = None
    # Put receiver just after the current tasklet in runnables and schedule
    # (which will pick it up).
    if preference < 0:  # Prefer the receiver.
      _insert_after_current(receiver)
      _schedule_to(receiver)
    else:
      _insert_before_current(receiver)
  else: # No receiver.
    if current.next is current and (current is main or main._channel_weak):
      raise RuntimeError('Deadlock: the last runnable tasklet '
                         'cannot be blocked.')
    tasklet_obj = current
    _remove(current)
    tasklet_obj.tempval = None
    tasklet_obj._data = data
    tasklet_obj._channel_weak = weakref.ref(channel_obj)
    if channel_obj.queue:
      channel_obj._queue_last.next = tasklet_obj
    else:
      channel_obj.queue = tasklet_obj
    tasklet_obj.prev = channel_obj._queue_last
    tasklet_obj.next = None
    channel_obj._queue_last = tasklet_obj
    channel_obj.balance += 1
    current._greenlet.switch()  # This may raise an exception (from _throw).
    # Whoever has insterted us back is responsible for removing us from the
    # channel by now.
    assert tasklet_obj._channel_weak is None
    if isinstance(tasklet_obj.tempval, bomb):
      bomb_obj, tasklet_obj.tempval = tasklet_obj.tempval, None
      raise bomb_obj.type, bomb_obj.value, bomb_obj.traceback


def getruncount():
  i = 1
  tasklet_obj = current.next
  while tasklet_obj is not current:
    i += 1
    tasklet_obj = tasklet_obj.next
  return i


def getcurrent():
  return current


def getmain():
  return main


def _coio_rebase(helper_module):
  """Rebase classes `tasklet' and `bomb' from those in the helper_module."""
  global tasklet
  global bomb
  global current
  global main
  global _tasklets_created
  is_tasklet_ok = list(tasklet.__bases__) == [helper_module.tasklet]
  if is_tasklet_ok and bomb is helper_module.bomb:
    return
  if main is not current:
    raise ImportTooLateError
  if main.next is not main:
    raise ImportTooLateError
  # We should check for the number of bombs as well, but that would be too
  # much work.
  if _tasklets_created != 1:
    raise ImportTooLateError
  if not is_tasklet_ok:
    # This would be easier: tasklet.__bases__ = (helper_module.tasklet,)
    # But it doesn't work: TypeError("__bases__ assignment: 'tasklet' deallocator differs from 'object'")
    dict_obj = dict(tasklet.__dict__)
    dict_obj['__slots__'] = _process_slots(
        dict_obj['__slots__'], helper_module.tasklet, dict_obj)
    #old_tasklet = tasklet
    tasklet.__new__ = classmethod(_new_too_late)
    tasklet = type(tasklet.__name__, (helper_module.tasklet,), dict_obj)
    current = main = _get_new_main()
    _tasklets_created = 1
    assert type(main) is tasklet
    #del old_tasklet
  if bomb is not helper_module.bomb:
    bomb.__new__ = classmethod(_new_too_late)
    bomb = helper_module.bomb


is_greenstackless = True
del greenstackless_helper
del _tasklet_base
