#! /usr/local/bin/stackless2.6

import stackless
import sys
import thread
import time

if len(sys.argv) > 1:
  thread.start_new_thread(time.sleep, (3,))

c = stackless.channel()
print stackless.getruncount()
# Stackless raises a
# RuntimeError('Deadlock: the last runnable tasklet cannot be blocked.')
# here unless we create the thread above.
print c.receive()
