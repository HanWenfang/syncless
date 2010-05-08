include "nbevent.pxi"
include "evdns.pxi"
#include "evhttp.pxi"

# --- Initialization.

assert not coio_loaded(), 'syncless.coio loaded multiple times'

if coio_event_init() != 0:
  raise OSError(EIO, 'event_init failed')

_setup_sigint()

# Don't publish it, as a safety for read-only.
cdef tasklet main_loop_tasklet
def get_main_loop_tasklet():
  return main_loop_tasklet
main_loop_tasklet = stackless.tasklet(MainLoop)()

try:
  read_etc_hosts()
except IOError:
  pass
