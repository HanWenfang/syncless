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
# This code is designed for Stackless Python 2.6.
#

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

# TODO(pts): Port to greenlet.
# TODO(pts): port to pure Python + select() or epoll().
import stackless
import socket
import __builtin__

# These are some Pyrex magic declarations which will enforce type safety in
# our *.pxi files by turning GCC warnings about const and signedness to Pyrex
# errors.
#
# stdlib.h is not explicitly needed, but providing a from clause prevents
# Pyrex from generating a ``typedef''.
cdef extern from "stdlib.h":
    ctypedef struct char_const:
        pass
    ctypedef struct uchar_const:
        pass
    ctypedef struct uchar:
        pass
    ctypedef char_const* char_constp "char const*"
    ctypedef uchar_const* uchar_constp "unsigned char const*"
    ctypedef uchar* uchar_p "unsigned char*"
    ctypedef int size_t

cdef extern from "unistd.h":
    cdef int os_write "write"(int fd, char *p, int n)
    cdef int os_read "read"(int fd, char *p, int n)
    cdef int dup(int fd)
    cdef int close(int fd)
    cdef int isatty(int fd)
    cdef int ftruncate(int fd, int size)
cdef extern from "string.h":
    cdef void *memset(void *s, int c, size_t n)
cdef extern from "stdlib.h":
    cdef void free(void *p)
cdef extern from "errno.h":
    cdef extern int errno
    cdef extern char *strerror(int)
    cdef enum errno_dummy:
        EAGAIN
        EINPROGRESS
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

cdef extern from "event.h":
    struct evbuffer_s "evbuffer":
        uchar_p buf "buffer"
        uchar_p orig_buffer
        int misalign
        int totallen
        int off
    struct event_watermark:
        int low
        int high
    struct bufev_t "bufferevent":
        evbuffer_s *input
        event_watermark wm_read
        event_watermark wm_write

    # These must match other declarations of the same name.
    evbuffer_s *evbuffer_new()
    void evbuffer_free(evbuffer_s *)
    int evbuffer_expand(evbuffer_s *, int)
    int evbuffer_add(evbuffer_s *, char *, int)
    int evbuffer_remove(evbuffer_s *, void *, int)
    #char *evbuffer_readline(evbuffer_s *)
    int evbuffer_add_buffer(evbuffer_s *, evbuffer_s *)
    int evbuffer_drain(evbuffer_s *b, int size)
    int evbuffer_write(evbuffer_s *, int)
    int evbuffer_read(evbuffer_s *, int, int)
    uchar_p evbuffer_find(evbuffer_s *, uchar_constp, int)
    # void evbuffer_setcb(evbuffer_s *, void (*)(struct evbuffer_s *, int, int, void *), void *)

cdef extern from "Python.h":
    object PyString_FromFormat(char_constp fmt, ...)
    object PyString_FromStringAndSize(char_constp v, Py_ssize_t len)
    object PyString_FromString(char_constp v)
    int    PyObject_AsCharBuffer(object obj, char_constp *buffer, Py_ssize_t *buffer_len)
    object PyInt_FromString(char*, char**, int)
cdef extern from "frameobject.h":  # Needed by core/stackless_structs.h
    pass
cdef extern from "core/stackless_structs.h":
    ctypedef struct PyObject:
        pass
    # This is only for pointer manipulation with reference counting.
    ctypedef struct PyTaskletObject:
        PyTaskletObject *next
        PyTaskletObject *prev
        PyObject *tempval
cdef extern from "stackless_api.h":
    object PyStackless_Schedule(object retval, int remove)
    int PyStackless_GetRunCount()
    ctypedef class stackless.tasklet [object PyTaskletObject]:
        cdef object tempval
    ctypedef class stackless.bomb [object PyBombObject]:
        cdef object curexc_type
        cdef object curexc_value
        cdef object curexc_traceback
    # Return -1 on exception, 0 on OK.
    int PyTasklet_Insert(tasklet task) except -1
    int PyTasklet_Remove(tasklet task) except -1
    tasklet PyStackless_GetCurrent()
    #tasklet PyTasklet_New(type type_type, object func);

def SendExceptionAndRun(tasklet tasklet_obj, exc_info):
    """Send exception to tasklet, even if it's blocked on a channel.

    To get the tasklet is activated (to handle the exception) after
    SendException, call tasklet.run() after calling SendException.

    tasklet.insert() is called automatically to ensure that it eventually gets
    scheduled.
    """
    if not isinstance(exc_info, list) and not isinstance(exc_info, tuple):
        raise TypeError
    if tasklet_obj is PyStackless_GetCurrent():
        if len(exc_info) < 3:
            exc_info = list(exc_info) + [None, None]
        raise exc_info[0], exc_info[1], exc_info[2]
    bomb_obj = bomb(*exc_info)
    if tasklet_obj.blocked:
        c = tasklet_obj._channel
        old_preference = c.preference
        c.preference = 1    # Prefer the sender.
        for i in xrange(-c.balance):
            c.send(bomb_obj)
        c.preference = old_preference
    else:
        tasklet_obj.tempval = bomb_obj
    tasklet_obj.insert()
    tasklet_obj.run()

# Example code:
#def Sayer(object name):
#    while 1:
#        print name
#        PyStackless_Schedule(None, 0)  # remove

def LinkHelper():
    raise RuntimeError('LinkHelper tasklet called')

# TODO(pts): Experiment calling these from Python instead of C.
def MainLoop(tasklet link_helper_tasklet):
    #cdef PyTaskletObject *pprev
    #cdef PyTaskletObject *pnext
    cdef PyTaskletObject *ptemp
    cdef PyTaskletObject *p
    cdef PyTaskletObject *c
    o = PyStackless_GetCurrent()
    # Using c instead of o below prevents reference counting.
    c = <PyTaskletObject*>o
    p = <PyTaskletObject*>link_helper_tasklet
    assert c != p

    while 1:  # ``while 1`'' is more efficient in Pyrex than ``while True''
        #print 'MainLoop', PyStackless_GetRunCount()
        # !! TODO(pts): what if nothing registered and we're running MainLoop
        # maybe loop has returned true and
        # stackless.current.prev is stackless.current.

        # We add link_helper_tasklet to the end of the queue. All other
        # tasklets added by loop(...) below will be added between
        # link_helper_tasklet
        if p.next != NULL:
            PyTasklet_Remove(link_helper_tasklet)
        PyTasklet_Insert(link_helper_tasklet)

        # This runs 1 iteration of the libevent main loop: waiting for
        # I/O events and calling callbacks.
        #
        # Exceptions (if any) in event handlers would propagate to here.
        # !! would they? or only 1 exception?
        # Argument: nonblocking: don't block if nothing available.
        #
        # Each callback we (nbevent.pxi)
        # have registered is just a tasklet_obj.insert(), but others may have
        # registered different callbacks.
        #
        # We compare against 2 because of stackless.current
        # (main_loop_tasklet) and link_helper_tasklet.
        loop(PyStackless_GetRunCount() > 2)

        # Swap link_helper_tasklet and stackless.current in the queue.  We
        # do this so that the tasklets inserted by the loop(...) call above
        # are run first, preceding tasklets already alive. This makes
        # scheduling more fair on a busy server.
        #
        # The swap implementation would work even for p == c, or if p and c
        # are adjacent.
        ptemp = p.next
        p.next = c.next
        c.next = ptemp
        p.next.prev = p
        c.next.prev = c
        ptemp = p.prev
        p.prev = c.prev
        c.prev = ptemp
        p.prev.next = p
        c.prev.next = c

        PyTasklet_Remove(link_helper_tasklet)

        PyStackless_Schedule(None, 0)  # remove=0


# TODO(pts): Use a cdef, and hard-code event_add().
def SigIntHandler(ev, sig, evtype, arg):
    SendExceptionAndRun(stackless.main, (KeyboardInterrupt,))

cdef void set_fd_nonblocking(int fd):
    # This call works on Unix, but it's not portable (to e.g. Windows).
    # See also the #ifdefs in socketmodule.c:internal_setblocking().
    cdef int old
    # TODO(pts): Don't silently ignore the errors.
    old = fcntl2(fd, F_GETFL)
    if old >= 0 and (old & ~O_NONBLOCK):
        fcntl3(fd, F_SETFL, old | O_NONBLOCK)

def SetFdBlocking(int fd, is_blocking):
    """Set a file descriptor blocking or nonblocking.

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


cdef void HandleCTimeoutWakeup(int fd, short evtype, void *arg) with gil:
    # PyStackless_Schedule will return this.
    # No easier way to assign a bool in Pyrex.
    if evtype == c_EV_TIMEOUT:
        (<tasklet>arg).tempval = True
    else:
        (<tasklet>arg).tempval = False
    PyTasklet_Insert(<tasklet>arg)  # No NULL- or type checking.

cdef void HandleCWakeup(int fd, short evtype, void *arg) with gil:
    PyTasklet_Insert(<tasklet>arg)

# This works, but it assumes that c.prev is kept in the runnable list during
# the inserts.
#def RRR(tasklet a, tasklet b):
#    """Insert a, b, and make sure they run next."""
#    cdef PyTaskletObject *p
#    cdef PyTaskletObject *c
#    o = PyStackless_GetCurrent()
#    # This assignment prevents reference counting below.
#    c = <PyTaskletObject*>o
#    p = c.prev
#    PyTasklet_Insert(a);
#    PyTasklet_Insert(b);
#    if p != c:
#      # Move p (stackless.current) right after p.
#      # TODO(pts): More checks.
#      c.prev.next = c.next
#      c.next.prev = c.prev
#      c.next = p.next
#      c.next.prev = c
#      c.prev = p
#      p.next = c

cdef class evbuffer:
    """A Python wrapper around libevent's I/O buffer: struct evbuffer

    Please note that this buffer wastes memory: after reading a very long
    line, the buffer space won't be reclaimed until self.reset() is called.
    """
    # We don't need __cinit__ for memset(<void*>&self.eb, 0, sizeof(self.eb))
    # to mimic the calloc() in evbuffer_new(), because Pyrex ensures the
    # clearing of object memory.
    cdef evbuffer_s eb
    # We must keep self.wakeup_ev on the heap (not on the C stack), because
    # hard switching in Stackless scheduling swaps the C stack, and libevent
    # needs all pending event_t structures available.
    cdef event_t wakeup_ev

    def __repr__(evbuffer self):
        return '<evbuffer misalign=%s, totallen=%s, off=%s at 0x%x>' % (
            self.eb.misalign, self.eb.totallen, self.eb.off, <unsigned>self)

    def __len__(evbuffer self):
        return self.eb.off

    def reset(evbuffer self):
        """Clear the buffer and free associated memory."""
        cdef evbuffer_s *eb
        eb = &self.eb
        free(eb.orig_buffer)
        # TODO(pts): Use memset().
        eb.buf = NULL
        eb.orig_buffer = NULL
        eb.off = 0
        eb.totallen = 0
        eb.misalign = 0

    property totallen:
        def __get__(evbuffer self):
            return self.eb.totallen

    property misalign:
        def __get__(evbuffer self):
            return self.eb.misalign

    def expand(evbuffer self, int n):
        """Expand the available buffer space (self.totallen) to >= n bytes.

        As a side effect, may discard consumed data (self.misalign = 0).

        Please note that 256 bytes will always be reserved. Call self.reset()
        to get rid of everything.
        """
        if evbuffer_expand(&self.eb, n):
            raise MemoryError

    def drain(evbuffer self, int n):
        evbuffer_drain(&self.eb, n)

    def append(evbuffer self, buf):
        cdef char_constp p
        cdef Py_ssize_t n
        if PyObject_AsCharBuffer(buf, &p, &n) < 0:
            raise TypeError
        return evbuffer_add(&self.eb, <char*>p, n)

    def consume(evbuffer self, int n=-1):
        """Read, drain and return at most n (or all) from the beginning.

        The corresponding C function is evbuffer_remove()."""
        cdef int got
        cdef char *p
        if n > self.eb.off or n < 0:
            n = self.eb.off
        if n == 0:
            return ''
        buf = PyString_FromStringAndSize(<char_constp>self.eb.buf, n)
        evbuffer_drain(&self.eb, n)
        return buf
        #assert got == n  # Assertions turned on by default. Good.

    def peek(evbuffer self, int n=-1):
        """Read and return at most n (or all) from the beginning, no drain."""
        cdef int got
        cdef char *p
        if n > self.eb.off or n < 0:
            n = self.eb.off
        return PyString_FromStringAndSize(<char_constp>self.eb.buf, n)

    def find(evbuffer self, buf):
        cdef Py_ssize_t n
        cdef char_constp p
        cdef char *q
        # TODO(pts): Intern n == 1 strings.
        if PyObject_AsCharBuffer(buf, &p, &n) < 0:
            raise TypeError
        q = <char*>evbuffer_find(&self.eb, <uchar_constp>p, n)
        if q == NULL:
            return -1
        return q - <char*>self.eb.buf

    def append_clear(evbuffer self, evbuffer source):
        """Append source and clear source.

        The corresponding C function is evbuffer_add_buffer().
        """
        if 0 != evbuffer_add_buffer(&self.eb, &source.eb):
            raise RuntimeError

    def consumeline(evbuffer self):
        """Read, drain and return string ending with '\\n', or ''.

        An empty string is returned instead of a partial line at the end of
        the buffer.

        This method doesn't use evbuffer_readline(), which is not binary
        (char 0) safe.
        """
        cdef int n
        cdef char *q
        q = <char*>evbuffer_find(&self.eb, <uchar_constp>'\n', 1)
        if q == NULL:
            return ''
        n = q - <char*>self.eb.buf + 1
        buf = PyString_FromStringAndSize(<char_constp>self.eb.buf, n)
        evbuffer_drain(&self.eb, n)
        return buf

    def nb_accept(evbuffer self, object sock):
        cdef tasklet wakeup_tasklet
        while 1:
            try:
                return sock.accept()
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, sock.fileno(), c_EV_READ,
                          HandleCWakeup, <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1

    def nb_flush(evbuffer self, int fd):
        """Use self.append*, then self.nb_flush. Don't reuse self for reads."""
        # Please note that this method may raise an error even if parts of the
        # buffer has been flushed.
        cdef tasklet wakeup_tasklet
        cdef int n
        while self.eb.off > 0:
            n = evbuffer_write(&self.eb, fd)
            if n < 0:
                if errno != EAGAIN:
                    # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                    raise IOError(errno, strerror(errno))
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_WRITE, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1

    def nb_readline(evbuffer self, int fd):
        cdef tasklet wakeup_tasklet
        cdef int n
        cdef int got
        cdef char *q
        q = <char*>evbuffer_find(&self.eb, <uchar_constp>'\n', 1)
        while q == NULL:
            # !! don't do ioctl(FIONREAD) if not necessary (in libevent)
            # !! where do we get totallen=32768? evbuffer_read has a strange
            # buffer growing behavior.
            got = evbuffer_read(&self.eb, fd, 8192)
            if got < 0:
                if errno != EAGAIN:
                    # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                    raise IOError(errno, strerror(errno))
                # PyStackless_GetCurrent() contains a
                # Py_INCREF(wakeup_tasklet) call, and the beginning of the C
                # function body contains a Py_INCREF(self) with the
                # corresponding Py_DECREF at the end of the C function body
                # generated by Pyrex. This is enough to prevent the
                # reference counting and thus (as confirmed by Guide) the
                # garbage collector from freeing wakeup_tasklet and self until
                # this method returns. This is good.
                #
                # event_add() requires that self.wakeup_ev is not free()d until
                # the event handler gets called. We ensure this by the method
                # (nb_readline) calling Py_INCREF(self) right at the beginning.
                # Since self has a positive reference count, and it contains
                # self.wakeup_ev, self.wakeup_ev won't be freed.
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_READ, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1
            elif got == 0:  # EOF, return remaining bytes ('' or partial line)
                n = self.eb.off
                buf = PyString_FromStringAndSize(<char_constp>self.eb.buf, n)
                evbuffer_drain(&self.eb, n)
                return buf
            else:
                # TODO(pts): Find from later than the beginning (just as read).
                q = <char*>evbuffer_find(&self.eb, <uchar_constp>'\n', 1)
        n = q - <char*>self.eb.buf + 1
        buf = PyString_FromStringAndSize(<char_constp>self.eb.buf, n)
        evbuffer_drain(&self.eb, n)
        return buf

    def peekline(evbuffer self):
        """Read and return string ending with '\\n', or '', no draining.

        An empty string is returned instead of a partial line at the end of
        the buffer.
        """
        cdef int n
        cdef char *q
        q = <char*>evbuffer_find(&self.eb, <uchar_constp>'\n', 1)
        if q == NULL:
            return ''
        return PyString_FromStringAndSize(<char_constp>self.eb.buf,
                                          q - <char*>self.eb.buf + 1)

    def read_from_fd(evbuffer self, int fd, int n):
        """Read from file descriptor, append to self,

        Does a ioctl(fd, FIONREAD, &c) before reading to limit the wasted
        buffer space.

        The corresponding C function is evbuffer_read().

        Returns:
          The number of bytes read.
        Raises:
          IOError: With the corresponding errno.
        """
        cdef int got
        got = evbuffer_read(&self.eb, fd, n)
        if got < 0:
            # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
            raise IOError(errno, strerror(errno))
        return got

    def read_from_fd_again(evbuffer self, int fd, int n):
        """Read from file descriptor, append to self,

        Does a ioctl(fd, FIONREAD, &c) before reading to limit the wasted
        buffer space.

        The corresponding C function is evbuffer_read().

        Returns:
          The number of bytes read, or None on EAGAIN.
        Raises:
          IOError: With the corresponding errno.
        """
        cdef int got
        got = evbuffer_read(&self.eb, fd, n)
        if got < 0:
            if errno == EAGAIN:
                return None
            # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
            raise IOError(errno, strerror(errno))
        return got

    def write_to_fd(evbuffer self, int fd, int n=-1):
        """Write and drain n bytes to file descriptor fd.

        A similar but weaker C function is evbuffer_write().

        Returns:
          The number of bytes written, which is not zero unless self is empty.
        Raises:
          IOError: With the corresponding errno.
        """
        if n > self.eb.off or n < 0:
            n = self.eb.off
        if n > 0:
            # TODO(pts): Use send(...) or evbuffer_write() on Win32.
            n = os_write(fd, <char*>self.eb.buf, n)
            if n < 0:
                # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                raise IOError(errno, strerror(errno))
            evbuffer_drain(&self.eb, n)
        return n

    def write_to_fd_again(evbuffer self, int fd, int n=-1):
        """Write and drain n bytes to file descriptor fd.

        A similar but weaker C function is evbuffer_write().

        Returns:
          The number of bytes written, which is not zero unless self is empty;
          or None on EAGAIN.
        Raises:
          IOError: With the corresponding errno.
        """
        if n > self.eb.off or n < 0:
            n = self.eb.off
        if n > 0:
            # TODO(pts): Use send(...) or evbuffer_write() on Win32.
            n = os_write(fd, <char*>self.eb.buf, n)
            if n < 0:
                if errno == EAGAIN:
                    return None
                # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                raise IOError(errno, strerror(errno))
            evbuffer_drain(&self.eb, n)
        return n


# Forward declaration.
#cdef class iterator


# TODO(pts): Implement all methods.
# TODO(pts): Implement close().
# !! implement timeout (does socket._realsocket.makefile do that?)
cdef class nbfile:
    """A non-blocking file (I/O channel)."""
    # We must keep self.wakeup_ev on the heap, because
    # Stackless scheduling swaps the C stack.
    cdef object close_ref
    cdef event_t wakeup_ev
    cdef int read_fd
    cdef int write_fd
    cdef int write_buf_limit
    # Maximum number of bytes to be read from read_fd, or -1 if unlimited.
    # Please note that the bytes in read_eb are not counted in c_read_limit.
    cdef int c_read_limit
    cdef evbuffer_s read_eb
    cdef evbuffer_s write_eb
    cdef char c_do_close
    cdef char c_closed
    cdef char c_softspace
    cdef object c_mode
    cdef object c_name

    def __init__(nbfile self, int read_fd, int write_fd,
                 int write_buf_limit=8192, char do_close=0,
                 object close_ref=None, object mode='r+',
                 object name=None):
        assert read_fd >= 0
        assert write_fd >= 0
        self.c_read_limit = -1
        self.c_do_close = do_close
        self.read_fd = read_fd
        self.write_fd = write_fd
        self.write_buf_limit = write_buf_limit
        self.close_ref = close_ref
        self.c_mode = mode
        self.c_name = name
        # evbuffer_new() clears the memory area of the object with zeroes,
        # but Pyrex (and __cinit__) ensure that happens, so we don't have to
        # do that.

    def fileno(nbfile self):
        return self.read_fd

    # This method is not present in standard file.
    def write_fileno(nbfile self):
        return self.write_fd

    def close(nbfile self):
        cdef int got
        try:
            if self.write_eb.off > 0:
                self.flush()
        finally:
            if not self.c_closed:
                self.c_closed = 1
                if self.c_do_close:
                    if self.close_ref is None:
                        got = close(self.read_fd)
                        if got < 0:
                            exc = IOError(errno, strerror(errno))
                            close(self.write_fd)
                            raise exc
                        got = close(self.write_fd)
                        if got < 0:
                            raise IOError(errno, strerror(errno))
                    else:
                        close_ref = self.close_ref
                        self.close_ref = False
                        if close_ref is not False:
                            close_ref.close()

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
        def __get__(nbfile self):
            """Maximum number of bytes to read from the file.
            
            Negative values stand for unlimited. After each read from the file
            (not from the buffer), this property is decremented accordingly.
            
            It is possible to set this property.
            """
            return self.c_read_limit
        def __set__(nbfile self, int new_value):
            self.c_read_limit = new_value

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

    def write(nbfile self, object buf):
        # TODO(pts): Flush the buffer eventually automatically.
        cdef char_constp p
        cdef Py_ssize_t n
        if PyObject_AsCharBuffer(buf, &p, &n) < 0:
            raise TypeError
        # !! TODO(pts): Don't even temporarily overflow the buffer.
        # !! TODO(pts): Do line buffering with buffer size == 1.
        evbuffer_add(&self.write_eb, <char*>p, n)
        if self.write_eb.off >= self.write_buf_limit:
            self.flush()

    def flush(nbfile self):
        # Please note that this method may raise an error even if parts of the
        # buffer has been flushed.
        cdef tasklet wakeup_tasklet
        cdef int n
        cdef int fd
        fd = self.read_fd
        while self.write_eb.off > 0:
            n = evbuffer_write(&self.write_eb, fd)
            if n < 0:
                if errno != EAGAIN:
                    # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                    raise IOError(errno, strerror(errno))
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_WRITE, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1

    property read_buffer_len:
        def __get__(nbfile self):
            return self.read_eb.off

    property write_buffer_len:
        def __get__(nbfile self):
            return self.write_eb.off

    def discard(nbfile self, int n):
        """Read and discard exactly n bytes.

        Args:
          n: Number of bytes to discard. Negative values are treated as 0.
        Returns:
          The number of bytes not discarded because of EOF.
        Raises:
          IOError: (but not EOFError)
        """
        cdef tasklet wakeup_tasklet
        cdef int got
        if self.read_eb.off > 0:
            if self.read_eb.off >= n:
                self.read_eb.off -= n
                return 0
            n -= self.read_eb.off
            evbuffer_drain(&self.read_eb, self.read_eb.off)
        if n <= 0:
            return 0
        while 1:  # n > 0
            if self.c_read_limit >= 0 and n > self.c_read_limit:
                got = self.c_read_limit
                if got == 0:
                    return n
            else:
                got = n
            if got > 8192:
                got = 8192
            #assert got > 0  # true, but don't check it for speed reasons
            # !! don't do ioctl(FIONREAD) if not necessary (in libevent)
            got = evbuffer_read(&self.read_eb, self.read_fd, got)
            if got < 0:
                if errno != EAGAIN:
                    raise IOError(errno, strerror(errno))
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_READ, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1
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
        """Discard the read buffer, and discard bytes from read_fd."""
        if self.read_eb.off > 0:
            evbuffer_drain(&self.read_eb, self.read_eb.off)
            #assert self.c_read_limit == 0
        if self.c_read_limit > 0:
            # TODO(pts): Speed this up by not doing a Python method call.
            self.discard(self.c_read_limit)
            assert self.c_read_limit == 0

    def read(nbfile self, int n):
        """Read exactly n bytes (or less on EOF), and return string

        Args:
          n: Number of bytes to read. Negative values are treated as 0.
        Returns:
          String containing the bytes read; an empty string on EOF.
        Raises:
          IOError: (but not EOFError)
        """
        cdef tasklet wakeup_tasklet
        cdef int got
        cdef object buf
        if self.c_read_limit >= 0 and n > self.c_read_limit:
            n = self.c_read_limit
        if n <= 0:
            return ''
        while self.read_eb.off < n:  # Data not fully in the buffer.
            got = n - self.read_eb.off
            if got > 65536 and got > self.read_eb.totallen:
                # Limit the total number of bytes read to the double of the
                # read buffer size.
                # evbuffer_read() does someting similar, also involving
                # EVBUFFER_MAX_READ == 4096.
                got = self.read_eb.totallen
            # !! don't do ioctl(FIONREAD) if not necessary (in libevent)
            got = evbuffer_read(&self.read_eb, self.read_fd, got)
            if got < 0:
                if errno != EAGAIN:
                    raise IOError(errno, strerror(errno))
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_READ, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1
            elif got == 0:  # EOF
                n = self.read_eb.off
                break
            else:
                if self.c_read_limit >= 0:
                    self.c_read_limit -= got
                evbuffer_drain(&self.read_eb, got)
        buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
        evbuffer_drain(&self.read_eb, n)
        return buf

    def read_at_most(nbfile self, int n):
        """Read at most n bytes and return the string.

        If the read buffer is not empty (self.read_buffer_len), data inside it
        will be returned, and no attempt is done to read self.read_fd.
        """
        cdef tasklet wakeup_tasklet
        cdef int got
        if n <= 0:
            return ''
        if self.read_eb.off > 0:
            if self.read_eb.off < n:
                n = self.read_eb.off
            buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
            evbuffer_drain(&self.read_eb, n)
            if self.c_read_limit >= 0:
                self.c_read_limit -= n
            # TODO(pts): Maybe read more from fd, if available and flag.
            return buf
        if self.c_read_limit >= 0 and n > self.c_read_limit:
            n = self.c_read_limit
        while 1:
            # TODO(pts): Don't read it to the buffer, read without memcpy.
            #            We'd need the readinto method for that.
            got = evbuffer_read(&self.read_eb, self.read_fd, n)
            if got < 0:
                if errno != EAGAIN:
                    raise IOError(errno, strerror(errno))
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_READ, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1
            elif got == 0:
                return ''
            else:
                buf = PyString_FromStringAndSize(
                    <char_constp>self.read_eb.buf, got)
                evbuffer_drain(&self.read_eb, got)
                if self.c_read_limit >= 0:
                    self.c_read_limit -= got
                return buf

    def readline(nbfile self):
        cdef tasklet wakeup_tasklet
        cdef int n
        cdef int got
        cdef char *q
        cdef int fd
        fd = self.write_fd
        q = <char*>evbuffer_find(&self.read_eb, <uchar_constp>'\n', 1)
        while q == NULL:
            # !! don't do ioctl(FIONREAD) if not necessary (in libevent)
            # !! where do we get totallen=32768? evbuffer_read has a strange
            # buffer growing behavior.
            # !! read more than 8192 bytes if the buffer has space for that
            n = 8192
            if self.c_read_limit >= 0 and n > self.c_read_limit:
                n = self.c_read_limit
                if n == 0:
                    n = self.read_eb.off
                    buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
                    evbuffer_drain(&self.read_eb, n)
                    return buf
            got = evbuffer_read(&self.read_eb, fd, 8192)
            if got < 0:
                if errno != EAGAIN:
                    # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                    raise IOError(errno, strerror(errno))
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_READ, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1
            elif got == 0:  # EOF, return remaining bytes ('' or partial line)
                n = self.read_eb.off
                buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
                evbuffer_drain(&self.read_eb, n)
                return buf
            else:
                if self.c_read_limit >= 0:
                    self.c_read_limit -= got
                # TODO(pts): Find from later than the beginning (just as read).
                q = <char*>evbuffer_find(&self.read_eb, <uchar_constp>'\n', 1)
        n = q - <char*>self.read_eb.buf + 1
        buf = PyString_FromStringAndSize(<char_constp>self.read_eb.buf, n)
        evbuffer_drain(&self.read_eb, n)
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

    def isatty(nbfile self):
        cdef int got
        got = isatty(self.read_fd)
        if got < 0:
            raise IOError(errno, strerror(errno))
        elif got:
            return True
        else:
            return False

    def truncate(nbfile self, int size):
        # TODO(pts): Do we need this? It won't work for streams (like seek, tell)
        if ftruncate(self.read_fd, size) < 0:
            raise IOError(errno, strerror(errno))

# !! implement open(...) properly, with modes etc.
# !! prevent writing to a nonwritable file
# !! implement read()
# !! implement readinto()
# !! implement readlines()
# !! implement seek() and tell()
# !! implement writelines()

# Forward declaration.
cdef class nbsocket

# With `cdef void', an exception here would be ignored, so
# we just do a `cdef object'. We don't make this a method so it won't
# be virtual.
cdef object handle_eagain(nbsocket self, int evtype):
    cdef tasklet wakeup_tasklet
    if self.timeout_value == 0.0:
        raise socket.error(e.errno, strerror(e.errno))
    wakeup_tasklet = PyStackless_GetCurrent()
    if self.timeout_value < 0.0:
        event_set(&self.wakeup_ev, self.fd, evtype,
                  HandleCWakeup, <void *>wakeup_tasklet)
        event_add(&self.wakeup_ev, NULL)
        PyStackless_Schedule(None, 1)  # remove=1
    else:
        event_set(&self.wakeup_ev, self.fd, evtype,
                  HandleCTimeoutWakeup, <void *>wakeup_tasklet)
        event_add(&self.wakeup_ev, &self.tv)
        if PyStackless_Schedule(None, 1):  # remove=1
            # Same error message as in socket.socket.
            raise socket.error('timed out')

# Implementation backend class for sockets. Should be socket._socket.socket
# (which is the same as socket._realsocket)
socket_impl = socket._realsocket

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

    cdef event_t wakeup_ev
    cdef int fd
    # -1.0 if None (infinite timeout).
    cdef float timeout_value
    # Corresponds to timeout (if not None).
    cdef timeval tv
    cdef object sock
    cdef char c_do_close

    def __init__(nbsocket self, *args, **kwargs):
        if 'socket_impl' in kwargs:
            my_socket_impl = kwargs['socket_impl']
        else:
            my_socket_impl = socket_impl
        if args and isinstance(args[0], my_socket_impl):
            self.sock = args[0]
            assert len(args) == 1
        else:
            self.sock = my_socket_impl(*args)
        self.fd = self.sock.fileno()
        # TODO(pts): self.sock.setblocking(False) on non-Unix.
        set_fd_nonblocking(self.fd)
        self.timeout_value = -1.0

    def fileno(nbsocket self):
        return self.fd

    def dup(nbsocket self):
        # TODO(pts): Skip the fcntl2 in the set_fd_nonblocking call in the
        # constructor.
        return type(self)(self.sock.dup())

    def close(nbsocket self):
        if self.c_do_close:
            # self.sock.close() calls socket(2) + close(2) if the filehandle
            # was already closed.
            self.sock.close()
        else:
            # TODO(pts): Make this faster, and work without a new object.
            self.sock = socket._closedsocket()
        self.fd = -1
        # There is no method or attribute socket.closed or
        # socket._real_socket.closed(), so we don't implement one either.
        # We don't release the reference to self.sock here, to imitate
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

    property type:
        def __get__(self):
            return self.sock.type

    property family:
        def __get__(self):
            return self.sock.family

    property timeout:
        def __get__(self):
            """Return a nonnegative float, or -1.0 if there is no timeout.

            socket._realsocket has .timeout, socket.socket doesn't have it.
            """
            if self.timeout_value < 0:
                return None
            else:
                return self.timeout_value

    property proto:
        def __get__(self):
            return self.sock.proto

    def setsockopt(nbsocket self, *args):
        return self.sock.setsockopt(*args)

    def getsockopt(nbsocket self, *args):
        return self.sock.getsockopt(*args)

    def getsockname(nbsocket self, *args):
        return self.sock.getsockname(*args)

    def getpeername(nbsocket self, *args):
        return self.sock.getpeername(*args)

    def bind(nbsocket self, *args):
        return self.sock.bind(*args)

    def listen(nbsocket self, *args):
        return self.sock.listen(*args)

    def gettimeout(nbsocket self):
        if self.timeout_value < 0:
            return None
        else:
            return self.timeout_value

    def setblocking(nbsocket self, is_blocking):
        if is_blocking:
            self.timeout_value = None
        else:
            self.timeout_value = 0.0
            self.tv.tv_sec = self.tv.tv_usec = 0

    def settimeout(nbsocket self, timeout):
        cdef float timeout_float
        if timeout is None:
            self.timeout_value = None
        else:
            timeout_float = timeout
            if timeout_float < 0.0:
                raise ValueError('Timeout value out of range')
            self.timeout_value = timeout_float
            self.tv.tv_sec = <long>timeout_float
            self.tv.tv_usec = <unsigned int>(
                (timeout_float - <float>self.tv.tv_sec) * 1000000.0)

    def accept(nbsocket self):
        while 1:
            try:
                asock, addr = self.sock.accept()
                esock = type(self)(asock)  # Create new nbsocket.
                return esock, addr
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_READ)

    def connect(nbsocket self, object address):
        # Do a non-blocking DNS lookup if needed.
        # There is no need to predeclare c_gethostbyname in Pyrex.
        address = c_gethostbyname(address, self.sock.family)

        while 1:
            err = self.sock.connect_ex(address)
            if err:
                if err != EAGAIN and err != EINPROGRESS:
                    raise socket.error(err, strerror(err))
                handle_eagain(self, c_EV_WRITE)
            else:
                return

    def connect_ex(nbsocket self, object address):
        # Do a non-blocking DNS lookup if needed.
        address = c_gethostbyname(address, self.sock.family)

        while 1:
            err = self.sock.connect_ex(address)
            if err != EAGAIN and err != EINPROGRESS:
                return err
            handle_eagain(self, c_EV_WRITE)

    def shutdown(nbsocket self, object how):
        while 1:
            err = self.sock.shutdown(how)
            if err != EAGAIN:
                return err
            # TODO(pts): Can this happen (with SO_LINGER?).
            handle_eagain(self, c_EV_WRITE)

    def recv(nbsocket self, *args):
        while 1:
            try:
                return self.sock.recv(*args)
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_READ)

    def recvfrom(nbsocket self, *args):
        while 1:
            try:
                return self.sock.recvfrom(*args)
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_READ)

    def recv_into(nbsocket self, *args):
        while 1:
            try:
                return self.sock.recv_into(*args)
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_READ)

    def recvfrom_into(nbsocket self, *args):
        while 1:
            try:
                return self.sock.recvfrom_into(*args)
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_READ)

    def send(nbsocket self, *args):
        while 1:
            try:
                return self.sock.send(*args)
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_WRITE)

    def sendto(nbsocket self, *args):
        while 1:
            try:
                return self.sock.sendto(*args)
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_WRITE)

    def sendall(nbsocket self, object data, int flags=0):
        cdef int got
        try:
            got = self.sock.send(data, flags)
            assert got > 0
        except socket.error, e:
            if e.errno != EAGAIN:
                raise
            handle_eagain(self, c_EV_WRITE)
            got = 0
        while got < len(data):
            try:
                got2 = self.sock.send(buffer(data, got), flags)
                assert got2 > 0
                got += got2
            except socket.error, e:
                if e.errno != EAGAIN:
                    raise
                handle_eagain(self, c_EV_WRITE)

    def makefile_samefd(nbsocket self, mode='r+', int bufsize=-1):
        """Create and return an nbfile with self.fd.

        The nbfile will be buffered, and its close method won't be cause an
        os.close(self.fd).

        This method is not part of normal sockets.
        """
        assert mode == 'r+'  # !! TODO(pts): Implement other modes
        return nbfile(self.fd, self.fd, bufsize)

    def makefile(nbsocket self, mode='r+', int bufsize=-1):
        """Create an nbfile (non-blocking file-like) object from self.

        os.dup(self.fd) will be passed to the new nbfile object, and its
        .close() method will close that file descriptor.
        """
        cdef int fd
        assert mode == 'r+'  # !! TODO(pts): Implement other modes
        fd = dup(self.fd)
        if fd < 0:
            raise socket.error(errno, strerror(errno))
        # TODO(pts): Verify proper close semantics for _realsocket emulation.
        return nbfile(fd, fd, bufsize, do_close=1, close_ref=self)


def new_realsocket(*args):
    """Non-blocking drop-in replacement for socket._realsocket.

    The most important difference between socket.socket and socket._realsocket
    is that socket._realsocket.close() closes the filehandle immediately,
    while socket.socket.close() just breaks the reference.
    """
    return nbsocket(*args).setdoclose(1)


def new_realsocket_fromfd(*args):
    """Non-blocking drop-in replacement for socket.fromfd."""
    return nbsocket(socket_fromfd(*args)).setdoclose(1)

cdef class sleeper:
    # We must keep self.wakeup_ev on the heap (not on the C stack), because
    # hard switching in Stackless scheduling swaps the C stack, and libevent
    # needs all pending event_t structures available.
    cdef event_t wakeup_ev

    def sleep(sleeper self, float duration):
        cdef tasklet wakeup_tasklet
        cdef timeval tv
        if duration > 0:
            wakeup_tasklet = PyStackless_GetCurrent()
            evtimer_set(&self.wakeup_ev, HandleCWakeup, <void*>wakeup_tasklet)
            event_add(&self.wakeup_ev, NULL)
            # TODO(pts): Optimize this for integers.
            tv.tv_sec = <long>duration
            tv.tv_usec = <unsigned int>(
                (duration - <float>tv.tv_sec) * 1000000.0)
            event_add(&self.wakeup_ev, &tv)
            PyStackless_Schedule(None, 1)  # remove=1

def sleep(float duration):
    """Non-blocking drop-in replacement for time.sleep."""
    # TODO(pts): Reuse existing sleepers (thread-local?) to speed this up.
    sleeper().sleep(duration)

# TODO(pts): Add new_file and nbfile(...)
# TODO(pts): If the buffering argument is given, 0 means unbuffered, 1 means
# line buffered, and larger numbers specify the buffer size.
