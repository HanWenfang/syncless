/*
 * coio_c_helper.h: helper functions implemented in pure C (not Pyrex)
 * by pts@fazekas.hu at Sat Apr 17 00:55:39 CEST 2010
 * #### pts #### This file has been entirely written by pts@fazekas.hu.
 *
 */

void coio_c_nop(void) {}

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

/* Helper type for passing PyObject pointers without reference counting. */
struct _UncountedObject;
typedef struct _UncountedObject UncountedObject;

struct coio_oneway_wakeup_info {
  struct event ev;
  struct event *other_ev;
  double timeout_value;
  int fd;
  struct timeval tv;
  /** Exception class to raise on I/O error */
  UncountedObject *exc_class;
  UncountedObject *sslobj;
};

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
  if (swi->timeout_value == 0.0) {
    /* This is what methods of socket.socket raise, we just mimic that */
    return PyErr_SetFromErrno(coio_socket_error);
  }
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

/* nbevent.pxi overrides these hard-coded values (from Python 2.6.5
 * Modules/_ssl.c) with actual imported values.
 */
static int coio_c_SSL_ERROR_WANT_READ = 2;
static int coio_c_SSL_ERROR_WANT_WRITE = 3;
static int coio_c_SSL_ERROR_EOF = 8;
static PyObject *coio_c_SSLError;  /* initialized in nbevent.pyx */
static PyObject *coio_c_errno_eagain;  /* initialized in nbevent.pyx */
static PyObject *coio_c_strerror_eagain;  /* initialized in nbevent.pyx */

/** Set the current exception to exc_class(EAGAIN) */
static void coio_c_exc_set_eagain(PyObject *exc_class) {
  PyObject *exc_args = PyTuple_New(2);
  if (NULL == (exc_args = PyTuple_New(2)))
    return;
  Py_INCREF(coio_c_errno_eagain);
  PyTuple_SET_ITEM(exc_args, 0, coio_c_errno_eagain);
  Py_INCREF(coio_c_errno_eagain);
  PyTuple_SET_ITEM(exc_args, 1, coio_c_strerror_eagain);
  PyErr_SetObject(exc_class, exc_args);
  Py_DECREF(exc_args);
}

/** Helper function to wait when sslobj gets blocked.
 *
 * This function is called from nbsslsocket.makefile().read(), called from
 * httplib used by urllib used by examples/demo_https_client.py.
 */
static int coio_c_handle_ssl_eagain(
    double timeout_value,
    struct timeval *tv,
    UncountedObject *exc_class,
    struct event *read_ev,
    struct event *write_ev,
    char do_return_zero_at_eof) {
  PyObject *ptype, *pvalue, *ptraceback, *retval;
  int errcode;
  if (!PyErr_ExceptionMatches(coio_c_SSLError))
    return -1;
  PyErr_Fetch(&ptype, &pvalue, &ptraceback);
  assert(pvalue != NULL);
  /* AnyException('foo', ...)[0] yields 'foo', no need for exc.args[0]
   * in Python 2.x (but needed in 3.x).
   */
  retval = PySequence_GetItem(pvalue, 0);
  if (retval == NULL) {
    PyErr_Restore(ptype, pvalue, ptraceback);
    return -1;
  }
  /* TODO(pts): if (retval != coio_event_happened_token && retval != NULL) */
  if (!PyInt_Check(retval)) {
    Py_DECREF(retval);
    PyErr_Restore(ptype, pvalue, ptraceback);
    return -1;
  }
  errcode = PyInt_AsLong(retval);
  Py_DECREF(retval);
  if (errcode == coio_c_SSL_ERROR_WANT_READ) {
    /* TODO(pts): More efficient wait. */
    Py_XDECREF(ptype); Py_XDECREF(pvalue); Py_XDECREF(ptraceback);
    if (timeout_value == 0.0) {
      /* This is what methods of socket.socket raise, we just mimic that */
      coio_c_exc_set_eagain((PyObject*)exc_class);
      return -1;
    }
    retval = coio_c_wait(read_ev, tv);
    if (retval != coio_event_happened_token && retval != NULL) {
      Py_DECREF(retval);
      PyErr_SetString(coio_socket_timeout, "timed out");
      return -1;
    }
    if (retval == NULL)
      return -1;
    Py_DECREF(retval);
    return 1;
  } else if (errcode == coio_c_SSL_ERROR_WANT_WRITE) {
    Py_XDECREF(ptype); Py_XDECREF(pvalue); Py_XDECREF(ptraceback);
    if (timeout_value == 0.0) {
      /* This is what methods of socket.socket raise, we just mimic that */
      coio_c_exc_set_eagain((PyObject*)exc_class);
      return -1;
    }
    retval = coio_c_wait(write_ev, tv);
    if (retval != coio_event_happened_token && retval != NULL) {
      Py_DECREF(retval);
      PyErr_SetString(coio_socket_timeout, "timed out");
      return -1;
    }
    if (retval == NULL)
      return -1;
    Py_DECREF(retval);
    return 1;
  } else if (errcode == coio_c_SSL_ERROR_EOF && do_return_zero_at_eof) {
    Py_XDECREF(ptype); Py_XDECREF(pvalue); Py_XDECREF(ptraceback);
    return 0;
  } else {
    PyErr_Restore(ptype, pvalue, ptraceback);
    return -1;
  }
}

/** Call function(args), and do a non-blocking wait for SSL IO if
 * needed.
 *
 * This function is called from nbsslsocket methods .do_handshake, .send,
 * .sendall, .recv, .read .write etc. The file created by nbsslsocket.makefile
 * doesn't call this function, but it calls coio_c_evbuffer_read() and
 * coio_c_writeall().
 */
static PyObject *coio_c_ssl_call(PyObject *function, PyObject *args,
                                 struct coio_socket_wakeup_info *swi,
                                 char do_handle_read_eof) {
  PyObject *retval;
  int got;
  while (1) {
    if (NULL != (retval = PyObject_CallObject(function, args)))
      return retval;
    got = coio_c_handle_ssl_eagain(
        swi->timeout_value, &swi->tv, (UncountedObject*)coio_c_SSLError,
        &swi->read_ev, &swi->write_ev, do_handle_read_eof);
    if (got == -1)  /* coio_c_handle_ssl_eagain could not catch exception */
      return NULL;
    if (got == 0)  /* EOF when do_handle_read_eof=1 */
      return PyString_FromStringAndSize(NULL, 0);
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
    struct coio_oneway_wakeup_info *owi,
    struct coio_evbuffer *read_eb,
    int n) {
  Py_ssize_t got;
  PyObject *obj, *read_obj, *args, *n_obj;
  const char *buffer;
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
  if (owi->sslobj != NULL) {
    /* sslobj is defined in Modules/_ssl.c */
    read_obj = PyObject_GetAttrString((PyObject*)owi->sslobj, "read");
    if (read_obj == NULL)
      return -1;
    if (n > 65536)  /* Avoid allocating a large string below at once. */
      n = 65536;
   read_again:
    n_obj = PyInt_FromSsize_t(n);
    if (n_obj == NULL) {
      Py_DECREF(read_obj);
      return -1;
    }
    args = PyTuple_New(1);
    if (args == NULL) {
      Py_DECREF(n_obj);
      Py_DECREF(read_obj);
      return -1;
    }
    PyTuple_SET_ITEM(args, 0, n_obj);
    obj = PyObject_CallObject(read_obj, args);
    Py_DECREF(args);
    if (obj == NULL) {
      got = coio_c_handle_ssl_eagain(
          owi->timeout_value, &owi->tv, owi->exc_class,
          &owi->ev, owi->other_ev, 1);
      if (got == -1) {
        Py_DECREF(read_obj);
        return -1;
      }
      if (got == 0)
        return 0;
      goto read_again;
    }
    if (PyObject_AsCharBuffer(obj, &buffer, &got) == -1) {
      Py_DECREF(obj);
      Py_DECREF(read_obj);
      return -1;
    }
    memcpy((char*)read_eb->buffer + read_eb->off, buffer, got);
    Py_DECREF(obj);
    Py_DECREF(read_obj);
  } else {
    while (0 > (got = read(
        owi->fd, (char*)read_eb->buffer + read_eb->off, n))) {
      if (errno == EAGAIN) {
        if (owi->timeout_value < 0) {
          if (NULL == coio_c_wait(&owi->ev, NULL))
            return -1;
        } else {
          if (owi->timeout_value == 0.0) {
            /* This is what methods of socket.socket raise, we just mimic that */
            PyErr_SetFromErrno((PyObject*)owi->exc_class);  /* EAGAIN */
            return -1;
          }
          obj = coio_c_wait(&owi->ev, &owi->tv);
          if (obj != coio_event_happened_token && obj != NULL) {
            Py_DECREF(obj);
            PyErr_SetString(coio_socket_timeout, "timed out");
            return -1;
          }
          if (obj == NULL)
            return -1;
          Py_DECREF(obj);
        }
      } else {
        PyErr_SetFromErrno((PyObject*)owi->exc_class);
        return -1;
      }
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
  owi->exc_class:
*/
static inline int coio_c_writeall(
    struct coio_oneway_wakeup_info *owi,
    const char *p,
    Py_ssize_t n) {
  PyObject *obj, *write_obj, *args, *buf;
  Py_ssize_t got;
  int fd = owi->fd;
  if (n <= 0)
    return 0;
  if (owi->sslobj != NULL) {
    /* sslobj is defined in Modules/_ssl.c */
    write_obj = PyObject_GetAttrString((PyObject*)owi->sslobj, "write");
    if (write_obj == NULL)
      return -1;
    do {
     write_again:
      if (NULL == (buf = PyBuffer_FromMemory((void*)p, n))) {
        Py_DECREF(write_obj);
        return -1;
      }
      if (NULL == (args = PyTuple_New(1))) {
        Py_DECREF(buf);
        Py_DECREF(write_obj);
        return -1;
      }
      PyTuple_SET_ITEM(args, 0, buf);
      obj = PyObject_CallObject(write_obj, args);
      Py_DECREF(args);
      if (obj == NULL) {
        if (-1 == coio_c_handle_ssl_eagain(
            owi->timeout_value, &owi->tv, owi->exc_class,
            owi->other_ev, &owi->ev, 0)) {
          Py_DECREF(write_obj);
          return -1;
        }
        goto write_again;
      }
      got = PyInt_AsSsize_t(obj);
      if (PyErr_Occurred()) {
        Py_DECREF(obj);
        Py_DECREF(write_obj);
        return -1;
      }
      Py_DECREF(obj);
      p += got;
      n -= got;
    } while (n > 0);
    Py_DECREF(write_obj);
  } else {
    do {
      while (0 > (got = write(fd, p, n))) {
        if (errno != EAGAIN) {
          PyErr_SetFromErrno((PyObject*)owi->exc_class);
          return -1;
        }
        /* Assuming caller has called event_set(...). */
        if (owi->timeout_value < 0) {
          if (NULL == coio_c_wait(&owi->ev, NULL))
            return -1;
        } else {
          if (owi->timeout_value == 0.0) {
            /* This is what methods of socket.socket raise, we just mimic. */
            PyErr_SetFromErrno((PyObject*)owi->exc_class);  /* EAGAIN */
            return -1;
          }
          obj = coio_c_wait(&owi->ev, &owi->tv);
          if (obj != coio_event_happened_token && obj != NULL) {
            Py_DECREF(obj);
            PyErr_SetString(coio_socket_timeout, "timed out");
            return -1;
          }
          if (obj == NULL)
            return -1;
          Py_DECREF(obj);
        }
      }
      p += got;
      n -= got;
    } while (n > 0);
  }
  return 0;
}

/* --- Wrapping exceptions */

static inline PyObject *coio_c_call_wrap_bomb(PyObject *function,
                                              PyObject *args,
                                              PyObject *kwargs,
                                              PyObject *bomb_class) {
  PyObject *retval = PyObject_Call(function, args, kwargs);
  PyObject *ptype, *pvalue, *ptraceback, *bomb_args;
  if (retval != NULL)
    return retval;
  PyErr_Fetch(&ptype, &pvalue, &ptraceback);

  /* No need to set ptraceback = ptraceback.tb_next, since
   * coio_c_call_wrap_bomb is a C function (in contrast to Pyrex), so we
   * have no Python frame to get rid of here.
   */
  bomb_args = PyTuple_New(3);
  if (bomb_args == NULL) {
    Py_XDECREF(ptype); Py_XDECREF(pvalue); Py_XDECREF(ptraceback);
    return NULL;
  }
  PyTuple_SET_ITEM(bomb_args, 0, ptype);  /* Transfer ownership of ptype. */
  PyTuple_SET_ITEM(bomb_args, 1, pvalue);
  PyTuple_SET_ITEM(bomb_args, 2, ptraceback);
  retval = PyObject_CallObject(bomb_class, bomb_args);
  Py_DECREF(bomb_args);
  return retval;
}
