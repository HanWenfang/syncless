#### pts #### This file has been entirely written by pts@fazekas.hu.

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
cdef extern from "unistd.h":
    cdef int os_write "write"(int fd, char *p, int n)
    cdef int os_read "read"(int fd, char *p, int n)
cdef extern from "stdlib.h":
    cdef void free(void *p)
cdef extern from "errno.h":
    cdef extern int errno
    cdef extern char *strerror(int)
    cdef enum errno_dummy:
        EAGAIN
cdef extern from "fcntl.h":
    cdef int fcntl2 "fcntl"(int fd, int cmd)
    cdef int fcntl3 "fcntl"(int fd, int cmd, long arg)
    int O_NONBLOCK
    int F_GETFL
    int F_SETFL
cdef extern from "signal.h":
    int SIGINT

cdef extern from "event.h":
    struct evbuffer:
        char *buf "buffer"
        char *orig_buffer
        int misalign
        int totallen
        int off
    struct event_watermark:
        int low
        int high
    struct bufev_t "bufferevent":
        evbuffer *input
        event_watermark wm_read
        event_watermark wm_write

    # These must match other declarations of the same name.
    evbuffer *evbuffer_new()
    void evbuffer_free(evbuffer *)
    int evbuffer_expand(evbuffer *, int)
    int evbuffer_add(evbuffer *, char *, int)
    int evbuffer_remove(evbuffer *, void *, int)
    char *evbuffer_readline(evbuffer *)
    int evbuffer_add_buffer(evbuffer *, evbuffer *)
    int evbuffer_drain(evbuffer *b, int size)
    int evbuffer_write(evbuffer *, int)
    int evbuffer_read(evbuffer *, int, int)
    char *evbuffer_find(evbuffer *, void*, int)
    # void evbuffer_setcb(evbuffer *, void (*)(struct evbuffer *, int, int, void *), void *)

cdef extern from "frameobject.h":  # Needed by core/stackless_structs.h
    pass
cdef extern from "core/stackless_structs.h":
    ctypedef struct PyTaskletObject:
        PyTaskletObject *next
        PyTaskletObject *prev

cdef extern from "stackless_api.h":
    object PyStackless_Schedule(object retval, int remove)
    int PyStackless_GetRunCount()
    ctypedef class stackless.tasklet [object PyTaskletObject]:
      pass
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
    bomb = stackless.bomb(*exc_info)
    if tasklet_obj.blocked:
        c = tasklet_obj._channel
        old_preference = c.preference
        c.preference = 1    # Prefer the sender.
        for i in xrange(-c.balance):
            c.send(bomb)
        c.preference = old_preference
    else:
        tasklet_obj.tempval = bomb
    tasklet_obj.insert()
    tasklet_obj.run()

# Example code:
#def Sayer(object name):
#    while True:
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

    while True:
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


def SetFdBlocking(int fd, is_blocking):
    """Set a file descriptor blocking or nonblocking.

    Please note that this may affect more than expected, for example it may
    affect sys.stderr when called for sys.stdout.

    Returns:
        The old blocking value (True or False).
    """
    cdef int old
    cdef int value
    old = fcntl2(fd, F_GETFL)
    if is_blocking:
        value = old & ~O_NONBLOCK
    else:
        value = old | O_NONBLOCK
    if old != value:
        fcntl3(fd, F_SETFL, value)
    return bool(old & O_NONBLOCK)


cdef void HandleCWakeup(int fd, short evtype, void *arg) with gil:
    PyTasklet_Insert(<tasklet>arg)  # No null or type checking.

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

cdef class evbufferobj:
    """A Python wrapper around libevent's I/O buffer: struct evbuffer

    Please note that this buffer wastes memory: after reading a very long
    line, the buffer space won't be reclaimed until self.reset() is called.
    """
    cdef evbuffer *eb
    # We must keep self.wakeup_ev on the heap, because
    # Stackless scheduling swaps the C stack.
    cdef event_t wakeup_ev

    def __cinit__(evbufferobj self):
        self.eb = evbuffer_new()

    def __dealloc__(evbufferobj self):
        evbuffer_free(self.eb)

    def __repr__(evbufferobj self):
        return '<evbufferobj misalign=%s, totallen=%s, off=%s at 0x%x>' % (
            self.eb.misalign, self.eb.totallen, self.eb.off, <unsigned>self)

    def __len__(evbufferobj self):
        return self.eb.off

    def reset(evbufferobj self):
        """Clear the buffer and free associated memory."""
        cdef evbuffer *eb
        eb = self.eb
        free(eb.orig_buffer)
        # TODO(pts): Use memset().
        eb.buf = NULL
        eb.orig_buffer = NULL
        eb.off = 0
        eb.totallen = 0
        eb.misalign = 0

    def expand(evbufferobj self, int n):
        """As a side effect, may discard consumed data.

        Please note that 256 bytes will always be reserved. Call self.reset()
        to get rid of everything.
        """
        return evbuffer_expand(self.eb, n)

    def drain(evbufferobj self, int n):
        evbuffer_drain(self.eb, n)

    def append(evbufferobj self, buf):
        cdef char *p
        cdef int n
        if PyObject_AsCharBuffer(buf, &p, &n) < 0:
            raise TypeError
        return evbuffer_add(self.eb, p, n)

    def consume(evbufferobj self, int n=-1):
        """Read, drain and return at most n (or all) from the beginning.

        The corresponding C function is evbuffer_remove()."""
        cdef int got
        cdef char *p
        if n > self.eb.off or n < 0:
            n = self.eb.off
        if n == 0:
            return ''
        buf = PyString_FromStringAndSize(self.eb.buf, n)
        evbuffer_drain(self.eb, n)
        return buf
        #assert got == n  # Assertions turned on by default. Good.

    def peek(evbufferobj self, int n=-1):
        """Read and return at most n (or all) from the beginning, no drain."""
        cdef int got
        cdef char *p
        if n > self.eb.off or n < 0:
            n = self.eb.off
        return PyString_FromStringAndSize(self.eb.buf, n)

    def find(evbufferobj self, buf):
        cdef int n
        cdef char *p
        cdef char *q
        # TODO(pts): Intern n == 1 strings.
        if PyObject_AsCharBuffer(buf, &p, &n) < 0:
            raise TypeError
        q = evbuffer_find(self.eb, p, n)
        if q == NULL:
            return -1
        return q - <char*>self.eb.buf

    def append_clear(evbufferobj self, evbufferobj source):
        """Append source and clear source.

        The corresponding C function is evbuffer_add_buffer().
        """
        if 0 != evbuffer_add_buffer(self.eb, source.eb):
            raise RuntimeError

    def consumeline(evbufferobj self):
        """Read, drain and return string ending with '\\n', or ''.

        An empty string is returned instead of a partial line at the end of
        the buffer.

        This method doesn't use evbuffer_readline(), which is not binary
        (char 0) safe.
        """
        cdef int n
        cdef char *q
        q = evbuffer_find(self.eb, '\n', 1)
        if q == NULL:
            return ''
        n = q - <char*>self.eb.buf + 1
        buf = PyString_FromStringAndSize(self.eb.buf, n)
        evbuffer_drain(self.eb, n)
        return buf

    def nb_accept(evbufferobj self, object sock):
        cdef tasklet wakeup_tasklet
        while True:
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

    def nb_flush(evbufferobj self, int fd):
        """Use self.append*, then self.nb_flush. Don't reuse self for reads."""
        # Please note that this method may raise an error even if parts of the
        # buffer has been flushed.
        cdef tasklet wakeup_tasklet
        cdef int n
        while self.eb.off > 0:
            n = evbuffer_write(self.eb, fd)
            if n < 0:
                if errno != EAGAIN:
                    # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                    raise IOError(errno, strerror(errno))
                wakeup_tasklet = PyStackless_GetCurrent()
                event_set(&self.wakeup_ev, fd, c_EV_WRITE, HandleCWakeup,
                          <void *>wakeup_tasklet)
                event_add(&self.wakeup_ev, NULL)
                PyStackless_Schedule(None, 1)  # remove=1

    def nb_readline(evbufferobj self, int fd):
        cdef tasklet wakeup_tasklet
        cdef int n
        cdef int got
        cdef char *q
        q = evbuffer_find(self.eb, '\n', 1)
        while q == NULL:
            # !! don't do ioctl(FIONREAD) if not necessary (in libevent)
            # !! where do we get totallen=32768? evbuffer_read has a strange
            # buffer growing behavior.
            got = evbuffer_read(self.eb, fd, 8192)
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
                buf = PyString_FromStringAndSize(self.eb.buf, n)
                evbuffer_drain(self.eb, n)
                return buf
            else:
                # TODO(pts): Find from later than the beginning (just as read).
                q = evbuffer_find(self.eb, '\n', 1)
        n = q - <char*>self.eb.buf + 1
        buf = PyString_FromStringAndSize(self.eb.buf, n)
        evbuffer_drain(self.eb, n)
        return buf

    def peekline(evbufferobj self):
        """Read and return string ending with '\\n', or '', no draining.

        An empty string is returned instead of a partial line at the end of
        the buffer.
        """
        cdef int n
        cdef char *q
        q = evbuffer_find(self.eb, '\n', 1)
        if q == NULL:
            return ''
        return PyString_FromStringAndSize(self.eb.buf,
                                          q - <char*>self.eb.buf + 1)

    def read_from_fd(evbufferobj self, int fd, int n):
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
        got = evbuffer_read(self.eb, fd, n)
        if got < 0:
            # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
            raise IOError(errno, strerror(errno))
        return got

    def read_from_fd_again(evbufferobj self, int fd, int n):
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
        got = evbuffer_read(self.eb, fd, n)
        if got < 0:
            if errno == EAGAIN:
                return None
            # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
            raise IOError(errno, strerror(errno))
        return got

    def write_to_fd(evbufferobj self, int fd, int n=-1):
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
            n = os_write(fd, self.eb.buf, n)
            if n < 0:
                # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                raise IOError(errno, strerror(errno))
            evbuffer_drain(self.eb, n)
        return n

    def write_to_fd_again(evbufferobj self, int fd, int n=-1):
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
            n = os_write(fd, self.eb.buf, n)
            if n < 0:
                if errno == EAGAIN:
                    return None
                # TODO(pts): Do it more efficiently with pyrex? Twisted does this.
                raise IOError(errno, strerror(errno))
            evbuffer_drain(self.eb, n)
        return n
