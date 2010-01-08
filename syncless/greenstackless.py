# Original _suncless.py downloaded from
# http://github.com/toymachine/concurrence/raw/master/lib/concurrence/_stackless.py
# at Thu Jan  7 22:59:54 CET 2010

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

Limitations of this module over real Stackless:

* greenlet is slower than Stackless
* greenlet has some memory leeks if greenlets reference each other
* no stackless.current support (use stackless.getcurrent())
* no multithreading support (don't use greenstackless in more than one
  thread (not even sequentially) in your application)
* no deadlock detection if the main tasklet gets stuck
"""

try:
    from py.magic import greenlet #as of version 1.0 of py, it does not supply greenlets anymore
except ImportError:
    from greenlet import greenlet #there is an older package containing just the greenlet lib

assert hasattr(greenlet, 'throw'), (
    'wrong version of greenlet loaded; please get greenlet from svn co '
    'http://codespeak.net/svn/py/release/0.9.x/py/c-extension/greenlet')

from collections import deque

class TaskletExit(SystemExit):pass

import __builtin__
__builtin__.TaskletExit = TaskletExit


class bomb(object):
    """used as a result value for sending exceptions trough a channel"""
    def __init__(self, exc_type = None, exc_value = None, exc_traceback = None):
        self.type = exc_type
        self.value = exc_value
        self.traceback = exc_traceback

    def raise_(self):
        raise self.type, self.value, self.traceback

class channel(object):
    """implementation of stackless's channel object"""
    def __init__(self):
        self.balance = 0
        self.preference = -1
        self.queue = deque()

    def receive(self):
        return _scheduler._receive(self, self.preference)

    def send(self, data):
        return _scheduler._send(self, data, self.preference)

    def send_exception(self, exc_type, *args):
        self.send(bomb(exc_type, exc_type(*args)))

    def send_sequence(self, iterable):
        for item in iterable:
            self.send(item)



class tasklet(object):
    """implementation of stackless's tasklet object"""

    def __init__(self, f = None, greenlet = None, alive = False):
        self.greenlet = greenlet
        self.func = f
        self.alive = alive
        self.blocked = False
        self.data = None

    def bind(self, func):
        if not callable(func):
            raise TypeError('tasklet function must be a callable')
        self.func = func

    def __call__(self, *args, **kwargs):
        """this is where the new task starts to run, e.g. it is where the greenlet is created
        and the 'task' is first scheduled to run"""
        if self.func is None:
            raise TypeError('tasklet function must be a callable')

        def _func(*_args, **_kwargs):
            try:
                self.func(*args, **kwargs)
            except TaskletExit:
                pass #let it pass silently
            except:
                import logging
                logging.exception('unhandled exception in greenlet')
                #don't propagate to parent
            finally:
                assert _scheduler.current == self
                _scheduler.remove(self)
                if _scheduler._runnable: #there are more tasklets scheduled to run next
                    #this make sure that flow will continue in the correct greenlet, e.g. the next in the schedule
                    self.greenlet.parent = _scheduler._runnable[0].greenlet
                self.alive = False
                del self.greenlet
                del self.func
                del self.data

        self.greenlet = greenlet(_func)
        self.alive = True
        _scheduler.append(self)
        return self

    def kill(self):
        _scheduler.throw(self, TaskletExit)

    def raise_exception(self, exc_class, *args):
        _scheduler.throw(self, exc_class(*args))

    def throw(self, typ, val, tb):
        """Raise the specified exception with the specified traceback.

        Please note there is no such method tasklet.throw in Stackless. In
        stackless, one can use tasklet_obj.tempval = stackless.bomb(...), and
        then tasklet_obj.run() -- or send the bomb in a channel if the
        target tasklet is blocked on receiving from.
        """
        _scheduler.throw(self, typ, val, tb)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        if hasattr(self, 'name'):
            _id = self.name
        else:
            _id = str(self.func)
        return '<tasklet %s at %0x>' % (_id, id(self))

    def remove(self):
        """Remove self from the main scheduler queue.

        Please note that this implementation has O(r) complexity, where r is
        the number or runnable (non-blocked) tasklets. The implementation in
        Stackless has O(1) complexity.
        """
        if self.blocked:
            raise RuntimeError('You cannot remove a blocked tasklet.')
        i = 0
        for task in _scheduler._runnable:
            if task is self:
                del _scheduler._runnable[i]
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
        if self.blocked:
            raise RuntimeError('You cannot run a blocked tasklet')
        if self not in _scheduler._runnable:
            _scheduler._runnable.append(self)

    @property
    def next(self):
        """Return the next tasklet in the doubly-linked list.

        Stackless implements this method for all tasklets. This implementation
        raises a NotImplementedError unless self is scheduler.getcurrent() or
        self is the last runnable tasklet.
        """
        runnable = _scheduler._runnable
        if self is runnable[0]:
            return runnable[len(runnable) > 1]
        elif self is runnable[-1]:
            return runnable[0]
        else:
            raise NotImplementedError('tasklet.next for not current or last')

    @property
    def prev(self):
        """Return the next tasklet in the doubly-linked list.

        Stackless implements this method for all tasklets. This implementation
        raises a NotImplementedError unless self is scheduler.getcurrent() or
        self is the last runnable tasklet.
        """
        runnable = _scheduler._runnable
        if self is runnable[0]:
            return runnable[-1]
        elif self is runnable[-1]:
            return runnable[-2]
        else:
            raise NotImplementedError('tasklet.prev for not current or last')

    def run(self):
        """Switch execution to self, make it stackless.getcurrent().

        Please note that this implementation has O(r) complexity, where r is
        the number or runnable (non-blocked) tasklets. The implementation in
        Stackless has O(1) complexity.
        """
        if self.blocked:
            raise RuntimeError('You cannot run a blocked tasklet')
        if not self.alive:
            raise RuntimeError('You cannot run an unbound(dead) tasklet')
        runnable = _scheduler._runnable
        i = 0
        for task in runnable:
            if task is self:
                if i:
                    runnable.rotate(-i)
                    self.greenlet.switch()
                return
            i += 1
        runnable.appendleft(self)
        self.greenlet.switch()


class scheduler(object):
    def __init__(self):
        self._main_task = tasklet(greenlet = greenlet.getcurrent(), alive = True)
        #all non blocked tast are in this queue
        #all tasks are only onces in this queue
        #the current task is the first item in the queue
        self._runnable = deque([self._main_task])

    def schedule(self):
        """schedules the next tasks and puts the current task back at the queue of runnables"""
        self._runnable.rotate(-1)
        self._runnable[0].greenlet.switch()

    def schedule_remove(self):
        """makes stackless.getcurrent() not runnable, schedules next tasks"""
        runnable = self._runnable
        if len(runnable) > 1:
            runnable.popleft()
            self._runnable[0].greenlet.switch()

    def schedule_block(self):
        """blocks the current task and schedules next"""
        self._runnable.popleft()
        next_task = self._runnable[0]
        next_task.greenlet.switch()

    def throw(self, task, typ, val=None, tb=None):
        """Raise an exception in the tasklet, and run it.

        Please note that this implementation has O(r) complexity, where r is
        the number or runnable (non-blocked) tasklets. The implementation in
        Stackless has O(1) complexity.
        """
        if not task.alive: return #this is what stackless does
        runnable = self._runnable
        # TODO(pts): Avoid cyclic parent chain exception here.
        if (task is not runnable[0] and
            runnable[0].greenlet.parent is not task.greenlet):
            task.greenlet.parent = runnable[0].greenlet
        if not task.blocked:
            i = 0
            for task2 in runnable:
                if task2 is task:
                    if i:
                        runnable.rotate(-i)
                        task.greenlet.throw(typ, val, tb)
                        return
                    else:
                        raise typ, val, tb
                i += 1
        runnable.appendleft(task)
        task.greenlet.throw(typ, val, tb)

    def _receive(self, channel, preference):
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
        if channel.balance > 0: #some sender
            channel.balance -= 1
            sender = channel.queue.popleft()
            sender.blocked = False
            data, sender.data = sender.data, None
            if preference >= 0:
                #sender preference
                self._runnable.rotate(-1)
                self._runnable.appendleft(sender)
                self._runnable.rotate(1)
                self.schedule()
            else:
                #receiver preference
                self._runnable.append(sender)
        else: #no sender
            current = self._runnable[0]
            channel.queue.append(current)
            channel.balance -= 1
            current.blocked = True
            try:
                self.schedule_block()
            except:
                channel.queue.remove(current)
                channel.balance += 1
                current.blocked = False
                raise

            data, current.data = current.data, None

        if isinstance(data, bomb):
            data.raise_()
        else:
            return data

    def _send(self, channel, data, preference):
        #  Sending 1):
        #    A tasklet wants to send and there is
        #    a queued receiving tasklet. The sender puts
        #    its data into the receiver, unblocks it,
        #    and inserts it at the top of the runnables.
        #    The receiver is scheduled.
        #  Sending 2):
        #    A tasklet wants to send and there is
        #    no queued receiving tasklet.
        #    The sender will become blocked and inserted
        #    into the queue. The next receiver will
        #    handle the rest through "Receiving 1)".
        #print 'send q', channel.queue
        if channel.balance < 0: #some receiver
            channel.balance += 1
            receiver = channel.queue.popleft()
            receiver.data = data
            receiver.blocked = False
            #put receiver just after current task in runnable and schedule (which will pick it up)
            if preference < 0: #receiver pref
                self._runnable.rotate(-1)
                self._runnable.appendleft(receiver)
                self._runnable.rotate(1)
                self.schedule()
            else: #sender pref
                self._runnable.append(receiver)
        else: #no receiver
            current = self.current
            channel.queue.append(current)
            channel.balance += 1
            current.data = data
            current.blocked = True
            try:
                self.schedule_block()
            except:
                channel.queue.remove(current)
                channel.balance -= 1
                current.data = None
                current.blocked = False
                raise

    def remove(self, task):
        assert task.blocked or task in self._runnable
        if task in self._runnable:
            self._runnable.remove(task)

    def append(self, task):
        assert task not in self._runnable
        self._runnable.append(task)

    @property
    def runcount(self):
        return len(self._runnable)

    @property
    def current(self):
        return self._runnable[0]

#there is only 1 scheduler, this is it:
_scheduler = scheduler()

def getruncount():
    return _scheduler.runcount

def getcurrent():
    return _scheduler.current

def schedule():
    return _scheduler.schedule()

def schedule_remove():
    return _scheduler.schedule_remove()
