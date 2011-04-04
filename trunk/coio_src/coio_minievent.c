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

/* TODO(pts): Use long long if available to store more than 8 * sizeof(long)
 * signals. But would that be atomic? Maybe store an array of ints or chars
 * instead.
 */
typedef unsigned minievent_signal_mask_t;

static volatile minievent_signal_mask_t minievent_got_signal_mask = 0;

static volatile struct timeval minievent_tv;

/* TODO(pts): Make sure this is Python-safe (?). */
static void minievent_signal_handler(int signum) {
  minievent_got_signal_mask |= 1L << signum;
  /* Avoid a race condition, i.e. prevent select(2) in event_loop() from
   * waiting if this signal handler runs earlier than select(2) is called.
   * Alternatively, to avoid the race conditions, we could use pselect(2)
   * instead of select(2) to block this signal handler until pselect(2) is
   * called. The reason why we use select(2) plus this zeroing is that it
   * seems to be more portable than pselect(2) + sigprocmask(2).
   */
  minievent_tv.tv_sec = minievent_tv.tv_usec = 0;
}

const char *event_get_version(void) {
  return "0.02";
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
    /* Please note that even with SA_RESTART, so system calls (such as
     * select(2), nanosleep(2), pause(2) and socket operations with
     * SO_RECVTIMEO or SO_SNDTIMEO) will still get an EINTR. See
     * `man 7 signal' on Linux for details.
     */
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
    sigaction(/*signum:*/ev->ev_fd, &sa, NULL);  /* Ignore return value. */
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
  int got, maxfd, got_errno;
  int non_internal_event_count;
  fd_set readfds;
  fd_set writefds;
  fd_set exceptfds;
  struct timeval tv;
  struct timeval now;
  minievent_signal_mask_t interesting_signal_mask;
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
    if (ev == &minievent_head) {
      MINIEVENT_DEBUG((stderr, "ddd no events registered\n"));
      return 1;  /* No events registered. */
    }
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
    non_internal_event_count = 0;  /* this would be smarter, but not compatible with libevent-1.4.13: = (flags & EVLOOP_NONBLOCK) != 0; */
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
    /* This doesn't make sense here, but we keep it for libevent 1.4.13
     * compatibility. The helper sleep tasklet in testSignalHandlerEvent
     * would not be necessary if we didn't return here.
     */
    if (0 == non_internal_event_count) {
      MINIEVENT_DEBUG((stderr, "ddd all events are internal\n"));
      return 1;
    }
    if (minievent_got_signal_mask & interesting_signal_mask) {
      /* Don't wait, because signal event is ready. */
      minievent_tv.tv_sec = minievent_tv.tv_usec = 0;
    } else if (tv.tv_sec == MINIEVENT_HIGH_SEC) {  /* Infinite timeout. */
      /* Set a very large timeout. Please note that we set tv_usec = 0, to
       * avoid a race condition with minievent_signal_handler().
       */
      minievent_tv.tv_sec = 100000;
      minievent_tv.tv_usec = 0;
    } else {
      MINIEVENT_DEBUG((stderr, "ddd expire %ld %ld\n", tv.tv_sec, tv.tv_usec));
      if (gettimeofday(&now, NULL) != 0) {
        MINIEVENT_DEBUG((stderr, "ddd gettimeofday1: %s\n", strerror(errno)));
        return -1;
      }
      tv.tv_sec = tv.tv_sec - now.tv_sec;
      tv.tv_usec = tv.tv_usec - now.tv_usec;
      MINIEVENT_FIX_TV_AFTER_SUBTRACT(tv);
      if (tv.tv_sec < 0) {
        minievent_tv.tv_sec = minievent_tv.tv_usec = 0;
      } else {
        minievent_tv = tv;
        /* Avoid the race condition with minievent_signal_handler(). */
        if (minievent_got_signal_mask & interesting_signal_mask)
          minievent_tv.tv_sec = minievent_tv.tv_usec = 0;
      }
    }
    MINIEVENT_DEBUG((stderr, "ddd timeout %ld %ld\n",
                     minievent_tv.tv_sec, minievent_tv.tv_usec));
    /* select(2) returns an EINTR if a signal was received while select(2)
     * was blocking, even if the signal handler was installed with
     * SA_RESTART. See `man 7 signal' on Linux for more information. This
     * is good for us here, because by select returning early we can
     * deliver the EV_SIGNAL events early.
     */
    /* TODO(pts): Use poll(2) instead of select(2) if available (on Unix,
     * it is), if it seems to be faster. Another advantage of poll(2) is
     * that it works with large fd values.
     */
    got = select(maxfd + 1, &readfds, &writefds, &exceptfds,
                 (struct timeval*)&minievent_tv);  /* Cast away volatile. */
    got_errno = errno;
    MINIEVENT_DEBUG((stderr, "ddd select got %d\n", got));
    if (got < 0 && got_errno != EINTR) {
      MINIEVENT_DEBUG((stderr, "ddd select: %s\n", strerror(errno)));
      return -1;
    }
    if (got > 0 || tv.tv_sec != MINIEVENT_HIGH_SEC) {
      if (gettimeofday(&now, NULL) != 0) {
        MINIEVENT_DEBUG((stderr, "ddd gettimeofday1: %s\n", strerror(errno)));
        return -1;
      }
      interesting_signal_mask = minievent_got_signal_mask;
      MINIEVENT_DEBUG((stderr, "ddd now %ld %ld signal_mask=0x%lx\n",
                       now.tv_sec, now.tv_usec,
                       (unsigned long)interesting_signal_mask));
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
                ((interesting_signal_mask & 1L << fd) ? EV_SIGNAL : 0) :
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
            /* This modification here doesn't contain a race condition,
             * because we've already made a copy (interesting_signal_mask)
             * above, and we use the copy to decide which event handlers to
             * run below.
             */
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
          MINIEVENT_DEBUG((stderr, "ddd callback fd=%d fev=%d\n", fd, fire_events));
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
  MINIEVENT_DEBUG((stderr, "ddd leave\n"));
  return 0;
}
