/*
 * coio_minievent.h: slow but simple fallback event notification lib for Unix
 * by pts@fazekas.hu at Mon May 10 20:47:07 CEST 2010
 *
 * Tested on Linux 2.6 with gcc 4.4.1, glibc 2.10.1.
 */

#ifndef COIO_MINIEVENT_H
#define COIO_MINIEVENT_H

#include <sys/time.h>  /* struct timeval */

/* Constants copied from event.h in libevent1 1.4.13 */
#define EVLIST_INTERNAL 0x10  /* !! TODO(pts): implement this */
#define EV_TIMEOUT	0x01
#define EV_READ		0x02
#define EV_WRITE	0x04
#define EV_SIGNAL	0x08
#define EV_PERSIST	0x10	/* Persistant event */
#define EVLOOP_ONCE     0x01    /**< Block at most once. */
#define EVLOOP_NONBLOCK 0x02    /**< Do not block. */

struct event_base;

struct event {
  struct event* evx_next;
  struct event* evx_prev;
  int ev_fd;
  short ev_events;
  struct timeval ev_timeout;
  struct timeval ev_expire;
  void (*ev_callback)(int, short, void *arg);
  void *ev_arg;
  int ev_flags;
};

const char *event_get_version(void);
const char *event_get_method(void);
struct event_base *event_init(void);
int event_reinit(struct event_base *base);
void event_base_free(struct event_base *base);
void event_set(struct event *ev, int fd,
               short events, void (*cb)(int, short, void *), void *arg);
int event_pending(struct event *ev, short events, struct timeval *tv);
int event_add(struct event *ev, const struct timeval *tv);
int event_del(struct event *ev);
int event_loop(int flags);

#endif
