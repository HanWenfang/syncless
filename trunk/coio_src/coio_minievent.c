/*
 * coio_minievent.c: slow but simple fallback event notification lib for Unix
 * by pts@fazekas.hu at Mon May 10 20:47:07 CEST 2010
 *
 * Tested on Linux 2.6 with gcc 4.4.1, glibc 2.10.1.
 *
 * Also works on (and coio_minihdns works as well):
 *
 * * Linux 2.6, glibc 2.10
 * * Mac OS X 10.5
 * * NetBSD 5.0.1 sparc64
 * * OpenBSD 4.4 on sparc64
 * * Solaris SunOS hagbard 5.10
 */

#include "./coio_minievent.h"

#include <sys/select.h>
#include <sys/time.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <signal.h>

#ifdef COIO_MINIEVENT_DEBUG
#  define MINIEVENT_DEBUG(x) fprintf x
#else
#  define MINIEVENT_DEBUG(x) do {} while(0)
#endif

#define MINIEVENT_HIGH_SEC (0x7fffffffL)
#define MINIEVENT_FIX_TV_AFTER_ADD(tv) do { \
  if ((tv).tv_usec >= 1000000L) { (tv).tv_usec -= 1000000L; ++(tv).tv_sec; } \
} while (0)
#define MINIEVENT_FIX_TV_AFTER_SUBTRACT(tv) do { \
  if ((tv).tv_usec < 0) { (tv).tv_usec += 1000000L; --(tv).tv_sec; } \
} while (0)
#define MINIEVENT_TV_LT(tva, tvb) \
    ((tva).tv_sec < (tvb).tv_sec || \
     ((tva).tv_sec == (tvb).tv_sec && (tva).tv_usec < (tvb).tv_usec))

static struct event minievent_head;
static struct event minievent_head = {
   .evx_next = &minievent_head,  /* gcc extension to C */
   .evx_prev = &minievent_head
};
static struct event *minievent_loop_ev = NULL;

static volatile long minievent_got_signal_mask = 0;

/* TODO(pts): Make sure this is Python-safe (?). */
static void minievent_signal_handler(int signum) {
  minievent_got_signal_mask |= 1L << signum;
}

const char *event_get_version(void) {
  return "0.01";
}
const char *event_get_method(void) {
  return "minievent-select";
}

struct event_base *event_init(void) {
  /* Forget about all events, if any; this is compatible to libevent1 */
  minievent_head.evx_next = minievent_head.evx_prev = &minievent_head;
  return (struct event_base*)1;
}

int event_reinit(struct event_base *base) {
  (void)base;
  return 0;
}

void event_base_free(struct event_base *base) {
  (void)base;
}

void event_set(struct event *ev, int fd,
               short events, void (*cb)(int, short, void *), void *arg) {
  ev->evx_next = ev->evx_prev = NULL;
  ev->ev_fd = fd;
  ev->ev_events = events;
  /* do not set ev->ev_timeout */
  ev->ev_callback = cb;
  ev->ev_arg = arg;
  ev->ev_flags = 0;
}

int event_pending(struct event *ev, short events, struct timeval *tv) {
  if (tv != NULL) {
    fprintf(stderr, "minievent: got timeout for event_pending\n");
    abort();
  }
  return ev->evx_next != NULL && (ev->ev_events & events);
}

int event_add(struct event *ev, const struct timeval *tv) {
  if (ev->ev_events & EV_SIGNAL) {
    struct sigaction sa;
    if (tv != NULL) {
      /* TODO(pts): We could support timeouts in event_loop by scanning
       * minievent_got_signal_mask in advance.
       */
      fprintf(stderr, "minievent: timeout not supported for signals\n");
      abort();
    }
    if (ev->ev_events & (EV_READ | EV_WRITE)) {
      fprintf(stderr, "minievent: cannot combine EV_SIGNAL in event\n");
      abort();
    }
    sa.sa_handler = minievent_signal_handler;
    sa.sa_flags = (ev->ev_fd == SIGCHLD) ? SA_NOCLDSTOP | SA_RESTART
                                         : SA_RESTART;
    sigemptyset(&sa.sa_mask);
    if (0 != sigaction(/*signum:*/ev->ev_fd, &sa, NULL))
      return -1;
  }
  ev->evx_prev = minievent_head.evx_prev;
  ev->evx_next = &minievent_head;
  minievent_head.evx_prev->evx_next = ev;
  minievent_head.evx_prev = ev;
  if (tv != NULL && tv->tv_sec < MINIEVENT_HIGH_SEC) {
    if (gettimeofday(&ev->ev_expire, NULL) != 0)
      return -1;
    ev->ev_timeout = *tv;
    ev->ev_expire.tv_sec  += tv->tv_sec;
    ev->ev_expire.tv_usec += tv->tv_usec;
    MINIEVENT_FIX_TV_AFTER_ADD(ev->ev_expire);
  } else {
    ev->ev_timeout.tv_sec = MINIEVENT_HIGH_SEC;
    ev->ev_timeout.tv_usec = 0;
    ev->ev_expire.tv_sec = MINIEVENT_HIGH_SEC;
    ev->ev_expire.tv_usec = 0;
  }
  MINIEVENT_DEBUG((stderr, "ddd add fd=%d events=%d flags=%d sec=%ld usec=%ld\n", ev->ev_fd, ev->ev_events, ev->ev_flags, ev->ev_timeout.tv_sec, ev->ev_timeout.tv_usec));
  return 0;
}

int event_del(struct event *ev) {
  if (ev == minievent_loop_ev)
    minievent_loop_ev = ev->evx_next;
  if (ev->ev_events & EV_SIGNAL) {
    struct sigaction sa;
    /* TODO(pts): Restore previous value (before event_add). */
    sa.sa_handler = SIG_DFL;
    sa.sa_flags = (ev->ev_fd == SIGCHLD) ? SA_NOCLDSTOP | SA_RESTART
                                         : SA_RESTART;
    sigemptyset(&sa.sa_mask);
    sigaction(/*signum:*/ev->ev_fd, &sa, NULL);  /* Ingore return value. */
  }
  if (ev->evx_prev != NULL)
    ev->evx_prev->evx_next = ev->evx_next;
  if (ev->evx_next != NULL)
    ev->evx_next->evx_prev = ev->evx_prev;
  ev->evx_next = ev->evx_prev = NULL;
  return 0;
}

/* Return 0 if there are events registered with EVLOOP_ONCE, 1 if there are
 * no more events registered.
 *
 * This function and all other functions in this file are not thread-safe or
 * reentrant.
 */
int event_loop(int flags) {
  struct event *ev;
  int got, maxfd;
  int non_internal_event_count;
  fd_set readfds;
  fd_set writefds;
  fd_set exceptfds;
  struct timeval tv;
  struct timeval now;
  long interesting_signal_mask;
  MINIEVENT_DEBUG((stderr, "ddd enter flags=%d\n", flags));
  if ((flags & EVLOOP_NONBLOCK) && !(flags & EVLOOP_ONCE)) {
    fprintf(stderr, "minievent: EVLOOP_NONBLOCK but not EVLOOP_ONCE\n");
    abort();
  }
  if (minievent_loop_ev != NULL) {
    fprintf(stderr, "minievent: event_loop() already in progress\n");
    abort();
  }
  do {
    ev = minievent_head.evx_next;
    if (ev == &minievent_head)
      return 1;  /* No events registered. */
    maxfd = -1;
    FD_ZERO(&readfds);
    FD_ZERO(&writefds);
    FD_ZERO(&exceptfds);
    if (flags & EVLOOP_NONBLOCK) {
      tv.tv_sec = tv.tv_usec = 0;
    } else {
      tv.tv_sec = MINIEVENT_HIGH_SEC;
      tv.tv_usec = 0;
    }
    interesting_signal_mask = 0;
    non_internal_event_count = 0;
    for (; ev != &minievent_head; ev = ev->evx_next) {
      int fd = ev->ev_fd;
      if (ev->ev_events & EV_READ) {
        MINIEVENT_DEBUG((stderr, "ddd EV_READ %d\n", fd));
        FD_SET(fd, &readfds);
        FD_SET(fd, &exceptfds);
        if (fd > maxfd) maxfd = fd;
      }
      if (ev->ev_events & EV_WRITE) {
        MINIEVENT_DEBUG((stderr, "ddd EV_WRITE %d\n", fd));
        if (fd > maxfd) maxfd = fd;
        FD_SET(fd, &writefds);
        FD_SET(fd, &exceptfds);
      }
      if (ev->ev_events & EV_SIGNAL) {
        MINIEVENT_DEBUG((stderr, "ddd EV_SIGNAL %d\n", fd));
        interesting_signal_mask |= 1L << ev->ev_fd;
      }
      MINIEVENT_DEBUG((stderr, "ddd ex %ld %ld\n", ev->ev_expire.tv_sec, ev->ev_expire.tv_usec));
      if (MINIEVENT_TV_LT(ev->ev_expire, tv))
        tv = ev->ev_expire;
      if (!(ev->ev_flags & EVLIST_INTERNAL))
        ++non_internal_event_count;
    }
    if (0 == non_internal_event_count)
      return 1;
    if (minievent_got_signal_mask & interesting_signal_mask)
      tv.tv_sec = tv.tv_usec = 0;  /* Don't wait: signal is ready. */
    MINIEVENT_DEBUG((stderr, "ddd expire %ld %ld\n", tv.tv_sec, tv.tv_usec));
    if (tv.tv_sec == MINIEVENT_HIGH_SEC) {
      /* TODO(pts): Use poll(2) if available (on Unix, it is) */
      got = select(maxfd + 1, &readfds, &writefds, &exceptfds, NULL);
    } else {
      if (gettimeofday(&now, NULL) != 0)
        return -1;
      tv.tv_sec = tv.tv_sec - now.tv_sec;
      tv.tv_usec = tv.tv_usec - now.tv_usec;
      MINIEVENT_FIX_TV_AFTER_SUBTRACT(tv);
      if (tv.tv_sec < 0)
        tv.tv_sec = tv.tv_usec = 0;
      MINIEVENT_DEBUG((stderr, "ddd timeout %ld %ld\n", tv.tv_sec, tv.tv_usec));
      got = select(maxfd + 1, &readfds, &writefds, &exceptfds, &tv);
      /* select() may modift tv.tv_sec, but we don't care since it won't
       * ever become tv.tv_sec.
       */
    }
    MINIEVENT_DEBUG((stderr, "ddd select got %d\n", got));
    if (got < 0 && errno != EINTR)
      return -1;
    if (got > 0 || tv.tv_sec != MINIEVENT_HIGH_SEC) {
      if (gettimeofday(&now, NULL) != 0)
        return -1;
      MINIEVENT_DEBUG((stderr, "ddd now %ld %ld\n", now.tv_sec, now.tv_usec));
      for (ev = minievent_head.evx_next;
           ev != &minievent_head;
           ev = minievent_loop_ev) {
        /* Copy early so the user can call event_del to any event from
         * within the callback.
         */
        int fd = ev->ev_fd;
        short events = ev->ev_events;
        short got_events =
            events & EV_SIGNAL ?
                ((minievent_got_signal_mask & 1L << fd) ? EV_SIGNAL : 0) :
            events == 0 ? 0 :  /* A pure timeout event. */
            FD_ISSET(fd, &exceptfds) ? (EV_READ | EV_WRITE) :
            ((FD_ISSET(fd, &readfds) ? EV_READ : 0) |
             (FD_ISSET(fd, &writefds) ? EV_WRITE : 0));
        short fire_events = 0;
        MINIEVENT_DEBUG((stderr, "ddd try fd=%d events=%d got_events=%d sec=%ld usec=%ld expired=%d\n",
            fd, events, got_events,
            ev->ev_expire.tv_sec, ev->ev_expire.tv_usec,
            !MINIEVENT_TV_LT(now, ev->ev_expire)));
        minievent_loop_ev = ev->evx_next;
        if (events & EV_READ) {
          if ((events & (EV_READ | EV_WRITE)) == (EV_READ | EV_WRITE)) {
            if (got_events)
              fire_events = got_events;
          } else {
            if (got_events & EV_READ)
              fire_events = EV_READ;
          }
        } else if (events & EV_WRITE) {
          if (got_events & EV_WRITE)
            fire_events = EV_WRITE;
        } else if (events & EV_SIGNAL) {
          if (got_events & EV_SIGNAL) {
            fire_events = EV_SIGNAL;
            minievent_got_signal_mask &= ~(1L << fd);
          }
        }
        if (fire_events != 0) {
         do_fire:
          if (events & EV_PERSIST) {
            if (ev->ev_expire.tv_sec != MINIEVENT_HIGH_SEC) {
              ev->ev_expire.tv_sec  += ev->ev_timeout.tv_sec;
              ev->ev_expire.tv_usec += ev->ev_timeout.tv_usec;
              MINIEVENT_FIX_TV_AFTER_ADD(ev->ev_expire);
            }
          } else {
            event_del(ev);
          }
          MINIEVENT_DEBUG((stderr, "ddd callback %d fev=%d\n", fd, fire_events));
          ev->ev_callback(fd, fire_events, ev->ev_arg);
        } else if (!MINIEVENT_TV_LT(now, ev->ev_expire)) {
          fire_events = EV_TIMEOUT;
          goto do_fire;
        }
      }
      minievent_loop_ev = NULL;
    }
    MINIEVENT_DEBUG((stderr, "ddd processed\n"));
  } while (!(flags & EVLOOP_ONCE));
  return 0;
}
