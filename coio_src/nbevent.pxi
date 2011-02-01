#
# nbevent.pxi: non-blocking I/Oclasses using libevent and buffering
# by pts@fazekas.hu at Sun Jan 31 12:07:36 CET 2010
# ### pts #### This file has been entirely written by pts@fazekas.hu.
#
# This code is designed for Stackless Python 2.6. It has been tested with
# Stackless Python 2.6.4 and 2.6.5. It also works (with reduced performance)
# with Python 2.5 and greenlet.
#
# Please note that stackless.schedule_remove() is ignored for stackless.main
# (but another tasklet may remove stackless.main), and also if there are no
# other tasklets in the queue when stackless.schedule_remove() is called, then
# the process exits (sys.exit(0)).
#
# TODO(pts): Test when multiple events are registered with the same fd.
# TODO(pts): Add module docstring.
# !! TODO(pts) there are still long requests, even with listen(2280)
#Connection Times (ms)
#              min  mean[+/-sd] median   max
#Connect:        0   28 288.3      0    3002
#Processing:     3   12  23.0     11    1868
#Waiting:        2   12  23.0     11    1868
#Total:          9   40 296.6     11    4547
#
#Percentage of the requests served within a certain time (ms)
#  50%     11
#  66%     11
#  75%     11
#  80%     11
#  90%     12
#  95%     13
#  98%     21
#  99%     60
# 100%   4547 (longest request)

# TODO(pts): Productionize TimeoutReceive
# TODO(pts): Port to greenlet.
# TODO(pts): Port to pure libev (instead of the libevent emulation layer).
# TODO(pts): Port to pure Python + select() or epoll().
import os
import stackless
import socket
#import __builtin__
import types

cdef object socket_error "coio_socket_error"
socket_error = socket.error
cdef object socket_timeout "coio_socket_timeout"
socket_timeout = socket.timeout

# These are some Pyrex magic declarations which will enforce type safety in
# our *.pxi files by turning GCC warnings about const and signedness to Pyrex
# errors.
#
# stdlib.h is not explicitly needed, but providing a from clause prevents
# Pyrex from generating a ``typedef''.
#
# The declarations are a bit quirky (using a helper struct and a helper
# typedef), but this is how to make them work in both Pyrex and Cython
# (Pyrex was more permissive).
#
# Please note that Pyrex is different from Cython in the sense that
# <unsigned><void*>self is needed in Cython instead of <unsigned>self.
#
# Please note that Pyrex is different from Cython in the sense that
# PyString_FromFormat(<char_constp><char*>'blah', ...) is needed in Cython
# instead of PyString_FromFormat(<char_constp>'blah', ...).
#
# Please note that Pyrex is different from Cython in the sense that Pyrex
# doesn't do bounds checking upon assignment to a char value from an int,
# e.g. mychar = <unsigned char>PyInt_FromString(items[i], NULL, 10).
cdef extern from *:
    struct void_consts:
        pass
    struct char_consts:
        pass
    struct uchar_s:
        pass
    struct uchar_consts:
        pass
    ctypedef void_consts void_constt "void const"
    ctypedef char_consts char_constt "char const"
    ctypedef uchar_s uchar_t "unsigned char"
    ctypedef uchar_consts uchar_constt "unsigned char const"
    ctypedef void_constt* void_constp "void const*"
    ctypedef char_constt* char_constp "char const*"
    ctypedef uchar_t* uchar_p "unsigned char*"
    ctypedef uchar_constt* uchar_constp "unsigned char const*"

cdef extern from "stdlib.h":
    ctypedef int size_t

cdef extern from "unistd.h":
    cdef int debug_write "write"(int fd, char_constp p, int n)
    cdef int debug_read "read"(int fd, char *p, int n)
    cdef int dup(int fd)
    cdef int close(int fd)
    cdef int isatty(int fd)
    cdef int ftruncate(int fd, int size)
cdef extern from "string.h":
    cdef void *memset(void *s, int c, size_t n)
    cdef void *memchr(void_constp s, int c, size_t n)
    cdef void *memcpy(void *dest, void_constp src, size_t n)
    cdef void *memmove(void *dest, void_constp src, size_t n)
    cdef int memcmp(void_constp s1, void_constp s2, size_t n)
cdef extern from "errno.h":
    cdef extern int errno
    cdef extern char *strerror(int)
    cdef enum errno_dummy:
        EAGAIN
        EINPROGRESS
        EALREADY
        EIO
        EISCONN
cdef extern from "fcntl.h":
    cdef int fcntl2 "fcntl"(int fd, int cmd)
    cdef int fcntl3 "fcntl"(int fd, int cmd, long arg)
    int O_NONBLOCK
    int F_GETFL
    int F_SETFL
cdef extern from "signal.h":
    int SIGINT
    int SIGUSR1
    int SIGUSR2
    int kill(int pid, int signum)
    int getpid()
cdef extern from "sys/socket.h":
    int AF_INET6
    int AF_INET
cdef extern from "sys/select.h":
    struct timeval:
        unsigned int tv_sec
        unsigned int tv_usec
    struct fd_set_s:
        pass
    ctypedef fd_set_s fd_set
    int os_select "select"(int nfds, fd_set *rset, fd_set *wset, fd_set *xset,
                           timeval *timeout)
cdef extern from "stdio.h":
    ctypedef struct FILE
    int fileno(FILE*)
    int fprintf(FILE*, char_constp fmt, ...)

ctypedef void (*event_handler)(int fd, short evtype, void *arg)

cdef extern from "./coio_c_include_libevent.h":
    int c_FEATURE_MAY_EVENT_LOOP_RETURN_1 "FEATURE_MAY_EVENT_LOOP_RETURN_1"
    int c_FEATURE_MULTIPLE_EVENTS_ON_SAME_FD "FEATURE_MULTIPLE_EVENTS_ON_SAME_FD"


    struct event_t "event":
        int   ev_fd
        int   ev_flags
        void *ev_arg
        #short ev_events  # c_EV_READ | c_EV_WRITE etc.
        event_handler ev_callback

    int coio_event_init()
    int coio_event_reinit(int do_recreate)
    void event_set(event_t *ev, int fd, short event,
                   event_handler handler, void *arg)
    int event_add(event_t *ev, timeval *tv)
    int event_del(event_t *ev)
    int event_loop(int loop) nogil
    int event_pending(event_t *ev, short, timeval *tv)

    char *event_get_version()
    char *event_get_method()

    int EVLOOP_ONCE
    int EVLOOP_NONBLOCK
    #int EVLIST_INTERNAL

    int c_EV_TIMEOUT "EV_TIMEOUT"
    int c_EV_READ "EV_READ"
    int c_EV_WRITE "EV_WRITE"
    int c_EV_SIGNAL "EV_SIGNAL"
    int c_EV_PERSIST "EV_PERSIST"

# TODO(pts): Do this (exporting to Python + reusing the constant in C)
# with less typing.
EV_TIMEOUT = c_EV_TIMEOUT
EV_READ = c_EV_READ
EV_WRITE = c_EV_WRITE
EV_SIGNAL = c_EV_SIGNAL
EV_PERSIST = c_EV_PERSIST

cdef extern from "./coio_c_evbuffer.h":
    struct evbuffer_s "coio_evbuffer":
        uchar_p buf "buffer"
        uchar_p orig_buffer
        size_t misalign
        size_t totallen
        size_t off
        void *cbarg
        void (*cb)(evbuffer_s*, int, int, void*)

    evbuffer_s *evbuffer_new "coio_evbuffer_new"()
    void evbuffer_free "coio_evbuffer_free"(evbuffer_s *)
    void evbuffer_reset "coio_evbuffer_reset"(evbuffer_s *)  # Non-std.
    int evbuffer_expand "coio_evbuffer_expand"(evbuffer_s *, int)
    int evbuffer_add "coio_evbuffer_add"(evbuffer_s *, void_constp, int)
    int evbuffer_drain "coio_evbuffer_drain"(evbuffer_s *b, int size)

cdef extern from "Python.h":
    ctypedef struct PyObject:
        pass
    void   Py_INCREF(object o)
    void   Py_DECREF(object o)
    object PyString_FromFormat(char_constp fmt, ...)
    object PyString_FromStringAndSize(char_constp v, Py_ssize_t len)
    object PyString_FromString(char_constp v)
    int    PyObject_AsCharBuffer(object obj, char_constp *buffer, Py_ssize_t *buffer_len) except -1
    object PyInt_FromString(char*, char**, int)
cdef extern from "pymem.h":
    void *PyMem_Malloc(size_t)
    void *PyMem_Realloc(void*, size_t)
    void PyMem_Free(void*)
cdef extern from "bufferobject.h":
    object PyBuffer_FromMemory(void *ptr, Py_ssize_t size)
    object PyBuffer_FromReadWriteMemory(void *ptr, Py_ssize_t size)
cdef extern from "./coio_c_fastsearch.h":  # Needed by stringlib/find.h
    # Similar to Objects/stringlib/find.h in the Python source.
    Py_ssize_t coio_stringlib_find(char_constp str, Py_ssize_t str_len,
                                   char_constp sub, Py_ssize_t sub_len,
                                   Py_ssize_t offset)
    Py_ssize_t coio_stringlib_rfind(char_constp str, Py_ssize_t str_len,
                                    char_constp sub, Py_ssize_t sub_len,
                                    Py_ssize_t offset)
cdef extern from "./coio_c_stackless.h":
    # cdef extern from "frameobject.h":  # Needed by core/stackless_structs.h
    # cdef extern from "core/stackless_structs.h":
    ctypedef struct PyTaskletObject
    # This is only for pointer manipulation with reference counting.
    ctypedef struct PyTaskletObject:
        PyTaskletObject *next
        PyTaskletObject *prev
        PyObject *tempval
    ctypedef class stackless.tasklet [object PyTaskletObject]:
        cdef object tempval
    ctypedef class stackless.bomb [object PyBombObject]:
        cdef object curexc_type
        cdef object curexc_value
        cdef object curexc_traceback
    #cdef extern from "stackless_api.h":
    object PyStackless_Schedule(object retval, int remove)
    int PyStackless_GetRunCount()
    # Return -1 on exception, 0 on OK.
    int PyTasklet_Insert(tasklet) except -1
    int PyTasklet_Remove(tasklet) except -1
    int PyTasklet_Kill(tasklet) except -1
    int PyTasklet_Alive(tasklet)
    tasklet PyStackless_GetCurrent()
    #tasklet PyTasklet_New(type type_type, object func);
    int PyTasklet_GetBlocked(tasklet task)
cdef extern from *:
    char *(*PyOS_ReadlineFunctionPointer)(FILE *, FILE *, char *)
cdef extern from "./coio_c_helper.h":
    struct _UncountedObject:
        pass
    ctypedef _UncountedObject UncountedObject
    struct socket_wakeup_info_s "coio_socket_wakeup_info":
        event_t read_ev
        event_t write_ev
        # -1.0 if None (infinite timeout).
        double timeout_value
        int fd
        # Corresponds to timeout (if not None).
        timeval tv
    struct oneway_wakeup_info_s "coio_oneway_wakeup_info":
        event_t ev
        # -1.0 if None (infinite timeout).
        double timeout_value
        int fd
        timeval tv
        # Exception class to raise on I/O error.
        UncountedObject *exc_class
        UncountedObject *sslobj
        event_t *other_ev

    # This involves a call to PyStackless_Schedule(None, 1).
    object coio_c_wait(event_t *ev, timeval *timeout)
    # A temporary event_t will be allocated, and its ev_arg would be set to
    # stackless.current.
    object coio_c_wait_for(int fd, short evtype, event_handler handler,
                           timeval *timeout)
    char coio_loaded()
    object coio_c_handle_eagain(socket_wakeup_info_s *swi, short evtype) 
    object coio_c_socket_call(object function, object args,
                              socket_wakeup_info_s *swi, short evtype)
    int coio_c_evbuffer_read(oneway_wakeup_info_s *owi, evbuffer_s *read_eb,
                             int n) except -1
    int coio_c_writeall(oneway_wakeup_info_s *owi, char_constp p,
                        Py_ssize_t n) except -1
    int c_SSL_ERROR_WANT_READ "coio_c_SSL_ERROR_WANT_READ"
    int c_SSL_ERROR_WANT_WITE "coio_c_SSL_ERROR_WANT_WRITE"
    int c_SSL_ERROR_EOF "coio_c_SSL_ERROR_EOF"
    void coio_c_nop()
    void coio_c_set_evlist_internal(event_t *ev)
    object coio_c_call_wrap_bomb(object function, object args, object kwargs,
                                 object bomb_class)
    object coio_c_ssl_call(object function, object args,
                           socket_wakeup_info_s *swi,
                           char do_handle_read_eof)

# --- Low-level event functions

def has_feature_may_loop_return_1():
    """Return true iff loop() may return 1."""
    return c_FEATURE_MAY_EVENT_LOOP_RETURN_1

def has_feature_multiple_events_on_same_fd():
    """Return true iff multiple events can be reliably registered on an fd."""
    return c_FEATURE_MULTIPLE_EVENTS_ON_SAME_FD

def version():
    return event_get_version()

def method():
    return event_get_method()

def reinit(int do_recreate=0):
    cdef int got
    if do_recreate:
        if sigint_ev.ev_flags:
            event_del(&sigint_ev)
            got = coio_event_reinit(1)
            if got >= 0:
                _setup_sigint()
        else:
            got = 0
    else:
        got = coio_event_reinit(0)
    if got < 0:
        raise OSError(EIO, 'event_reinit failed')

def nonblocking_loop_for_tests():
    """Run event_loop(EVLOOP_ONCE | EVLOOP_NONBLOCK).

    This method is intended to be used in tests to check that no events are
    registered.
    """
    cdef int got
    with nogil:
        got = event_loop(EVLOOP_ONCE | EVLOOP_NONBLOCK)
    return got

# --- Utility functions

import sys

# Maximum number of bytes that can be written to a pipe (or socket) without
# blocking if nobody is reading on the other end.
cdef int c_max_nonblocking_pipe_write_size
if sys.platform == 'linux2':
  c_max_nonblocking_pipe_write_size = 65536  # Measured maximum on Linux 2.6.34 i386 is 112448
else:
  c_max_nonblocking_pipe_write_size = 8192   # Measured maximum on Mac OS X 10.5.0 is 8192
max_nonblocking_pipe_write_size = c_max_nonblocking_pipe_write_size

cdef int connect_tv_magic_usec
connect_magic_usec = 120

cdef object c_errno_eagain "coio_c_errno_eagain"
cdef object c_strerror_eagain "coio_c_strerror_eagain"

c_errno_eagain = EAGAIN
c_strerror_eagain = strerror(EAGAIN)

def _schedule_helper():
  return PyStackless_GetCurrent().next.next.remove().run()


_schedule_helper_tasklet = stackless.tasklet(_schedule_helper)().remove()


def insert_after_current(next_tasklet):
  """Insert next_tasklet after stackless.current if possible."""
  # This is tricky, see the details in best_greenlet.py.
  # TODO(pts): Present this on the conference.
  if (next_tasklet and next_tasklet.alive and
      not next_tasklet.blocked and
      next_tasklet is not PyStackless_GetCurrent()):
    next_now = PyStackless_GetCurrent().next
    if next_now is next_tasklet:
      pass
    elif next_now is PyStackless_GetCurrent():
      next_tasklet.insert()
    else:
      # Magic to make next_tasklet the next tasklet after this
      # TaskletWrapper returns.
      next_tasklet.remove()
      _schedule_helper_tasklet.insert()
      next_tasklet.insert()
      _schedule_helper_tasklet.run()
      _schedule_helper_tasklet.remove()


def SendExceptionAndScheduleNext(tasklet tasklet_obj, exc_info):
    """Send exception to tasklet, even if it's blocked on a channel.

    To get the tasklet is activated (to handle the exception) after
    SendExceptionAndScheduleNext, just fall through to stackless.schedule()
    and stackless.schedule_remove().

    tasklet.insert() is called automatically to ensure that it eventually gets
    scheduled.
    """
    if not (isinstance(exc_info, list) or isinstance(exc_info, tuple)):
        raise TypeError
    if not exc_info:
        raise ValueError
    if tasklet_obj is PyStackless_GetCurrent():
        if len(exc_info) == 3:
            raise exc_info[0], exc_info[1], exc_info[2]
        elif len(exc_info) == 2:
            raise exc_info[0], exc_info[1], None
        else:
            raise exc_info[0], None, None
    bomb_obj = bomb(*exc_info)
    if tasklet_obj.blocked:
        c = tasklet_obj._channel
        old_preference = c.preference
        c.preference = 1    # Prefer the sender.
        # TODO(pts): Don't send to other tasklets (manipulate the
        # c.head and c.tail so that our tasklet becomes the first on the
        # channel)
        for i in xrange(-c.balance):
            c.send(bomb_obj)
        c.preference = old_preference
        assert not tasklet_obj.blocked
    else:
        tasklet_obj.tempval = bomb_obj
    insert_after_current(tasklet_obj)

cdef void set_fd_nonblocking(int fd):
    # This call works on Unix, but it's not portable (to e.g. Windows).
    # See also the #ifdefs in socketmodule.c:internal_setblocking().
    cdef int old
    # TODO(pts): Don't silently ignore the errors.
    old = fcntl2(fd, F_GETFL)
    if old >= 0 and not (old & O_NONBLOCK):
        fcntl3(fd, F_SETFL, old | O_NONBLOCK)

def set_fd_blocking(int fd, is_blocking):
    """Set a file descriptor blocking or non-blocking.

    Please note that this may affect more than expected, for example it may
    affect sys.stderr when called for sys.stdout.

    Returns:
      The old blocking value (True or False).
    """
    cdef int old
    cdef int value
    # TODO(pts): Don't silently ignore the errors.
    old = fcntl2(fd, F_GETFL)
    if old < 0:
        return
    if is_blocking:
        value = old & ~O_NONBLOCK
    else:
        value = old | O_NONBLOCK
    if old != value:
        fcntl3(fd, F_SETFL, value)
    return bool(old & O_NONBLOCK)

# --- The main loop

# Is the main loop waiting for events to happen, not continuing until at an
# event happens?
cdef char is_main_loop_waiting
is_main_loop_waiting = 0

def cancel_main_loop_wait():
    """Cancel the waiting for events to happen in the main loop."""
    if is_main_loop_waiting:
        kill(getpid(), SIGUSR2)

# A cdef wouldn't work here, because we call `stackless.tasklet(_main_loop)'.
def _main_loop():
    global is_main_loop_waiting
    #cdef PyTaskletObject *pprev
    #cdef PyTaskletObject *pnext
    cdef int loop_retval
    cdef PyTaskletObject *p
    cdef PyTaskletObject *m
    cdef tasklet tm
    tm = PyStackless_GetCurrent()
    m = <PyTaskletObject*>tm

    while 1:  # `while 1' is more efficient in Pyrex than `while True'
        # This runs 1 iteration of the libevent main loop: waiting for
        # I/O events and calling callbacks.
        #
        # Exceptions (if any) in event handlers would be printed to stderr
        # by libevent, and then ignored. This is OK for us since our event
        # handlers are very simple, don't contain user code, and normally don't
        # raise exceptions.
        #
        # Each callback we (nbevent.pxi)
        # have registered is just a tasklet_obj.insert(), but others may have
        # registered different callbacks.
        #
        # We compare against 2 because of stackless.current
        # (main_loop_tasklet) and link_helper_tasklet.
        if m.next != m:  # PyStackless_GetRunCount() > 1:
            p = m.prev
            # We must and do make sure that there are no non-local exits
            # (e.g. exceptions) until the corresponding Py_DECREF.
            Py_INCREF(<object>p)
            with nogil:
                event_loop(EVLOOP_ONCE | EVLOOP_NONBLOCK)
            if (p.next != NULL and
                not PyTasklet_GetBlocked(<tasklet>p) and
                p.next != m):
                # Move m (main_loop_tasklet) after p (last_tasklet).
                #
                # We do this so that the tasklets inserted by the loop(...)
                # call above are run first, preceding tasklets already
                # alive. This makes scheduling more fair on a busy server.
                m.prev.next = m.next
                m.next.prev = m.prev
                m.next = p.next
                m.prev = p
                p.next.prev = m
                p.next = m
            Py_DECREF(<object>p)
        else:
            # Block, wait for events once, without timeout.
            is_main_loop_waiting = 1
            with nogil:
                loop_retval = event_loop(EVLOOP_ONCE)
            is_main_loop_waiting = 0
            if loop_retval:
                # No events registered, and no tasklets in the queue. This
                # means that nothing more can happen in this program. By
                # returning here the stackless tasklet queue becomes empty,
                # so the process will exit (sys.exit(0)).
                #
                # !! SUXX: event_loop() of libev never returns true here.
                #
                # !! SUXX: there are registered events after an evdns lookup.
                return

        PyStackless_Schedule(None, 0)  # remove=0


# TODO(pts): Use a cdef, and hard-code event_add().
# !! TODO(pts): Schedule the main thread upon the SIGINT, don't wait for
# cooperative scheduling.
# TODO(pts): Rename all capitalized methods, e.g. to _sigint_handler.
def SigIntHandler():
    SendExceptionAndScheduleNext(stackless.main, (KeyboardInterrupt,))

cdef void HandleCSigInt(int fd, short evtype, void *arg) with gil:
    # Should an exception occur, Pyrex will print it to stderr, and ignore it.
    try:
       SigIntHandler()  # Print and ignore exceptions.
    except TaskletExit, e:
       pass

cdef void HandleCSigUsr1(int fd, short evtype, void *arg) with gil:
    # Should an exception occur, Pyrex will print it to stderr, and ignore it.
    from syncless import remote_console
    remote_console.ConsoleSignalHandler()

cdef event_t sigint_ev
sigint_ev.ev_flags = 0

cdef void _setup_sigint():
    event_set(&sigint_ev, SIGINT, c_EV_SIGNAL | c_EV_PERSIST,
              HandleCSigInt, NULL)
    # Make loop() exit immediately of only EVLIST_INTERNAL events
    # were added. Add EVLIST_INTERNAL after event_set.
    coio_c_set_evlist_internal(&sigint_ev)
    # This is needed so Ctrl-<C> raises (eventually, when the main_loop_tasklet
    # gets control) a KeyboardInterrupt in the main tasklet.
    event_add(&sigint_ev, NULL)


cdef event_t sigusr1_ev
sigusr1_ev.ev_flags = 0

# Set up a RemoteConsole activation handler for SIGUSR2. Please note that this
# is safe, because that RemoteConsole accepts connections only from the same
# UID on 127.0.0.1
cdef void _setup_sigusr1():
    event_set(&sigusr1_ev, SIGUSR1, c_EV_SIGNAL | c_EV_PERSIST,
              HandleCSigUsr1, NULL)
    coio_c_set_evlist_internal(&sigusr1_ev)
    event_add(&sigusr1_ev, NULL)

cdef event_t sigusr2_ev
sigusr2_ev.ev_flags = 0

# Set up a null handler for SIGUSR2.
cdef void _setup_sigusr2():
    event_set(&sigusr2_ev, SIGUSR2, c_EV_SIGNAL | c_EV_PERSIST,
              <event_handler>coio_c_nop, NULL)
    coio_c_set_evlist_internal(&sigusr2_ev)
    event_add(&sigusr2_ev, NULL)

# The token in waiting_tasklet.tempval to signify that the event-waiting is
# pending. This token is intentionally not exported to Python code, so they
# can't easily mess with it. (But they can still get it from a
# waiting_tasklet.tempval.)
#
# TODO(pts): doc:
# It is assumed that the user never sets a waiting_tasklet.tempval to
# waiting_token.
cdef object waiting_token "coio_waiting_token"
waiting_token = object()

# event_happened_token is the token in waiting_tasklet.tempval to signify
# that the event handler callback has been called. This token is
# intentionally not exported to Python code, so they can't easily mess with
# it. (But they can still get it from a waiting_tasklet.tempval.)
#
# TODO(pts): doc:
# It is assumed that the user never sets a waiting_tasklet.tempval to
# event_happened_token.
#
# TODO(pts): override str(coio_event_happened_token)
cdef object coio_event_happened_token "coio_event_happened_token"
coio_event_happened_token = object()
event_happened_token = coio_event_happened_token

# Since this function returns void, exceptions raised (e.g. if <tasklet>arg)
# will be ignored (by Pyrex?) and printed to stderr as something like:
# Exception AssertionError: 'foo' in 'coio.HandleCWakeup' ignored
cdef void HandleCWakeup(int fd, short evtype, void *arg) with gil:
    #os_write(2, <char_constp>'W', 1)
    if (<tasklet>arg).tempval is waiting_token:
        (<tasklet>arg).tempval = coio_event_happened_token
    PyTasklet_Insert(<tasklet>arg)

cdef void HandleCTimeoutWakeup(int fd, short evtype, void *arg) with gil:
    # PyStackless_Schedule will return tempval.
    # Writing <tasklet>arg will use arg as a tasklet without a NULL-check or a
    # type-check in Pyrex. This is what we want here.
    if (<tasklet>arg).tempval is waiting_token:
        if evtype == c_EV_TIMEOUT:
            (<tasklet>arg).tempval = None
        else:
            (<tasklet>arg).tempval = coio_event_happened_token
    PyTasklet_Insert(<tasklet>arg)

#cdef char *(*_orig_readline_pointer)(FILE *, FILE *, char *)
#
## Load readline in case we'll be running interactively. (Importing readline
## overrides PyOS_ReadlineFunctionPointer. Save the original
## readline pointer only after that.
#try:
#  __import__('readline')
#except ImportError, e:
#  pass
#_orig_readline_pointer = PyOS_ReadlineFunctionPointer
#
#cdef char *_interactive_readline(FILE *fin, FILE *fout, char *prompt):
#  fprintf(fout, <char_constp>"PROMPT(%s)\n", prompt)
#  # SUXX: this segfaults in PyStackless_GetCurrent() (not always properly
#  # initialized)
#  coio_c_wait_for(fileno(fin), c_EV_READ, HandleCWakeup, NULL)
#  # TODO(pts): Verify that fileno(fin) is actually readable now.
#  return _orig_readline_pointer(fin, fout, prompt)
#
#PyOS_ReadlineFunctionPointer = _interactive_readline

# --- nbfile

cdef enum dummy:
    DEFAULT_MIN_READ_BUFFER_SIZE  = 8192  # TODO(pts): Do speed tests.
    DEFAULT_WRITE_BUFFER_LIMIT = 8192  # TODO(pts): Do speed tests.

cdef class nbfile

# Read from nbfile at most limit characters.
#
# Precondition: limit > 0.
#
# TODO(pts): Rewrite this with brand new buffering.
cdef object nbfile_readline_with_limit(nbfile self, Py_ssize_t limit):
    cdef Py_ssize_t n
    cdef Py_ssize_t got
    cdef Py_ssize_t min_off
    cdef char_constp q
    cdef int fd
    cdef char had_short_read
    #DEBUG assert limit > 0
    fd = self.read_owi.fd
    had_short_read = 0
    min_off = 0
    if limit <= self.read_eb.off:  # All data already in buffer.
        q = <char_constp>memchr(<void_constp>self.read_eb.buf, c'\n', limit)
        if q != NULL:
            limit = q - <char_constp>self.read_eb.buf + 1
        buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, limit)
        evbuffer_drain(&self.read_eb, limit)
        return buf
    q = <char_constp>memchr(<void_constp>self.read_eb.buf, c'\n',
                            self.read_eb.off)
    while q == NULL:
        if had_short_read:
            evbuffer_expand(&self.read_eb, 1)
        elif self.read_eb.totallen == 0:
            evbuffer_expand(&self.read_eb, self.c_min_read_buffer_size)
        else:
            evbuffer_expand(&self.read_eb, self.read_eb.totallen >> 1)
        n = self.read_eb.totallen - self.read_eb.off - self.read_eb.misalign
        got = coio_c_evbuffer_read(&self.read_owi, &self.read_eb, n)
        if got == 0:  # EOF, return remaining bytes ('' or partial line)
            n = self.read_eb.off
            if limit < n:
                # TODO(pts): Cache EOF, don't coio_c_evbuffer_read(...) again.
                if limit == 0:
                    return ''
                n = limit
            buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
            evbuffer_drain(&self.read_eb, n)
            return buf
        if limit <= self.read_eb.off:  # All data already in buffer.
            q = <char_constp>memchr(<void_constp>self.read_eb.buf, c'\n', limit)
            if q != NULL:
                limit = q - <char_constp>self.read_eb.buf + 1
            buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, limit)
            evbuffer_drain(&self.read_eb, limit)
            return buf
        if got < n:
            # Most proably we'll get an EOF next time, so we shouldn't
            # pre-increase our buffer.
            had_short_read = 1
        q = <char_constp>memchr(<void_constp>(self.read_eb.buf + min_off),
                                c'\n', self.read_eb.off - min_off)
        min_off = self.read_eb.off
    n = q - <char_constp>self.read_eb.buf + 1
    buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
    evbuffer_drain(&self.read_eb, n)
    return buf

# Read from nbfile at most limit characters, strip '\r\n' and '\n' from the end,
# return None on EOF or on an incomplete line.
#
# Precondition: limit > 0.
#
# TODO(pts): Rewrite this with brand new buffering.
cdef object nbfile_readline_stripend_with_limit(nbfile self, Py_ssize_t limit, Py_ssize_t *delta_out):
    cdef Py_ssize_t n
    cdef Py_ssize_t got
    cdef Py_ssize_t min_off
    cdef char_constp q
    cdef int fd
    cdef char had_short_read
    #DEBUG assert limit > 0
    fd = self.read_owi.fd
    had_short_read = 0
    min_off = 0
    if limit <= self.read_eb.off:  # All data already in buffer.
        q = <char_constp>memchr(<void_constp>self.read_eb.buf, c'\n', limit)
        if q == NULL:
            return None
        limit = q - <char_constp>self.read_eb.buf
        delta_out[0] = limit
        got = limit - (limit > 0 and (<char*>self.read_eb.buf)[limit - 1] == c'\r')
        buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, got)
        evbuffer_drain(&self.read_eb, limit + 1)
        return buf
    q = <char_constp>memchr(<void_constp>self.read_eb.buf, c'\n',
                            self.read_eb.off)
    while q == NULL:
        if had_short_read:
            evbuffer_expand(&self.read_eb, 1)
        elif self.read_eb.totallen == 0:
            evbuffer_expand(&self.read_eb, self.c_min_read_buffer_size)
        else:
            evbuffer_expand(&self.read_eb, self.read_eb.totallen >> 1)
        n = self.read_eb.totallen - self.read_eb.off - self.read_eb.misalign
        got = coio_c_evbuffer_read(&self.read_owi, &self.read_eb, n)
        if got == 0:  # EOF, return remaining bytes ('' or partial line)
            n = self.read_eb.off
            if limit < n:
                # TODO(pts): Cache EOF, don't coio_c_evbuffer_read(...) again.
                if limit == 0:
                    delta_out[0] = 0
                    return None
                n = limit
            if n == 0:
                delta_out[0] = 0
                return None
            n -= 1
            delta_out[0] = n
            got = n - (n > 0 and (<char*>self.read_eb.buf)[n - 1] == c'\r')
            buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, got)
            evbuffer_drain(&self.read_eb, n + 1)
            return buf
        if limit <= self.read_eb.off:  # All data already in buffer.
            q = <char_constp>memchr(<void_constp>self.read_eb.buf, c'\n', limit)
            if q == NULL:
                delta_out[0] = 0
                return None
            limit = q - <char_constp>self.read_eb.buf
            delta_out[0] = limit
            got = limit - (limit > 0 and (<char*>self.read_eb.buf)[limit - 1] == c'\r')
            buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, got)
            evbuffer_drain(&self.read_eb, limit + 1)
            return buf
        if got < n:
            # Most proably we'll get an EOF next time, so we shouldn't
            # pre-increase our buffer.
            had_short_read = 1
        q = <char_constp>memchr(<void_constp>(self.read_eb.buf + min_off),
                                c'\n', self.read_eb.off - min_off)
        min_off = self.read_eb.off
    n = q - <char_constp>self.read_eb.buf
    delta_out[0] = n
    got = n - (n > 0 and (<char*>self.read_eb.buf)[n - 1] == c'\r')
    buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, got)
    evbuffer_drain(&self.read_eb, n + 1)
    return buf

cdef object nbfile_read(nbfile self, Py_ssize_t n):
    cdef Py_ssize_t got
    cdef object buf

    if n < 0:
        if self.read_eb.totallen == 0:
            evbuffer_expand(&self.read_eb,
                            self.c_min_read_buffer_size)
        while 1:
            # TODO(pts): Check out-of-memory error everywhere.
            evbuffer_expand(&self.read_eb, self.read_eb.totallen >> 1)
            got = coio_c_evbuffer_read(
                &self.read_owi, &self.read_eb,
                self.read_eb.totallen - self.read_eb.off -
                self.read_eb.misalign)
            if got == 0:  # EOF
                break
        buf = PyString_FromStringAndSize(
            <char_constp>self.read_eb.buf, self.read_eb.off)
        evbuffer_drain(&self.read_eb, self.read_eb.off)
        return buf
    if self.read_eb.off >= n:  # Satisfy read from read_eb.
        if n <= 0:
            return ''
        buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
        evbuffer_drain(&self.read_eb, n)
        return buf

    # TODO(pts): Speed if self.read_eb.off is at least half of the data
    # to be read, then pre-read it to a preallocated buf, and memcpy later.
    # This might not be a good idea if n as very large and most likely we
    # will be reading much less.

    while self.read_eb.off < n:  # Data not fully in the buffer.
        # !! Fill the buffer, it might be helpful.
        # !! Should we always pre-read?
        got = n - self.read_eb.off
        if got > 65536 and got > self.read_eb.totallen:
            # Limit the total number of bytes read to the double of the
            # read buffer size.
            # evbuffer_read() does someting similar, also involving
            # EVBUFFER_MAX_READ == 4096.
            # !! TODO(pts): Get rid of magic constant 65536.
            got = self.read_eb.totallen
        got = coio_c_evbuffer_read(&self.read_owi, &self.read_eb, got)
        if got == 0:  # EOF
            n = self.read_eb.off
            break
    buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
    evbuffer_drain(&self.read_eb, n)
    return buf

cdef Py_ssize_t nbfile_discard(nbfile self, Py_ssize_t n) except -1:
    if n <= 0:
        return 0
    if self.read_eb.off > 0:
        if self.read_eb.off >= n:
            evbuffer_drain(&self.read_eb, n)
            return 0
        evbuffer_drain(&self.read_eb, n)  # Discard everything.
        n -= self.read_eb.off
    while 1:  # n > 0
        got = n
        if self.read_eb.totallen == 0:
            # Expand to the next power of 2.
            evbuffer_expand(&self.read_eb, self.c_min_read_buffer_size)
        got = coio_c_evbuffer_read(&self.read_owi, &self.read_eb, got)
        if got == 0:  # EOF
            return n
        else:
            n -= got
            evbuffer_drain(&self.read_eb, got)
            if n == 0:
                return 0

# * limit is the maximum target number of bytes in the input buffer.
# * Returns the number of bytes read.
# * Raises EOFError on EOF.
cdef Py_ssize_t nbfile_read_more1(nbfile self, Py_ssize_t limit) except -1:
    cdef Py_ssize_t got
    cdef evbuffer_s *read_eb
    read_eb = &self.read_eb
    if limit <= read_eb.off:
        raise IndexError  # Request too long.
    else:
        if read_eb.totallen == 0:
            evbuffer_expand(read_eb, self.c_min_read_buffer_size)
        else:
            # This expands by at least read_eb.totallen if the buffer is
            # full (because evbuffer doubles its size at minimum).
            evbuffer_expand(read_eb, read_eb.totallen >> 1)
        got = read_eb.totallen - read_eb.off - read_eb.misalign
        if got > limit - read_eb.off:
            got = limit - read_eb.off
        got = coio_c_evbuffer_read(&self.read_owi, read_eb, got)
    if got == 0:  # EOF
        raise EOFError
    return got

# See the docstring of nbfile.read_http_reqhead for documenation.
cdef object nbfile_read_http_reqhead(nbfile self, Py_ssize_t limit):
    cdef evbuffer_s *read_eb
    cdef char c
    cdef Py_ssize_t i
    cdef Py_ssize_t j
    cdef Py_ssize_t k
    cdef object buf
    cdef char_constp p
    cdef char_constp q
    cdef list req_lines

    req_lines = []
    read_eb = &self.read_eb
    if read_eb.off == 0:
        nbfile_read_more1(self, limit)
    c = (<char*>read_eb.buf)[0]
    if c == c'\x80':
        return 'ssl', None, None, 'ssl', req_lines
    elif c == c'<':
        if limit > 32:
            limit = 32
        while 1:
            q = <char_constp>memchr(<void_constp>read_eb.buf, c'\0', read_eb.off)
            if q != NULL:
                break
            nbfile_read_more1(self, limit)
        if (read_eb.off >= 23 and
            0 == memcmp(<void_constp>read_eb.buf,
                        <void_constp><char*>'<policy-file-request/>\0', 23)):
            evbuffer_drain(read_eb, 23)
            return 'GET', 'policy-file', 'HTTP/1.0', 'policy-file', req_lines
        raise ValueError
    elif c < c'A' or c > c'Z':
        raise ValueError

    # Read and split the first line of the the HTTP request.
    while 1:
        q = <char_constp>memchr(<void_constp>read_eb.buf, c'\n', read_eb.off)
        if q != NULL:
            break
        nbfile_read_more1(self, limit)
    i = j = q - <char_constp>read_eb.buf
    if (<char*>q)[-1] == c'\r':
        j -= 1
    buf = PyString_FromStringAndSize(<char_constp>read_eb.buf, j)
    evbuffer_drain(read_eb, i + 1)
    limit -= i + 1
    # This raises a ValueError if there are too few items. Good.
    # TODO(pts): Use a Python API function for this.
    method, suburl, http_version = buf.split(' ', 2)

    # Read the request header lines (key--value pairs).
    # TODO(pts): Add support for HTTP/0.9.
    while 1:
        q = <char_constp>memchr(<void_constp>read_eb.buf, c'\n', read_eb.off)
        if q == NULL:
            nbfile_read_more1(self, limit)
        else:
            i = j = q - <char_constp>read_eb.buf
            if j > 0 and (<char*>q)[-1] == c'\r':
                j -= 1
            if j == 0:  # Received an empty line.
                evbuffer_drain(read_eb, i + 1)
                # limit -= i + 1  # Superfluous.
                break
            c = (<char*>read_eb.buf)[0]
            if <unsigned>c - c'a' <= <unsigned>c'z' - c'a':
                c -= 32  # Convert to upper case.
            if j < 5 or c < c'A' or c > c'Z':
                raise ValueError
            p = <char_constp>read_eb.buf
            q = <char_constp>memchr(<void_constp>p, c':', i)
            if q == NULL:
                raise ValueError
            while p != q:
                c = (<char*>p)[0]
                if c == c'-':
                    (<char*>p)[0] = c'_'
                elif <unsigned>c - c'a' <= <unsigned>c'z' - c'a':
                    (<char*>p)[0] -= 32  # Convert to upper case.
                elif (<unsigned>c - c'A' > <unsigned>c'Z' - c'A' and
                      <unsigned>c - c'0' > <unsigned>c'9' - c'0'):
                    raise ValueError
                p += 1
            p = <char_constp>read_eb.buf
            k = q - p
            q += 1
            if (<char*>q)[0] == c' ':
              q += 1
            j -= q - p
            req_lines.append((
                PyString_FromStringAndSize(<char_constp>read_eb.buf, k),
                PyString_FromStringAndSize(q, j)))
            evbuffer_drain(read_eb, i + 1)
            limit -= i + 1

    return method, suburl, http_version, None, req_lines
  

cdef class nbfile:
    """A non-blocking file (I/O channel).

    The filehandles are assumed to be non-blocking.

    Please note that nbfile supports line buffering (write_buffer_limit=1),
    but it doesn't set up write buffering by default for terminal devices.
    For that, please use our fdopen (defined below).

    Please note that changing self.write_buffer_limit doesn't flush the
    write buffer, but it will affect subsequent self.write(...) operations.

    Please don't subclass nbfile -- nblimitreader and maybe others won't
    work with subclasses.
    """
    # We must keep self.wakeup_ev on the heap, because
    # Stackless scheduling swaps the C stack.
    cdef object close_ref
    # We have different event buffers for reads and writes, because one tasklet
    # might be waiting for read, and another one waiting for write.
    cdef oneway_wakeup_info_s read_owi
    cdef oneway_wakeup_info_s write_owi
    # bufsize, buffer size, This must not be negative. Allowed values:
    # 0: (compatible with Python `file') no buffering, call write(2)
    #    immediately
    # 1: (compatible with Python `file', unimplemented) line buffering
    #    Just like Python `file', this setting flushes partial lines with >=
    #    DEFAULT_WRITE_BUFFER_LIMIT bytes long.
    # 2: infinite buffering, until an explicit flush
    # >=3: use the value for the buffer size in bytes
    cdef int c_write_buffer_limit
    cdef int c_min_read_buffer_size
    cdef evbuffer_s read_eb
    cdef evbuffer_s write_eb
    cdef char c_do_close
    cdef char c_closed
    cdef char c_softspace
    cdef object c_mode
    cdef object c_name
    cdef object sslobj

    def __init__(nbfile self, int read_fd, int write_fd,
                 int write_buffer_limit=-1, int min_read_buffer_size=-1,
                 char do_set_fd_nonblocking=1,
                 char do_close=0,
                 object close_ref=None, object mode='r+',
                 object name=None, object sslobj=None,
                 double timeout_double=-1.0):
        cdef event_handler wakeup_handler
        assert read_fd >= 0 or mode == 'w'
        assert write_fd >= 0 or mode == 'r'
        assert mode in ('r', 'w', 'r+')
        self.c_do_close = do_close
        self.read_owi.exc_class = <UncountedObject*>IOError
        self.write_owi.exc_class = <UncountedObject*>IOError
        self.read_owi.fd = read_fd
        self.write_owi.fd = write_fd
        if sslobj:
            self.sslobj = sslobj  # Just for the Py_INCREF(...).
            self.read_owi.sslobj = self.write_owi.sslobj = (
                <UncountedObject*>sslobj)
            self.read_owi.other_ev = &self.write_owi.ev
            self.write_owi.other_ev = &self.read_owi.ev
        else:
            self.sslobj = None
            self.read_owi.sslobj = self.write_owi.sslobj = NULL
        if timeout_double < 0.0:
            self.read_owi.timeout_value = self.write_owi.timeout_value = -1.0
            wakeup_handler = HandleCWakeup
        elif timeout_double == 0.0:
            wakeup_handler = HandleCTimeoutWakeup
            self.read_owi.timeout_value = self.write_owi.timeout_value = 0.0
            self.read_owi.tv.tv_sec = 0
            self.read_owi.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            self.write_owi.tv = self.read_owi.tv
        else:
            wakeup_handler = HandleCTimeoutWakeup
            self.read_owi.timeout_value = self.write_owi.timeout_value = (
                timeout_double)
            self.read_owi.tv.tv_sec = <long>timeout_double
            self.read_owi.tv.tv_usec = <unsigned int>(
                (timeout_double - <double>self.read_owi.tv.tv_sec) * 1000000.0)
            self.write_owi.tv = self.read_owi.tv

        if do_set_fd_nonblocking:
            if read_fd >= 0:
                set_fd_nonblocking(read_fd)
            if write_fd >=0 and write_fd != read_fd:
                set_fd_nonblocking(write_fd)
        if write_buffer_limit < 0:  # -1
            self.c_write_buffer_limit = DEFAULT_WRITE_BUFFER_LIMIT
        else:
            self.c_write_buffer_limit = write_buffer_limit
        if min_read_buffer_size < 3:  # -1, 0, 1, 2
            self.c_min_read_buffer_size = DEFAULT_MIN_READ_BUFFER_SIZE
        else:
            self.c_min_read_buffer_size = min_read_buffer_size
        self.close_ref = close_ref
        self.c_mode = mode
        self.c_name = name
        # evbuffer_new() clears the memory area of the object with zeroes,
        # but Pyrex (and __cinit__) ensure that happens, so we don't have to
        # do that.
        if read_fd >= 0:
            event_set(&self.read_owi.ev, read_fd, c_EV_READ,
                      wakeup_handler, NULL)
        if write_fd >= 0:
            event_set(&self.write_owi.ev, write_fd, c_EV_WRITE,
                      wakeup_handler, NULL)

    property timeout:
        """Return a nonnegative double, or None if there is no timeout.

        socket._realsocket has a read-only .timeout, socket.socket doesn't
        have an attribute named timeout.
        """
        def __get__(self):
            if self.read_owi.timeout_value < 0:
                return None
            else:
                return self.read_owi.timeout_value

    def settimeout(nbfile self, timeout):
        cdef double timeout_double
        if timeout is None:
            # SUXX: Pyrex or Cython wouldn't catch the type error if we had
            # None instead of -1.0 here.
            self.read_owi.timeout_value = self.write_owi.timeout_value = -1.0
            self.read_owi.ev.ev_callback = self.write_owi.ev.ev_callback = (
                HandleCWakeup)
        else:
            timeout_double = timeout
            if timeout_double < 0.0:
                raise ValueError('Timeout value out of range')
            self.read_owi.timeout_value = self.write_owi.timeout_value = (
                timeout_double)
            if timeout_double == 0.0:
                self.read_owi.tv.tv_sec = 0
                self.read_owi.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            else:
                self.read_owi.tv.tv_sec = <long>timeout_double
                self.read_owi.tv.tv_usec = <unsigned int>(
                    (timeout_double - <double>self.read_owi.tv.tv_sec) * 1000000.0)
            self.write_owi.tv = self.read_owi.tv
            self.read_owi.ev.ev_callback = self.write_owi.ev.ev_callback = (
                HandleCTimeoutWakeup)

    def fileno(nbfile self):
        if self.read_owi.fd >= 0:
            return self.read_owi.fd
        else:
            return self.write_owi.fd

    # This method is not present in standard file.
    def write_fileno(nbfile self):
        return self.write_owi.fd

    # !! TODO: SUXX: __dealloc__ is not allowed to call close() or flush()
    #          (too late, see Pyrex docs), __del__ is not special
    def __dealloc__(nbfile self):
        self.close()

    def forget_write_fd(nbfile self):
       """Return and forget the write file descriptor."""
       cdef int retval
       retval = self.write_owi.fd
       self.write_owi.fd = -1
       return retval

    def close(nbfile self):
        cdef int got
        self.sslobj = None
        try:
            if self.write_eb.off > 0:
                # This can raise self.write_owi.exc_class.
                self.flush()
        finally:
            evbuffer_reset(&self.read_eb)  # Also free the allocated buffer.
            evbuffer_reset(&self.write_eb)
            if not self.c_closed:
                self.c_closed = 1
                if self.c_do_close:
                    if self.close_ref is None:
                        if self.read_owi.fd >= 0:
                            got = close(self.read_owi.fd)
                            if got < 0:
                                exc = (<object>self.write_owi.exc_class)(errno, strerror(errno))
                                close(self.write_owi.fd)
                                raise exc
                        if (self.read_owi.fd != self.write_owi.fd and
                            self.write_owi.fd > 0):
                            got = close(self.write_owi.fd)
                            if got < 0:
                                raise (<object>self.write_owi.exc_class)(errno, strerror(errno))
                    else:
                        close_ref = self.close_ref
                        self.close_ref = False
                        if close_ref is not False:
                            return close_ref.close()

    property closed:
        def __get__(nbfile self):
            if self.c_closed:
                return True
            else:
                return False

    # This is not a standard property of `file'.
    property do_close:
        def __get__(nbfile self):
            return self.c_do_close

    property read_exc_class:
        def __get__(nbfile self):
            return <object>self.read_owi.exc_class
        def __set__(nbfile self, object new_value):
            if not issubclass(new_value, BaseException):
              raise TypeError
            # No need for reference counting, new_value (as a class) has
            # references anyway.
            self.read_owi.exc_class = <UncountedObject*>new_value

    property write_exc_class:
        def __get__(nbfile self):
            return <object>self.write_owi.exc_class
        def __set__(nbfile self, object new_value):
            if not issubclass(new_value, BaseException):
              raise TypeError
            self.write_owi.exc_class = <UncountedObject*>new_value

    property mode:
        def __get__(nbfile self):
            return self.c_mode

    property name:
        def __get__(nbfile self):
            return self.c_name

    # file.softspace is used by `print'.
    property softspace:
        def __get__(nbfile self):
            return self.c_softspace
        def __set__(nbfile self, char softspace):
            self.c_softspace = softspace

    # Simplification over `file'.
    property encoding:
        def __get__(nbfile self):
            return None

    # Simplification over `file'.
    property newlines:
        def __get__(nbfile self):
            return None

    # Unicode error handler. Simplification over `file'.
    property errors:
        def __get__(nbfile self):
            return None

    def unread(nbfile self, object buf):
        """Push back some data to beginning of the read buffer.

        There is no such Python `file' method (file.unread).

        Please note that this can be slow (quadratic) if the same amount
        (or a bit more) has not been read recently.
        """
        cdef char_constp p
        cdef Py_ssize_t n
        cdef evbuffer_s *read_eb
        PyObject_AsCharBuffer(buf, &p, &n)
        if n <= 0:
            return
        read_eb = &self.read_eb
        if read_eb.off == 0:
            evbuffer_add(read_eb, <void_constp>p, n)
        elif read_eb.misalign >= n:
            read_eb.misalign -= n
            read_eb.buf -= n
            read_eb.off += n
            memcpy(read_eb.buf, <void_constp>p, n)
            # We don't call callbacks.
        else:
            # The slow (quadratic) path.
            evbuffer_expand(read_eb, n)
            memmove(read_eb.buf + n, <void_constp>read_eb.buf, read_eb.off)
            memcpy(read_eb.buf, <void_constp>p, n)
            read_eb.off += n
            # We don't call callbacks.

    def unread_append(nbfile self, object buf):
        """Push back some data to end of the read buffer.

        There is no such Python `file' method (file.unread_buffer).

        Please note that this call is always linear.
        """
        cdef char_constp p
        cdef Py_ssize_t n
        PyObject_AsCharBuffer(buf, &p, &n)
        if n > 0:
            evbuffer_add(&self.read_eb, <void_constp>p, n)

    def write(nbfile self, object buf):
        # TODO(pts): Flush the buffer eventually automatically.
        cdef char_constp p
        cdef Py_ssize_t k
        cdef Py_ssize_t n
        cdef int wlimit
        cdef int keepc
        PyObject_AsCharBuffer(buf, &p, &n)
        if n <= 0:
            return
        wlimit = self.c_write_buffer_limit
        # Adding write_eb as a local variable here wouldn't make it any
        # faster.
        if wlimit == 2:  # Infinite write buffer.
            evbuffer_add(&self.write_eb, <void_constp>p, n)
            return
        if wlimit == 0 and self.write_eb.off == 0:
            # Direct output without buffering. We check for the empty buffer
            # above so we wouldn't take this shortcut if the buffer wasn't
            # empty.
            # TODO(pts): Use the socket timeout.
            coio_c_writeall(&self.write_owi, p, n)
            return
        if wlimit == 1:  # Line buffering.
            k = n
            while k > 0 and (<char*>p)[k - 1] != c'\n':
                k -= 1
            if k == 0:  # No newline yet, so add the whole p to write_eb.
                evbuffer_expand(&self.write_eb, self.c_min_read_buffer_size)
                evbuffer_add(&self.write_eb, <void_constp>p, n)
                return
            keepc = n - k
            n = k
            # We can flush everything up to p[:n].

            k = self.write_eb.totallen - (
                self.write_eb.off + self.write_eb.misalign)
            if k > n:  # Buffer not full yet.
                evbuffer_add(&self.write_eb, <void_constp>p, n)
                coio_c_writeall(&self.write_owi,
                                <char_constp>self.write_eb.buf,
                                self.write_eb.off)
                self.write_eb.buf = self.write_eb.orig_buffer
                self.write_eb.misalign = 0
                self.write_eb.off = 0
            else:
                if self.write_eb.off > 0:
                    # Flush self.write_eb.
                    coio_c_writeall(&self.write_owi,
                                    <char_constp>self.write_eb.buf,
                                    self.write_eb.off)
                    self.write_eb.buf = self.write_eb.orig_buffer
                    self.write_eb.misalign = 0
                    self.write_eb.off = 0
                # Flush lines directly from the argument.
                coio_c_writeall(&self.write_owi, p, n)
            if keepc > 0:
                p += n
                if self.write_eb.totallen == 0:
                    # Use the read buffer size as an approximation for the
                    # write buffer size.
                    evbuffer_expand(&self.write_eb,
                                    self.c_min_read_buffer_size)
                evbuffer_add(&self.write_eb, <void_constp>p, keepc)
        else:  # Non-line buffering.
            if self.write_eb.off != 0:  # Expand and flush if not empty.
                if self.write_eb.totallen == 0:
                    evbuffer_expand(&self.write_eb, wlimit)
                k = self.write_eb.totallen - (
                    self.write_eb.off + self.write_eb.misalign)
                if k > n:  # Buffer not full yet.
                    evbuffer_add(&self.write_eb, <void_constp>p, n)
                    return
                evbuffer_add(&self.write_eb, <void_constp>p, k)
                p += k
                n -= k

                # Flush self.write_eb.
                # TODO(pts): Speed: return early even if coio_c_writeall
                # couldn't write everything yet (EAGAIN). Do this everywhere.
                coio_c_writeall(&self.write_owi,
                                <char_constp>self.write_eb.buf,
                                self.write_eb.off)
                self.write_eb.buf = self.write_eb.orig_buffer
                self.write_eb.misalign = 0
                self.write_eb.off = 0

            if n >= wlimit:
                # Flush directly from the argument.
                coio_c_writeall(&self.write_owi, p, n)
            else:
                if self.write_eb.totallen == 0:
                    evbuffer_expand(&self.write_eb, wlimit)
                evbuffer_add(&self.write_eb, <void_constp>p, n)

    def flush(nbfile self):
        # Please note that this method may raise an error even if parts of the
        # buffer has been flushed.
        if self.write_eb.off > 0:
            coio_c_writeall(&self.write_owi,
                            <char_constp>self.write_eb.buf, self.write_eb.off)
            self.write_eb.buf = self.write_eb.orig_buffer
            self.write_eb.misalign = 0
            self.write_eb.off = 0

    property read_buffer_len:
        def __get__(nbfile self):
            return self.read_eb.off

    property read_buffer_misalign:
        def __get__(nbfile self):
            return self.read_eb.misalign

    property read_buffer_totallen:
        def __get__(nbfile self):
            return self.read_eb.totallen

    property write_buffer_len:
        def __get__(nbfile self):
            return self.write_eb.off

    property write_buffer_limit:
        """Setting the write_buffer_limit doesn't call flush()."""
        def __get__(nbfile self):
            return self.c_write_buffer_limit
        def __set__(nbfile self, int new_limit):
            if new_limit < 0:
                self.c_write_buffer_limit = DEFAULT_WRITE_BUFFER_LIMIT
            else:
                self.c_write_buffer_limit = new_limit

    def discard_write_buffer(nbfile self):
        evbuffer_drain(&self.write_eb, self.write_eb.off)

    def discard(nbfile self, n):
        """Read and discard exactly n bytes.

        Please note that self.read_owi.fd won't be read past the n bytes specified.
        TODO(pts): Add an option to speed up HTTP keep-alives by batching
        multiple read requests.

        Args:
          n: Number of bytes to discard. Negative values are treated as 0.
        Returns:
          The number of bytes not discarded because of EOF.
        Raises:
          self.c_read_exc_cass or IOError: (but not EOFError)
        """
        return nbfile_discard(self, n)

    def wait_for_readable(nbfile self, object timeout=None):
        cdef event_t *wakeup_ev_ptr
        cdef timeval tv
        cdef double timeout_double
        # !! TODO(pts): Speed: return early if already readable.
        if timeout is None:
            return (coio_c_wait(&self.read_owi.ev, NULL)
                    is coio_event_happened_token)
        else:
            timeout_double = timeout
            if timeout_double < 0.0:
                raise ValueError('Timeout value out of range')
            if timeout_double == 0.0:
                tv.tv_sec = 0
                tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            else:
                tv.tv_sec = <long>timeout_double
                tv.tv_usec = <unsigned int>(
                    (timeout_double - <double>tv.tv_sec) * 1000000.0)
            return coio_c_wait_for(
                self.read_owi.fd, c_EV_READ, HandleCTimeoutWakeup, &tv
                ) is coio_event_happened_token

    def read(nbfile self, n=-1):
        """Read exactly n bytes (or less on EOF), and return string

        Args:
          n: Number of bytes to read. Negative values mean: read up to EOF.
        Returns:
          String containing the bytes read; an empty string on EOF.
        Raises:
          self.read_owi.exc_class or IOError: (but not EOFError)
        """
        return nbfile_read(self, n)

    def read_http_reqhead(nbfile self, limit):
        """Read a HTTP request headers (and the first line).

        HTTP/0.9 requests will be rejected with a ValueError.

        Please note that this method is not a validating parser. The caller
        is encouraged to do some additional consistency checks after this
        method returns.

        Returns:
          ('GET', 'policy-file', 'HTTP/1.0', 'policy-file', [])  or
          ('ssl', None, None, 'ssl', [])  or
          (method, suburl, http_version, None, req_lines).
          Here req_lines is a list of HTTP request header (name_upper,
          value) pairs, where '-' is replaced by '_', and letters converted
          to upper case in name_upper.
        Raises:
          EOFError: If an EOF was found before the end of the request.
          IndexError: If the request was too long.
          ValueError: On a request parse error.
          IOError: On any other I/O error.
        """
        return nbfile_read_http_reqhead(self, limit)

    def read_at_most(nbfile self, int n):
        """Read at most n bytes and return the string.

        Negative values for n are not allowed.

        If the read buffer is not empty (self.read_buffer_len), data inside it
        will be returned, and no attempt is done to read self.read_owi.fd.
        """
        cdef int got
        if n <= 0:
            if n < 0:
                raise ValueError
            return ''
        if self.read_eb.off > 0:
            if self.read_eb.off < n:
                n = self.read_eb.off
            buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
            evbuffer_drain(&self.read_eb, n)
            # TODO(pts): Maybe read more from fd, if available and flag.
            return buf
        while 1:
            # TODO(pts): Don't read it to the buffer, read without memcpy.
            #            We'd need the readinto method for that.
            got = coio_c_evbuffer_read(&self.read_owi, &self.read_eb, n)
            if got == 0:
                return ''
            else:
                buf = PyString_FromStringAndSize(
                    <char_constp>self.read_eb.buf, got)
                evbuffer_drain(&self.read_eb, got)
                return buf

    def read_upto(nbfile self, n):
        """Read so that read buffer is >= n bytes long, return new size.

        There is no such Python `file' method (file.read_upto).

        Args:
          n: The minimum number of bytes the read buffer should contain when
            this method returns. Negative values are treated as zero.
        Returns:
          The resulting number of bytes in the read buffer. It can be less
          than n iff EOF was reached.
        """
        cdef Py_ssize_t c_n
        cdef Py_ssize_t got
        c_n = n
        while c_n > <Py_ssize_t>self.read_eb.off:  # Works also for negative values of n.
            if self.read_eb.totallen == 0:
                evbuffer_expand(&self.read_eb,
                                self.c_min_read_buffer_size)
            else:
                # This expands by at least read_eb.totallen if the buffer is
                # full (because evbuffer doubles its size at minimum).
                evbuffer_expand(&self.read_eb, self.read_eb.totallen >> 1)
            got = coio_c_evbuffer_read(
                &self.read_owi, &self.read_eb,
                self.read_eb.totallen - self.read_eb.off -
                self.read_eb.misalign)
            if got == 0:  # EOF
                break
        return self.read_eb.off

    def read_more(nbfile self, n):
        """Read to buffer at least n more bytes, return number of bytes read.

        There is no such Python `file' method (file.read_more).
        """
        cdef Py_ssize_t c_n
        cdef Py_ssize_t got
        cdef Py_ssize_t c_n0
        c_n = n
        c_n0 = c_n
        while c_n > 0:  # Works also for negative values of n.
            if self.read_eb.totallen == 0:
                evbuffer_expand(&self.read_eb,
                                self.c_min_read_buffer_size)
            else:
                # This expands by at least read_eb.totallen if the buffer is
                # full (because evbuffer doubles its size at minimum).
                evbuffer_expand(&self.read_eb, self.read_eb.totallen >> 1)
            got = coio_c_evbuffer_read(
                &self.read_owi, &self.read_eb,
                self.read_eb.totallen - self.read_eb.off -
                self.read_eb.misalign)
            if got == 0:  # EOF
                break
            else:
                c_n -= got
        return c_n0 - c_n

    def find(nbfile self, substring, start_idx=0, end_idx=None):
        """Find the first occurrence of substring in read buffer.

        There is no such Python `file' method (file.find).

        start_idx is used just like in string.find. end_idx is to ignore
        everything from that index in the read buffer.

        For a regular expression search, please use
        re.search(r'...', nbfile_obj.get_read_buffer()).

        Returns:
          -1 if not found, or the start offset where it was found.
        """
        cdef Py_ssize_t c_start_idx
        cdef Py_ssize_t c_end_idx
        cdef char_constp sbuf
        cdef Py_ssize_t slen
        PyObject_AsCharBuffer(substring, &sbuf, &slen)
        if end_idx is None:
            c_end_idx = self.read_eb.off
        else:
            c_end_idx = end_idx
            if c_end_idx < 0:
                c_end_idx += self.read_eb.off
                if c_end_idx < 0:
                    c_end_idx = 0
            elif c_end_idx > self.read_eb.off:
                c_end_idx = self.read_eb.off
        c_start_idx = start_idx
        if c_start_idx < 0:
            c_start_idx += self.read_eb.off
            if c_start_idx < 0:
                c_start_idx = 0
        if c_start_idx > c_end_idx:
            return -1
        return coio_stringlib_find(
            <char_constp>self.read_eb.buf + c_start_idx,
            c_end_idx - c_start_idx, sbuf, slen, c_start_idx)

    def rfind(nbfile self, substring, start_idx=0, end_idx=None):
        """Find the last occurrence of substring in read buffer.

        There is no such Python `file' method (file.rfind).

        start_idx is used just like in string.rfind. end_idx is to ignore
        everything from that index in the read buffer.

        Returns:
          -1 if not found, or the start offset where it was found.
        """
        cdef Py_ssize_t c_start_idx
        cdef Py_ssize_t c_end_idx
        cdef char_constp sbuf
        cdef Py_ssize_t slen
        PyObject_AsCharBuffer(substring, &sbuf, &slen)
        if end_idx is None:
            c_end_idx = self.read_eb.off
        else:
            c_end_idx = end_idx
            if c_end_idx < 0:
                c_end_idx += self.read_eb.off
                if c_end_idx < 0:
                    c_end_idx = 0
            elif c_end_idx > self.read_eb.off:
                c_end_idx = self.read_eb.off
        c_start_idx = start_idx
        if c_start_idx < 0:
            c_start_idx += self.read_eb.off
            if c_start_idx < 0:
                c_start_idx = 0
        if c_start_idx > c_end_idx:
            return -1
        return coio_stringlib_rfind(
            <char_constp>self.read_eb.buf + c_start_idx,
            c_end_idx - c_start_idx, sbuf, slen, c_start_idx)

    def get_string(nbfile self, start_idx=0, end_idx=None):
        """Get string from read buffer.

        There is no such Python `file' method (file.get_string).
        """
        cdef Py_ssize_t c_start_idx
        cdef Py_ssize_t c_end_idx
        if end_idx is None:
            c_end_idx = self.read_eb.off
        else:
            c_end_idx = end_idx
            if c_end_idx < 0:
                c_end_idx += self.read_eb.off
                if c_end_idx < 0:
                    c_end_idx = 0
            elif c_end_idx > self.read_eb.off:
                c_end_idx = self.read_eb.off
        c_start_idx = start_idx
        if c_start_idx < 0:
            c_start_idx += self.read_eb.off
            if c_start_idx < 0:
                c_start_idx = 0
        if c_start_idx >= c_end_idx:
            return ''
        return PyString_FromStringAndSize(
            <char_constp>self.read_eb.buf + c_start_idx,
            c_end_idx - c_start_idx)

    def get_read_buffer(nbfile self, start_idx=0, end_idx=None):
        """Get read-write buffer object pointing to our read buffer.

        There is no such Python `file' method (file.get_read_buffer).

        Please note that the returned buffer points to a valid memory
        location until this nbfile gets closed or a read or discard
        operation is performed on it. If you attempt to use returned buffer
        after that, you may find garbage inside, or you may get a Segmentation
        fault for an invalid read.
        """
        cdef Py_ssize_t c_start_idx
        cdef Py_ssize_t c_end_idx
        if end_idx is None:
            c_end_idx = self.read_eb.off
        else:
            c_end_idx = end_idx
            if c_end_idx < 0:
                c_end_idx += self.read_eb.off
                if c_end_idx < 0:
                    c_end_idx = 0
            elif c_end_idx > self.read_eb.off:
                c_end_idx = self.read_eb.off
        c_start_idx = start_idx
        if c_start_idx < 0:
            c_start_idx += self.read_eb.off
            if c_start_idx < 0:
                c_start_idx = 0
        if c_start_idx >= c_end_idx:
            return PyBuffer_FromReadWriteMemory(NULL, 0)
        return PyBuffer_FromReadWriteMemory(
             <void*>(self.read_eb.buf + c_start_idx),
             c_end_idx - c_start_idx)

    def readline(nbfile self, int limit=-1):
        # TODO(pts): Add a read limit for the line length.
        # TODO(pts): Implement helper method for reading a HTTP request.
        # TODO(pts): Make this just as fast as Python's file() object
        #            (which always reads 8192 bytes).
        #  fd = os.open('kjv.rawtxt', os.O_RDONLY)
        #  # 100 iterations real    0m1.561s; user    0m1.300s; sys     0m0.260s
        #  return syncless.coio.nbfile(fd, -1, 8192, 8192, mode='r', do_close=True)
        #  # 100 iterations real    0m1.510s; user    0m1.260s;  sys     0m0.248s
        #  return syncless.coio.nbfile(fd, -1, 16384, 16384, mode='r', do_close=True)
        #  # 100 iterations real    0m1.074s; user    0m0.892s; sys     0m0.172s
        #  #return os.fdopen(fd, 'r', 8192)
        cdef int n
        cdef int got
        cdef int min_off
        cdef char_constp q
        cdef int fd
        cdef evbuffer_s *read_eb
        cdef int had_short_read
        read_eb = &self.read_eb
        fd = self.read_owi.fd
        had_short_read = 0
        min_off = 0
        if limit >= 0:
            if limit == 0:
                return ''
            return nbfile_readline_with_limit(self, limit)
        #DEBUG assert limit < 0
        q = <char_constp>memchr(<void_constp>read_eb.buf, c'\n', read_eb.off)
        while q == NULL:
            if had_short_read:
                evbuffer_expand(read_eb, 1)
            elif read_eb.totallen == 0:
                evbuffer_expand(read_eb, self.c_min_read_buffer_size)
            else:
                evbuffer_expand(read_eb, read_eb.totallen >> 1)
            n = read_eb.totallen - read_eb.off - read_eb.misalign

            got = coio_c_evbuffer_read(&self.read_owi, &self.read_eb, n)
            if got == 0:  # EOF, return remaining bytes ('' or partial line)
                n = read_eb.off
                buf = PyString_FromStringAndSize(<char_constp>read_eb.buf, n)
                evbuffer_drain(read_eb, n)
                return buf
            else:
                if got < n:
                    # Most proably we'll get an EOF next time, so we shouldn't
                    # pre-increase our buffer.
                    had_short_read = 1
                q = <char_constp>memchr(<void_constp>(read_eb.buf + min_off),
                                        c'\n', read_eb.off - min_off)
                min_off = read_eb.off
        n = q - <char_constp>read_eb.buf + 1
        buf = PyString_FromStringAndSize(<char_constp>read_eb.buf, n)
        evbuffer_drain(read_eb, n)
        return buf

    def __next__(nbfile self):
        line = self.readline()
        if line:
            return line
        raise StopIteration

    def __iter__(nbfile self):
        # We have to use __builtins__.iter because Pyrex expects 1 argument for
        # iter(...).
        #return __builtin__.iter(self.readline, '')
        return self

    def xreadlines(nbfile self):
        return self  # Just like file.xreadlines

    def readlines(nbfile self):
        cdef list lines
        lines = []
        while 1:
            line = self.readline()
            if not line:
                break
            lines.append(line)
        return lines

    def writelines(nbfile self, lines):
       for line in lines:
           self.write(line)

    def isatty(nbfile self):
        cdef int got
        got = isatty(self.read_owi.fd)
        if got < 0:
            raise (<object>self.read_owi.exc_class)(errno, strerror(errno))
        elif got:
            return True
        else:
            return False

    def truncate(nbfile self, int size):
        # TODO(pts): Do we need this? It won't work for streams (like seek, tell)
        if ftruncate(self.read_owi.fd, size) < 0:
            raise (<object>self.write_owi.exc_class)(errno, strerror(errno))

# --- nblimitreader

cdef class nblimitreader:
    """Class reading from an nbfile, limiting it at the specified position."""

    cdef nbfile f
    cdef Py_ssize_t limit

    def __init__(nblimitreader self, nbfile f, limit):
        self.limit = limit
        assert self.limit >= 0, 'positive limit expected, got %s' % self.limit
        if self.limit == 0:
          self.f = None
        else:
          self.f = f

    def __len__(nblimitreader self):
        return self.limit

    def read(nblimitreader self, size=-1):
        cdef object buf
        cdef Py_ssize_t c_size
        c_size = size
        if c_size > self.limit or c_size < 0:
            c_size = self.limit
        if c_size == 0:
            return ''
        buf = nbfile_read(self.f, c_size)
        c_size = len(buf)
        if c_size > 0:
            self.limit -= c_size
        else:
            self.limit = 0
            self.f = None
        return buf

    def readline(nblimitreader self):
        cdef object buf
        cdef Py_ssize_t size
        if self.limit == 0:
            return ''
        buf = nbfile_readline_with_limit(self.f, self.limit)
        size = len(buf)
        if size > 0:
            self.limit -= size
            if self.limit == 0:
                self.f = None
        else:
            self.limit = 0
            self.f = None
        return buf

    def readline_stripend(nblimitreader self):
        """Read line, strip '\\r\\n' or '\\n' from the end.

        Returns:
          The line read, with '\\r\\n' or '\\n' stripped, or None on EOF or
          on an incomplete line before EOF.
        """
        cdef object buf
        cdef Py_ssize_t size
        cdef Py_ssize_t delta
        if self.limit == 0:
            return ''
        delta = 0
        buf = nbfile_readline_stripend_with_limit(self.f, self.limit, &delta)
        if buf:
            self.limit -= delta
            if self.limit == 0:
                self.f = None
        else:
            self.limit = 0
            self.f = None
        return buf

    def readlines(nblimitreader self, hint=None):
        cdef list retval
        cdef object buf
        cdef Py_ssize_t size
        retval = []
        while self.limit > 0:
          buf = nbfile_readline_with_limit(self.f, self.limit)
          size = len(buf)
          if size > 0:
              self.limit -= size
              retval.append(buf)
          else:
              self.limit = 0
              self.f = None
        return retval

    def __next__(nblimitreader self):
        cdef object buf
        cdef Py_ssize_t size
        if self.limit == 0:
            raise StopIteration
        buf = nbfile_readline_with_limit(self.f, self.limit)
        size = len(buf)
        if size > 0:
            self.limit -= size
            return buf
        else:
            self.limit = 0
            self.f = None
            raise StopIteration

    def __iter__(nblimitreader self):
        return self

    def discard_to_read_limit(nblimitreader self):
        cdef Py_ssize_t size
        if self.limit != 0:
            self.limit = nbfile_discard(self.f, self.limit)
            if self.limit == 0:
                self.f = None
        return self.limit

# ---

# !! implement open(...) properly, with modes etc.
# !! prevent writing to a nonwritable file
# !! implement readinto()
# !! implement seek() and tell()

# Copy early to avoid infinite recursion.
os_popen = os.popen

def popen(command, mode='r', int bufsize=-1):
    """Non-blocking drop-in replacement for os.popen."""
    mode = mode.replace('b', '')
    f = os_popen(command, mode, 0)
    fd = f.fileno()
    return nbfile(fd, fd, mode=mode, write_buffer_limit=bufsize, do_close=True,
                  close_ref=f)

def fdopen(int fd, mode='r', int bufsize=-1,
           write_buffer_limit=-1, char do_close=1, object name=None):
    """Non-blocking drop-in replacement for os.fdopen."""
    cdef int read_fd
    cdef int write_fd
    assert fd >= 0
    read_fd = fd
    write_fd = fd
    mode = mode.replace('b', '')  # Handle mode='rb' etc.
    # TODO(pts): Handle mode='rb' etc.
    if mode == 'r':
        write_fd = -1
    elif mode == 'w':
        read_fd = -1
    elif mode == 'r+':
         pass
    else:
         assert 0, 'bad mode: %r' % mode
    if write_buffer_limit < 0:  # Set default from bufsize.
        write_buffer_limit = bufsize
    if write_fd >= 0 and write_buffer_limit == -1 and isatty(write_fd) > 0:
        # Enable line buffering for terminal output. This is what
        # os.fdopen() and open() do.
        write_buffer_limit = 1
    return nbfile(read_fd, write_fd, write_buffer_limit=write_buffer_limit,
                  min_read_buffer_size=bufsize, do_close=do_close, mode=mode)

# TODO(pts): Add new_file and nbfile(...)
# TODO(pts): If the buffering argument (write_buffer_limit) is given, then
# 0 means unbuffered (autoflush on), 1 means line buffered, 2 means infinite
# buffer size, and larger numbers specify the buffer size in bytes.

# --- Sockets (non-SSL).

# Forward declarations.
cdef class nbsocket
cdef class nbsslsocket

# Implementation backend class for sockets. Should be socket._socket.socket
# (which is the same as socket._realsocket)
socket_impl = socket._realsocket

# The original socket._realsocket class. Reference saved so further patching
# (in syncless.path) won't have an effect on it.
socket_realsocket = socket._realsocket

socket_realsocketpair = socket._socket.socketpair

socket_fromfd = socket.fromfd

# We're not inheriting from socket._socket.socket, because with the current
# socketmodule.c implementation it would be impossible to wrap the return
# value of accept() this way.
#
# TODO(pts): Implement a streaming fast socket class which uses fd and read(2).
# TODO(pts): For socket.socket, the socket timeout affects socketfile.read.
cdef class nbsocket:
    """Non-blocking drop-in replacement class for socket.socket.

    See the function new_realsocket for using this class as a replacement for
    socket._realsocket.
    """
    cdef socket_wakeup_info_s swi
    cdef int c_family
    # A socket._realsocket.
    cdef object realsock
    cdef char c_do_close

    def __init__(nbsocket self, *args, **kwargs):
        if 'socket_impl' in kwargs:
            my_socket_impl = kwargs.pop('socket_impl')
        else:
            my_socket_impl = socket_impl
        if args and isinstance(args[0], my_socket_impl):
            self.realsock = args[0]
            assert len(args) == 1
        else:
            self.realsock = my_socket_impl(*args, **kwargs)
        self.c_family = self.realsock.family
        self.swi.fd = self.realsock.fileno()
        # TODO(pts): self.realsock.setblocking(False) on non-Unix operating
        # systems.
        set_fd_nonblocking(self.swi.fd)
        self.swi.timeout_value = -1.0
        event_set(&self.swi.read_ev,  self.swi.fd, c_EV_READ,
                  HandleCTimeoutWakeup, NULL)
        event_set(&self.swi.write_ev, self.swi.fd, c_EV_WRITE,
                  HandleCTimeoutWakeup, NULL)

    def fileno(nbsocket self):
        return self.swi.fd

    def dup(nbsocket self):
        # TODO(pts): Skip the fcntl2 in the set_fd_nonblocking call in the
        # constructor, it's superfluous.
        # socket.socket.dup and socket._realsocket.dup don't copy self.timeout,
        # so we won't copy either here in nbsocket.dup.
        return type(self)(self.realsock.dup())

    # !! TODO: SUXX: __dealloc__ is not allowed to call close() or flush()
    #          (too late, see Pyrex docs), __del__ is not special
    def __dealloc__(nbfile self):
        self.close()

    def close(nbsocket self):
        if self.c_do_close:
            # self.realsock.close() calls socket(2) + close(2) if the filehandle
            # was already closed.
            self.realsock.close()
        else:
            # TODO(pts): Make this faster, and work without a new object.
            self.realsock = socket._closedsocket()
        self.swi.fd = -1
        # There is no method or attribute socket.closed or
        # socket._real_socket.closed(), so we don't implement one either.
        # We don't release the reference to self.realsock here, to imitate
        # after-close behavior of the object.

    def setdoclose(nbsocket self, char do_close):
        """With True, makes self.close() close the filehandle.

        Returns:
          self
        """
        self.c_do_close = do_close
        return self

    # This is not a standard property of `socket.socket'.
    property do_close:
        def __get__(self):
            return self.c_do_close

    property _sock:
        """Return a socket._realsocket.

        This makes it possible to pass an nbsocket to the ssl.SSLSocket
        constructor.
        """
        def __get__(self):
            return self.realsock

    property type:
        def __get__(self):
            return self.realsock.type

    property family:
        def __get__(self):
            return self.realsock.family

    property timeout:
        """Return a nonnegative double, or None if there is no timeout.

        socket._realsocket has a read-only .timeout, socket.socket doesn't
        have an attribute named timeout.
        """
        def __get__(self):
            if self.swi.timeout_value < 0:
                return None
            else:
                return self.swi.timeout_value

    property proto:
        def __get__(self):
            return self.realsock.proto

    def setsockopt(nbsocket self, *args):
        return self.realsock.setsockopt(*args)

    def getsockopt(nbsocket self, *args):
        return self.realsock.getsockopt(*args)

    def getsockname(nbsocket self, *args):
        return self.realsock.getsockname(*args)

    def getpeername(nbsocket self, *args):
        return self.realsock.getpeername(*args)

    def bind(nbsocket self, *args):
        return self.realsock.bind(*args)

    def listen(nbsocket self, *args):
        return self.realsock.listen(*args)

    def gettimeout(nbsocket self):
        if self.swi.timeout_value < 0:
            return None
        else:
            return self.swi.timeout_value

    def setblocking(nbsocket self, is_blocking):
        if is_blocking:
            self.swi.timeout_value = None
        else:
            self.swi.timeout_value = 0.0
            self.swi.tv.tv_sec = 0
            self.swi.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0

    def settimeout(nbsocket self, timeout):
        cdef double timeout_double
        if timeout is None:
            # SUXX: Pyrex or Cython wouldn't catch the type error if we had
            # None instead of -1.0 here.
            self.swi.timeout_value = -1.0
        else:
            timeout_double = timeout
            if timeout_double < 0.0:
                raise ValueError('Timeout value out of range')
            self.swi.timeout_value = timeout_double
            if timeout_double == 0.0:
                self.swi.tv.tv_sec = 0
                self.swi.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            else:
                self.swi.tv.tv_sec = <long>timeout_double
                self.swi.tv.tv_usec = <unsigned int>(
                    (timeout_double - <double>self.swi.tv.tv_sec) * 1000000.0)

    def accept(nbsocket self):
        asock, addr = coio_c_socket_call(self.realsock.accept, (),
                                         &self.swi, c_EV_READ)
        esock = type(self)(asock)  # Create new nbsocket.
        return esock, addr

    def connect(nbsocket self, object address):
        cdef timeval tv
        cdef int c_err
        # Do a non-blocking DNS lookup if needed.
        # There is no need to predeclare c_gethostbyname in Pyrex.
        address = c_gethostbyname(address, self.realsock.family)

        while 1:
            err = self.realsock.connect_ex(address)
            c_err = err  # It's 0 on success.
            if c_err and c_err != EISCONN:  # EISCONN is for the Mac OS X (Snow Leopard, 10.6.5)
                # We might get EALREADY occasionally for some slow connects.
                if c_err != EAGAIN and c_err != EINPROGRESS and c_err != EALREADY:
                    raise socket_error(err, strerror(err))

                # Workaround for Linux 2.6.31-20 for the delayed non-blocking
                # select() problem.
                # http://stackoverflow.com/questions/2708738/why-is-a-non-blocking-tcp-connect-occasionally-so-slow-on-linux
                if self.c_family == AF_INET:
                    tv.tv_sec = 0
                    tv.tv_usec = connect_magic_usec
                    os_select(0, NULL, NULL, NULL, &tv)

                coio_c_handle_eagain(&self.swi, c_EV_WRITE)
            else:
                return

    def connect_ex(nbsocket self, object address):
        cdef timeval tv
        cdef int c_err
        # Do a non-blocking DNS lookup if needed.
        address = c_gethostbyname(address, self.realsock.family)

        while 1:
            err = self.realsock.connect_ex(address)
            c_err = err  # It's 0 on success.
            # We might get EALREADY occasionally for some slow connects.
            if c_err != EAGAIN and c_err != EINPROGRESS and c_err != EALREADY and c_err != EISCONN:
                return err  # Including 0 for success.

            # Workaround for Linux 2.6.31-20 for the delayed non-blocking
            # select() problem.
            # http://stackoverflow.com/questions/2708738/why-is-a-non-blocking-tcp-connect-occasionally-so-slow-on-linux
            if self.c_family == AF_INET:
                tv.tv_sec = 0
                tv.tv_usec = connect_magic_usec
                os_select(0, NULL, NULL, NULL, &tv)

            coio_c_handle_eagain(&self.swi, c_EV_WRITE)

    def shutdown(nbsocket self, object how):
        while 1:
            err = self.realsock.shutdown(how)
            if err != EAGAIN:
                return err
            # TODO(pts): Can this happen (with SO_LINGER?).
            coio_c_handle_eagain(&self.swi, c_EV_WRITE)

    def recv(nbsocket self, *args):
        return coio_c_socket_call(self.realsock.recv, args,
                                  &self.swi, c_EV_READ)

    def recvfrom(nbsocket self, *args):
        return coio_c_socket_call(self.realsock.recvfrom, args,
                                  &self.swi, c_EV_READ)

    def recv_into(nbsocket self, *args):
        return coio_c_socket_call(self.realsock.recv_into, args,
                                  &self.swi, c_EV_READ)

    def recvfrom_into(nbsocket self, *args):
        return coio_c_socket_call(self.realsock.recvfrom_into, args,
                                  &self.swi, c_EV_READ)

    def send(nbsocket self, *args):
        return coio_c_socket_call(self.realsock.send, args,
                                  &self.swi, c_EV_WRITE)

    def sendto(nbsocket self, *args):
        return coio_c_socket_call(self.realsock.sendto, args,
                                  &self.swi, c_EV_WRITE)

    def sendall(nbsocket self, object data, int flags=0):
        cdef int got
        cdef int got2
        try:
            # TODO(pts): Write directly to self.swi.fd.
            got = self.realsock.send(data, flags)
            assert got > 0
        except socket_error, e:
            if e.args[0] != EAGAIN:  # Pyton2.5 doesn't support e.errno.
                raise
            coio_c_handle_eagain(&self.swi, c_EV_WRITE)
            got = 0
        while got < len(data):
            try:
                got2 = self.realsock.send(buffer(data, got), flags)
                assert got2 > 0
                got += got2
            except socket_error, e:
                if e.args[0] != EAGAIN:
                    raise
                coio_c_handle_eagain(&self.swi, c_EV_WRITE)

    def makefile_samefd(nbsocket self, mode='r+', int bufsize=-1):
        """Create and return an nbfile with self.swi.fd.

        The nbfile will be buffered, and its close method won't close any
        filehandles (especially not self.swi.fd).

        This method is not part of normal sockets.
        """
        return nbfile(self.swi.fd, self.swi.fd, bufsize, bufsize,
                      do_set_fd_nonblocking=0,
                      timeout_double=self.swi.timeout_value)

    def makefile(nbsocket self, mode='r', int bufsize=-1):
        """Create an nbfile (non-blocking file-like) object from self.

        os.dup(self.swi.fd) will be passed to the new nbfile object, and its
        .close() method will close that file descriptor.

        Args:
          mode: 'r', 'w', 'r+' etc. The default is mode 'r', just as for
            socket.socket.makefile.
        """
        cdef int fd
        fd = dup(self.swi.fd)
        if fd < 0:
            raise socket_error(errno, strerror(errno))
        # TODO(pts): Verify proper close semantics for _realsocket emulation.
        return nbfile(fd, fd, bufsize, bufsize, do_close=1,
                      do_set_fd_nonblocking=0,
                      timeout_double=self.swi.timeout_value)


def new_realsocket(*args):
    """Non-blocking drop-in replacement for socket._realsocket.

    The most important difference between socket.socket and socket._realsocket
    is that socket._realsocket.close() closes the filehandle immediately,
    while socket.socket.close() just breaks the reference.
    """
    return nbsocket(*args).setdoclose(1)


def socketpair(*args):
    """Non-blocking drop-in replacement for socket.socketpair."""
    sock1, sock2 = socket_realsocketpair(*args)
    return nbsocket(sock1), nbsocket(sock2)


def new_realsocket_fromfd(*args):
    """Non-blocking drop-in replacement for socket.fromfd.

    Please note that socket.fromfd returns a socket._realsocket in Python 2.6.

    Please note that the fileno() of the returned socket is different from
    args[0], because it's dup()ed. 
    """
    return nbsocket(socket_fromfd(*args)).setdoclose(1)


# --- SSL sockets

cdef object c_SSLError "coio_c_SSLError"
try:
    import ssl
    sslsocket_impl = ssl.SSLSocket
    c_SSLError = ssl.SSLError
    c_SSL_ERROR_EOF = ssl.SSL_ERROR_EOF
    c_SSL_ERROR_WANT_READ = ssl.SSL_ERROR_WANT_READ
    c_SSL_ERROR_WANT_WRITE = ssl.SSL_ERROR_WANT_WRITE
except ImportError, e:
    sslsocket_impl = None
    ssl = None
    # c_SSLError is None by default (set by initcoio()).


cdef class sockwrapper:
    """A helper class for holding a self._sock."""
    cdef object c_sock

    def __init__(sockwrapper self, sock):
        self.c_sock = sock

    property _sock:
        def __get__(self):
            return self.c_sock


# !! TODO(pts): implement all NotImplementedError
cdef class nbsslsocket:
    """Non-blocking drop-in replacement class for ssl.SSLSocket.

    Please note that this class is not as speed-optimized as nbsocket or
    nbfile, because how the `ssl' module provides abstractions.

    Just like ssl.SSLSocket, nbsslsocket uses a socket._realsocket
    (derived from the first constructor argument) for the underlying raw
    communication.

    Just like ssl.SSLSocket, please don't communicate using the unerlying socket._realsocket
    after the nbsslsocket has been created -- but close it when
    necessary. Just like ssl.SSLSocket, nbsslsocket will never call the
    .close() method of the underlying socket._realsocket, it will just
    drop reference to it.

    Args:
      args: Same arguments as to the ssl.SSLSocket constructor.
        ssl.SSLSocket requires a socket.socket as a first argument, and
        derives its underlying the socket._realsocket from its first
        argument (using the ._sock property). As an exterions to this,
        nbsslsocket accepts a socket.socket, socket._realsocket or
        nbsocket (all treated equvalently) in its first argument, and gets
        its underlying socket._realsocket accordingly.
    """
    cdef socket_wakeup_info_s swi

    # Of type socket._realsocket.
    cdef object realsock
    # Of type ssl.SSLSocket.
    cdef object sslsock
    # Of type ssl._ssl.SSLType, i.e. 'ssl.SSLContext' defined in
    # modules/_ssl.c; or None if not connected.
    cdef object sslobj
    cdef char do_handle_read_eof

    def __init__(nbsslsocket self, *args, **kwargs):
        cdef int do_handshake_now
        if 'sslsocket_impl' in kwargs:
            my_sslsocket_impl = kwargs.pop('sslsocket_impl')
        else:
            my_sslsocket_impl = sslsocket_impl
        if (hasattr(args[0], '_sock') and
            isinstance(args[0]._sock, socket_realsocket)):
            # This works with isinstance(args[0], socket.socket) or
            # isinstance(args[0], nbsocket).
            pass
        elif isinstance(args[0], socket_realsocket):
            args = list(args)
            args[0] = sockwrapper(args[0])
        else:
            raise TypeError('bad type for underlying socket: ' + str(args[0]))
        if len(args) > 7:
            raise NotImplementedError(
                'do_handshake_on_connect= specified as positional argument')
        do_handshake_now = 0
        if kwargs.get('do_handshake_on_connect'):
            kwargs['do_handshake_on_connect'] = False
            do_handshake_now = 1

        # TODO(pts): Make sure we do a non-blocking handshake (do_handshake)
        # in my_sslsocket_impl.__init__. Currently it's blocking.
        self.sslsock = my_sslsocket_impl(*args, **kwargs)
        if self.sslsock.recv is args[0]._sock.recv:
          # Fix memory leak because of circular references. Also makes
          # self.realsock autoclosed if there are no more references. See also
          # syncless.patch.fix_ssl_init_memory_leak().
          for attr in socket._delegate_methods:
            delattr(self.sslsock, attr)
        self.realsock = self.sslsock._sock
        self.sslobj = self.sslsock._sslobj
        if self.sslsock.suppress_ragged_eofs:
          self.do_handle_read_eof = 1
        self.swi.fd = self.realsock.fileno()
        timeout = self.realsock.gettimeout()
        # It seems that either of these setblocking calls are enough.
        self.realsock.setblocking(False)
        #self.sslsock.setblocking(False)
        self.swi.timeout_value = -1.0
        event_set(&self.swi.read_ev,  self.swi.fd, c_EV_READ,
                  HandleCTimeoutWakeup, NULL)
        event_set(&self.swi.write_ev, self.swi.fd, c_EV_WRITE,
                  HandleCTimeoutWakeup, NULL)

        # Do the handshake as late as possible, so that we are already
        # non-blocking.
        # We do the handshake with infinite timeout, because
        # ssl.SSLSocket.__init__ does that.
        if do_handshake_now:
            # TODO(pts): Maybe set this in a `finally:' block?
            self.sslsock.do_handshake_on_connect = True
            if self.sslobj:
                self.do_handshake()

        # TODO(pts): Set this in a `finally:' block.
        if timeout is not None:
            self.swi.timeout_value = timeout

    def get_sslobj(nbsslsocket self):
        return self.sslobj

    def fileno(nbsslsocket self):
        return self.swi.fd

    def dup(nbsslsocket self):
        """Duplicates to a non-SSL socket (just like SSLSocket.dup)."""
        # TODO(pts): Skip the fcntl2 in the set_fd_nonblocking call in the
        # constructor.
        return nbsocket(self.realsock.dup())

    # TODO(pts): SUXX: __dealloc__ is not allowed to call close() or flush()
    #            (too late, see Pyrex docs), __del__ is not special
    def __dealloc__(nbsslsocket self):
        self.close()

    def close(nbsslsocket self):
        """Incompatible with SSLSocket.close: just drops the references."""
        self.swi.fd = -1
        if self.sslsock:
          self.sslsock.close()  # This sets self.sslsock._sslobj = None
        self.sslobj = self.realsock = self.sslsock = None
        # Compatibility: self.sslobj = self.sslsock._sslobj

    property type:
        def __get__(self):
            return self.realsock.type

    property family:
        def __get__(self):
            return self.realsock.family

    property proto:
        def __get__(self):
            return self.realsock.proto

    property _sslobj:
        def __get__(self):
            return self.sslobj

    property _sock:
        def __get__(self):
            return self.realsock

    property _sslsock:
        """Return the corresponding SSLSocket instance.

        Property _sslsock is not present in SSLSocket.
        """
        def __get__(self):
            return self.sslsock

    property keyfile:
        def __get__(self):
            return self.sslsock.keyfile

    property certfile:
        def __get__(self):
            return self.sslsock.cerfile

    property cert_reqs:
        def __get__(self):
            return self.sslsock.cert_reqs

    property ssl_version:
        def __get__(self):
            return self.sslsock.ssl_version

    property ca_certs:
        def __get__(self):
            return self.sslsock.ca_certs

    property do_handshake_on_connect:
        def __get__(self):
            return self.sslsock.do_handshake_on_connect
        def __set__(self, val):
            self.sslsock.do_handshake_on_connect = bool(val)

    property suppress_ragged_eofs:
        def __get__(self):
            return self.do_handle_read_eof

    property _makefile_refs:
        def __get__(self):
            return self.sslsock._makefile_refs

    property timeout:
        """Return a nonnegative double, or -1.0 if there is no timeout."""
        def __get__(self):
            if self.swi.timeout_value < 0:
                return None
            else:
                return self.swi.timeout_value

    def setsockopt(nbsslsocket self, *args):
        return self.realsock.setsockopt(*args)

    def getsockopt(nbsslsocket self, *args):
        return self.realsock.getsockopt(*args)

    def getsockname(nbsslsocket self, *args):
        return self.realsock.getsockname(*args)

    def getpeername(nbsslsocket self, *args):
        return self.realsock.getpeername(*args)

    def bind(nbsslsocket self, *args):
        return self.realsock.bind(*args)

    def listen(nbsslsocket self, *args):
        return self.realsock.listen(*args)

    def gettimeout(nbsslsocket self):
        if self.swi.timeout_value < 0:
            return None
        else:
            return self.swi.timeout_value

    def setblocking(nbsslsocket self, is_blocking):
        if is_blocking:
            self.swi.timeout_value = None
        else:
            self.swi.timeout_value = 0.0
            self.swi.tv.tv_sec = 0
            self.swi.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0

    def settimeout(nbsslsocket self, timeout):
        cdef double timeout_double
        if timeout is None:
            self.swi.timeout_value = -1.0
        else:
            timeout_double = timeout
            if timeout_double < 0.0:
                raise ValueError('Timeout value out of range')
            self.swi.timeout_value = timeout_double
            if timeout_double == 0.0:
                self.swi.tv.tv_sec = 0
                self.swi.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            else:
                self.swi.tv.tv_sec = <long>timeout_double
                self.swi.tv.tv_usec = <unsigned int>(
                    (timeout_double - <double>self.swi.tv.tv_sec) * 1000000.0)

    def read(nbsslsocket self, len=1024):
        """Emulate ssl.SSLSocket.read, doesn't make much sense."""
        return coio_c_ssl_call(self.sslobj.read, (len,), &self.swi,
                               self.do_handle_read_eof)

    def write(nbsslsocket self, data):
        """Emulate ssl.SSLSocket.write, doesn't make much sense."""
        return coio_c_ssl_call(self.sslobj.write, (data,), &self.swi, 0)

    def accept(nbsslsocket self):
        cdef nbsslsocket asslsock
        asock, addr = coio_c_socket_call(self.realsock.accept, (),
                                         &self.swi, c_EV_READ)
        asslsock = nbsslsocket(
            sockwrapper(asock),
            keyfile=self.sslsock.keyfile,
            certfile=self.sslsock.certfile,
            server_side=True,
            cert_reqs=self.sslsock.cert_reqs,
            ssl_version=self.sslsock.ssl_version,
            ca_certs=self.sslsock.ca_certs,
            do_handshake_on_connect=False,
            suppress_ragged_eofs=self.sslsock.suppress_ragged_eofs)
        if self.sslsock.do_handshake_on_connect:
            asslsock.sslsock.do_handshake_on_connect = True
            asslsock.do_handshake()  # Non-blocking.
        return (asslsock, addr)

    def connect(nbsslsocket self, object address):
        cdef timeval tv
        cdef int c_err
        if self._sslobj:
            raise ValueError('attempt to connect already-connected SSLSocket!')
                    
        # Do a non-blocking DNS lookup if needed.
        # There is no need to predeclare c_gethostbyname in Pyrex.
        address = c_gethostbyname(address, self.realsock.family)

        while 1:
            err = self.realsock.connect_ex(address)
            c_err = err  # It's 0 on success.
            if c_err and c_err != EISCONN:
                if c_err != EAGAIN and c_err != EINPROGRESS:
                    raise socket_error(err, strerror(err))

                # Workaround for Linux 2.6.31-20 for the delayed non-blocking
                # select() problem.
                # http://stackoverflow.com/questions/2708738/why-is-a-non-blocking-tcp-connect-occasionally-so-slow-on-linux
                if self.realsock.family == AF_INET:
                    tv.tv_sec = 0
                    tv.tv_usec = connect_magic_usec
                    os_select(0, NULL, NULL, NULL, &tv)

                coio_c_handle_eagain(&self.swi, c_EV_WRITE)
            else:
                break

        self.sslsock._sslobj = self.sslobj = ssl._ssl.sslwrap(
            self.realsock, False, self.sslsock.keyfile,
            self.sslsock.certfile, self.sslsock.cert_reqs,
            self.sslsock.ssl_version, self.sslsock.ca_certs)

        if self.sslsock.do_handshake_on_connect:
            self.do_handshake()

    def connect_ex(nbsslsocket self, object address):
        """Do a connect(2), and return 0 or the error code.

        The implementation of connect_ex is not optimized for speed.

        This is incompatible with SSLSocket.connect_ex, which doesn't do the
        SSL handshake, and connects only the socket._realsocket.
        
        Returns:
          0 on success; errno for socket_error and -800 - errno for
          ssl.SSLError.
        """
        try:
            self.connect(address)
        except socket_error, e:
            return e.args[0]
        except c_SSLError, e:
            return -800 - e.errno  # TODO(pts): Better reporting
        return 0

    def shutdown(nbsslsocket self, object how):
        # Clearing sslobj mimics the behavior of ssl.SSLSocket.shutdown.
        self.sslsock._sslobj = None
        self.sslobj = None
        while 1:
            err = self.realsock.shutdown(how)
            if err != EAGAIN:
                return err
            # TODO(pts): Can this happen (with SO_LINGER?).
            coio_c_handle_eagain(&self.swi, c_EV_WRITE)

    def pending(nbsslsocket self):
        # TODO(pts): How is this method useful?
        return self.sslsock.pending()

    def unwrap(nbsslsocket self):
        if self.sslobj:
            s = self.sslobj.shutdown()
            self.sslsock._sslobj = None
            self.sslobj = None
            return s
        raise ValueError('No SSL wrapper around ' + str(self.sslsock))

    def do_handshake(nbsslsocket self):
        return coio_c_ssl_call(self.sslobj.do_handshake, (), &self.swi, 0)

    def getpeercert(nbsslsocket self, binary_form=False):
        return self.sslobj.peer_certificate(binary_form)

    def cipher(self):
        if not self.sslobj:
            return None
        else:
            return self.sslobj.cipher()

    def recv(nbsslsocket self, int buflen=1024, int flags=0):
        """Receive data from the SSL or non-SSL connection.

        The defaults for buflen and flags are the same as in ssl.SSLSocket.
        """        
        if self.sslobj:
            if flags:
                raise ValueError(
                    'flags=0 expected for recv on ' + str(self.__class__))
            return coio_c_ssl_call(self.sslobj.read, (buflen,), &self.swi,
                                   self.do_handle_read_eof)
        return coio_c_socket_call(self.realsock.recv, (buflen, flags),
                                  &self.swi, c_EV_READ)

    def recvfrom(nbsslsocket self, *args):
        raise NotImplementedError  # !!
        return coio_c_socket_call(self.realsock.recvfrom, args,
                                  &self.swi, c_EV_READ)

    def recv_into(nbsslsocket self, buf, nbytes=None, flags=0):
        if self.sslobj:
            if flags:
                raise ValueError(
                    'flags=0 expected for recv on ' + str(self.__class__))
            if not nbytes:
                # ssl.SSLScoket.recv_into sets nbytes to 1024 if the buffer
                # is false. How can a buffer be false (and still extensible)?
                nbytes = len(buffer)
            if nbytes > 65536:  # Don't preallocate too much below.
                nbytes = 65536
            # No .readinto method in self.sslobj, so doing a regular read.
            data = coio_c_ssl_call(self.sslobj.read, (nbytes,), &self.swi,
                                   self.do_handle_read_eof)
            buf[:len(data)] = data
            return len(data)
        return coio_c_socket_call(self.realsock.recv_into,
                                  (buf, nbytes or 0, flags),
                                  &self.swi, c_EV_READ)

    def recvfrom_into(nbsslsocket self, *args):
        raise NotImplementedError  # !!
        return coio_c_socket_call(self.realsock.recvfrom_into, args,
                                  &self.swi, c_EV_READ)

    def send(nbsslsocket self, data, int flags=0):
        if self.sslobj:
            if flags:
                raise ValueError(
                    'flags=0 expected for send on ' + str(self.__class__))
            return coio_c_ssl_call(self.sslobj.write, (data,), &self.swi, 0)
        return coio_c_socket_call(self.realsock.send, (data, flags),
                                  &self.swi, c_EV_WRITE)

    def sendto(nbsslsocket self, *args):
        raise NotImplementedError  # !!
        return coio_c_socket_call(self.realsock.sendto, args,
                                  &self.swi, c_EV_WRITE)

    def sendall(nbsslsocket self, object data, int flags=0):
        cdef int got
        cdef int got2
        got = 0
        buf = data   # TODO(pts): Verify buffer or str (no unicode).
        if data:
            if self.sslobj:
                if flags:
                    raise ValueError(
                        'flags=0 expected for sendall on ' +
                        str(self.__class__))
                while 1:
                    got2 = coio_c_ssl_call(self.sslobj.write, (buf,), &self.swi, 0)
                    assert got2 > 0
                    got += got2
                    if got >= len(data):
                        return
                    buf = buffer(data, got)
            while 1:
                try:
                    got2 = 0  # Pacify gcc warning.
                    got2 = self.realsock.send(buf, flags)
                except socket_error, e:
                    if e.args[0] != EAGAIN:
                        raise
                    coio_c_handle_eagain(&self.swi, c_EV_WRITE)
                    continue
                assert got2 > 0
                got += got2
                if got >= len(data):
                    return
                # It's not possible to modify (slice) an existing buffer, so
                # we create a new one.
                buf = buffer(data, got)

    def makefile_samefd(nbsslsocket self, mode='r+', int bufsize=-1):
        """Create and return an nbfile with self.swi.fd.

        The nbfile will be buffered, and its close method won't close any
        filehandles (especially not self.swi.fd).

        This method is not part of normal sockets.

        Both the returned nbfile and this nbsslsocket will see the decrypted
        data.
        """
        # !! fix this if self.sslobj is None
        return nbfile(self.swi.fd, self.swi.fd, bufsize, bufsize,
                      do_set_fd_nonblocking=0, sslobj=self.sslobj,
                      timeout_double=self.swi.timeout_value)

    def makefile(nbsslsocket self, mode='r', int bufsize=-1):
        """Create an nbfile (non-blocking file-like) object from self.

        The .close() method of the returned nbfile will close a different
        file descriptor than the .close() method of this nbsslsocket _after_
        this function returns.

        Due to implementation quirks, nbsslsocket.makefile behaves a bit
        funnily: TODO(pts): Document this in the README.

        * The original nbsslsocket (self) loses its SSL property: attempts
          to .send() and .recv() from it will see the encrypted byte stream.
          (This is because it's impossible to change the fileno of
          self.sslobj.)
        * The .fileno() of the original nbsslsocket (self) is changed, and the
          returned nbfile gets the original fileno.

        To avoid this funniness, use self.makefile_samefd() instead.

        Args:
          mode: 'r', 'w', 'r+' etc. The default is mode 'r', just as for
            socket.socket.makefile.
        """
        cdef int fd
        # !! fix this if self.sslobj is None
        realsock = self.realsock.dup()
        sslobj = self.sslobj
        fd = self.swi.fd
        self.sslsock._sock = self.realsock = self.realsock.dup()
        self.sslobj = self.sslsock._sslobj = None
        self.swi.fd = self.realsock.fileno()
        # do_close=0, because sslobj forcibly closes when there are no more
        # references.
        return nbfile(fd, fd, bufsize, bufsize, do_close=0,
                      do_set_fd_nonblocking=0, sslobj=sslobj,
                      timeout_double=self.swi.timeout_value)


cdef class nbsslobj:
    """Non-blocking drop-in replacement class for ssl._ssl.sslwrap(...).
    
    Most users need nbsslsocket instead of nbsslobj instead.
    """
    cdef socket_wakeup_info_s swi
    cdef object sslobj

    def __init__(nbsslobj self, sock, *args):
        # We must disallow sslobj (isinstance(sock, ssl._ssl.SSLType)) here,
        # because it's impossible to query the fileno and the timeout.
        timeout = sock.gettimeout()
        if timeout is None:
            self.swi.timeout_value = -1.0
        else:
            self.swi.timeout_value = timeout
            if self.swi.timeout_value <= 0.0:
                self.swi.timeout_value = 0.0
                self.swi.tv.tv_sec = 0
                self.swi.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            else:
                self.swi.tv.tv_sec = <long>self.swi.timeout_value
                self.swi.tv.tv_usec = <unsigned int>(
                    (self.swi.timeout_value -
                     <double>self.swi.tv.tv_sec) * 1000000.0)
        self.swi.fd = sock.fileno()
        event_set(&self.swi.read_ev,  self.swi.fd, c_EV_READ,
                  HandleCTimeoutWakeup, NULL)
        event_set(&self.swi.write_ev, self.swi.fd, c_EV_WRITE,
                  HandleCTimeoutWakeup, NULL)

        if hasattr(sock, 'get_sslobj') and hasattr(sock, 'makefile_samefd'):
            # isinstance(sock, nbsslsocket)
            self.sslobj = sock.get_sslobj()
        else:
            # This not only puts self.swi.fd to O_NONBLOCK, but it
            # communicates to the to-be-created sslobj that it should return
            # c_SSLERROR(c_SSL_ERROR_WANT_READ) etc.
            sock.settimeout(0)
            if hasattr(sock, '_sock'):
                self.sslobj = ssl._ssl.sslwrap(sock._sock, *args)
            else:
                # isinstance(sock, socket._realsocket)
                # isinstance(sock, socket_impl)
                self.sslobj = ssl._ssl.sslwrap(sock, *args)

    # Delegate sslobj methods which never block.
    def cipher(nbsslobj self):
        return self.sslobj.cipher()
    def issuer(nbsslobj self):
        return self.sslobj.issuer()
    def peer_certificate(nbsslobj self, der=False):
        return self.sslobj.peer_certificate(der)
    def server(nbsslobj self):
        return self.server()

    # Delegate and wrap sslobj methods which may block.
    def do_handshake(nbsslobj self):
        # TODO(pts): Maybe prefetch self.sslobj.do_handshake to speed up,
        # also in other classes and methods as well.
        return coio_c_ssl_call(self.sslobj.do_handshake, (), &self.swi, 0)
    def pending(nbsslobj self):
        # Deliberately no EOF handling (last arg 0) here for compatibility.
        return coio_c_ssl_call(self.sslobj.pending, (), &self.swi, 0)
    def read(nbsslobj self, len=1024):
        if len <= 0:
            # The original sslobj doesn't return immediately on len=0, so
            # we may be a little incompatible here.
            return ''
        # Deliberately no EOF handling (last arg 0) here for compatibility.
        return coio_c_ssl_call(self.sslobj.read, (len,), &self.swi, 0)
    def shutdown(nbsslobj self):
        return coio_c_ssl_call(self.sslobj.shutdown, (), &self.swi, 0)
    def write(nbsslobj self, data):
        return coio_c_ssl_call(self.sslobj.write, (data,), &self.swi, 0)


def sslwrap_simple(sock, keyfile=None, certfile=None):
    """Non-blocking drop-in replacement for function ssl.sslwrap_simple().

    Please note that the socket.ssl() function is the Python 2.5 equivalent
    of ssl.sslwrap_simple(), and it has been deprecated in Python 2.6. This
    function is thus a drop-in replacement for socket.ssl() as well.

    This function returns a new, possibly handshaked instance of nbsslobj.
    """
    nbsslobj_obj = nbsslobj(sock, 0, keyfile, certfile, ssl.CERT_NONE,
                            ssl.PROTOCOL_SSLv23, None)
    try:
        sock.getpeername()
    except socket_error, e:
        pass
    else:
        nbsslobj_obj.do_handshake()  # Do the handshake if connected.
    return nbsslobj_obj


if ssl:
    _fake_ssl_globals = {'SSLSocket': nbsslsocket}
    ssl_wrap_socket = types.FunctionType(
      ssl.wrap_socket.func_code, _fake_ssl_globals,
      None, ssl.wrap_socket.func_defaults)
    ssl_wrap_socket.__doc__ = (
        """Non-blocking drop-in replacement for ssl.wrap_socket.""")
else:
    globals()['nbsslsocket'] = None  
    globals()['nbsslobj'] = None
    globals()['sslwrap_simple'] = None


# --- Sleeping.

cdef void HandleCSleepWakeup(int fd, short evtype, void *arg) with gil:
    # Set tempval so coio_c_wait doesn't have to call event_del(...).
    if (<tasklet>arg).tempval is waiting_token:
        (<tasklet>arg).tempval = coio_event_happened_token
    PyTasklet_Insert(<tasklet>arg)


def sleep(double duration):
    """Non-blocking drop-in replacement for time.sleep.

    Please note that sleep() (unlike time.sleep()) is not aborted by a signal.

    Return value:

    * If sleeping_tasklet.raise_exception(...) or sleeping_tasklet.kill()
      was called while sleeping, then cancel the sleep and raise that
      exception.
    * Otherwise, if sleeping_tasklet.tempval was set to a stackless.bomb(...)
      value and then sleeping_tasklet.insert() was called, and then
      sleeping_tasklet got scheduled, then cancel the sleep and raise the
      exception in the bomb.
    * Otherwise, if sleeping_tasklet.tempval was set, and then
      sleeping_tasklet.insert() was called, and then sleeping_tasklet got
      scheduled, then cancel the sleep and return sleeping_tasklet.tempval.
    * Otherwise, if sleeping_tasklet.tempval was not set, and then
      sleeping_tasklet.insert() was called, and then sleeping_tasklet got
      scheduled, then cancel the sleep and return waiting_token (a true value).
      (Please don't explicitly check for that.)
    * Otherwise sleep for the whole sleep duration, and return an object
      (coio_event_happened_token == coio.event_happened_token, a true value).
    """
    cdef timeval tv
    if duration <= 0:
        return
    tv.tv_sec = <long>duration
    tv.tv_usec = <unsigned int>((duration - <double>tv.tv_sec) * 1000000.0)
    # See #define evtimer_set(...) in event.h.
    return coio_c_wait_for(-1, 0, HandleCSleepWakeup, &tv)


# --- Channels with timeout.


# Helper method used by receive_with_timeout.
def ReceiveSleepHelper(double timeout, tasklet receiver_tasklet):
  if sleep(timeout):  # If timeout has been reached or woken up.
    if PyTasklet_Alive(receiver_tasklet):
      # This call immediately activates receiver_tasklet.
      receiver_tasklet.raise_exception(IndexError)


def receive_with_timeout(object timeout, object receive_channel,
                         object default_value=None):
  """Receive from receive_channel with a timeout.

  Args:
    timeout: Number of seconds of timeout, or None if infinite.
  """
  cdef timeout_double
  if timeout is None:  # Infinite timeout.
    return receive_channel.receive()
  sleeper_tasklet = stackless.tasklet(ReceiveSleepHelper)(
      timeout, stackless.current)
  try:
    received_value = receive_channel.receive()
  except IndexError, e:  # Sent by sleeper_tasklet.
    # The `except' above would segfault without a `, e'.
    received_value = default_value
  except:  # TODO(pts): Test this.
    if PyTasklet_Alive(sleeper_tasklet):
      PyTasklet_Remove(sleeper_tasklet)
      PyTasklet_Kill(sleeper_tasklet)
    raise  # TODO(pts): Isn't this too late?
  if PyTasklet_Alive(sleeper_tasklet):
    PyTasklet_Remove(sleeper_tasklet)
    # Since it was removed above from the runnables list, this kill gives us
    # back the control once sleeper_tasklet is done.
    PyTasklet_Kill(sleeper_tasklet)
  return received_value


# --- select() emulation.


cdef class selecter

cdef void HandleCSelectWakeup(int fd, short evtype, void *arg) with gil:
    cdef selecter selecter_obj
    selecter_obj = <selecter>arg
    # TODO(pts): Add tests to ensure we don't append to writeable_fds if
    # only select-for-read was requested in this select (etc.).
    if evtype & c_EV_READ:
        selecter_obj.readable_fds.append(fd)
    if evtype & c_EV_WRITE:
        selecter_obj.writeable_fds.append(fd)
    # It's OK to insert it multiple times.
    PyTasklet_Insert(selecter_obj.wakeup_tasklet)

cdef class selecter:
    """Helper class for the select() emulation. Call coio.select instead.

    The caller must ensure that there are no multiple self.do_select() calls
    on the same selecter object. That's because some instance variables are
    shared.
    """
    cdef event_t *wakeup_evs
    cdef list readable_fds
    cdef list writeable_fds
    cdef tasklet wakeup_tasklet

    #def __cinit__(selecter self):
    #    self.wakeup_evs = NULL  # Automatic.
    #    self.readable_fds = None  # Automatic.
    #    self.writeable_fds = None  # Automatic.

    def __dealloc__(selecter self):
        if self.wakeup_evs != NULL:
            PyMem_Free(self.wakeup_evs)

    def do_select(selecter self, rlist, wlist, timeout):
        cdef int c
        cdef int i
        cdef int fd
        cdef timeval tv
        cdef double duration
        cdef dict fd_to_fh
        cdef list readable_fds
        cdef list writeable_fds
        self.readable_fds = readable_fds = []
        self.writeable_fds = writeable_fds = []
        self.wakeup_tasklet = PyStackless_GetCurrent()
        fd_to_fh = {}
        c = len(rlist) + len(wlist)
        if timeout is not None:
            duration = timeout
            if duration <= 0:
                if c == 0:
                    return [], [], []
                tv.tv_sec = 0
                tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            else:
                tv.tv_sec = <long>duration
                tv.tv_usec = <unsigned int>(
                    (duration - <double>tv.tv_sec) * 1000000.0)
            c += 1
        if self.wakeup_evs != NULL:
            PyMem_Free(self.wakeup_evs)
        self.wakeup_evs = <event_t*>PyMem_Malloc(sizeof(event_t) * c)
        if self.wakeup_evs == NULL:
            raise MemoryError
        i = 0
        for fh in rlist:
            if isinstance(fh, int):
                fd = fh
                fd_to_fh[fd] = fh  # TODO(pts): Make mapping easier.
            else:
                fd = fh.fileno()
                # TODO(pts): Check that the same filehandle is not added as
                # both fd and fh (possibly to read and write).
                fd_to_fh[fd] = fh
            assert fd >= 0
            event_set(self.wakeup_evs + i, fd, c_EV_READ, HandleCSelectWakeup,
                      <void*>self)
            event_add(self.wakeup_evs + i, NULL)
            i += 1
        for fh in wlist:
            if isinstance(fh, int):
                fd = fh
                fd_to_fh[fd] = fh  # TODO(pts): Make mapping easier.
            else:
                fd = fh.fileno()
                # TODO(pts): Check that the same filehandle is not added as
                # both fd and fh (possibly to read and write).
                fd_to_fh[fd] = fh
            assert fd >= 0
            event_set(self.wakeup_evs + i, fd, c_EV_WRITE, HandleCSelectWakeup,
                      <void*>self)
            # We don't need a PyINCREF(self) here because the `finally:' block
            # below cleans up.
            event_add(self.wakeup_evs + i, NULL)
            i += 1
        if i < c:
            event_set(self.wakeup_evs + i, -1, 0, HandleCWakeup,
                      <void*>self.wakeup_tasklet)
            event_add(self.wakeup_evs + i, &tv)
            i += 1
        assert i == c
        try:
            PyStackless_Schedule(None, 1)  # remove=1
        finally:
            for 0 <= i < c:
                event_del(self.wakeup_evs + i)
            PyMem_Free(self.wakeup_evs)
            self.wakeup_evs = NULL
            self.readable_fds = None
            self.writeable_fds = None
            self.wakeup_tasklet = None
        return (map(fd_to_fh.__getitem__, readable_fds),
                map(fd_to_fh.__getitem__, writeable_fds),
                [])

def select(rlist, wlist, xlist, timeout=None):
    """Non-blocking drop-in replacement for select.select.

    Please note that select(2) is inherently slow (compared to libevent,
    Linux epoll, BSD kqueue etc.), so please use other Syncless features
    (such as a combination of nbsocket and tasklets) for performance-critical
    operation. If your program uses select(2), please consider redesigning it
    so it would use Syncless non-blocking communication classes and tasklets.

    Limitation: Exceptional filehandles (non-empty xlist) are not
    supported.

    The built-in select.select() doesn't cooperate nicely with input
    buffering (e.g. after sys.stdin.readline()), Syncless doesn't
    do that either.

    Please note that because of the slow speed of select(2), this function is
    provided only for completeness and for legacy application compatibility.
    """
    if xlist:
        raise NotImplementedError('except-filehandles for select')
    # TODO(pts): Simplify if len(rlist) == 1 and wlist is empty (etc.).
    return selecter().do_select(rlist, wlist, timeout)


def select_ignorexlist(rlist, wlist, xlist, timeout=None):
    """Like select, but tread xlist as empty."""
    return selecter().do_select(rlist, wlist, timeout)


# --- Twisted 10.0.0 syncless.reactor and Tornado support classes

cdef class wakeup_info

cdef void HandleCWakeupInfoWakeup(int fd, short evtype, void *arg) with gil:
    cdef wakeup_info wakeup_info_obj
    cdef int mode
    wakeup_info_obj = <wakeup_info>arg
    if fd >= 0:  # fd is -1 for a timer (such as timeout_event)
        mode = 0
        if evtype & EV_READ:
            mode |= 1
        if evtype & EV_WRITE:
            mode |= 2
        # Create a list instead of a tuple so `mode' can be modified later by
        # our users.
        wakeup_info_obj.c_pending_events.append([fd, mode])
    if wakeup_info_obj.wakeup_tasklet:
        PyTasklet_Insert(wakeup_info_obj.wakeup_tasklet)

cdef class wakeup_info_event:
    # It's important to hold this reference.
    cdef event_t ev
    cdef wakeup_info wakeup_info_obj

    def __cinit__(wakeup_info_event self,
                  wakeup_info wakeup_info_obj,
                  int evtype,
                  int handle,
                  timeout):
        cdef timeval tv
        cdef double timeout_double
        assert wakeup_info_obj
        self.wakeup_info_obj = wakeup_info_obj  # Implied Py_INCREF.
        event_set(&self.ev, handle, evtype, HandleCWakeupInfoWakeup,
                  <void*>wakeup_info_obj)
        if timeout is None:
            event_add(&self.ev, NULL)
        else:
            timeout_double = timeout
            if timeout_double <= 0:
                tv.tv_sec = 0
                tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            else:
                tv.tv_sec = <long>timeout_double
                tv.tv_usec = <unsigned int>(
                    (timeout_double - <double>tv.tv_sec) * 1000000.0)
            event_add(&self.ev, &tv)
        Py_INCREF(self)

    def delete(self):
        event_del(&self.ev)
        Py_DECREF(self)
        self.wakeup_info_obj = None

    # No need for `def __dealloc__', Py_INCREF(self) above ensures that the
    # object is not auto-destroyed.


cdef class wakeup_info:
    """Information for event handlers to wake up the main loop tasklet.

    In the various methods, mode is an or-ed bitmask of 1 for reading, and
    2 for writing.    
    """
    cdef tasklet wakeup_tasklet
    cdef list c_pending_events

    def __cinit__(wakeup_info self):
        self.c_pending_events = []

    property pending_events:
        def __get__(wakeup_info self):
            return self.c_pending_events

    def create_event(wakeup_info self, fd, mode):
        """Create and return an event object with a .delete() method."""
        cdef int evtype
        cdef int c_mode
        c_mode = mode
        evtype = c_EV_PERSIST
        if c_mode & 1:
            evtype |= c_EV_READ
        if c_mode & 2:
            evtype |= c_EV_WRITE
        return wakeup_info_event(self, evtype, fd, None)

    def tick(wakeup_info self, timeout):
        """Do one tick of the main loop iteration up to timeout.

        Returns:
          The list of pending (fd, mode) pairs. The caller must remove
          items from the list before the next call to tick() as it's
          processing the events, by pop()ping the item before calling the
          event handler.
        """
        cdef event_t timeout_ev
        cdef wakeup_info_event timeout_event
        assert self.wakeup_tasklet is None
        if self.c_pending_events or (timeout is not None and timeout <= 0):
            # Let the Syncless main loop collect more libevent events.
            PyStackless_Schedule(None, 0)  # remove=0
        elif timeout is None:
            # Event handlers call self.wakeup_tasklet.insert() to cancel this
            # stackless.schedule_remove().
            try:
                PyStackless_Schedule(None, 1)  # remove=1
            finally:
                self.wakeup_tasklet = None
        else:
            timeout_event = wakeup_info_event(self, 0, -1, timeout)
            self.wakeup_tasklet = stackless.current
            # Event handlers call self.wakeup_tasklet.insert() to cancel this
            # stackless.schedule_remove().
            try:
                PyStackless_Schedule(None, 1)  # remove=1
            finally:
                self.wakeup_tasklet = None
                timeout_event.delete()
        return self.c_pending_events

    def tick_and_move(wakeup_info self, timeout):
        """Like self.tick(), but create a new list on each call."""
        cdef list list_obj
        list_obj = list(self.tick(timeout))
        del self.c_pending_events[:]
        return list_obj

# --- Signal support for Twisted 10.0.0

# Map signal signums to signal_event objects.
cdef dict signal_events
signal_events = {}

cdef void HandleCSignal(int signum, short evtype, void *arg) with gil:
    (<object>arg)(signum)  # Call with the signal number.
    # Since this functions returns `void', Pyrex prints and ignores
    # exceptions.

cdef class signal_event:
    cdef event_t ev

    def __cinit__(signal_event self, int signum, object handler):
        if not callable(handler):
            raise TypeError('signal handler not callable')
        if signum == SIGINT and sigint_ev.ev_flags != 0:
            event_del(&sigint_ev)
            sigint_ev.ev_flags = 0
        if signum == SIGUSR1 and sigusr1_ev.ev_flags != 0:
            event_del(&sigusr1_ev)
            sigusr1_ev.ev_flags = 0
        # Prevent automatic __dealloc__. So we don't have to def __dealloc__.
        Py_INCREF(self)
        Py_INCREF(handler)
        event_set(&self.ev, signum, c_EV_SIGNAL | c_EV_PERSIST,
                  HandleCSignal, <void*>handler)
        # Make loop() exit immediately of only EVLIST_INTERNAL events
        # were added. Add EVLIST_INTERNAL after event_set.
        coio_c_set_evlist_internal(&self.ev)
        event_add(&self.ev, NULL)

    def delete(signal_event self):
        cdef int signum
        if self.ev.ev_flags != 0:
            signum = self.ev.ev_fd
            Py_DECREF(<object>self.ev.ev_arg)
            event_del(&self.ev)
            self.ev.ev_flags = 0
            Py_DECREF(self)  # Corresponding to __cinit__.
            signal_events.pop(self, None)
            if signum == SIGINT and sigint_ev.ev_flags == 0:
                _setup_sigint()

def signal(int signum, object handler):
    """Register or unregister a signal handler.

    Args:
      signum: Positive signal number (e.g. signal.SIGINT). Unchecked.
      handler: Callable or None. handler(signum) will be called in the event
        loop as soon as the signal numbered signum gets received, and as many
        times as it gets received. Exceptions raised by the handler are printed
        briefly (without a traceback), and get ignored.
    Returns:
      The resulting signal_event object or None if unregistered.
    """
    cdef event_t *ev
    signum_obj = signum

    if signum == SIGUSR1:
        event_del(&sigusr1_ev)
        sigusr1_ev.ev_flags = 0
    elif signum == SIGUSR2:
        event_del(&sigusr2_ev)
        sigusr2_ev.ev_flags = 0

    # TODO(pts): Make Pyrex call `get' as a PyDictObject.
    signal_event_obj = signal_events.get(signum_obj)
    if signal_event_obj is None:
        if handler is not None:
            signal_event_obj = signal_event(signum, handler)
            signal_events[signum_obj] = signal_event_obj
            return signal_event_obj
    elif handler is None:
        (<signal_event>signal_event_obj).delete()
        del signal_events[signum_obj]
    else:
        ev = &(<signal_event>signal_event_obj).ev
        Py_DECREF(<object>ev.ev_arg)
        Py_INCREF(handler)
        ev.ev_arg = <void*>handler
        return signal_event_obj

# --- Concurrence 0.3.1 support
#
# See also patch.patch_concurrence().

cdef list concurrence_triggered
concurrence_triggered = []

def get_concurrence_triggered():
    return concurrence_triggered

def get_swap_concurrence_triggered():
    global concurrence_triggered
    retval = concurrence_triggered
    concurrence_triggered = []
    return retval

cdef list concurrence_main_tasklets
concurrence_main_tasklets = []

def get_concurrence_main_tasklets():
    return concurrence_main_tasklets

cdef class concurrence_event

cdef void HandleCConcurrence(int fd, short evtype, void *arg) with gil:
    pair = ((<concurrence_event>arg).callback, evtype)
    if not (<concurrence_event>arg).pending():
        Py_DECREF(<object>arg)
    concurrence_triggered.append(pair)
    for tasklet_obj in concurrence_main_tasklets:
        PyTasklet_Insert(<tasklet>tasklet_obj)

class EventError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, '%s: %s' % (msg, strerror(errno)))

cdef class concurrence_event:
    """event(callback, evtype=0, handle=None) -> event object
    
    Create a new event object with a user callback.

    Arguments:

    callback -- user callback with (ev, handle, evtype, arg) prototype
    arg      -- optional callback arguments
    evtype   -- bitmask of EV_READ or EV_WRITE, or EV_SIGNAL
    handle   -- for EV_READ or EV_WRITE, a file handle, descriptor, or socket
                for EV_SIGNAL, a signal number
    """
    cdef event_t ev
    cdef object evtype, callback
    cdef timeval tv

    def __init__(self, callback, short evtype=0, handle=-1):
        if callable(handle):
            # Concurrence repo has this at Sat May  8 03:16:07 CEST 2010:
            # event.event(fd, event_type, self._on_event)
            handle, callback = callback, handle
        self.callback = callback
        self.evtype = evtype
        if evtype == 0 and not handle:  # Timeout.
            event_set(&self.ev, -1, 0, HandleCConcurrence, <void *>self)
        elif isinstance(handle, int):
            event_set(&self.ev, handle, evtype, HandleCConcurrence, <void *>self)
        else:
            event_set(&self.ev, handle.fileno(), evtype, HandleCConcurrence, <void *>self)

    # We don't have to def __dealloc__ just to call event_del(&self.ev),
    # because the Py_INCREF(self) above ensures that if the event is
    # pending, then this object is not deleted.

    def add(self, double timeout=-1):
        """Add event to be executed after an optional timeout."""
        if not self.pending():
            Py_INCREF(self)
            
        if timeout >= 0.0:
            self.tv.tv_sec = <long>timeout
            self.tv.tv_usec = <long>((timeout - <double>self.tv.tv_sec) * 1000000.0)
            if event_add(&self.ev, &self.tv) == -1:
                raise EventError('could not add event')
        else:
            self.tv.tv_sec = 0
            self.tv.tv_usec = 1  # libev-3.9 ignores the timeout of 0
            if event_add(&self.ev, NULL) == -1:
                raise EventError('could not add event')

    def pending(self):
        """Return 1 if the event is scheduled to run, or else 0."""
        return event_pending(&self.ev, c_EV_TIMEOUT | c_EV_SIGNAL | c_EV_READ | c_EV_WRITE, NULL)
    
    def delete(self):
        """Remove event from the event queue."""
        if self.pending():
           if event_del(&self.ev) == -1:
                raise EventError('could not delete event')
           Py_DECREF(self)

    def __repr__(self):
        return '<event flags=0x%x, callback=%s' % (self.ev.ev_flags, self.callback)


# --- Thread pool

def _thread_worker_function(result_channel, start_lock, list call_info):
    """Function which runs forever in a thread."""
    while 1:
        start_lock.acquire()
        function, args, kwargs = call_info
        del call_info[:]
        # We need a wrapper, because sys.exc_info() doesn't work in Pyrex
        # (returns None in Pyrex 0.9.9) and `except BaseException, e, tb'
        # doesn't work in Cython.
        retval = coio_c_call_wrap_bomb(function, args, kwargs, bomb)
        if result_channel.balance < 0:
            result_channel.send(retval)  # Prefer the sender.
            cancel_main_loop_wait()


# Field indices of a ThreadWorkerInfo.
cdef enum:
    TWI_RESULT_CHANNEL = 0
    TWI_START_LOCK = 1
    TWI_CALL_INFO = 2


cdef class thread_pool:
    """A bounded thread pool of workers to run arbitrary functions.

    The thread pool can be used to wrap blocking operations (such as SQLite3
    queries) inside the non-blocking Syncless program.

    The __call__ method of the thread pool runs an arbitrary function in a
    worker thread (created with thread.start_new_thread, and retained for
    future use), waits for the result, and returns the result (or raises the
    corresponding exception). Other tasklets can run while the caller is
    waiting for the result.

    Please try to avoid a thread pool, and revert to it if there is no other
    feasible solution, because the thread pool needs more memory and CPU than
    coroutines (tasklets), so you might lose most performance advantages of
    Syncless (over threads) if you use the thread pool. For example, please use
    a non-blocking MySQL client (see the Syncless README) instead of calling
    the methods of libmysqlclient in a thread pool.

    See examples/demo_thread_pool*.py for example uses.

    Please note that TaskletExit or SystemExit is not raised in the worker
    threads active when the process is exiting. Those will just get aborted
    abrouptly.
    """

    cdef int startable_count
    cdef list available_thread_workers
    cdef object notify_channel
    cdef object allocate_lock
    cdef object start_new_thread

    def __cinit__(self, int max_thread_count, thread=None):
        if thread is None:
            thread = __import__('thread')
        self.allocate_lock = thread.allocate_lock
        self.start_new_thread = thread.start_new_thread
        self.startable_count = int(max_thread_count)
        self.available_thread_workers = []
        # Channel to notify waiting callers that a thread_worker_info is available.
        self.notify_channel = stackless.channel()
        self.notify_channel.preference = 1    # Prefer the sender.

    def __call__(self, function, *args, **kwargs):
        cdef list thread_worker
        if self.available_thread_workers:
            thread_worker = self.available_thread_workers.pop()
        elif self.startable_count:
            #TWI_RESULT_CHANNEL = 0
            #TWI_START_LOCK = 1
            #TWI_CALL_INFO = 2
            thread_worker = [stackless.channel(),   # TWI_RESULT_CHANNEL = 0
                             self.allocate_lock(),  # TWI_START_LOCK = 1
                             []]                    # TWI_CALL_INFO = 2
            thread_worker[TWI_RESULT_CHANNEL].preference = 1    # Prefer the sender.
            thread_worker[TWI_START_LOCK].acquire()
            # TODO(pts): Let the user specify the thread stack size
            # (thread.stack_size(...)).
            self.start_new_thread(_thread_worker_function, tuple(thread_worker))
            self.startable_count -= 1
        else:
            # This blocks until 
            thread_worker = self.notify_channel.receive()
        try:
            assert thread_worker[TWI_START_LOCK].locked()
            assert not thread_worker[TWI_CALL_INFO]
            thread_worker[TWI_CALL_INFO][:] = (function, args, kwargs)
            thread_worker[TWI_START_LOCK].release()
            # At this point Work calls function, puts the result to thread_worker.call_info, and
            # calls thread_worker.result_channel.release().
            #
            # This receive operation blocks.
            #
            # This might raise a bomb.
            #
            # This poeration happens to work even with greenstackless.
            # TODO(pts): examples/demo_thread_pool_work.py seems to wait an
            # extra amount above CR with greenstackless (as compared to real
            # stackless).
            return thread_worker[TWI_RESULT_CHANNEL].receive()
        finally:
            if self.available_thread_workers or self.notify_channel.balance >= 0:
                self.available_thread_workers.append(thread_worker)
            else:
                self.notify_channel.send(thread_worker)
