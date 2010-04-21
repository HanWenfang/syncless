static PyObject *waiting_token;

/*
 * coio_c_helper.c: helper functions implemented in pure C (not Pyrex)
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

/**
 * Make the current tasklet wait on event ev with the specified timeout,
 * expecting to be woken up (and the event deleted) or an exception raised
 * (and the event either deleted or not, this function will delete it).
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
  event_add(ev, timeout);
  /* This also sets stackless.current.tempval = None */
  tempval = PyStackless_Schedule(waiting_token, /*do_remove:*/1);
  if (!tempval ||  /* exception occured (maybe stackless.bomb) */
      tempval == waiting_token /* reinserted while waiting */
     ) {
    event_del(ev);  /* harmless if event_del(ev) has already been called */
  }
  return tempval;
}
