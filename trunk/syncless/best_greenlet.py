#! /usr/local/bin/stackless2.6

"""A greenlet emulator using Stackless Python (or greenlet itself).

To use this module, replace the first occurrence of your imports:

  # Old module import: import greenlet
  from syncless.best_greenlet import greenlet
  
  # Old class import: from greenlet import greenlet
  from syncless.best_greenlet.greenlet import greenlet

  # If you don't need the `greenlet' symbol in the current module, but you
  # want to make sure that the emulation is available for subsequent modules.
  import syncless.best_greenlet

After that, you can keep subsequent `import greenlet' statements in your code.

This module works with and without gevent and Syncless. For a combination of
gevent and Syncless, see patch_gevent() in the syncless.patch module.

In addition to the regular symbols in the Greenlet module, 

This emulation is at least 20% slower than real greenlet, but it can be much
slower. (Speed measurements needed.) The emphasis was on the correctness of
the emulation (as backed by test/greenlet_test.py) rather than its speed.

TODO(pts): Do speed measurements.
"""

__author__ = 'Peter Szabo (pts@fazekas.hu)'

def gevent_hub_main():
  """Run the gevent hub main loop forever."""
  # This doesn't work with Syncless, but we have a monkey-patch for that.
  try:
    __import__('gevent.hub').hub.get_hub().switch()
  except greenlet.GreenletExit:
    raise SystemExit

try:
  import greenlet
except ImportError:
  try:
    __import__('stackless')
  except ImportError:
    raise ImportError('either greenlet or stackless required')
  from syncless import greenlet_using_stackless as greenlet

# This is to make `from syncless.best_greenlet.greenlet import greenlet
# work, where the rightmost greenlet is our greenlet.greenlet below.
__import__('sys').modules[__name__ + '.greenlet'] = greenlet
greenlet.gevent_hub_main = gevent_hub_main
# Not setting greenlet.greenlet.gevent_hub_main, because the regular
# greenlet.greenlet is an extension type (class), so it wouldn't work.
