/*
 * coio_c_helper.h: helper functions implemented in pure C (not Pyrex)
 * by pts@fazekas.hu at Sat Apr 17 00:55:39 CEST 2010
 * #### pts #### This file has been entirely written by pts@fazekas.hu.
 *
 */

/* --- Event pool */

/** Not 16384 to give some space for malloc's linked list headers. */
/* TODO(pts): Evaluate how much malloc headers need. */
#define COIO_EVENT_POOL_BLOCK_COUNT (16300 / sizeof(struct event))

static struct event *coio_event_pool_first_free = NULL;

/** Release an event allocated by coio_event_pool_malloc_event.
 * Just put the event back to the free list, never shrink the event pool.
 */
static void coio_event_pool_free_event(struct event *ev) {
#ifndef NDEBUG
  memset(ev, '\0', sizeof*ev);
#endif
  *(struct event**)ev = coio_event_pool_first_free;
  coio_event_pool_first_free = ev;
}

/** Allocate a new struct event and return its address.
 * Structures are allocated from the event pool, if there are unused events
 * there. If there aren't, the event pool is extended with 1 block (about
 * 16300 bytes).
 *
 * This function returns NULL on out-of-memory.
 */
static struct event* coio_event_pool_malloc_event(void) {
  if (coio_event_pool_first_free != NULL) {
    struct event* ev = coio_event_pool_first_free;
    coio_event_pool_first_free = *(struct event**)ev;
#ifndef NDEBUG  /* TODO(pts): Mark as uninitialized for valgrind. */
    memset(ev, '\0', sizeof*ev);
#endif
    return ev;
  } else {
    int i;
    /* COMPILE_ASSERT(COIO_EVENT_POOL_BLOCK_COUNT > 0) */
    /* We must keep the event_t structures on the heap (not on the C stack),
     * because hard switching in Stackless scheduling swaps the C stack, and
     * that would clobber our event_t with another tasklet's data, and
     * libevent needs all pending event_t structures always available.
     */
    struct event* ev = PyMem_Malloc(
        COIO_EVENT_POOL_BLOCK_COUNT * sizeof(struct event));
    if (ev == NULL)
      return NULL;
    coio_event_pool_first_free = &ev[1];
    for (i = 1; i < COIO_EVENT_POOL_BLOCK_COUNT - 1; ++i) {
      *(struct event**)&ev[i] = &ev[i + 1];
    }
    *(struct event**)&ev[COIO_EVENT_POOL_BLOCK_COUNT - 1] = NULL;
    return ev;
  }
}

/* --- Waiting */

static PyObject *coio_waiting_token;
static PyObject *coio_event_happened_token;

/**
 * Make the current tasklet wait on event ev with the specified timeout,
 * expecting to be woken up (and the event deleted) or an exception raised
 * (and the event either deleted or not, this function will delete it).
 *
 * This function follows the Python ABI and it's exception-safe.
 *
 * Call event_add(ev, timeout), then call
 * PyStackless_Schedule(Py_None, do_remove), and if it raises an
 * exception, call event_del(ev) before propagating the exception.
 *
 * The return value is the tasklet_obj.tempval, or NULL if that was a
 * stackless.bomb.
 *
 * Please note that HandleWakeup and HandleCWakeup changes the tasklet's
 * tempval (as returned by PyStackless_Schedule) to a non-None value.
 */
static inline PyObject *coio_c_wait(struct event *ev,
                                    const struct timeval *timeout) {
  PyObject *tempval;
  struct event *ev2 = NULL;
  if (ev->ev_arg != NULL) {  /* Event in use */
    ev2 = coio_event_pool_malloc_event();
    if (ev2 == NULL) {
      PyErr_NoMemory();
      return NULL;
    }
    /*write(2, "M", 1);*/
    event_set(ev2, ev->ev_fd, ev->ev_events, ev->ev_callback,
              PyStackless_GetCurrent());
    ev = ev2;
  } else {
    ev->ev_arg = PyStackless_GetCurrent();  /* implicit Py_INCREF */
  }
  event_add(ev, timeout);
  /* This also sets stackless.current.tempval = coio_waiting_token */
  tempval = PyStackless_Schedule(coio_waiting_token, /*do_remove:*/1);
  Py_DECREF(((PyObject*)ev->ev_arg));  /* stackless.current above */
  if (tempval != coio_event_happened_token) {
    /* We also run this on an exception (tempval == 0). */
    event_del(ev);  /* harmless if event_del(ev) has already been called */
  }
  if (ev2 == NULL) {
    ev->ev_arg = NULL;  /* Mark ev as unused. */
  } else {
    coio_event_pool_free_event(ev2);
  }
  return tempval;
}

/**
 * Wait in the current tasklet for (fd, evtype) or timeout to happen, call
 * callback with arg == stackless.current, return what callback has put to
 * stackless.current.tempval (or raise it if it's a bomb).
 *
 * This function follows the Python ABI and it's exception-safe.
 *
 * The struct event structure is allocated dynamically.
 */
static inline PyObject *coio_c_wait_for(
    int fd,
    short evtype,
    void (*callback)(int, short, void*),
    struct timeval *timeout) {
  PyObject *tempval;
  struct event *ev = coio_event_pool_malloc_event();
  if (ev == NULL) {
    PyErr_NoMemory();
    return NULL;
  }
  /* implicit Py_INCREF */
  event_set(ev, fd, evtype, callback, PyStackless_GetCurrent());
  event_add(ev, timeout);
  /* This also sets stackless.current.tempval = None */
  tempval = PyStackless_Schedule(coio_waiting_token, /*do_remove:*/1);
  Py_DECREF(((PyObject*)ev->ev_arg));  /* stackless.current above */
  if (tempval != coio_event_happened_token) {
    /* We also run this on an exception (tempval == 0). */
    event_del(ev);  /* harmless if event_del(ev) has already been called */
  }
  coio_event_pool_free_event(ev);
  return tempval;
}

static inline int coio_loaded(void) {
  static char loaded = 0;
  if (loaded) return 1;
  loaded = 1;
  return 0;
}

struct coio_socket_wakeup_info {
  struct event read_ev;
  struct event write_ev;
  double timeout_value;
  int fd;
  struct timeval tv;
};

static PyObject *coio_socket_error;
static PyObject *coio_socket_timeout;

static inline PyObject *coio_c_handle_eagain(
    struct coio_socket_wakeup_info *swi,
    short evtype) {
  /*
  cdef event_t *wakeup_ev
  if evtype == c_EV_READ:
      wakeup_ev = &swi.read_ev
  elif evtype == c_EV_WRITE:
      wakeup_ev = &swi.write_ev
  if swi.timeout_value == 0.0:
      raise socket_error(EAGAIN, strerror(EAGAIN))
  if swi.timeout_value < 0.0:
      coio_c_wait(wakeup_ev, NULL)
  else:
      if coio_c_wait(wakeup_ev, &swi.tv) is not event_happened_token:
          # Same error message as in socket.socket.
          raise socket_error('timed out')
  */
  PyObject *retval;
  struct event *wakeup_ev;
  if (swi->timeout_value == 0.0)
    return PyErr_SetFromErrno(coio_socket_error);
  wakeup_ev =
      evtype == EV_READ ?  &swi->read_ev :
      evtype == EV_WRITE ? &swi->write_ev : 0;
  if (swi->timeout_value < 0.0)
    return coio_c_wait(wakeup_ev, NULL);
  retval = coio_c_wait(wakeup_ev, &swi->tv);
  if (retval != coio_event_happened_token && retval != NULL) {
    Py_DECREF(retval);
    PyErr_SetString(coio_socket_timeout, "timed out");
    return NULL;
  }
  return retval;
}

static inline PyObject *coio_c_socket_call(PyObject *function, PyObject *args,
                                           struct coio_socket_wakeup_info *swi,
                                           short evtype) {
  /*
  while 1:
    try:
      return function(*args)
    except socket_error, e:
      if e.args[0] != EAGAIN:
        raise
      handle_eagain(swi, evtype)
  */
  /* TODO(pts): Ensure there are no memory leaks. */
  PyObject *retval;
  PyObject *ptype, *pvalue, *ptraceback;
  while (1) {
    retval = PyObject_CallObject(function, args);
    if (retval != NULL) return retval;
    if (!PyErr_ExceptionMatches(coio_socket_error)) return NULL;
    PyErr_Fetch(&ptype, &pvalue, &ptraceback);
    assert(pvalue != NULL);
    /* AnyException('foo', ...)[0] yields 'foo', no need for exc.args[0]
     * in Python 2.x (but needed in 3.x).
     */
    retval = PySequence_GetItem(pvalue, 0);
    if (retval == NULL) {
      PyErr_Restore(ptype, pvalue, ptraceback);
      return NULL;
    }
    if (!PyInt_Check(retval)) {
      Py_DECREF(retval);
      PyErr_Restore(ptype, pvalue, ptraceback);
      return NULL;
    }
    if (PyInt_AsLong(retval) != EAGAIN) {
      Py_DECREF(retval);
      PyErr_Restore(ptype, pvalue, ptraceback);
      return NULL;
    }
    Py_XDECREF(ptype); Py_XDECREF(pvalue); Py_XDECREF(ptraceback);
    Py_DECREF(retval);  /* errno_obj */
    /* TODO(pts): Make sure this call is inlined. */
    retval = coio_c_handle_eagain(swi, evtype);
    if (retval == NULL) return NULL;
    Py_DECREF(retval);
  }
}

/* Read at most n bytes to read_eb from file fd.

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
*/
static inline int coio_c_evbuffer_read(
    struct coio_evbuffer *read_eb,
    int fd,
    int n,
    PyObject *read_exc_class,
    struct event *read_wakeup_ev) {
  int got;
  if (n > 0) {
    if (0 != coio_evbuffer_expand(read_eb, n)) {
      PyErr_SetString(PyExc_MemoryError, "not enough memory for read buffer");
      return -1;
    }
  } else if (n == 0) {
    return 0;
  } else {
    /* assert read_eb.totallen */
    n = read_eb->totallen - read_eb->off - read_eb->misalign;
    if (n == 0)
      return 0;
  }
  while (0 > (got = read(fd, (char*)read_eb->buffer + read_eb->off, n))) {
    if (errno == EAGAIN) {
      if (NULL == coio_c_wait(read_wakeup_ev, NULL))
        return -1;
    } else {
      PyErr_SetFromErrno(read_exc_class);
      return -1;
    }
  }
  read_eb->off += got;
  /* We don't use callbacks, so we don't call them here
   * if read_eb.cb != NULL:
   *  read_eb.cb(read_eb, read_eb.off - got, read_eb.off, read_eb.cbarg)
   */
  return got;
}

/* Write all n bytes at p to fd, waking up based on write_wakeup_ev.

Returns:
  None
Raises:
  write_exc_class:
*/
static inline int coio_c_writeall(
    int fd,
    struct event *write_wakeup_ev,
    const char *p,
    Py_ssize_t n,
    PyObject *write_exc_class) {
  int got;
  while (n > 0) {
    got = write(fd, p, n);
    while (got < 0) {
      if (errno != EAGAIN) {
        PyErr_SetFromErrno(write_exc_class);
        return -1;
      }
      /* Assuming caller has called event_set(...). */
      coio_c_wait(write_wakeup_ev, NULL);
      got = write(fd, p, n);
    }
    p += got;
    n -= got;
  }
  return 0;
}
