include "event.pxi"
include "nbevent.pxi"
include "evdns.pxi"
#include "evhttp.pxi"

# --- Initialization.

event_init()

# This is needed so Ctrl-<C> raises (eventually, when the main_loop_tasklet
# gets control) a KeyboardInterrupt in the main tasklet.
event(SigIntHandler, handle=SIGINT, evtype=EV_SIGNAL | EV_PERSIST).add()

# Don't publish it. MainLoop depends on it not being changed.
cdef tasklet link_helper_tasklet
link_helper_tasklet = stackless.tasklet(LinkHelper)().remove()

# Don't publish it, as a safety for read-only.
cdef tasklet main_loop_tasklet
def get_main_loop_tasklet():
  return main_loop_tasklet
main_loop_tasklet = stackless.tasklet(MainLoop)(link_helper_tasklet)
