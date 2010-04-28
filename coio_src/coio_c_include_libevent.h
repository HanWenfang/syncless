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
#define MAY_EVENT_LOOP_RETURN_1 1
#endif

#ifdef COIO_USE_LIBEVENT1
#include <event.h>
#define MAY_EVENT_LOOP_RETURN_1 1
#endif

#ifdef COIO_USE_LIBEV
#include "./ev-event.h"
#define MAY_EVENT_LOOP_RETURN_1 0
#endif
