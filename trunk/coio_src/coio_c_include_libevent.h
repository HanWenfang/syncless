/* by pts@fazekas.hu at Wed Apr 28 21:38:19 CEST 2010 */

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
#endif

#ifdef COIO_USE_LIBEVENT1
/* We use a local copy because stock event.h might be from libev */
#include "./coio_event1_event.h"
#define FEATURE_MAY_EVENT_LOOP_RETURN_1    1
#define FEATURE_MULTIPLE_EVENTS_ON_SAME_FD 0
#define coio_event_reinit_low() event_reinit(coio_default_base)
#endif

#ifdef COIO_USE_LIBEV
/* We use a local copy because stock event.h might be from libevent1 */
#include "./coio_ev_event.h"
#define FEATURE_MAY_EVENT_LOOP_RETURN_1    0
#define FEATURE_MULTIPLE_EVENTS_ON_SAME_FD 1
static int coio_event_reinit_low(void) {
  ev_default_fork();
  return event_loop(EVLOOP_ONCE | EVLOOP_NONBLOCK);
}
#endif

static struct event_base *coio_default_base = NULL;
static int coio_event_init(void) {
  if (coio_default_base == NULL) {
    if (NULL == (coio_default_base = (struct event_base*)event_init()))
      return -1;
  }
  return 0;
}
static int coio_event_reinit(int do_recreate) {
  if (do_recreate) {
    if (coio_default_base != NULL) event_base_free(coio_default_base);
    return -(NULL == (coio_default_base = (struct event_base*)event_init()));
  } else {
    return coio_event_reinit_low();
  }
}
