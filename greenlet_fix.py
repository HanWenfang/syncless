#! /usr/local/bin/stackless2.6

"""A greenlet emulator using Stackless Python (or greenlet itself).

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
                                                 
To use this module, replace the first

  import greenlet

in your program with

  from greenlet_fix import greenlet

After that, you can keep subsequent `import greenlet' statements in your code.

This module works with gevent.

This code is based on the file eventlet-0.9.2/eventlet/support/stacklesss.py
downloaded from http://pypi.python.org/packages/source/e/eventlet/eventlet-0.9.2.tar.gz
at Sat Jan  9 14:42:22 CET 2010.

TODO(pts): Do speed measurements.
"""

__author__ = 'Peter Szabo (pts@fazekas.hu)'

try:
  import greenlet
except ImportError:
  try:
    import stackless
  except ImportError:
    raise ImportError('either greenlet or stackless requred')

  import sys

  current = None

  def getcurrent():
    return current

  class GreenletExit(BaseException):
    pass

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

      def FirstSwitch(*args, **kwargs):
        run = self.run

        def Wrapper():
          try:
            run(*args, **kwargs)
            self.dead = True
            self.parent.switch()
          except GreenletExit:
            self.dead = True
            self.parent.switch()
          except:
            self.dead = True
            self.parent.throw(*sys.exc_info())

        del self.switch
        if 'run' in self.__dict__:  # Keep methods of subclasses.
          del self.run
        self._tasklet = t = stackless.tasklet(Wrapper)()
        if (type(self) != greenlet and
            repr(type(self)) == "<class 'gevent.hub.Hub'>"):
          # We have to do a little monkey-patching here to make the program
          # exit when the main tasklet exits. Without this monkey-patching,
          # upon stackless.main exit, Stackless raises TaskletExit in the hub
          # tasklet, which an exception handler prints and ignores, and the
          # main loop in core.dispatch() continues running forever. With this
          # monkey-patching (and with `except TaskletExit:' later) we create
          # an abortable main loop, and abort it when stackless.main exits.
          self.is_gevent_hub = True
          core = __import__('gevent.core').core
          if not hasattr(core, 'goon'):
            core.goon = True
            def Dispatch():
              result = 0
              while core.goon and not result:
                result = core.loop()
              return result
            core.dispatch = Dispatch
        global current
        caller = current
        current = self
        if hasattr(caller, 'is_gevent_hub'):
          try:
            t.run()
          except TaskletExit:
            __import__('gevent.core').core.goon = False
            return
        else:
          t.run()
        obj = caller._obj
        self._obj = None  # Save memory.
        return obj

      self.switch = FirstSwitch

      self._obj = None

    def run(self):
      """Can be overridden in subclasses."""
      pass

    def switch(self, obj=None):
      target = self
      while target.dead:
        target = target.parent
      if stackless.current is target._tasklet:  # current == target
        return obj
      target._obj = obj
      obj = None  # Save memory.
      global current
      caller = current
      current = target
      if hasattr(caller, 'is_gevent_hub'):
        try:
          target._tasklet.run()
        except TaskletExit:
          __import__('gevent.core').core.goon = False
          return
      else:
        # TODO(pts): Use a channel instead so greenlets won't get added to the
        # stackless main queue.
        target._tasklet.run()
      # We don't reach this below in case of `throw'.
      obj = caller._obj
      caller._obj = None  # Save memory.
      return obj

    def __len__(self):
      """Implements bool(self)."""
      return int(not (self.dead or 'switch' in self.__dict__))

    def throw(self, typ=None, val=None, tb=None):
      if not typ:
        typ = GreenletExit
      target = self
      while True:
        if not target.dead:
          if target._tasklet:
            break
          target.dead = True
        target = target.parent
      target._tasklet.tempval = stackless.bomb(typ, val, tb)
      return target.switch()

    getcurrent = staticmethod(globals()['getcurrent'])
    GreenletExit = staticmethod(globals()['GreenletExit'])

  greenlet_class = greenlet
  greenlet = type(sys)('greenlet')
  sys.modules['greenlet'] = greenlet
  greenlet.greenlet = greenlet_class
  greenlet.getcurrent = getcurrent
  greenlet.GreenletExit = GreenletExit
  current = greenlet_class()
  del current.switch  # It's already running.
  current._tasklet = stackless.current
