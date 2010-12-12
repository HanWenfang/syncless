#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Fri Aug  6 12:44:56 CEST 2010

"""Interactive Python console listening on a TCP port for Syncless.

Example startup:

  $ python -m syncless.remote_console 5454
  (keep it running)

Example client connection with line editing:

  $ python -m syncless.backdoor_client 127.0.0.1 5454

Example client connection without line editing:

  $ telnet 127.0.0.1 5454

Although snycless.remote_console can be used as a script alone (see
``Example startup'' above), and it can serve multiple concurrent backdoor
console connections, it's even more useful as part of a real server
application, for debugging, e.g.

  from syncless import coio
  from syncless import remote_console
  coio.stackless.tasklet(
      remote_console.RemoteConsoleListener)('127.0.0.1', 5454)
  for i in xrange(100):
    coio.sleep(1)

Or, even better, all Syncless applications start a RemoteConsole
automatically when they receive a SIGUSR1 (without further configuration).
Use syncless/backdoor_client.py to send this SIGUSR1, and connect to the
RemoteConsole of any Syncless application. Please note that this automatice
RemoteConsole creation is safe, because it accepts connections on 127.0.0.1,
and only from the same UID. To disable this functionality, call

  from syncless import coio
  coio.signal(signal.SIGUSR1, None)

Then, a client connection (see ``Example client connection'' above) can
examine the state of the server, e.g.

  >>> import __main__
  >>> __main__.i
  14
  >>> __main__.i
  15

Please note that you should disable the RemoteConsoleListener in non-debug
configurations (and/or in the default settings) of your applications,
because the functinality it exposes is huge security risk, because attackers
can execute arbitrary Python code (and thus arbitrary code) on the machine,
without authentication, if the backdoor TCP port is open for them.

TODO(pts): See more on http://code.google.com/p/syncless/wiki/Console .
"""

import code
import errno
import logging
import os
import socket
import sys
import types
from syncless import coio


class RemoteConsoleExit(Exception):
  """Raised when the user wants to exit from the remote console."""


class FakeKeyboardInterrupt(Exception):
  """Never raised. Just for faking KeyboardInterrupt in interact()."""


class RemoteConsole(code.InteractiveConsole):
  """Console for incoming telnet and syncless.backdoor_client connections.

  Other Python libraries have the same functionaly in a module named
  ``backdoor''.

  This console doesn't override sys.stdout, sys.stdin or the print instruction.
  I/O to them goes to them instead of the RemoteConsole. So typing `print 42'
  (outputs to the original sys.stdout) is different from typing just `42' 
  (outputs to the RemoteConsole).

  Please note that the Python debugger is not supported.
  """

  def __init__(self, console_file):
    code.InteractiveConsole.__init__(self)
    if not hasattr(console_file, 'readline'):
      raise TypeError
    if not hasattr(console_file, 'write'):
      raise TypeError
    if not hasattr(console_file, 'flush'):
      raise TypeError
    self.console_file = console_file
    self.had_eof = False
    if 'compile' in self.__dict__:
      self.interactive_compile = self.__dict__['compile']
      del self.compile
    else:
      self.interactive_compile = code.CommandCompiler()
    assert 'compile' not in self.__dict__

  def raw_input(self, prompt):
    if self.had_eof:
      raise EOFError
    prompt = prompt.replace('\0', '')
    # We pad the prompt on both sides for syncless.backdoor_client, so it can
    # know when to start reading the prompt with readline. The padding is
    # ignored by telnet and most Unix terminal emulators.
    self.write('\0\r\0\r\r' + prompt + '\0')
    try:
      # Sometimes we get ECONNRESET.
      line = self.console_file.readline()
    except (IOError, socket.error):
      line = ''
    if line:
      return line.rstrip('\r\n')
    else:
      self.had_eof = True
      raise EOFError

  def write(self, msg):
    try:
      # We assume that self.console_file has autoflush turned on.
      self.console_file.write(msg)
    except (IOError, socket.error):
      self.had_eof = True

  def compile(self, source, filename, symbol):
    assert not isinstance(source, unicode), (
        'sys.stdin not patched properly in RemoteConsole.interact()')
    #print repr(source)
    if source == '\xff\xf3\xff\xfd\x06':  # Ctrl-<Baskslash> <Enter> in telnet.
      source = 'quit()'
    if source == '\xff\xf4\xff\xfd\x06':  # Ctrl-<C> <Enter> in telnet.
      source = 'quit()'
    if source == '\x04':  # Ctrl-<D> <Enter> in telnet.
      source = 'quit()'
    if source in ('quit()', 'exit()'):
      raise RemoteConsoleExit
    if symbol != 'single':  # Not used by default
      return self.interactive_compile(source, filename, symbol)
    code1 = self.interactive_compile(source, filename, 'exec')
    if code1 is None:  # source is incomplete.
      return None
    try:
      code2 = self.interactive_compile(source, filename, 'eval')
    except SyntaxError:
      return code1  # Return the statement code.
    if code2 is None:  # Unlikely that source is incomplete.
      return code1

    def EvalAndPrint():
      self = globals().pop('___Console__')
      code2 = globals().pop('___Code2__')
      self.write('%s\n' % eval(code2, self.locals))

    self.locals['___Console__'] = self
    self.locals['___Code2__'] = code2
    return EvalAndPrint.func_code  # Will be called once in self.runcode.

  def interact(self):
    self.write('\0\0\r')  # Signify that we're a RemoteClient server.

    # Fake sys.stdin in code.InteractiveConsole.interact
    func = code.InteractiveConsole.interact  # .im_func not needed
    fake_globals = dict(func.func_globals)
    sys = fake_globals['sys']
    fake_globals['sys'] = type(sys)('fake_sys')
    # Don't ignore (!) the real KeyboardInterrupt while waiting for a command
    # prompt response.
    fake_globals['KeyboardInterrupt'] = FakeKeyboardInterrupt
    for name in dir(sys):
      if name != 'stdin':
        setattr(fake_globals['sys'], name, getattr(sys, name))
    # Make getattr(sys.stdin, "encoding", None) in code.py return None.
    fake_globals['sys'].stdin = object()

    try:
      types.FunctionType(
          func.func_code, fake_globals, None, func.func_defaults)(self)
    except RemoteConsoleExit:
      pass


def HasTcpPeerUid(peer_name, uid):
  """Return true if the specified UID as the specified TCP peer open.
  
  Root (UID 0) is also accepted instead of uid.
  
  Please note that multiple users might have the same TCP peer open. This
  function returns True if uid is one of them.
  """
  if peer_name[0] != '127.0.0.1':
    return False
  f = coio.popen(
      'exec lsof -a -n -i4TCP@127.0.0.1:%d -u%d' % (peer_name[1], uid))
  try:
    data = f.read()
  finally:
    status = f.close()
  return not status and ('TCP 127.0.0.1:%d->' % peer_name[1]) in data


def RemoteConsoleHandler(sock, saddr, do_check_uid):
  """Handle a RemoteConsole client connection."""
  # Please note that we can't allow anyone else other than os.geteuid(), not
  # even root, because lsof(1) used by HasTcpPeerUid cannot list other user's
  # files, so HasTcpPeerUid would return false anyway.
  if do_check_uid and not HasTcpPeerUid(saddr, os.geteuid()):
    sock.close()
    return
  # Set the buffer size to 0 (autoflush).
  if hasattr(sock, 'makefile_samefd'):
    f = sock.makefile_samefd('r+', 0)
    do_close = True
  else:
    f = sock.makefile('r+', 0)
    sock = None  # Release reference so f.close() will close the connection.
    do_close = False
  fd = f.fileno()
  logging.info('RemoteConsole accepted from=%r, fd=%d' % (saddr, fd))
  try:
    console = RemoteConsole(f).interact()
  finally:
    try:
      logging.info('RemoteConsole disconnected from=%r, fd=%d' % (saddr, fd))
    except IOError:
      pass
    if do_close and not f.closed:
      f.close()


def RemoteConsoleListener(bind_addr, bind_port):
  """Listen for RemoteConsole connections, and handle them in tasklets."""
  server_socket = coio.nbsocket(socket.AF_INET, socket.SOCK_STREAM)
  server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server_socket.bind((bind_addr, bind_port))
  logging.info(
      'RemoteConsole accepting on %r' % (server_socket.getsockname(),))
  baddr = server_socket.getsockname()
  logging.info(
      'connect with: %s -m syncless.backdoor_client %s %s' %
      (sys.executable, baddr[0], baddr[1]))
  logging.info('fallback connect with: telnet %s %s' % baddr[:2])
  logging.info('press Ctrl-<C> to abort the app with the RemoteConsole')
  server_socket.listen(16)
  while True:
    sock, saddr = server_socket.accept()
    coio.stackless.tasklet(RemoteConsoleHandler)(
        sock, saddr, do_check_uid=False)
    sock = saddr = None  # Save memory, allow early close.

def SilentConsoleListener(server_socket):
  while True:
    sock, saddr = server_socket.accept()
    coio.stackless.tasklet(RemoteConsoleHandler)(
        sock, saddr, do_check_uid=True)
    sock = saddr = None  # Save memory, allow early close.

console_signal_server = []

def ConsoleSignalHandler(signum=None):
  """This is called by coio on SIGUSR1."""
  if not console_signal_server:
    console_server_socket = coio.nbsocket(socket.AF_INET, socket.SOCK_STREAM)
    console_server_socket.bind(('127.0.0.1', 0))
    console_server_socket.listen(16)
    filename = '/tmp/syncless.console.port.%s' % (
        console_server_socket.getsockname()[1])
    f = open(filename, 'a')
    try:
      os.unlink(filename)
    except OSError, e:
      if e[0] != errno.ENOENT:  # It's OK if the file was missing.
        raise
    coio.stackless.tasklet(SilentConsoleListener)(console_server_socket)
    console_signal_server[:] = [console_server_socket, f]
    # We just don't close f, so `lsof' would display filename + ' (deleted)'
    # (on Linux) or '/private' + filename (on Mac OS X).


def main(argv):
  if not (1 <= len(argv) <= 3) or (len(argv) > 1 and
                                       argv[1] == '--help'):
    print >>sys.stderr, (
        'Usage: %s [[<bind-addr>] <tcp-port>]\n'
        'Default <bind-addr> is 127.0.0.1, other useful: 0.0.0.0.\n'
        'Default <tcp-port> is 5454.' % argv[0])
    sys.exit(1)
  logging.root.setLevel(logging.INFO)
  logging.BASIC_FORMAT = '[%(created)f] %(levelname)s %(message)s'
  if len(argv) > 2:
    bind_addr = argv[1]
  else:
    bind_addr = '127.0.0.1'
  if len(argv) > 1:
    bind_port = int(argv[-1])
  else:
    bind_port = 5454
  RemoteConsoleListener(bind_addr, bind_port)


if __name__ == '__main__':
  sys.exit(main(sys.argv) or 0)
