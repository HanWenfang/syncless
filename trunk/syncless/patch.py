#! /usr/local/bin/stackless2.6

"""Functions for monkey-patching Python libraries to use Syncless."""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys
import types

# TODO(pts): Have a look at Concurrence (or others) for patching everything.

fake_create_connection = None

def get_fake_create_connection():
  global fake_create_connection
  if fake_create_connection is None:
    import socket
    import coio
    fake_create_connection_globals = {
        'getaddrinfo': coio.partial_getaddrinfo,
        'socket': coio.nbsocket,
        'SOCK_STREAM': socket.SOCK_STREAM,
        '_GLOBAL_DEFAULT_TIMEOUT': socket._GLOBAL_DEFAULT_TIMEOUT,
        'error': socket.error,
    }
    fake_create_connection = types.FunctionType(
      socket.create_connection.func_code, fake_create_connection_globals,
      None, socket.create_connection.func_defaults)
    fake_create_connection.__doc__ = (
        """Non-blocking drop-in replacement for socket.create_connection.""")
  return fake_create_connection


def _populate_socket_module_with_coio(socket_module):
  """Populate a socket module with coio non-blocking functions and classes."""
  from syncless import coio
  # There is no need to afraid that ssl.SSLSocket would pick up coio.nbsocket
  # as its base class, because when `coio' is loaded above, it loads `ssl' as
  # well, so loading `ssl' happens before the following assignment.
  socket_module.socket = coio.nbsocket
  # TODO(pts): Maybe make this a class?
  socket_module._realsocket = coio.new_realsocket
  if not hasattr(socket_module, '_socket'):
     # Create new module.
    socket_module._socket = type(socket_module)('fake_coio_c_socket')
  socket_module._socket.socket = coio.new_realsocket
  socket_module.gethostbyname = coio.gethostbyname
  socket_module.gethostbyname_ex = coio.gethostbyname_ex
  socket_module.gethostbyaddr = coio.gethostbyaddr
  socket_module.getfqdn = coio.getfqdn
  # TODO(pts): Better indicate NotImplementedError
  socket_module.getaddrinfo = None
  socket_module.getnameinfo = None
  socket_module.create_connection = get_fake_create_connection()
  socket_module.socketpair = coio.socketpair
  return socket_module

fake_coio_socket_module = None
"""None or a fake socket module containing constants and some coio values."""

def get_fake_coio_socket_module():
  global fake_coio_socket_module
  if fake_coio_socket_module is None:
    import socket
    fake_coio_socket_module = type(socket)('fake_coio_socket')
    for name in dir(socket):
      if (name[0] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' and
          isinstance(getattr(socket, name), int)):
        setattr(fake_coio_socket_module, name, getattr(socket, name))
    _populate_socket_module_with_coio(fake_coio_socket_module)
  return fake_coio_socket_module


fake_coio_select_module = None
"""None or a fake select module containing select()."""

def get_fake_coio_select_module():
  global fake_coio_select_module
  if fake_coio_select_module is None:
    from syncless import coio
    fake_coio_select_module = type(coio)('fake_coio_select')
    fake_coio_select_module.select = coio.select
  return fake_coio_select_module


def patch_socket():
  """Monkey-patch the socket module for non-blocking I/O."""
  import socket
  _populate_socket_module_with_coio(socket)


def patch_ssl():
  """Monkey-patch the standard ssl module for non-blocking I/O."""
  import ssl
  from syncless import coio
  ssl.SSLSocket = coio.nbsslsocket
  # There is no need to patch ssl.wrap_socket since ssl.SSLSocket is already
  # patched.
  #ssl.wrap_socket = coio.ssl_wrap_socket


def patch_mysql_connector():
  from mysql.connector import connection
  connection.socket = get_fake_coio_socket_module()


def patch_pymysql():
  from pymysql import connections
  connections.socket = get_fake_coio_socket_module()


def patch_time():
  import time
  from syncless import coio
  time.sleep = coio.sleep


def patch_select():
  import select
  from syncless import coio
  select.select = coio.select
  if hasattr(select, 'poll'):
    del select.poll  # So smart libs won't try to use it.
  if hasattr(select, 'epoll'):
    del select.epoll  # So smart libs won't try to use it.


def patch_asyncore():
  import asyncore
  import select
  from syncless import coio
  select_module = type(asyncore)('fake_asyncore_select')
  # Ignore the xlist.
  select_module.select = (lambda rlist, wlist, xlist, timeout = None:
                          coio.select(rlist, wlist, (), timeout))
  select_module.error = select.error
  asyncore.select = select_module


def patch_tornado():
  from syncless import coio
  import tornado.ioloop

  # Constants as used by coio.wakeup_info.
  tornado.ioloop.IOLoop.READ = 1
  tornado.ioloop.IOLoop.WRITE = 2
  # Ignore IOLoop.ERROR, libevent cannot poll for that.
  tornado.ioloop.IOLoop.ERROR = 0

  class TornadoSynclessPoll(object):
    """A Syncless-based tornado.ioloop.IOLoop polling implementation."""
    def __init__(self):
      self.wakeup_info = coio.wakeup_info()
      self.fd_to_event = {}

    def register(self, fd, events):
      self.fd_to_event[fd] = self.wakeup_info.create_event(fd, events)

    def modify(self, fd, events):
      # A combination of unregister + register.
      event = self.fd_to_event.pop(fd, None)
      if event:
        event.delete()
      self.fd_to_event[fd] = self.wakeup_info.create_event(fd, events)

    def unregister(self, fd):
      event = self.fd_to_event.pop(fd, None)
      if event:
        event.delete()

    def poll(self, timeout):
      return self.wakeup_info.tick_and_move(timeout)

  tornado.ioloop._poll = TornadoSynclessPoll


def patch_concurrence():
  """Patch Concurrence r117.

  Concurrence r117 was checked out from
  http://concurrence.googlecode.com/svn/trunk at Thu Apr 29 19:43:44 CEST 2010.
  """
  import logging
  import sys
  from concurrence import core
  try:
    from concurrence import event  # In repo at Sat May  8 03:06:41 CEST 2010
  except ImportError:
    event = type(sys)('unused_event')
  from concurrence import _event
  from syncless import coio
  stackless = coio.stackless

  def Exit(code=0):
    raise SystemExit(code)

  def Quit(exitcode=core.EXIT_CODE_OK):
    core._running = False
    core._exitcode = exitcode
    # TODO(pts): Test this.
    coio.get_concurrence_triggered().append(lambda evtype: 0, 0)
    for tasklet_obj in coio.get_concurrence_main_tasklets():
      tasklet_obj.insert()

  def Dispatch(f=None):
    """Replacement for concurrence.core.dispatch().

    This function can be run in any tasklet, even in multiple tasklets in
    parallel (but that doesn't make sense).
    """
    # TODO(pts): Don't count this as a regular tasklet for Syncless exiting.
    # TODO(pts): Make this configurable.
    #event_interrupt = SignalEvent(
    #    core.SIGINT, lambda core.quit(core.EXIT_CODE_SIGINT))
    main_tasklets = coio.get_concurrence_main_tasklets()
    assert stackless.current not in main_tasklets
    main_tasklets.append(stackless.current)
    # We set _running to True for compatibility with Concurrence.
    core._running = True
    try:
      if callable(f):
        core.Tasklet.new(f)()
      while core._running:
        try:
          # coio.HandleCConcurrence will insert us back.
          if coio.get_concurrence_triggered():
            stackless.schedule(None)
          else:
            stackless.schedule_remove(None)
        except TaskletExit:
          pass
        except KeyboardInterrupt:
          raise
        except:
          logging.exception('unhandled exception in dispatch schedule')
        for callback, evtype in coio.get_swap_concurrence_triggered():
          try:
            # The callback can extend coio.get_concurrence_triggered().
            # TODO(pts): How come??
            callback(evtype)
          except TaskletExit:
            raise
          except:
            logging.exception('unhandled exception in dispatch event callback')
            # TODO(pts): Push back to coio.get_concurrence_triggered().
    finally:
      main_tasklets.remove(stackless.current)

  for name in dir(_event):
    if name != '__builtins__' and name != '__name__':
      delattr(_event, name)
  for name in dir(event):
    if name != '__builtins__' and name != '__name__':
      delattr(event, name)
  assert core.event is event
  _event.method = event.method = coio.method
  _event.version = event.version = coio.version
  _event.event = event.event = coio.concurrence_event
  _event.EV_TIMEOUT = event.EV_TIMEOUT = coio.EV_TIMEOUT
  _event.EV_READ = event.EV_READ = coio.EV_READ
  _event.EV_WRITE = event.EV_WRITE = coio.EV_WRITE
  _event.EV_SIGNAL = event.EV_SIGNAL = coio.EV_SIGNAL
  _event.EV_PERSIST = event.EV_PERSIST = coio.EV_PERSIST
  core.quit = Quit
  core._dispatch = Dispatch
  sys.exit = Exit

  # Replace the broken Stackless emulation in concurrence.core with the
  # better emulation in Stackless.
  core.stackless = stackless
  if core.Tasklet.__bases__[0] is not stackless.tasklet:
    # It's time for some Python class model black magic.
    dict_obj = dict(core.Tasklet.__dict__)
    assert '__slots__' not in dict_obj
    # Changing the __new__ method here would create new objects even if
    # someone has a reference to the old class, e.g. from an earlier
    # `from concurrence.core import Tasklet'.
    core.Tasklet.__new__ = classmethod(lambda *args: core.Tasklet())
    core.Tasklet = type(core.Tasklet.__name__,
                        (stackless.tasklet,) + core.Tasklet.__bases__[1:],
                        dict_obj)


def _check_both_native():
  assert not (
      sys.modules.get('stackless') and
      sys.modules.get('greenlet') and
      type(sys.modules['stackless'].getcurrent) is not types.FunctionType and
      type(sys.modules['greenlet'].getcurrent) is not types.FunctionType), (
      'This Python supports both stackless and greenlet natively. '
      'syncless.patch.patch_gevent() needs one of them emulated.')


def gevent_hub_main():
  """Run the gevent hub (+ Syncless) main loop forever.

  This function is a drop-in replacement of gevent.hub.get_hub.switch() with
  re-raising the GreeenletExit as SystemExit.

  See also patch_gevent() for more documentation.
  """
  from syncless import best_greenlet
  if 'syncless.coio' not in sys.modules:
    return best_greenlet.gevent_hub_main()
  _check_both_native()
  from gevent import hub
  if not getattr(hub, 'is_syncless_fake_hub', None):
    patch_gevent()
  from syncless import coio
  main_loop_tasklet = coio.get_main_loop_tasklet()
  hub_obj = hub.get_hub()
  hub_type = str(type(hub_obj))
  assert hub_type.startswith('<class '), hub_type
  assert hub_type.endswith(".SynclessFakeHub'>"), hub_type
  assert hub_obj, 'gevent hub not running'
  assert hub_obj._tasklet is main_loop_tasklet
  import stackless
  assert stackless.current is not main_loop_tasklet
  if hasattr(best_greenlet, 'current'):  # Emulated greenlet.
    best_greenlet.current = hub_obj
    best_greenlet._insert_after_current_tasklet(main_loop_tasklet)
  else:
    # Implement _insert_after_current_tasklet(main_loop_tasklet).
    if stackless.current.next is stackless.current:
      main_loop_tasklet.insert()
    elif stackless.current.next is not main_loop_tasklet:
      # This is tricky, see the details in best_greenlet.py.
      # TODO(pts): Present this on the conference.
      main_loop_tasklet.remove()
      helper_tasklet = stackless.tasklet(
          lambda: stackless.current.next.next.remove().run())()
      helper_tasklet.insert()
      main_loop_tasklet.insert()
      helper_tasklet.run()
      helper_tasklet.remove()

    if best_greenlet.greenlet.getcurrent() is hub.MAIN:
      try:
        return stackless.schedule_remove()
      except best_greenlet.greenlet.GreenletExit:
        raise SystemExit
  return stackless.schedule_remove()


def patch_gevent():
  """Patch gevent so it works with Syncless in the same process.

  Tested with gevent-0.12.2, please upgrade your gevent if it's older.

  Ctrl-<C> (KeyboardInterrupt) works as intended: it aborts the process by
  default with the KeyboardInterrupt exception in the main tasklet/greenlet.

  Since gevent is based on greenlet, and Syncless is based on Stackless, one
  of those has to be emulated. patch_gevent() takes care of this by using
  syncless.best_greenlet and syncless.best_stackess.

  Please note that if you just want to use grevent without the Syncless
  non-blocking functionality, just do this:

    import syncless.best_greenlet  # To emulate greenlet with Stackless.
    #from syncless.best_greenlet.greenlet import greenlet  # If used.
    ...
    import gevent.hub ...
    ...
    if __name__ == '__main__':
      ...  # Create the server sockets, but don't accept() yet.
      gevent.hub.spawn_raw(Listener, ...)  # accept() in Listener().
      syncless.best_greenlet.gevent_hub_main()

   If you want to use gevent and Syncless together, import like this:
   
    #from syncless.best_greenlet.greenlet import greenlet  # If used.
    ...
    import gevent.hub ...
    from syncless import coio
    from syncless import patch
    ...
    if __name__ == '__main__':
      ...  # Create the server sockets, but don't accept() yet.
      gevent.hub.spawn_raw(Listener, ...)  # accept() in Listener().
      ...  # Create and start non-blocking Syncless tasklets.
      syncless.best_greenlet.gevent_hub_main()
      # Alternatively, instead of gevent_hub_main() you can do a any Syncless
      # non-blocking I/O (forever) -- but no gevent non-blocking I/O.

  See examples/demo_gevent.py for a comprehensive example program.

  Please note the following simple limitations of the gevent + Syncless
  cooperation:

  * You have to compile gevent and Syncless with the same version of libevent
    (e.g. libevent1 >= 1.4.13 or libevent2 >= 2.0.4). libev won't work, because
    gevent doesn't support libev. The same-version limitation is there because
    the Syncless main loop must be able to wait (poll) for events registered
    by gevent.
    
    Here is how to compile Syncless with libevent1:

      $ SYNCLESS_USE_LIBEVENT1=1 python setup.py build    
      $ sudo python setup.py install

    patch.patch_gevent() verifies that both the version and the notification
    method (e.g. select or epoll) used by Syncless and gevent match.
    Furthermore, the library file must be the same (e.g. it's not OK to
    compile Syncless with libevent.so in /usr/lib, and gevent with
    libevent.so in /usr/local/lib). This is not checked.

  * All non-blocking gevent I/O operations must be initiated from a greenlet
    created by the gevent hub. So you may create a server socket (and bind
    to it) in the main greenlet, but you may only accept() it in another
    greenlet, created by the gevent hub. So put your accept() to a function
    named Listener, and do a gevent.hub.spawn_raw(Listener) or
    gevent.swawn(Listener). There is no such restriction for Syncless I/O
    operations: you can do them anywhere.

  * Communication and synchronization between gevent greenlets and
    Syncless/Stackless tasklets in the same process is not possible, i.e. a
    tasklet cannot wait for data generated by a greenlet or vice versa.
    (Please note that data sharing in the process memory works as intended,
    because both greenlets and tasklets are coroutine-based.) If you need
    that, currently your only option is to create a pipe or a socket, and
    send notification bytes through it. Please note that you don't have to
    serialize the actual data, since you can store them in a variable
    accessible to both the tasklet and the greenlet.

  * Don't do Syncless non-blocking I/O before importing gevent (because the
    event_init() called when importing gevent.core makes all
    registered Syncless events vanish, without ever triggering).

  * The gevent.hub.get_hub().shutdown() function is not supported. Please
    use sys.exit() from your main greenlet, and gevent.hub.MAIN.throw()
    (or gevent.hub.MAIN.throw(SystemExit)) form all non-blocking greenlets
    started by the gevent hub.

  TODO(pts): Measure performance (will be slower than pure Syncless or pure
  gevent, because either Stackless or gevent is emulated).

  Note: It was very tricky to get exception handling right, especially
  making the exception handler in gevent.core.__event_handler ignore the
  TaskletExit exceptions at exit time.
  """
  from syncless import best_greenlet
  is_greenlet_emulated = bool(getattr(
      best_greenlet.greenlet.greenlet, 'is_pts_greenlet_emulated', None))
  assert is_greenlet_emulated == hasattr(best_greenlet, 'current')
  greenlet = best_greenlet.greenlet.greenlet
  import traceback
  from gevent import core
  from gevent import hub
  if getattr(hub, 'is_syncless_fake_hub', None):
    return   # Already patched.
  assert greenlet.getcurrent() is hub.MAIN
  from syncless import coio
  stackless = coio.stackless
  _check_both_native()
  gevent_info = (core.get_method(), core.get_version())
  syncless_info = (coio.method(), coio.version())
  assert gevent_info == syncless_info, (
      'event library mismatch: gevent uses %r, Syncless uses %r' %
      (gevent_info, syncless_info))
  hub_obj = getattr(getattr(hub, '_threadlocal', hub), 'hub', None)
  if hasattr(hub_obj, 'switch'):
    # A hub is not a switch :-).
    # Seriously, we execute this branch there is already a greenlet hub.
    # This assertion prevents the possibility that the patching happens
    # inside an libevent event handler executing in the gevent hub.
    assert not hub_obj, 'too late, gevent hub already running'
  hub.__dict__.pop('thread', None)
  hub.is_syncless_fake_hub = True
  def RaiseInvalidHubSwitch():
    xtra = ''
    if stackless.current is stackless.main:
      xtra = ('; define a Main function, and call us from '
              'gevent.hub.spawn_raw(Main)')
      raise AssertionError(
        'gevent.hub.get_hub().switch() called from the wrong tasklet (%r), '
        'expected main_loop_tasklet %r%s' %
        (stackless.current, coio.get_main_loop_tasklet(), xtra))
  class SynclessFakeHub(greenlet):
    if is_greenlet_emulated:
      # This is needed so late TaskletExit exceptions in best_greenlet will be
      # properly ignored.
      is_gevent_hub = True
      def switch(self):
        if self._tasklet.scheduled:
          RaiseInvalidHubSwitch()
        cur = best_greenlet.current  # greenlet.getcurrent()
        assert cur is not self, (
            'Cannot switch to MAINLOOP from MAINLOOP')
        switch_out = getattr(cur, 'switch_out', None)
        if switch_out is not None: 
          try:
            switch_out()
          except:
            traceback.print_exc()  
        return greenlet.switch(self)
      @property
      def run(self):
        assert 0, 'internal logic error: FakeHub().run requested'
    else:  # With real (non-emulated) greenlet.
      def switch(self):
        main_loop_tasklet = coio.get_main_loop_tasklet()
        if stackless.current is not main_loop_tasklet:
          RaiseInvalidHubSwitch()
        cur = greenlet.getcurrent()
        assert cur is not main_loop_tasklet._greenlet, (
            'Cannot switch to MAINLOOP from MAINLOOP')
        switch_out = getattr(cur, 'switch_out', None)
        if switch_out is not None:
          try:
            switch_out()
          except:
            traceback.print_exc()
        # `return main_loop_tasklet._greenlet.switch()' would be straightforward
        # here, but greenlet seems to call self.run anyway after accept (proably
        # because it's C code ignoring the override of self.switch).
        return greenlet.switch(self)
      def run(self):
        self.parent.switch()  # Resume to patch_gevent() after first startup.
        main_loop_tasklet = coio.get_main_loop_tasklet()
        assert self is not main_loop_tasklet._greenlet
        while True:
          assert stackless.current is main_loop_tasklet
          main_loop_tasklet._greenlet.switch()
  fake_hub = SynclessFakeHub()
  if not is_greenlet_emulated:
    greenlet.switch(fake_hub)  # Start the hub for the first time.
  fake_hub._tasklet = coio.get_main_loop_tasklet()
  hub._threadlocal = type(hub)('fake_threadlocal')
  # Make existing references to the old get_hub() work.
  hub.hub = hub._threadlocal.hub = fake_hub
  hub.get_hub = lambda fake_hub=fake_hub: fake_hub
  def ErrorNoNewHub(self):
    assert 0, 'too late creating a new Hub'
  hub.Hub.__new__ = classmethod(lambda *args: ErrorNoNewHub())
  del hub.Hub
  SynclessFakeHub.__new__ = classmethod(lambda *args: ErrorNoNewHub())
  gevent_hub_main.__doc__ = best_greenlet.gevent_hub_main.__doc__
  best_greenlet.gevent_hub_main = gevent_hub_main
  best_greenlet.greenlet.gevent_hub_main = gevent_hub_main
  # Can't set best_greenlet.greenlet.greenlet.gevent_hub_main, because
  # greenlet.greenlet is an extension type (class).


def patch_eventlet():
  """Patch Eventlet so it works with Syncless in the same process.

  This has been tested with Eventlet 0.9.7.

  Please note that multithreaded use of Eventlet is untested. (It could be
  tested by creating a thread pool of database client connections.)
  
  The emulation works with both Stackless and greenlet.
  """
  # Make sure greenlet is loaded properly.
  from syncless.best_greenlet.greenlet import greenlet
  from syncless import coio
  from eventlet import hubs
  from eventlet.hubs import hub
  from eventlet.common import clear_sys_exc_info
  old_hub_class = str(getattr(hubs._threadlocal, 'Hub', None))
  if (old_hub_class.startswith('<class \'') and
      old_hub_class.endswith('.SynclessHub\'>')):
    return  # Already patched.
  assert hub.greenlet.greenlet is greenlet, (
      'greenlet class implementation mismatch: syncless uses %r, '
      'Eventlet uses %r; import syncless.best_greenlet first to resolve' %
      (greenlet, hub.greenlet.greenlet))
  assert not hasattr(hubs._threadlocal, 'hub'), (
      'too late, Eventlet hub already created; '
      'to resolve, call patch_eventlet() before doing blocking I/O')

  EVTYPE_STR_TO_MODE = {
      hub.READ: 1,
      hub.WRITE: 2,
  }

  class SynclessHub(hub.BaseHub):
    def __init__(self, *args, **kwargs):
      hub.BaseHub.__init__(self, *args, **kwargs)
      # Map file descriptors to coio.wakeup_info_event objects.
      self.wakeup_info = coio.wakeup_info()
      self.listeners_by_mode = [None, self.listeners[hub.READ],
                                self.listeners[hub.WRITE]]
      # The dict maps file descriptors to coio.wakeup_info_event objects.
      self.events_by_mode = [None, {}, {}]

    def add(self, evtype, fileno, cb):
      # Eventlet is slow in general, because it creates an FdListener
      # (self.class) for each non-ready read and write operation.
      mode = EVTYPE_STR_TO_MODE[evtype]
      listener = self.lclass(evtype, fileno, cb)
      listener.mode = mode
      listeners = self.listeners_by_mode[mode]
      if fileno in listeners:
        listeners[fileno].append(listener)
      else:
        # Eventlet is careful: it doesn't install multiple listeners for the
        # same (fd, mode), so it would work with libevent.
        self.events_by_mode[mode][fileno] = self.wakeup_info.create_event(
            fileno, mode)
        listeners[fileno] = [listener]
      return listener

    def remove(self, listener):
      listeners = self.listeners_by_mode[listener.mode]
      fileno = listener.fileno
      try:
        listeners[fileno].remove(listener)
        if not listeners[fileno]:
          del listeners[fileno]
          self.events_by_mode[listener.mode].pop(fileno).delete()
      except (KeyError, ValueError):
        pass

    def remove_descriptor(self, fileno):
      if self.listeners_by_mode[1].pop(fileno, None):
        self.events_by_mode[1].pop(fileno).delete()
      if self.listeners_by_mode[2].pop(fileno, None):
        self.events_by_mode[2].pop(fileno).delete()

    def wait(self, timeout=None):
      # This calls the Syncless main loop if needed.
      events = self.wakeup_info.tick(timeout)
      while events:
        fileno, mode = events.pop()
        listeners = self.listeners_by_mode[mode][fileno]
        try:
          if listeners:
            # By design, Eventlet calls only the first registered listener.
            listeners[0](fileno)
        except self.SYSTEM_EXCEPTIONS:
          raise
        except:
          self.squelch_exception(fileno, sys.exc_info())
          clear_sys_exc_info()

  hubs.use_hub(SynclessHub)
  assert SynclessHub is hubs._threadlocal.Hub


def ExceptHook(orig_excepthook, *args):
  from syncless import coio
  try:
    old_blocking = coio.set_fd_blocking(2, True)
    orig_excepthook(*args)
  finally:
    coio.set_fd_blocking(2, old_blocking)


def patch_stderr():
  from syncless import coio
  if not isinstance(sys.stderr, coio.nbfile):
    new_stderr = coio.fdopen(sys.stderr.fileno(), 'w', bufsize=0, do_close=0)
    logging = sys.modules.get('logging')
    if logging:
      for handler in logging.root.handlers:
        stream = getattr(handler, 'stream', None)
        if stream is sys.stderr:
          handler.stream = new_stderr
    sys.stderr = new_stderr
    # Make sure we can print the final exception which causes the death of the
    # program.
    orig_excepthook = sys.excepthook
    sys.excepthook = lambda *args: ExceptHook(orig_excepthook, *args)


def patch_stdin_and_stdout():
  from syncless import coio
  # !! patch stdin and stdout separately (for sys.stdout.fileno())
  if (not isinstance(sys.stdin,  coio.nbfile) or
      not isinstance(sys.stdout, coio.nbfile)):
    # Unfortunately it's not possible to get the current buffer size from a
    # Python file object, so we just set up the defaults here.
    write_buffer_limit = 8192
    import os
    if os.isatty(sys.stdout.fileno()):
      write_buffer_limit = 1  # Set up line buffering.
    new_stdinout = coio.nbfile(sys.stdin.fileno(), sys.stdout.fileno(),
                               write_buffer_limit=write_buffer_limit,
                               do_close=0)
    sys.stdin = sys.stdout = new_stdinout


def get_close_fds():
  import os
  def close_fds(self, but):
    """Close everything larger than 2, but different from `but'."""
    try:
      fd_list = os.listdir('/proc/self/fd')
    except OSError:
      os.closerange(3, but)
      os.closerange(but + 1, subprocess.MAXFD)
      return
    # This is much faster than closing millions of unopened Linux filehandles.
    for fd_str in fd_list:
      fd = int(fd_str)
      if fd > 2 and fd != but:
        try:
          os.close(fd)
        except OSError:  # Skip the os.listdir filehandle.
          pass
  return close_fds


def get_closerange():
  """Return a faster, unlimited replacement of os.closerange."""
  import os
  def closerange(a, b):
    try:
      fd_list = os.listdir('/proc/self/fd')
    except OSError:
      return os.closerange(a, b)
    # This is much faster than closing millions of unopened Linux filehandles.
    for fd_str in fd_list:
      fd = int(fd_str)
      if a <= fd < b:
        try:
          os.close(fd)
        except OSError:  # Skip the os.listdir filehandle.
          pass
  return closerange


def _get_patched_fork(unpatched_fork):
  from syncless import coio
  def fork():
    pid = unpatched_fork()
    if not pid:  # Child.
      coio.reinit()
    return pid
  fork.is_syncless_patched = True
  return fork


def patch_os():
  import os
  from syncless import coio
  os.fdopen = coio.fdopen
  os.popen = coio.popen
  if not getattr(os.fork, 'is_syncless_patched', None):
    os.fork = _get_patched_fork(os.fork)
    assert os.fork.is_syncless_patched


def patch_subprocess():
  import os
  import subprocess
  from syncless import coio
  # This is not strictly necessary, but speeds up close() operations.
  fix_subprocess_close()
  os_module = type(os)('fake_os')
  for key in dir(os):
    setattr(os_module, key, getattr(os, key))
  os_module.__name__ = 'fake_os'
  os_module.closerange = None  # Fail on call attempt.
  os_module.fdopen = coio.fdopen
  subprocess.os = os_module


def patch_popen2():
  import popen2
  from syncless import coio
  # This is not strictly necessary, but speeds up close() operations.
  fix_popen2_close()
  assert popen2.os.__name__ == 'fake_os'
  popen2.os.fdopen = coio.fdopen


def fix_subprocess_close():
  """Fix closing millions of many unopened file in the subprocess module."""
  import subprocess
  subprocess.Popen._close_fds = get_close_fds()


def fix_popen2_close():
  """Fix closing millions of many unopened file in the popen2 module."""
  import os
  import popen2
  if popen2.os.__name__ == 'os':
    os_module = type(os)('fake_os')
    for key in dir(os):
      setattr(os_module, key, getattr(os, key))
    os_module.__name__ = 'fake_os'
    popen2.os = os_module
  popen2.os.closerange = get_closerange()


def fix_ssl_makefile():
  """Fix the reference counting in ssl.SSLSocket.makefile().
  
  This is the reference counting bugfix (close=True) for Stackless 2.6.4.
  """
  try:
    import ssl
  except ImportError:
    ssl = None
  if ssl:
    import socket
    def SslMakeFileFix(self, mode='r', bufsize=-1):
      self._makefile_refs += 1
      return socket._fileobject(self, mode, bufsize, close=True)
    ssl.SSLSocket.makefile = types.MethodType(
        SslMakeFileFix, None, ssl.SSLSocket)


def fix_ssl_init_memory_leak():
  """Fix the memory leak in ssl.SSLSocket.__init__ in Python 2.6.4.

  ssl.SSLSocket.__init__ has code like this:

    self.send = lambda data, flags=0: SSLSocket.send(self, data, flags)

  It could have been this simple, and it would still produce a memory leak:
  
    self.foo = lambda: self

  This creates a circular reference (self -> __init__ -> lambda -> self),
  which prevents self._sock from being automatically closed when self goes out
  of scope.

  The fix just removes those lambdas (and function attributes created by
  socket.socket.__init__ as well). This fixes the memory leak, and provides
  correct behavior.
  """
  try:
    import ssl
  except ImportError:
    return
  import socket
  import types
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  if getattr(ssl.SSLSocket(sock).recv, 'func_name', None) == '<lambda>':
    del sock
    # TODO(pts): Don't create a socket.socket just for the detection above.
    old_init = ssl.SSLSocket.__init__.im_func
    def SslInitFix(*args, **kwargs):
      self = args[0]
      try:
        old_init(*args, **kwargs)
      finally:
        if self.recv.func_name == '<lambda>':
          for attr in socket._delegate_methods:
            delattr(self, attr)
    ssl.SSLSocket.__init__ = types.MethodType(SslInitFix, None, ssl.SSLSocket)


def validate_new_sslsock(**kwargs):
  """Validate contructor arguments of ssl.SSLSocket.

  Validate SSL parameter constructor arguments of ssl.SSLSocket. This is useful
  to check if the specified keyfile= and certfile= exist and have a valid
  format etc.

  Normal ssl.SSLSocket does the validation only upon connect() or accept().

  Args:
    kwargs: keyfile=, certfile=, cert_reqs=, ssl_version=, ca_certs=
      (some of them can be missing)
  """
  import errno
  import ssl
  import socket
  nsock = socket._realsocket(socket.AF_INET, socket.SOCK_STREAM)
  try:
    nsslobj = ssl._ssl.sslwrap(
        nsock, False,
        kwargs.get('keyfile'),
        kwargs.get('certfile'),
        kwargs.get('cert_reqs', ssl.CERT_NONE),
        kwargs.get('ssl_version', ssl.PROTOCOL_SSLv23),
        kwargs.get('ca_certs'))
    try:
      nsslobj.do_handshake()
    except socket.error, e:
      if e.errno not in (errno.EPIPE, errno.ENOTCONN):
        raise
  finally:
    nsock.close()


def fix_all_std():
  fix_ssl_makefile()
  fix_ssl_init_memory_leak()
  fix_subprocess_close()


def patch_all_std():
  fix_all_std()
  patch_asyncore()
  #patch_concurrence()  # Non-standard module, don't patch.
  patch_os()
  patch_popen2()
  patch_socket()
  patch_subprocess()
  patch_ssl()
  #patch_mysql_connector()  # Non-standard module, don't patch.
  #patch_pymysql()  # Non-standard module, don't patch.
  patch_time()
  patch_select()
  #patch_tornado()  # Non-standard module, don't patch.
  patch_stdin_and_stdout()
  patch_stderr()
  patch_subprocess()
