#! /usr/local/bin/stackless2.6

"""A greenlet emulator using Stackless Python (or greenlet itself).

Please see the docstring of the syncless.greenlet_using_stackless module to
get a godd understanding of the emulator backend, its limitations etc.

To use this emulator, replace the first occurrence of your imports:

  # Old module import: import greenlet
  from syncless.best_greenlet import greenlet
  
  # Old class import: from greenlet import greenlet
  from syncless.best_greenlet.greenlet import greenlet

  # If you don't need the `greenlet' symbol in the current module, but you
  # want to make sure that the emulation is available for subsequent modules.
  import syncless.best_greenlet

After that, you can keep subsequent `import greenlet' statements in your code.

This emulator works with and without gevent and Syncless. For a combination
of gevent and Syncless, see patch_gevent() in the syncless.patch module.

This emulator supports gevent. Example code:

  import syncless.best_greenlet  # Use real greenlet, or revert to emulation.
  import gevent.wsgi
  def WsgiApp(env, start_response):
    return ['Hello, <b>World</b>!']
  gevent.wsgi.WSGIServer(('127.0.0.1', 8080), WsgiApp).serve_forever()

"""

__author__ = 'Peter Szabo (pts@fazekas.hu)'

def gevent_hub_main():
  """Run the gevent hub main loop forever."""
  # This doesn't work with Syncless, but we have a monkey-patch for that,
  # see syncless.patch.gevent_hub_main().
  __import__('gevent.hub').hub.get_hub().switch()

try:
  import greenlet
except ImportError:
  try:
    __import__('stackless')
  except ImportError:
    raise ImportError('either greenlet or stackless required')
  from syncless import greenlet_using_stackless as greenlet
  __import__('sys').modules['greenlet'] = greenlet

# This is to make `from syncless.best_greenlet.greenlet import greenlet
# work, where the rightmost greenlet is our greenlet.greenlet below.
__import__('sys').modules[__name__ + '.greenlet'] = greenlet
greenlet.gevent_hub_main = gevent_hub_main
# Not setting greenlet.greenlet.gevent_hub_main, because the regular
# greenlet.greenlet is an extension type (class), so it wouldn't work.
