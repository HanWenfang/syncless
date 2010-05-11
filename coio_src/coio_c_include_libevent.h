/* by pts@fazekas.hu at Wed Apr 28 21:38:19 CEST 2010 */

static struct event_base *coio_default_base = NULL;

#ifdef COIO_USE_LIBEVENT2
#include <event2/event.h>
#include <event2/event_struct.h>
#include <event2/event_compat.h>
/* We don't include these because of conflicting types for
 * evdns_err_to_string.
#include <event2/dns.h>
#include <event2/dns_compat.h>
*/
#define FEATURE_MAY_EVENT_LOOP_RETURN_1    1
#define FEATURE_MULTIPLE_EVENTS_ON_SAME_FD 1
#define coio_event_reinit_low() event_reinit(coio_default_base)
#define coio_event_init_low() event_init()
#endif

#ifdef COIO_USE_LIBEVENT1
/* We use a local copy because stock event.h might be from libev */
#include "./coio_event1_event.h"
#define FEATURE_MAY_EVENT_LOOP_RETURN_1    1
#define FEATURE_MULTIPLE_EVENTS_ON_SAME_FD 0
#define coio_event_reinit_low() event_reinit(coio_default_base)
#define coio_event_init_low() event_init()
#endif

#ifdef COIO_USE_MINIEVENT
/* We use a local copy because stock event.h might be from libev */
#include "./coio_minievent.h"
#define FEATURE_MAY_EVENT_LOOP_RETURN_1    1
#define FEATURE_MULTIPLE_EVENTS_ON_SAME_FD 1
#define coio_event_reinit_low() 0
#define coio_event_init_low() event_init()
#endif

#ifdef COIO_USE_LIBEV
/* We use a local copy because stock event.h might be from libevent1 */
#include "./coio_ev_event.h"
#define FEATURE_MAY_EVENT_LOOP_RETURN_1    0
#define FEATURE_MULTIPLE_EVENTS_ON_SAME_FD 1
static inline void coio_event_set(struct event *ev, int fd, short events,
                                  void (*cb)(int, short, void*), void *arg) {
  event_set(ev, fd, events, cb, arg);
  (ev)->ev_base = (void*)coio_default_base;
}
#define event_set coio_event_set  
#define event_loop(flags) event_base_loop(coio_default_base, flags)
/* We use ev_loop_new(EVFLAG_AUTO) instead of event_init() here because
 * the event_init() in libev-3.9 would install a SIGCHLD signal handler,
 * os os.wait() and os.waitpid() would cease to work.
 */
#define coio_event_init_low() ev_loop_new(EVFLAG_AUTO)
static int coio_event_reinit_low(void) {
  ev_loop_fork((struct ev_loop*)coio_default_base);
  return event_loop(EVLOOP_ONCE | EVLOOP_NONBLOCK);
}
#endif  /*  COIO_USE_LIBEV */

static int coio_event_init(void) {
  if (coio_default_base == NULL) {
    if (NULL == (coio_default_base =
                 (struct event_base*)coio_event_init_low()))
      return -1;
  }
  return 0;
}
static int coio_event_reinit(int do_recreate) {
  if (do_recreate) {
    if (coio_default_base != NULL) event_base_free(coio_default_base);
    return -(NULL == (coio_default_base =
                      (struct event_base*)coio_event_init_low()));
  } else {
    return coio_event_reinit_low();
  }
}
