#! /usr/local/bin/stackless2.6

"""A demo broadcasting chat server with Syncless.

This demo server runs a chat session on the console (terminal window) and it
also listens for interactive TCP connections (using telnet).
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import socket
import sys

from syncless import coio
from syncless import patch

nick_to_file = {
}
"""Dictionary mapping participants' nicknames to file objects."""

broadcast_channel = coio.stackless.channel()
"""Strings sent to this channel are broadcast to all participants."""


def BroadcastWorker():
  while True:
    msg = broadcast_channel.receive()
    for nick in sorted(nick_to_file):
      f = nick_to_file.get(nick)  # May have disappeared.
      try:
        f.write(msg)
        f.flush()
      except IOError, e:
        f.close()
        f2 = nick_to_file.get(nick)
        if f2 is f:
          print >>sys.stderr, (
              'info: I/O error broadcasting to %s (%s), closing it' %
              (nick, e))
          del nick_to_file[nick]
          if nick_to_file.get(nick) is f:
            del nick_to_file[nick]
            broadcast_channel.send('* %s has disconnected\r\n' % nick)


def ChatWorker(f, addr):
  nick = None
  try:
    try:
      f.write('* Hello, what is your nickname?\r\n')
      f.flush()
      while True:
        nick = f.readline()
        if not nick:  # EOF
          return
        nick = nick.strip()
        if nick in nick_to_file:
          f.write('* The name %s is in use, please choose another one.\r\n' %
                  nick)
          f.flush()
        else:
          break
      others = sorted(nick_to_file)
      if others:
        others_msg = 'Others online are: %s' % ', '.join(others)
      else:
        others_msg = 'Nobody else online.'
      # TODO(pts): Don't send this message to ourselves.
      broadcast_channel.send('* %s has joined\r\n' % nick)
      nick_to_file[nick] = f
      f.write('* Welcome to the chat, %s!\r\n* %s\r\n'
              '* If you enter a message, it will be sent to everyone.\r\n' %
              (nick, others_msg))
      others = others_msg = None
      f.flush()
      while True:
        msg = f.readline()
        if not msg:  # EOF
          break
        msg = msg.rstrip()
        if msg:
          if len(nick_to_file) == 1 and nick_to_file.get(nick) is f:
            f.write('* Nobody else in the chat to send your message to.\r\n')
            f.flush()
          else:
            # TODO(pts): Don't send this message to ourselves.
            broadcast_channel.send('<%s> %s\r\n' % (nick, msg))
    except IOError, e:
      print >>sys.stderr, (
          'info: I/O error to %s (%s), closing it' % (nick, e))
      if nick_to_file.get(nick) is f:
        del nick_to_file[nick]
        broadcast_channel.send('* %s has disconnected\r\n' % nick)
    except TaskletExit:
      if nick_to_file.get(nick) is f:
        del nick_to_file[nick]
        nick = None  # Prevent messages.
  finally:
    f.close()
    if nick_to_file.get(nick) is f:
      print >>sys.stderr, (
          'info: %s at %r has disconnected' % (nick, addr))
      del nick_to_file[nick]
      broadcast_channel.send('* %s has left\r\n' % nick)


def ChatListener(addr):
  ss = coio.new_realsocket(socket.AF_INET, socket.SOCK_STREAM)
  ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  ss.bind(addr)
  ss.listen(128)
  print >>sys.stderr, 'info: listening for telnet chat on %r' % (
      ss.getsockname(),)
  print >>sys.stderr, 'info: to connect, run:  telnet %s %s' % (
      ss.getsockname()[:2])
  while True:
    cs, csaddr = ss.accept()
    print >>sys.stderr, 'info: connection from %r' % (csaddr,)
    coio.stackless.tasklet(ChatWorker)(cs.makefile(), csaddr)
    cs = csaddr = None  # Free memory early.


if __name__ == '__main__':
  patch.patch_stdin_and_stdout()  # sets sys.stdin = sys.stdout = ...
  patch.patch_stderr()  # For fair exeption reporting.
  assert sys.stdin is sys.stdout
  server_host = ('127.0.0.1')
  port = 1337
  if len(sys.argv) > 2:
    server_host = sys.argv[1]
    server_port = int(sys.argv[2])
  elif len(sys.argv) > 1:
    port = int(sys.argv[1])
  broadcast_channel = coio.stackless.channel()
  broadcast_channel.preference = 1  # Prefer the sender.
  coio.stackless.tasklet(BroadcastWorker)()
  coio.stackless.tasklet(ChatListener)((server_host, port))
  # sys.stdin here can be used for writing, as set up by patch_stdin_and_stdout
  coio.stackless.tasklet(ChatWorker)(sys.stdin, 'console')
  coio.stackless.schedule_remove(None)
  # The program will run indefinitely because BroadcastWorker never exists.
