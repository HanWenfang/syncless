#
# nbevent.pxi: non-blocking I/Oclasses using libevent and buffering
# by pts@fazekas.hu at Sun Jan 31 12:07:36 CET 2010
# ### pts #### This file has been entirely written by pts@fazekas.hu.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
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
    cdef int os_write "write"(int fd, char_constp p, int n)
    cdef int os_read "read"(int fd, char *p, int n)
    cdef int dup(int fd)
    cdef int close(int fd)
    cdef int isatty(int fd)
    cdef int ftruncate(int fd, int size)
cdef extern from "string.h":
    cdef void *memset(void *s, int c, size_t n)
    cdef void *memchr(void_constp s, int c, size_t n)
    cdef void *memcpy(void *dest, void_constp src, size_t n)
    cdef void *memmove(void *dest, void_constp src, size_t n)
cdef extern from "errno.h":
    cdef extern int errno
    cdef extern char *strerror(int)
    cdef enum errno_dummy:
        EAGAIN
        EINPROGRESS
        EALREADY
        EIO
cdef extern from "fcntl.h":
    cdef int fcntl2 "fcntl"(int fd, int cmd)
    cdef int fcntl3 "fcntl"(int fd, int cmd, long arg)
    int O_NONBLOCK
    int F_GETFL
    int F_SETFL
cdef extern from "signal.h":
    int SIGINT
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

ctypedef void (*event_handler)(int fd, short evtype, void *arg)

cdef extern from "./coio_c_include_libevent.h":
    int c_FEATURE_MAY_EVENT_LOOP_RETURN_1 "FEATURE_MAY_EVENT_LOOP_RETURN_1"
    int c_FEATURE_MULTIPLE_EVENTS_ON_SAME_FD "FEATURE_MULTIPLE_EVENTS_ON_SAME_FD"


    struct event_t "event":
        int   ev_fd
        int   ev_flags
        void *ev_arg
        #short ev_events  # c_EV_READ | c_EV_WRITE etc.

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
    int EVLIST_INTERNAL

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
        int misalign
        int totallen
        int off
        void *cbarg
        void (*cb)(evbuffer_s*, int, int, void*)

    # These must match other declarations of the same name.
    evbuffer_s *evbuffer_new "coio_evbuffer_new"()
    void evbuffer_free "coio_evbuffer_free"(evbuffer_s *)
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
    int    PyObject_AsCharBuffer(object obj, char_constp *buffer, Py_ssize_t *buffer_len)
    object PyInt_FromString(char*, char**, int)
cdef extern from "pymem.h":
    void *PyMem_Malloc(size_t)
    void *PyMem_Realloc(void*, size_t)
    void PyMem_Free(void*)
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
cdef extern from "./coio_c_helper.h":
    struct socket_wakeup_info_s "coio_socket_wakeup_info":
        event_t read_ev
        event_t write_ev
        # -1.0 if None (infinite timeout).
        double timeout_value
        int fd
        # Corresponds to timeout (if not None).
        timeval tv

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

cdef int connect_tv_magic_usec
connect_magic_usec = 120

def _schedule_helper():
  return stackless.current.next.next.remove().run()

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
    tasklet_obj.remove()
    tasklet_obj.insert()
    # Implement _insert_after_current_tasklet(tasklet_obj).
    # TODO(pts): use PyStackless*.
    if stackless.current.next is stackless.current:
      tasklet_obj.insert()
    elif stackless.current.next is not tasklet_obj:
      # This is tricky, see the details in best_greenlet.py.
      # TODO(pts): Present this on the conference.
      tasklet_obj.remove()
      helper_tasklet = stackless.tasklet(_schedule_helper)()
      helper_tasklet.insert()
      main_loop_tasklet.insert()
      helper_tasklet.run()
      helper_tasklet.remove()

# ---

def MainLoop():
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
            with nogil:
                loop_retval = event_loop(EVLOOP_ONCE)
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

cdef event_t sigint_ev
sigint_ev.ev_flags = 0

cdef void _setup_sigint():
    event_set(&sigint_ev, SIGINT, c_EV_SIGNAL | c_EV_PERSIST,
              HandleCSigInt, NULL)
    # Make loop() exit immediately of only EVLIST_INTERNAL events
    # were added. Add EVLIST_INTERNAL after event_set.
    sigint_ev.ev_flags |= EVLIST_INTERNAL
    # This is needed so Ctrl-<C> raises (eventually, when the main_loop_tasklet
    # gets control) a KeyboardInterrupt in the main tasklet.
    event_add(&sigint_ev, NULL)

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


cdef int nbevent_read(evbuffer_s *read_eb, int fd, int n):
    """Read at most n bytes to read_eb from file fd.

    This function is similar to evbuffer_read, but it doesn't do an
    ioctl(FIONREAD), and it doesn't do weird magic on allocating a buffer 4
    times as large as needed.

    Args:
      read_eb: evbuffer to read to. It must not be empty, i.e. read_eb.totallen
        must be positive; this can be achieved with evbuffer_expand.
      fd: File descriptor to read from.
      n: Number of bytes to read. Negative values mean: read everything up to
        the available buffer size.
    Returns:
      Number of bytes read, or -1 on error. Error code is in errno.
    """
    cdef int got
    if n > 0:
        evbuffer_expand(read_eb, n)
    elif n == 0:
        return 0
    else:
        assert read_eb.totallen
        n = read_eb.totallen - read_eb.off - read_eb.misalign
        if n == 0:
            return 0
    got = os_read(fd, <char*>read_eb.buf + read_eb.off, n)
    if got > 0:
        read_eb.off += got
        # We don't use callbacks, so we don't call them.
        #if read_eb.cb != NULL:
        #    read_eb.cb(read_eb, read_eb.off - got, read_eb.off, read_eb.cbarg)
    return got

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
cdef object event_happened_token "coio_event_happened_token"
event_happened_token = object()

# Since this function returns void, exceptions raised (e.g. if <tasklet>arg)
# will be ignored (by Pyrex?) and printed to stderr as something like:
# Exception AssertionError: 'foo' in 'coio.HandleCWakeup' ignored
cdef void HandleCWakeup(int fd, short evtype, void *arg) with gil:
    #os_write(2, <char_constp>'W', 1)
    if (<tasklet>arg).tempval is waiting_token:
        (<tasklet>arg).tempval = event_happened_token
    PyTasklet_Insert(<tasklet>arg)

cdef void HandleCTimeoutWakeup(int fd, short evtype, void *arg) with gil:
    # PyStackless_Schedule will return tempval.
    # Writing <tasklet>arg will use arg as a tasklet without a NULL-check or a
    # type-check in Pyrex. This is what we want here.
    if (<tasklet>arg).tempval is waiting_token:
        if evtype == c_EV_TIMEOUT:
            (<tasklet>arg).tempval = None
        else:
            (<tasklet>arg).tempval = event_happened_token
    PyTasklet_Insert(<tasklet>arg)


cdef object write_all_to_fd(int fd, event_t *write_wakeup_ev, char_constp p,
                            Py_ssize_t n, object write_exc_class):
    """Write all n bytes at p to fd, waking up based on write_wakeup_ev.

    Returns:
      None
    """
    cdef int got
    while n > 0:
        got = os_write(fd, p, n)
        while got < 0:
            if errno != EAGAIN:
                # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                raise write_exc_class(errno, strerror(errno))
            # Assuming caller has called event_set(...).
            coio_c_wait(write_wakeup_ev, NULL)
            got = os_write(fd, p, n)
        p += got
        n -= got

cdef enum dummy:
    DEFAULT_MIN_READ_BUFFER_SIZE  = 8192  # TODO(pts): Do speed tests.
    DEFAULT_WRITE_BUFFER_LIMIT = 8192  # TODO(pts): Do speed tests.

# --- nbfile

cdef class nbfile

# Read from nbfile at most limit characters.
#
# Precondition: limit > 0.
# Precondition: self.c_read_limit < 0 ||
#               limit <= self.read_eb.off + self.c_read_limit
cdef object nbfile_readline_with_limit(nbfile self, int limit):
    cdef int n
    cdef int got
    cdef int min_off
    cdef char_constp q
    cdef int fd
    cdef evbuffer_s *read_eb
    cdef int had_short_read
    #DEBUG assert limit > 0
    #DEBIG assert (self.c_read_limit < 0 ||
    #              limit <= self.read_eb.off + self.c_read_limit)
    read_eb = &self.read_eb
    fd = self.read_fd
    had_short_read = 0
    min_off = 0
    if limit <= read_eb.off:  # All data already in buffer.
        q = <char_constp>memchr(<void_constp>read_eb.buf, c'\n', limit)
        if q != NULL:
            limit = q - <char_constp>read_eb.buf + 1
        buf = PyString_FromStringAndSize(<char_constp>read_eb.buf, limit)
        evbuffer_drain(read_eb, limit)
        return buf
    q = <char_constp>memchr(<void_constp>read_eb.buf, c'\n',
                            read_eb.off)
    while q == NULL:
        if had_short_read:
            evbuffer_expand(read_eb, 1)
        elif read_eb.totallen == 0:
            evbuffer_expand(read_eb, self.c_min_read_buffer_size)
        else:
            evbuffer_expand(read_eb, read_eb.totallen >> 1)
        n = read_eb.totallen - read_eb.off - read_eb.misalign
        if self.c_read_limit >= 0 and self.c_read_limit < n:
            n = self.c_read_limit

        got = nbevent_read(read_eb, fd, n)
        while got < 0:
            if errno != EAGAIN:
                # TODO(pts): Do it more efficiently with Pyrex?
                # Twisted does exactly this.
                raise self.c_read_exc_class(errno, strerror(errno))
            coio_c_wait(&self.read_wakeup_ev, NULL)
            got = nbevent_read(read_eb, fd, n)

        if got == 0:  # EOF, return remaining bytes ('' or partial line)
            n = read_eb.off
            if limit < n:
                # TODO(pts): Cache EOF, don't nbevent_read(...) again.
                if limit == 0:
                    return ''
                n = limit
            buf = PyString_FromStringAndSize(<char_constp>read_eb.buf, n)
            evbuffer_drain(read_eb, n)
            return buf
        if self.c_read_limit >= 0:
            self.c_read_limit -= got
        if limit <= read_eb.off:  # All data already in buffer.
            q = <char_constp>memchr(<void_constp>read_eb.buf, c'\n', limit)
            if q != NULL:
                limit = q - <char_constp>read_eb.buf + 1
            buf = PyString_FromStringAndSize(<char_constp>read_eb.buf, limit)
            evbuffer_drain(read_eb, limit)
            return buf
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

# !! implement timeout (does socket._realsocket.makefile do that?)
cdef class nbfile:
    """A non-blocking file (I/O channel).

    The filehandles are assumed to be non-blocking.

    Please note that nbfile supports line buffering (write_buffer_limit=1),
    but it doesn't set up write buffering by default for terminal devices.
    For that, please use our fdopen (defined below).

    Please note that changing self.write_buffer_limit doesn't flush the
    write buffer, but it will affect subsequent self.write(...) operations.
    """
    # We must keep self.wakeup_ev on the heap, because
    # Stackless scheduling swaps the C stack.
    cdef object close_ref
    cdef event_t read_wakeup_ev
    # We have different event buffers for reads and writes, because one tasklet
    # might be waiting for read, and another one waiting for write.
    # !! what if multiple tasklets waiting for read?
    cdef event_t write_wakeup_ev
    cdef int read_fd
    cdef int write_fd
    # This must not be negative. Allowed values:
    # 0: (compatible with Python `file') no buffering, call write(2)
    #    immediately
    # 1: (compatible with Python `file', unimplemented) line buffering
    #    Just like Python `file', this setting flushes partial lines with >=
    #    DEFAULT_WRITE_BUFFER_LIMIT bytes long.
    # 2: infinite buffering, until an explicit flush
    # >=3: use the value for the buffer size in bytes
    cdef int c_write_buffer_limit
    cdef int c_min_read_buffer_size
    # Maximum number of bytes to be read from self.read_fd, or -1 if unlimited.
    # Please note that the bytes already read to se.fread_eb are not counted in
    # c_read_limit.
    cdef int c_read_limit
    cdef evbuffer_s read_eb
    cdef evbuffer_s write_eb
    cdef char c_do_close
    cdef char c_closed
    cdef char c_softspace
    cdef object c_mode
    cdef object c_name
    cdef object c_read_exc_class
    cdef object c_write_exc_class

    def __init__(nbfile self, int read_fd, int write_fd,
                 int write_buffer_limit=-1, int min_read_buffer_size=-1,
                 char do_set_fd_nonblocking=1,
                 char do_close=0,
                 object close_ref=None, object mode='r+',
                 object name=None):
        assert read_fd >= 0 or mode == 'w'
        assert write_fd >= 0 or mode == 'r'
        assert mode in ('r', 'w', 'r+')
        self.c_read_limit = -1
        self.c_do_close = do_close
        self.c_read_exc_class = IOError
        self.c_write_exc_class = IOError
        self.read_fd = read_fd
        self.write_fd = write_fd
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
            event_set(&self.read_wakeup_ev, read_fd, c_EV_READ,
                      HandleCWakeup, NULL)
        if write_fd >= 0:
            event_set(&self.write_wakeup_ev, write_fd, c_EV_WRITE,
                      HandleCWakeup, NULL)

    def fileno(nbfile self):
        if self.read_fd >= 0:
            return self.read_fd
        else:
            return self.write_fd

    # This method is not present in standard file.
    def write_fileno(nbfile self):
        return self.write_fd

    # !! TODO: SUXX: __dealloc__ is not allowed to call close() or flush()
    #          (too late, see Pyrex docs), __del__ is not special
    def __dealloc__(nbfile self):
        self.close()

    def close(nbfile self):
        cdef int got
        try:
            if self.write_eb.off > 0:
                # This can raise self.c_write_exc_class.
                self.flush()
        finally:
            if not self.c_closed:
                self.c_closed = 1
                if self.c_do_close:
                    if self.close_ref is None:
                        if self.read_fd >= 0:
                            got = close(self.read_fd)
                            if got < 0:
                                exc = self.c_write_exc_class(errno, strerror(errno))
                                close(self.write_fd)
                                raise exc
                        if (self.read_fd != self.write_fd and
                            self.write_fd > 0):
                            got = close(self.write_fd)
                            if got < 0:
                                raise self.c_write_exc_class(errno, strerror(errno))
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

    property read_limit:
        # TODO(pts): How is the property docstring propagated?
        """Maximum number of bytes to read from the file.

        Negative values stand for unlimited. After each read from the file
        (not from the buffer), this property is decremented accordingly.
        
        It is possible to set this property. A nonnegative value activates
        the limit, a negative value makes it unlimited.
        """
        def __get__(nbfile self):
            return self.c_read_limit
        def __set__(nbfile self, int new_value):
            self.c_read_limit = new_value

    property read_exc_class:
        def __get__(nbfile self):
            return self.c_read_exc_class
        def __set__(nbfile self, object new_value):
            self.c_read_exc_class = new_value

    property write_exc_class:
        def __get__(nbfile self):
            return self.c_write_exc_class
        def __set__(nbfile self, object new_value):
            self.c_write_exc_class = new_value

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
        if PyObject_AsCharBuffer(buf, &p, &n) < 0:
            raise TypeError
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

    def write(nbfile self, object buf):
        # TODO(pts): Flush the buffer eventually automatically.
        cdef char_constp p
        cdef Py_ssize_t k
        cdef Py_ssize_t n
        cdef int wlimit
        cdef int keepc
        if PyObject_AsCharBuffer(buf, &p, &n) < 0:
            raise TypeError
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
            return write_all_to_fd(self.write_fd, &self.write_wakeup_ev, p, n,
                                   self.c_write_exc_class)

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
                write_all_to_fd(self.write_fd, &self.write_wakeup_ev,
                                <char_constp>self.write_eb.buf,
                                self.write_eb.off,
                                self.c_write_exc_class)
                self.write_eb.buf = self.write_eb.orig_buffer
                self.write_eb.misalign = 0
                self.write_eb.off = 0
            else:
                if self.write_eb.off > 0:
                    # Flush self.write_eb.
                    write_all_to_fd(self.write_fd, &self.write_wakeup_ev,
                                    <char_constp>self.write_eb.buf,
                                    self.write_eb.off,
                                    self.c_write_exc_class)
                    self.write_eb.buf = self.write_eb.orig_buffer
                    self.write_eb.misalign = 0
                    self.write_eb.off = 0
                # Flush lines directly from the argument.
                write_all_to_fd(self.write_fd, &self.write_wakeup_ev, p, n,
                                self.c_write_exc_class)
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
                # TODO(pts): Speed: return early even if write_all_to_fd
                # couldn't write everything yet (EAGAIN). Do this everywhere.
                write_all_to_fd(self.write_fd, &self.write_wakeup_ev,
                                <char_constp>self.write_eb.buf,
                                self.write_eb.off,
                                self.c_write_exc_class)
                self.write_eb.buf = self.write_eb.orig_buffer
                self.write_eb.misalign = 0
                self.write_eb.off = 0

            if n >= wlimit:
                # Flush directly from the argument.
                write_all_to_fd(self.write_fd, &self.write_wakeup_ev, p, n,
                                self.c_write_exc_class)
            else:
                if self.write_eb.totallen == 0:
                    evbuffer_expand(&self.write_eb, wlimit)
                evbuffer_add(&self.write_eb, <void_constp>p, n)

    def flush(nbfile self):
        # Please note that this method may raise an error even if parts of the
        # buffer has been flushed.
        if self.write_eb.off > 0:
            write_all_to_fd(self.write_fd, &self.write_wakeup_ev,
                            <char_constp>self.write_eb.buf, self.write_eb.off,
                            self.c_write_exc_class)
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

    def discard(nbfile self, int n):
        """Read and discard exactly n bytes.

        Please note that self.read_fd won't be read past the n bytes specified.
        TODO(pts): Add an option to speed up HTTP keep-alives by batching
        multiple read requests.

        Args:
          n: Number of bytes to discard. Negative values are treated as 0.
        Returns:
          The number of bytes not discarded because of EOF.
        Raises:
          self.c_read_exc_cass or IOError: (but not EOFError)
        """
        cdef int got
        if n <= 0:
            return 0
        if self.read_eb.off > 0:
            if self.read_eb.off >= n:
                evbuffer_drain(&self.read_eb, n)
                return 0
            evbuffer_drain(&self.read_eb, n)  # Discard everything.
            n -= self.read_eb.off
        while 1:  # n > 0
            if self.c_read_limit >= 0 and n > self.c_read_limit:
                got = self.c_read_limit
                if got == 0:
                    return n
            else:
                got = n
            if self.read_eb.totallen == 0:
                # Expand to the next power of 2.
                evbuffer_expand(&self.read_eb, self.c_min_read_buffer_size)
            got = nbevent_read(&self.read_eb, self.read_fd, got)
            if got < 0:
                if errno != EAGAIN:
                    raise self.c_read_exc_class(errno, strerror(errno))
                coio_c_wait(&self.read_wakeup_ev, NULL)
            elif got == 0:  # EOF
                return n
            else:
                n -= got
                if self.c_read_limit >= 0:
                    self.c_read_limit -= got
                evbuffer_drain(&self.read_eb, got)
                if n == 0:
                    return 0

    def discard_to_read_limit(nbfile self):
        """Discard the read buffer, and discard bytes from read_fd.

        If there is no read limit set up, than no bytes will be discarded
        from read_fd.

        Returns:
          The number of bytes not discarded because of EOF.
        Raises:
          self.c_read_exc_cass or IOError: (but not EOFError)
        """
        if self.read_eb.off > 0:
            evbuffer_drain(&self.read_eb, self.read_eb.off)
            #assert self.c_read_limit == 0
        if self.c_read_limit > 0:
            # TODO(pts): Speed this up by not doing a Python method call.
            return self.discard(self.c_read_limit)
        else:
            return 0

    def wait_for_readable(nbfile self, object timeout=None):
        cdef event_t *wakeup_ev_ptr
        cdef timeval tv
        cdef double timeout_double
        # !! TODO(pts): Speed: return early if already readable.
        if timeout is None:
            coio_c_wait(&self.read_wakeup_ev, NULL)
            return True
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
                self.read_fd, c_EV_READ, HandleCTimeoutWakeup, &tv
                ) is event_happened_token

    def read(nbfile self, int n):
        """Read exactly n bytes (or less on EOF), and return string

        Args:
          n: Number of bytes to read. Negative values are not allowed.
        Returns:
          String containing the bytes read; an empty string on EOF.
        Raises:
          self.c_read_exc_class or IOError: (but not EOFError)
        """
        cdef int got
        cdef object buf

        if n < 0:
            raise NotImplementedError  # TODO(pts): Read up to EOF.

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

        if self.c_read_limit >= 0:
            got = self.c_read_limit + self.read_eb.off
            if n > got:
                n = got
            if n <= 0:
                return ''
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
            got = nbevent_read(&self.read_eb, self.read_fd, got)
            if got < 0:
                if errno != EAGAIN:
                    raise self.c_read_exc_class(errno, strerror(errno))
                coio_c_wait(&self.read_wakeup_ev, NULL)
            elif got == 0:  # EOF
                n = self.read_eb.off
                break
            else:
                if self.c_read_limit >= 0:
                    self.c_read_limit -= got
        buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
        evbuffer_drain(&self.read_eb, n)
        return buf

    def read_at_most(nbfile self, int n):
        """Read at most n bytes and return the string.

        Negative values for n are not allowed.

        If the read buffer is not empty (self.read_buffer_len), data inside it
        will be returned, and no attempt is done to read self.read_fd.
        """
        cdef int got
        if n <= 0:
            if n < 0:
                raise NotImplementedError  # TODO(pts): Read up to EOF.
            return ''
        if self.read_eb.off > 0:
            if self.read_eb.off < n:
                n = self.read_eb.off
            buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
            evbuffer_drain(&self.read_eb, n)
            # TODO(pts): Maybe read more from fd, if available and flag.
            return buf
        if self.c_read_limit >= 0 and n > self.c_read_limit:
            n = self.c_read_limit
            if n <= 0:
                return ''
        while 1:
            # TODO(pts): Don't read it to the buffer, read without memcpy.
            #            We'd need the readinto method for that.
            got = nbevent_read(&self.read_eb, self.read_fd, n)
            if got < 0:
                if errno != EAGAIN:
                    raise self.c_read_exc_class(errno, strerror(errno))
                coio_c_wait(&self.read_wakeup_ev, NULL)
            elif got == 0:
                return ''
            else:
                buf = PyString_FromStringAndSize(
                    <char_constp>self.read_eb.buf, got)
                evbuffer_drain(&self.read_eb, got)
                if self.c_read_limit >= 0:
                    self.c_read_limit -= got
                return buf

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
        fd = self.read_fd
        had_short_read = 0
        min_off = 0
        if self.c_read_limit >= 0:
            if limit < 0 or limit > read_eb.off + self.c_read_limit:
                limit = read_eb.off + self.c_read_limit
        if limit >= 0:
            if limit == 0:
                return ''
            return nbfile_readline_with_limit(self, limit)
        #DEBUG assert limit < 0
        #DEBUG assert self.c_read_limit < 0
        q = <char_constp>memchr(<void_constp>read_eb.buf, c'\n', read_eb.off)
        while q == NULL:
            if had_short_read:
                evbuffer_expand(read_eb, 1)
            elif read_eb.totallen == 0:
                evbuffer_expand(read_eb, self.c_min_read_buffer_size)
            else:
                evbuffer_expand(read_eb, read_eb.totallen >> 1)
            # TODO(pts): fix bug in libevent-1.4.13 evbuffer_expand
            # need = buf->off + datlen when reallocing.
            n = read_eb.totallen - read_eb.off - read_eb.misalign

            got = nbevent_read(read_eb, fd, n)
            while got < 0:
                if errno != EAGAIN:
                    # TODO(pts): Do it more efficiently with Pyrex?
                    # Twisted does exactly this.
                    raise self.c_read_exc_class(errno, strerror(errno))
                coio_c_wait(&self.read_wakeup_ev, NULL)
                got = nbevent_read(read_eb, fd, n)

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
        got = isatty(self.read_fd)
        if got < 0:
            raise self.c_read_exc_class(errno, strerror(errno))
        elif got:
            return True
        else:
            return False

    def truncate(nbfile self, int size):
        # TODO(pts): Do we need this? It won't work for streams (like seek, tell)
        if ftruncate(self.read_fd, size) < 0:
            raise self.c_write_exc_class(errno, strerror(errno))

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
        """Return a nonnegative double, or -1.0 if there is no timeout.

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
        # Do a non-blocking DNS lookup if needed.
        # There is no need to predeclare c_gethostbyname in Pyrex.
        address = c_gethostbyname(address, self.realsock.family)

        while 1:
            err = self.realsock.connect_ex(address)
            if err:
                # We might get EALREADY occasionally for some slow connects.
                if err != EAGAIN and err != EINPROGRESS and err != EALREADY:
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
        # Do a non-blocking DNS lookup if needed.
        address = c_gethostbyname(address, self.realsock.family)

        while 1:
            err = self.realsock.connect_ex(address)
            # We might get EALREADY occasionally for some slow connects.
            if err != EAGAIN and err != EINPROGRESS and err != EALREADY:
                return err  # Inclusing `0' for success.

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

        The nbfile will be buffered, and its close method won't cause an
        os.close(self.swi.fd).

        This method is not part of normal sockets.
        """
        return nbfile(self.swi.fd, self.swi.fd, bufsize, bufsize,
                      do_set_fd_nonblocking=0)

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
        return nbfile(fd, fd, bufsize, bufsize, do_close=1, close_ref=self,
                      do_set_fd_nonblocking=0)


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

cdef int SSL_ERROR_EOF
cdef int SSL_ERROR_WANT_READ
cdef int SSL_ERROR_WANT_WRITE
try:
    import ssl
    sslsocket_impl = ssl.SSLSocket
    SSLError = ssl.SSLError
    SSL_ERROR_EOF = ssl.SSL_ERROR_EOF
    SSL_ERROR_WANT_READ = ssl.SSL_ERROR_WANT_READ
    SSL_ERROR_WANT_WRITE = ssl.SSL_ERROR_WANT_WRITE
except ImportError, e:
    sslsocket_impl = None
    ssl = None


cdef class sockwrapper:
    """A helper class for holding a self._sock."""
    cdef object c_sock

    def __init__(sockwrapper self, sock):
        self.c_sock = sock

    property _sock:
        def __get__(self):
            return self.c_sock



# !! TODO(pts): implement all NotImplementedError
# TODO(pts): Test timeout for connect and do_handshake.
# TODO(pts): Test timeout for send, recv.
# TODO(pts): Test timeout for makefile read, write.
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
            
    def fileno(nbsslsocket self):
        return self.swi.fd

    def dup(nbsslsocket self):
        """Duplicates to a non-SSL socket (as in SSLSocket.dup)."""
        # TODO(pts): Skip the fcntl2 in the set_fd_nonblocking call in the
        # constructor.
        return nbsocket(self.realsock.dup())

    # !! TODO: SUXX: __dealloc__ is not allowed to call close() or flush()
    #          (too late, see Pyrex docs), __del__ is not special
    def __dealloc__(nbfile self):
        self.close()

    def close(nbsslsocket self):
        self.sslsock.close()
        self.sslobj = self.sslsock._sslobj

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
            return self.sslsock._suppress_ragged_eofs

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
        while 1:
            try:
                return self.sslobj.read(len)
            except SSLError, e:
                if e.errno == SSL_ERROR_WANT_READ:
                    coio_c_handle_eagain(&self.swi, c_EV_READ)
                elif e.errno == SSL_ERROR_WANT_WRITE:
                    coio_c_handle_eagain(&self.swi, c_EV_WRITE)
                elif (e.errno == SSL_ERROR_EOF and
                      self.sslsock.suppress_ragged_eofs):
                    return ''
                else:
                    raise

    def write(nbsslsocket self, data):
        """Emulate ssl.SSLSocket.write, doesn't make much sense."""
        while 1:
            try:
                return self.sslobj.write(data)
            except SSLError, e:
                if e.errno == SSL_ERROR_WANT_READ:
                    coio_c_handle_eagain(&self.swi, c_EV_READ)
                elif e.errno == SSL_ERROR_WANT_WRITE:
                    coio_c_handle_eagain(&self.swi, c_EV_WRITE)
                else:
                    raise

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
        if self._sslobj:
            raise ValueError('attempt to connect already-connected SSLSocket!')
                    
        # Do a non-blocking DNS lookup if needed.
        # There is no need to predeclare c_gethostbyname in Pyrex.
        address = c_gethostbyname(address, self.realsock.family)

        while 1:
            err = self.realsock.connect_ex(address)
            if err:
                if err != EAGAIN and err != EINPROGRESS:
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
        except ssl.SSLError, e:
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
        while 1:
            try:
                self.sslobj.do_handshake()
                return
            except SSLError, e:
                if e.errno == SSL_ERROR_WANT_READ:
                    coio_c_handle_eagain(&self.swi, c_EV_READ)
                elif e.errno == SSL_ERROR_WANT_WRITE:
                    coio_c_handle_eagain(&self.swi, c_EV_WRITE)
                else:
                    raise

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
            while 1:
                try:
                    return self.sslobj.read(buflen)
                except SSLError, e:
                    if e.errno == SSL_ERROR_WANT_READ:
                        coio_c_handle_eagain(&self.swi, c_EV_READ)
                    elif e.errno == SSL_ERROR_WANT_WRITE:
                        coio_c_handle_eagain(&self.swi, c_EV_WRITE)
                    elif (e.errno == SSL_ERROR_EOF and
                          self.sslsock.suppress_ragged_eofs):
                        return ''
                    else:
                        raise
        return coio_c_socket_call(self.realsock.recv, (buflen, flags),
                                  &self.swi, c_EV_READ)

    def recvfrom(nbsslsocket self, *args):
        raise NotImplementedError  # !!
        return coio_c_socket_call(self.realsock.recvfrom, args,
                                  &self.swi, c_EV_READ)

    def recv_into(nbsslsocket self, *args):
        raise NotImplementedError  # !!
        return coio_c_socket_call(self.realsock.recv_into, args,
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
            while 1:
                try:
                    return self.sslobj.write(data)
                except SSLError, e:
                    if e.errno == SSL_ERROR_WANT_READ:
                        coio_c_handle_eagain(&self.swi, c_EV_READ)
                    elif e.errno == SSL_ERROR_WANT_WRITE:
                        coio_c_handle_eagain(&self.swi, c_EV_WRITE)
                    else:
                        raise
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
                    try:
                        got2 = 0  # Pacify gcc warning.
                        got2 = self.sslobj.write(buf)
                    except SSLError, e:
                        if e.errno == SSL_ERROR_WANT_READ:
                            coio_c_handle_eagain(&self.swi, c_EV_READ)
                        elif e.errno == SSL_ERROR_WANT_WRITE:
                            coio_c_handle_eagain(&self.swi, c_EV_WRITE)
                        else:
                            raise
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
                assert got2 > 0
                got += got2
                if got >= len(data):
                    return
                # It's not possible to modify (slice) an existing buffer, so
                # we create a new one.
                buf = buffer(data, got)

    def makefile(nbsslsocket self, mode='r+', int bufsize=-1):
        """Create an nbfile (non-blocking file-like) object from self.

        os.dup(self.swi.fd) will be passed to the new nbfile object, and its
        .close() method will close that file descriptor.

        As of now, the returned file object is slow (uses a pure Python
        implementation of socket._fileobject).

        Args:
          mode: 'r', 'w', 'r+' etc. The default is mode'r', just as for
            socket.socket.makefile.
        """
        # !! TODO(pts): Implement .makefile_samefd() using our fast buffering
        # (something similar to nbfile).
        self.sslsock._makefile_refs += 1
        return socket._fileobject(self, mode, bufsize, close=True)

if ssl:
    _fake_ssl_globals = {'SSLSocket': nbsslsocket}
    ssl_wrap_socket = types.FunctionType(
      ssl.wrap_socket.func_code, _fake_ssl_globals,
      None, ssl.wrap_socket.func_defaults)
    ssl_wrap_socket.__doc__ = (
        """Non-blocking drop-in replacement for ssl.wrap_socket.""")
else:
    globals()['nbsslsocket'] = None  


# --- Sleeping.

cdef void HandleCSleepWakeup(int fd, short evtype, void *arg) with gil:
    # Set tempval so coio_c_wait doesn't have to call event_del(...).
    if (<tasklet>arg).tempval is waiting_token:
        (<tasklet>arg).tempval = event_happened_token
    PyTasklet_Insert(<tasklet>arg)


def sleep(double duration):
    """Non-blocking drop-in replacement for time.sleep.

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
      (event_happened_token, a true value).
    """
    cdef timeval tv
    if duration <= 0:
        return
    tv.tv_sec = <long>duration
    tv.tv_usec = <unsigned int>((duration - <double>tv.tv_sec) * 1000000.0)
    # See #define evtimer_set(...) in event.h.
    return coio_c_wait_for(-1, 0, HandleCSleepWakeup, &tv)


# ---


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

    def __destroy__(selecter self):
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

    Please note that because of the slow speed of select(2), this function is
    provided only for completeness and for legacy application compatibility.
    """
    if xlist:
        raise NotImplementedError('except-filehandles for select')
    # TODO(pts): Simplify if len(rlist) == 1 and wlist is empty (etc.).
    return selecter().do_select(rlist, wlist, timeout)

# --- Twisted 10.0.0 syncless.reactor and Tornado support classes

cdef class wakeup_info

cdef void HandleCWakeupInfoWakeup(int fd, short evtype, void *arg) with gil:
    cdef wakeup_info wakeup_info_obj
    cdef int mode
    wakeup_info_obj = <wakeup_info>arg
    if fd >= 0:  # fd is -1 for a create_timer.
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

    # No need for `def __destroy__', Py_INCREF(self) above ensures that the
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
            timeout_event = wakeup_info_event(self, c_EV_TIMEOUT, -1,
                                              timeout)
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
        # Prevent automatic __dealloc__. So we don't have to def __dealloc__.
        Py_INCREF(self)
        Py_INCREF(handler)
        event_set(&self.ev, signum, c_EV_SIGNAL | c_EV_PERSIST,
                  HandleCSignal, <void*>handler)
        # Make loop() exit immediately of only EVLIST_INTERNAL events
        # were added. Add EVLIST_INTERNAL after event_set.
        self.ev.ev_flags |= EVLIST_INTERNAL
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
