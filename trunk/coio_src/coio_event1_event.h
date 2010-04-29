/* Header extracted from libevent-1.4.13/event.h
 * by pts@fazekas.hu at Thu Apr 29 11:00:38 CEST 2010
 */

#ifndef _EVENT_H_
#define _EVENT_H_

/* Original event.h is:
 * Copyright (c) 2000-2007 Niels Provos <provos@citi.umich.edu>
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. The name of the author may not be used to endorse or promote products
 *    derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
 * OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
 * IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
 * NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
 * THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */


struct timeval;
struct event_base;

#define EVLIST_TIMEOUT  0x01
#define EVLIST_INSERTED 0x02
#define EVLIST_SIGNAL   0x04
#define EVLIST_ACTIVE   0x08
#define EVLIST_INTERNAL 0x10
#define EVLIST_INIT     0x80
#define EV_TIMEOUT	0x01
#define EV_READ		0x02
#define EV_WRITE	0x04
#define EV_SIGNAL	0x08
#define EV_PERSIST	0x10	/* Persistant event */
#define EVLOOP_ONCE     0x01    /**< Block at most once. */
#define EVLOOP_NONBLOCK 0x02    /**< Do not block. */

/* Fix so that ppl dont have to run with <sys/queue.h> */
#ifndef TAILQ_ENTRY  /* This is true for normal #include <event.h> */
#define _EVENT_DEFINED_TQENTRY
#define TAILQ_ENTRY(type)						\
struct {								\
	struct type *tqe_next;	/* next element */			\
	struct type **tqe_prev;	/* address of previous next element */	\
}
#endif /* !TAILQ_ENTRY */

struct event_base;
struct event {
	TAILQ_ENTRY (event) ev_next;
	TAILQ_ENTRY (event) ev_active_next;
	TAILQ_ENTRY (event) ev_signal_next;
	unsigned int min_heap_idx;	/* for managing timeouts */

	struct event_base *ev_base;

	int ev_fd;
	short ev_events;
	short ev_ncalls;
	short *ev_pncalls;	/* Allows deletes in callback */

	struct timeval ev_timeout;

	int ev_pri;		/* smaller numbers are higher priority */

	void (*ev_callback)(int, short, void *arg);
	void *ev_arg;

	int ev_res;		/* result passed to event callback */
	int ev_flags;
};

/*#define event_initialized(ev)      ((ev)->ev_flags & EVLIST_INIT)*/
/*#define evtimer_set(ev,cb,data)    event_set (ev, -1, 0, cb, data)*/
/*const char *event_get_version (void);*/
/*const char *event_get_method (void);*/
/*#define _EVENT_LOG_DEBUG 0*/
/*#define _EVENT_LOG_MSG   1*/
/*#define _EVENT_LOG_WARN  2*/
/*#define _EVENT_LOG_ERR   3*/
/*void event_base_free (struct event_base *base);*/
/*int event_base_set (struct event_base *base, struct event *ev);*/
/*int event_base_loop (struct event_base *base, int);*/
/*int event_base_loopexit (struct event_base *base, struct timeval *tv);*/
/*int event_base_dispatch (struct event_base *base);*/
/*int event_base_once (struct event_base *base, int fd, short events, void (*cb)(int, short, void *), void *arg, struct timeval *tv);*/
/*int event_base_priority_init (struct event_base *base, int fd);*/
/*int event_loopexit (struct timeval *tv);*/
/*int event_priority_init (int npri);*/
/*int event_priority_set (struct event *ev, int pri);*/
/*typedef void (*event_log_cb)(int severity, const char *msg);*/
/*void event_set_log_callback(event_log_cb cb);*/
/*void event_active (struct event *ev, int res, short ncalls);*/ /* ncalls is being ignored */
/*int event_once (int fd, short events, void (*cb)(int, short, void *), void *arg, struct timeval *tv);*/

void *event_init (void);
int event_loop (int);
int event_dispatch (void);  /* not crucial for Syncless */
void event_set (struct event *ev, int fd, short events, void (*cb)(int, short, void *), void *arg);
int event_add (struct event *ev, const struct timeval *tv);
int event_del (struct event *ev);
int event_pending (struct event *ev, short, struct timeval *tv);

#endif
