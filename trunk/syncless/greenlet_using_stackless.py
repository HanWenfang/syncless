#! /usr/local/bin/stackless2.6

"""A greenlet emulator using Stackless Python.

This emulator wants to mimic the real greenlet (0.3.1) as closely as possible,
even at the cost of performance. It also passes the extensive unit test
test/greenlet_test.py . Should you encounter a situation in which this
emulator behaves differently from real Greenlet, then please consider this as
a bug in the emulator, and report it to the author, preferably by creating a
new issue in the Syncless bug tracker:
http://code.google.com/p/syncless/issues/entry

Please use syncless.best_greenlet instead of this module
(syncless.greenlet_using_stackless) for convenience, since best_greenlet can
use the existing greenlet module, it also creates the top-level greenlet
module to be imported by other modules, and it also provides the
gevent_hub_main() convenience function.

Please note that this emulator has been tested only with native Syncless. It
most probably doesn't work with emulated Stackless (e.g. stacklesss.py in
Eventlet, greenstackless.py in Syncless and PyPy's Stackless emulation).
This emulator doesn't do any checks if it's using native Stackless.

Please note that this emulator is self-contained: it requires Stackless
Python only.

Please note that this emulator doesn't use the native greenlet module (but
it provides the emulation anyway) even if it is available. The emulation can
coexist with the native greenlet module in the same Python interpreter.

Please note that this emulator allows multiple tasklets and emulated
greenlets coexist in the same Python interpreter, but it doesn't provide any
means of communication between tasklets and greenlets.

To use this emulator, replace the first occurrence of your imports:

  # Old module import: import greenlet
  from syncless import greenlet_using_stackless as greenlet
  
  # Old class import: from greenlet import greenlet
  from syncless.greenlet_using_stackless import greenlet

This emulator supports gevent. Example code:

  import sys
  try:
    import greenlet
  except ImportError:  # Use emulation if real greenlet is not available.
    print 'using emulation'
    from syncless import greenlet_using_stackless as greenlet
    sys.modules['greenlet'] = greenlet  # Make gevent see it.
  import gevent.wsgi
  def WsgiApp(env, start_response):
    return ['Hello, <b>World</b>!']
  gevent.wsgi.WSGIServer(('127.0.0.1', 8080), WsgiApp).serve_forever()

A minimalistic fake stackless module which lets the greenlet_using_stackless
module be imported without exceptions (but it wouldn't work):

  class FakeTasklet(object):
    def __init__(self, function):
      pass
    def __call__(self, *args, **kwargs):
      return self
    def remove(self):
      pass
  stackless = sys.modules['stackless'] = type(sys)('stackless')
  stackless.tasklet = FakeTasklet
  stackless.current = FakeTasklet(None)

This emulator is at least 20% slower than real greenlet, but it can be much
slower. (Speed measurements needed.) The emphasis was on the correctness of
the emulation (as backed by test/greenlet_test.py) rather than its speed.


TODO(pts): Do speed measurements.
TODO(pts): Detect and disallow loop in the .parent chain when setting
           greenlet_obj.parent.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import stackless
import sys

current = None

def getcurrent():
  return current

class GreenletExit(BaseException):  # Just like in real greenlet.
  pass

def _finish_helper():
  """Helper tasklet for inserting a tasklet after stackless.current.

  See the code of the users of _finish_helper_tasklet for more information.    
  """
  while True:
    stackless.current.next.next.remove().run()

def _finish_helper2():
  """Helper tasklet for inserting two tasklets after stackless.current.

  See the code of the users of _finish_helper_tasklet for more information.    
  """
  while True:
    stackless.current.next.next.next.remove().run()

_finish_helper_tasklet = stackless.tasklet(_finish_helper)().remove()

_finish_helper2_tasklet = stackless.tasklet(_finish_helper2)().remove()

_placeholder_tasklet = stackless.tasklet(lambda: _PlaceHolder_)().remove()

gevent_hub_tasklet = None


def _insert_after_current_tasklet(tasklet_obj):
  """Like tasklet_obj.insert(), but forcibly (re)insert _after_ current."""
  assert tasklet_obj is not stackless.current
  if stackless.current.next is stackless.current:  # Only stackless.current.
    tasklet_obj.insert()
  elif stackless.current.next is not tasklet_obj:
    # Use a trick to insert tasklet_obj right after us (as
    # stackless.current.next), so it gets scheduled as soon as this
    # _wrapper returns.
    #DEBUG assert not _finish_helper_tasklet.scheduled
    tasklet_obj.remove()
    _finish_helper_tasklet.insert()
    tasklet_obj.insert()
    _finish_helper_tasklet.run()
    #DEBUG assert stackless.current.next is _finish_helper_tasklet
    #DEBUG assert stackless.current.next.next is tasklet_obj
    _finish_helper_tasklet.remove()
  #DEBUG assert stackless.current.next is tasklet_obj


def _insert_two_after_current_tasklet(tasklet1, tasklet2):
  """Forcibly (re)insert tasklet1 and tasklet2 after the current tasklet.

  It is not allowed for tasklet1 and tasklet2 be the same object.

  After calling this function, the following will be true:

    assert stackless.current.next is tasklet1
    assert stackless.current.next.next is tasklet2
  """
  assert tasklet1 is not tasklet2
  if stackless.current.next is stackless.current:  # Only stackless.current.
    tasklet1.insert()
    tasklet2.insert()
  elif stackless.current.next is tasklet2:
    assert tasklet1 is not stackless.current
    tasklet1.remove()
    _finish_helper_tasklet.insert()
    tasklet1.insert()
    _finish_helper_tasklet.run()
    _finish_helper_tasklet.remove()
  else:
    assert tasklet1 is not stackless.current
    assert tasklet2 is not stackless.current
    tasklet1.remove()
    tasklet2.remove()
    _finish_helper2_tasklet.insert()
    tasklet1.insert()
    tasklet2.insert()
    _finish_helper2_tasklet.run()
    _finish_helper2_tasklet.remove()
  #DEBUG assert stackless.current.next is tasklet1
  #DEBUG assert stackless.current.next.next is tasklet2


def _wrapper(run, args, kwargs):
  """Wrapper to run `run' as the callable of a greenlet--tasklet."""
  global current
  try:
    assert current._tasklet is stackless.current
    stackless.current.next.remove()
    apply_args = [(run, args, kwargs)]
    del run, args, kwargs   # Save memory, break reference chain.
    # This call returns as soon as the greenlet main function returns.
    # This might take quite a long time, and multiple .switch() etc.
    # calls.
    value = apply(*apply_args.pop())
    # Still true (but del'ed above): assert greenlet_obj is current
    target = current.parent
    while target.dead:
      target = target.parent
    if target._tasklet is None:
      _first_switch(target, value)
    else:
      target._tasklet.tempval = value
  except GreenletExit, e:
    # Still true (but del'ed above): assert greenlet_obj is current
    target = current.parent
    while target.dead:
      target = target.parent
    if target._tasklet is None:
      _first_switch(target, e)
    else:
      target._tasklet.tempval = e
  except TaskletExit, e:
    # This doesn't happen with gevent in a worker greenlet, because the
    # exception handler in the hub (gevent.core.__event_handler) stops the
    # TaskletExit from propagating.
    # Still true (but del'ed above): assert greenlet_obj is current
    target = current.parent
    while target.dead:
      target = target.parent
    if target._tasklet is None:
      _first_switch(target, e)
    else:
      target._tasklet.tempval = e
  except:
    # Still true (but del'ed above): assert greenlet_obj is current
    bomb_obj = stackless.bomb(*sys.exc_info())
    target = current.parent
    while True:  # This logic is tested in GreenletTest.testThrow.
      if not target.dead:
        if target._tasklet:
          break
        # This is tested in greenlet5 of GreenletTest.testSwitchToParent.
        target.dead = True
        target.__dict__.pop('run', None)  # Keep methods of subclasses.
      target = target.parent
    target._tasklet.tempval = bomb_obj
    del bomb_obj  # Save memory.
  if getattr(current, '_is_revived', False):
    current.dead = True
    # Not inserting the placeholder, because the parent wouldn't remove it.
    _insert_after_current_tasklet(target._tasklet)
    current = target
    return
  assert target._tasklet
  current.dead = True
  # We insert the placeholder so target._tasklet can remove it as its next
  # (using stackless.current.next.remove()).
  _insert_two_after_current_tasklet(target._tasklet, _placeholder_tasklet)
  current = target
  #DEBUG assert current._tasklet is stackless.current.next


def _first_switch(target, *args, **kwargs):
  global current
  run = target.run
  target.__dict__.pop('run', None)  # Keep methods of subclasses.
  # Create the tasklet that late.
  target._tasklet = stackless.tasklet(_wrapper)(
      run, args, kwargs).remove()
  run = args = kwargs = None  # Save memory.
  if (type(target) is not greenlet and
      repr(type(target)) == "<class 'gevent.hub.Hub'>"):
    # TODO(pts): Revisit our strategy here.
    # We have to do a little monkey-patching here to make the program
    # exit when the main tasklet exits. Without this monkey-patching,
    # upon stackless.main exit, Stackless raises TaskletExit in the hub
    # tasklet, which an exception handler prints and ignores, and the
    # main loop in core.dispatch() continues running forever. With this
    # monkey-patching (and with `except TaskletExit:' later) we create
    # an abortable main loop, and abort it when stackless.main exits.
    global gevent_hub_tasklet
    gevent_hub_tasklet = target._tasklet
    core = __import__('gevent.core').core
    if not hasattr(core, 'goon'):
      core.goon = True
      def Dispatch():
        result = 0
        while core.goon and not result:
          result = core.loop()
        # For gevent-0.13.6: Hub.run() raises DispatchExit(...) upon return,
        # but we want to run a GreenletExit.
        if core.goon is ():  # The hub tasklet is being deleted.
          raise GreenletExit
        return result
      core.dispatch = Dispatch


def _handle_tasklet_exit_in_switch(typ, val, tb, *args):
  global current
  typ, val, tb = sys.exc_info()
  stackless.current.next.remove()
  if current._tasklet is stackless.current:
    raise typ, val, tb  # So the rest of the tasklet code won't get executed.
  # Received TaskletExit because the last reference to this greenlet
  # is gone. We just create a new greenlet to be able to exit cleanly.
  # We set the parent to the new greenlet to the greenlet where __del__
  # occurs (i.e. `current') -- real greenlets do the same.
  if stackless.current is gevent_hub_tasklet:
    hub_greenlet = sys.modules['gevent.hub']._threadlocal.hub
    assert hub_greenlet._tasklet is stackless.current
    hub_greenlet.parent = current
    current = hub_greenlet
    core = sys.modules['gevent.core']
    # If we raised GreenletExit here, it would be caught, reported and
    # ignored in the `except:' clause of gevent.core.__event_handler or
    # gevent.core.__simple_handler (in gevent/core.pyx). These are the
    # functions the hub greenlet gets stuck in.
    #
    # So instead of raising an exception we rather set `core.goon = ()',
    # which signals our modified gevent.core.dispatch (see
    # Dispatch elsewhere in this module), so it would return.
    core.goon = ()
    # This is for all gevent.greenlet.Greenlet objects to prevent further
    # error reporting.
    # TODO(pts): Is this needed? Where does it help?
    #if getattr(greenlet_obj, '_report_error', None):
    #  greenlet_obj._report_error = lambda *args, **kwargs: None
    #def _ignore(*args, **kwargs):
    #  pass
    #if core and core.sys:
    #  if core.traceback.print_exc is not _ignore:
    #    core.traceback = type(core.traceback)('fake_traceback')
    #    core.traceback.print_exc = _ignore
    #    core.traceback.print_exception = _ignore
    #  # Disable sys.stderr.write in greenlet.core.__event_handler.
    #  core.sys = None
    return None
  else:
    current = greenlet()  # This sets parent to the old current.
    current._tasklet = stackless.current
    current._is_revived = True
    raise GreenletExit(*val.args)


def _switch(target):
  """Switch to the specified target greenlet.

  The caller must set target._tasklet.tempval to the switch value first.
  """


class greenlet(object):
  def __init__(self, run=None, parent=None):
    self._tasklet = None
    self.dead = False
    # TODO(pts): Support greenlet.gr_frame.
    # TODO(pts): Detect cycle of parents when setting the parent attribute.
    if parent is None:
      parent = getcurrent()
    self.parent = parent
    if run is not None:
      self.run = run

  def __len__(self):
    """Implements bool(self).

    Returns:
      A true value (1) iff self has been started but not finished yet.
    """
    return int(not (not self._tasklet or self.dead))

  def run(self):
    """Can be overridden in subclasses to do useful work in the greenlet."""

  def switch(self, *args, **kwargs):
    global current
    target = self
    while target.dead:
      target = target.parent
    del self    # Save memory.
    if target._tasklet is None:
      # This creates new reference (self._tasklet function)
      _first_switch(target, *args, **kwargs)
    else:
      assert not kwargs
      if args:
        assert len(args) <= 1
        if target is current:
          return args[0]
        target._tasklet.tempval = args[0]
      else:
        if target is current:
          return ()
        target._tasklet.tempval = ()
    del args, kwargs    # Save memory.

    # The following code is duplicated between .switch() and .throw(), but
    # it would be too slow to refactor to a function because of the extra
    # references to `target'.
    current = target
    target = [target._tasklet.remove().run]
    try:
      # With target.pop() we ensure that this method invocation will cease
      # to hold a reference to the target greenlet before .run() is called.
      # locals().pop('target') wouldn't remove the reference (because that's
      # how the Python interpreter handles local variables).
      retval = target.pop()()
    except TaskletExit:
      return _handle_tasklet_exit_in_switch(*sys.exc_info())
    except:
      stackless.current.next.remove()
      assert current._tasklet is stackless.current
      raise
    stackless.current.next.remove()
    assert current._tasklet is stackless.current
    return retval

  def throw(self, typ=None, val=None, tb=None):
    global current
    if not typ:
      typ = GreenletExit
    target = self
    del self  # Save memory and drop reference.
    while True:  # This logic is tested in GreenletTest.testThrow.
      if not target.dead:
        if target._tasklet:
          break
        target.dead = True
        target.__dict__.pop('run', None)  # Keep methods of subclasses.
        if issubclass(typ, GreenletExit):
          # This is tested by GreenletUsingStacklesstest.testParentOnKill.
          apply_args = [(target.parent.switch, (typ(val),))]
          del target, typ, val, tb  # Save memory and drop reference.
          return apply(*apply_args.pop())
      target = target.parent
    if target is current:
      raise typ, val, tb
    target._tasklet.tempval = stackless.bomb(typ, val, tb)
    del typ, val, tb  # Save memory and drop reference.
    # Don't call target.switch, it might be overridden in a subclass.

    # The following code is duplicated between .switch() and .throw(), but
    # it would be too slow to refactor to a function because of the extra
    # references to `target'.
    current = target
    target = [target._tasklet.remove().run]
    try:
      retval = target.pop()()
    except TaskletExit:
      return _handle_tasklet_exit_in_switch(*sys.exc_info())
    except:
      stackless.current.next.remove()
      assert current._tasklet is stackless.current
      raise
    stackless.current.next.remove()
    assert current._tasklet is stackless.current
    return retval

  getcurrent = staticmethod(globals()['getcurrent'])
  GreenletExit = staticmethod(globals()['GreenletExit'])
  is_pts_greenlet_emulated = True


is_pts_greenlet_emulated = True
# Sets current.parent = None, because current was None.
current = greenlet()
current._tasklet = stackless.current
