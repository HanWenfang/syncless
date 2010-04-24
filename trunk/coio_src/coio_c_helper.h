/*
 * coio_c_helper.h: helper functions implemented in pure C (not Pyrex)
 * by pts@fazekas.hu at Sat Apr 17 00:55:39 CEST 2010
 * #### pts #### This file has been entirely written by pts@fazekas.hu.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
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
    for (i = 1; i < COIO_EVENT_POOL_BLOCK_COUNT; --i) {
      *(struct event**)&ev[i] = &ev[i + 1];
    }
    return ev;
  }
}

/* --- Waiting */

static PyObject *waiting_token;

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
  if (ev->ev_arg != NULL) {  /* Event in use */
    struct event *ev2 = coio_event_pool_malloc_event();
    if (ev2 == NULL) {
      PyErr_NoMemory();
      return NULL;
    }
    /*write(2, "M", 1);*/
    event_set(ev2, ev->ev_fd, ev->ev_events, ev->ev_callback,
              PyStackless_GetCurrent());
    ev = ev2;
    event_add(ev, timeout);
    /* This also sets stackless.current.tempval = None */
    tempval = PyStackless_Schedule(waiting_token, /*do_remove:*/1);
    Py_DECREF(((PyObject*)ev->ev_arg));  /* stackless.current above */
    coio_event_pool_free_event(ev);
  } else {
    ev->ev_arg = PyStackless_GetCurrent();  /* implicit Py_INCREF */
    event_add(ev, timeout);
    /* This also sets stackless.current.tempval = None */
    tempval = PyStackless_Schedule(waiting_token, /*do_remove:*/1);
    Py_DECREF(((PyObject*)ev->ev_arg));  /* stackless.current above */
    ev->ev_arg = NULL;
  }
  if (!tempval ||  /* exception occured (maybe stackless.bomb) */
      tempval == waiting_token /* reinserted while waiting */
     ) {
    event_del(ev);  /* harmless if event_del(ev) has already been called */
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
  tempval = PyStackless_Schedule(waiting_token, /*do_remove:*/1);
  Py_DECREF(((PyObject*)ev->ev_arg));  /* stackless.current above */
  if (!tempval ||  /* exception occured (maybe stackless.bomb) */
      tempval == waiting_token /* reinserted while waiting */
     ) {
    event_del(ev);  /* harmless if event_del(ev) has already been called */
  }
  coio_event_pool_free_event(ev);
  return tempval;
}
