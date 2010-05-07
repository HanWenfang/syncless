#! /usr/bin/python2.5

"""Use Stackless Python or emulate it with greenlet.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

Example: Use

  from syncless.best_stackless import stackless   # Emulates if needed.

instead of

  import stackless  # No emulation.

If your program has to work even without Syncless, use this:

  try:
    from syncless.best_stackless import stackless
  except ImportError:
    import stackless

If you import syncless.coio in your module, you don't have to import stackless:
you can just use coio.stackless instead.

"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

try:
  # Use __import__ to avoid loading from os.path.dirname(__file__)
  stackless = __import__('stackless')
except ImportError:
  import greenstackless as stackless  # syncless.greenstackless
  __import__('sys').modules['stackless'] = stackless
