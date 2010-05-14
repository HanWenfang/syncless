#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Fri May 14 14:22:30 CEST 2010

"""Interactive Python console for Syncless and coroutines.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.


Example invocation:

  $ python -m syncless.console

See more on http://code.google.com/p/syncless/wiki/Console .
"""

import array
import code
import errno
import fcntl
import os
import re
import select
import site
import struct
import sys
import termios

from syncless import coio
from syncless import patch
from syncless import wsgi

def BlockingWriteAll(out_fd, data):
  """A blocking version to write all of data to out_fd."""
  while len(data):
    got = os.write(out_fd, data)
    if got == len(data):
      break
    data = buffer(data, got)


PROMPT_ANSI_RE = re.compile(r'\e\[[0-9;]*m')


def GetPromptWidth(prompt):
  """Return the display width of a prompt."""
  # We could be much smarter here, e.g. interpret '\n' and '\r' to jump to
  # 0, detect UTF-8, and count UTF-8 characters only.
  if '\e' in prompt:
    # Get rid of \e[...m (ANSI escape sequence character mode formatting).
    prompt = PROMPT_ANSI_RE.sub('', prompt)
  return len(prompt)


def WritePromptToNextLine(out_fd, prompt, prompt_width):
  packed_hh = struct.pack('hh', 0, 0)
  try:
    width = struct.unpack('hh', fcntl.ioctl(
        out_fd, termios.TIOCGWINSZ, packed_hh))[1]
  except (IOError, OSError, ValueError, IndexError, struct.error):
    width = None
  if width and width > 1 + prompt_width:
    # Move cursor to the beginning of the (next) line. This trich is
    # also done by zsh(1).
    BlockingWriteAll(
        out_fd, '%%%s\r%s' %
        (' ' * (width - 1 - prompt_width), prompt))
  else:
    # Move cursor to the beginning of the line.
    BlockingWriteAll(out_fd, '\r' + prompt)

just_after_prompt = False
"""False or (out_fd, prompt).

Boolean value indicates if a prompt was displayed but nothing typed.
"""

def NewReadLine(in_fd, out_fd):
  """Terminal-enhanced readline function generator.

  Tested on Linux 2.6.
  """
  xin = coio.fdopen(in_fd, 'r', do_close=False)
  packed_i = struct.pack('i', 0)

  def NonTerminalReadLine(prompt=''):
    xout.write(prompt)
    xout.flush()
    # Coroutines are scheduled while xin.readline() is reading the rest of
    # its line.
    line = xin.readline()
    if line:
      return line.rstrip('\n')
    raise EOFError

  def TerminalReadLine(prompt=''):
    old = termios.tcgetattr(0)
    new = list(old)
    new[6] = list(new[6])  # Copy sublist.
    #print 'READLINE', prompt
    new[3] &= ~termios.ECHO  # [2] is c_lflag
    new[3] &= ~termios.ICANON  # [3] is c_lflag
    #new[6][termios.VMIN] = '\0'  # !! VMIN -- no effect below, affects only blocking / nonblocking reads
    termios.tcsetattr(0, termios.TCSANOW, new)
    BlockingWriteAll(out_fd, prompt)
    global just_after_prompt
    just_after_prompt = (out_fd, prompt)
    try:
      while not xin.wait_for_readable():
        pass
    finally:
      just_after_prompt = False
    # Is this the correct way to disable new input while we're examining the
    # existing input?
    termios.tcflow(in_fd, termios.TCIOFF)
    nread = struct.unpack('i', fcntl.ioctl(
        in_fd, termios.FIONREAD, packed_i))[0]
    # We read more than 1 character here so that we can push all characters in
    # an escape sequence back.
    got = xin.read_at_most(nread)
    if got in ('\r', '\n'):  # Helps GNU libreadline a bit.
      BlockingWriteAll(out_fd, '\n')
      return ''
    if '\x04' in got:  # Got EOF (isn't handled well here by readline).
      new[3] |= termios.ECHO  # [2] is c_lflag; this is needed by readline.so
      new[3] |= termios.ICANON  # [2] is c_lflag; superfluous
      termios.tcsetattr(0, termios.TCSANOW, new)
      for c in got:
        fcntl.ioctl(in_fd, termios.TIOCSTI, c)
      termios.tcflow(in_fd, termios.TCION)
      raise EOFError
    prompt_width = GetPromptWidth(prompt)
    if 'readline' in sys.modules:  # raw_input() is GNU libreadline.
      WritePromptToNextLine(out_fd, '', prompt_width)
      new[3] |= termios.ICANON  # [2] is c_lflag; superfluous
      termios.tcsetattr(0, termios.TCSANOW, new)
      for c in got:
        fcntl.ioctl(in_fd, termios.TIOCSTI, c)
      new[3] |= termios.ECHO  # [2] is c_lflag; this is needed by readline.so
      termios.tcsetattr(0, termios.TCSANOW, new)
      termios.tcflow(in_fd, termios.TCION)
      # The disadvantage of the GNU libreadline implementation of
      # raw_input() here is that coroutines are not scheduled while readline
      # is reading the prompt (the non-first character).
      try:
        return raw_input(prompt)
      finally:
        termios.tcsetattr(in_fd, termios.TCSANOW, old)
    else:
      WritePromptToNextLine(out_fd, prompt, prompt_width)
      new[3] |= termios.ECHO  # [2] is c_lflag; this is needed by readline.so
      new[3] |= termios.ICANON  # [2] is c_lflag; superfluous
      termios.tcsetattr(0, termios.TCSANOW, new)
      for c in got:
        fcntl.ioctl(in_fd, termios.TIOCSTI, c)
      termios.tcflow(in_fd, termios.TCION)
      if False:
        # Coroutines are scheduled in xin.readline(), so this would be
        # incompatible with raw_input() above.
        try:
          line = xin.readline()
        finally:
          termios.tcsetattr(in_fd, termios.TCSANOW, old)
        if line:
          return line.rstrip('\n')
        raise EOFError
      line = array.array('c')  # TODO(pts): Use a byte arra
      while True:
        # Do a blocking read on purpose, so other tasklets are suspended until
        # the user finishes typing the command.
        try:
          c = os.read(in_fd, 1)  # Don't read past the first '\n'.
        except OSError, e:
          if e.errno != errno.EAGAIN:
            raise
          select.select([in_fd], (), ())
          continue
        if not c:
          if line:
            return line.tostring()  # Without the terminating '\n'.
          else:
            raise EOFError
        if c in ('\r', '\n'):
          return line.tostring()
        line.append(c)

  if os.isatty(in_fd):
    return TerminalReadLine
  else:
    xout = coio.fdopen(out_fd, 'w', do_close=False)
    return NonTerminalReadLine

class _Ticker(object):
  """Background tasklet demonstration for syncless.console.

  To start the tasklet, type this to syncless.console: +ticker

  To stop the tasklet, type this: -ticker
  """

  ticker_worker = None

  @classmethod
  def TickerWorker(cls, sleep_amount):
    while True:
      os.write(1, '.')
      coio.sleep(sleep_amount)

  def __pos__(self):
    if self.ticker_worker is None:
      self.ticker_worker = coio.stackless.tasklet(self.TickerWorker)(0.1)

  def __neg__(self):
    if self.ticker_worker is not None:
      self.ticker_worker.remove()
      self.ticker_worker.kill()
      self.ticker_worker = None

console_tasklet = None

def wrap_tasklet(function):
  """Create tasklet like stackless.tasklet(function), handle exceptions."""
  import traceback

  def TaskletWrapper(*args, **kwargs):
    try:
      function(*args, **kwargs)
    except TaskletExit:
      pass
    except:
      newlines = '\n\n'
      if just_after_prompt:
        newlines = '\n'
      BlockingWriteAll(
          2, '\n%sException terminated tasklet, resuming syncless.console.%s'
          % (''.join(traceback.format_exc()), newlines))
      if just_after_prompt:  # Display the prompt again.
        out_fd, prompt = just_after_prompt
        BlockingWriteAll(out_fd, prompt)
      coio.insert_after_current(console_tasklet)

  return coio.stackless.tasklet(TaskletWrapper)


# Create a class just to display its name.
class SynclessInteractiveConsole(code.InteractiveConsole):
  pass


SYNCLESS_CONSOLE_HELP = (
    'See more on http://code.google.com/p/syncless/wiki/Console\n'
    'Example commands on syncless.console:\n'
    '+ticker\n'
    '-ticker\n'
    'wsgi.simple(8080, lambda *args: [\'Hello, <b>World!</b>\']) or None\n'
    'wrap_tasklet(lambda: 1 / 0)()')

class _Helper(site._Helper):
  def __repr__(self):
    return ('%s\n%s') % (site._Helper.__repr__(self), SYNCLESS_CONSOLE_HELP)


console_module = type(code)('__console__')
# Initialize __builtins__ etc.
exec '' in console_module.__dict__
# TODO(pts): Add functionality to suspend all other tasklets temporarily.
console_module.coio = coio
console_module.patch = patch
console_module.wsgi = wsgi
console_module.stackless = coio.stackless
console_module.help = _Helper()
console_module.ticker = _Ticker()
console_module.wrap_tasklet = wrap_tasklet
sys.modules['__console__'] = console_module

def main(argv=None):
  console = SynclessInteractiveConsole(console_module.__dict__)
  if os.isatty(0):
    try:
      import readline
    except ImportError:
      pass
  console.raw_input = NewReadLine(0, 1)
  global console_tasklet
  console_tasklet = coio.stackless.current
  try:
    console.interact(None)
  finally:
    console_tasklet = None

if __name__ == '__main__':
  sys.exit(main(sys.argv) or 0)
