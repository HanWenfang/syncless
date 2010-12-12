include "nbevent.pxi"
include "evdns.pxi"
#include "evhttp.pxi"

# --- Initialization.

assert not coio_loaded(), 'syncless.coio loaded multiple times'

import sys
if ('gevent.core' in sys.modules and
    sys.modules['gevent.core'].get_version() == version()):
  # gevent.core.init() has already called event_init(), so we won't call it
  # here again. If we did, then the events registered by gevent would get
  # lost.
  pass
elif coio_event_init() != 0:
  raise OSError(EIO, 'event_init failed')

_setup_sigint()
_setup_sigusr1()
_setup_sigusr2()

# Don't publish it, as a safety for read-only.
cdef tasklet main_loop_tasklet
def get_main_loop_tasklet():
  return main_loop_tasklet
main_loop_tasklet = stackless.tasklet(_main_loop)()

try:
  read_etc_hosts()
except IOError:
  pass
