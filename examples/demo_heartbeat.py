#! /usr/local/bin/stackless2.6
#
# demo.py: demo echo server with heartbeat
# by pts@fazekas.hu at Mon Apr 12 16:55:21 CEST 2010
#

import logging
import socket
import stackless
import time

from syncless import coio


def Writer(timestamps, chan, sock):
  while True:
    msg = chan.receive()
    if msg is None:
      break
    if not isinstance(msg, str):
      raise TypeError
    timestamps[1] = max(timestamps[1], time.time())  # Register write.
    # TODO(pts): Handle errno.EPIPE (client has closed the connection while
    # we were sending).
    sock.sendall(msg)  # This might block.


def Sleeper(timestamps, write_channel, interval):
  if timestamps[0] is not None:
    sleep_amount = min(timestamps) + interval - time.time()
    while True:
      if sleep_amount > 0:
        coio.sleep(sleep_amount)
        if timestamps[0] is None:
          break
        sleep_amount = min(timestamps) + interval - time.time()
        if sleep_amount > 0:
          continue
      now_ts = time.time()
      write_channel.send('heart-beat\r\n')
      for i in xrange(len(timestamps)):
        timestamps[i] = max(timestamps[i], now_ts)
      sleep_amount = min(timestamps) + interval - time.time()


def Worker(sock, addr):
  write_channel = stackless.channel()
  write_channel.preference = 1  # Prefer the sender.
  now_ts = time.time()
  timestamps = [now_ts, now_ts]  # read_ts, write_ts
  writer_tasklet = stackless.tasklet(Writer)(timestamps, write_channel, sock)
  sleeper_tasklet = stackless.tasklet(Sleeper)(timestamps, write_channel, 3)
  # TODO(pts): Flush earlier.
  write_channel.send('Hello, please type something.\r\n')
  try:
    while True:
      msg = sock.recv(256)
      if not msg:
        break
      timestamps[0] = max(timestamps[0], time.time())  # Register read.
      # TODO(pts): Flush earlier.
      write_channel.send('You typed %r.\r\n' % msg)
  finally:
    logging.info('connection closed from %r' % (addr,))
    if writer_tasklet.alive:
      write_channel.send(None)  # Will kill writer_tasklet eventually.
    timestamps[0] = None  # Will kill sleeper_tasklet eventually.
    while writer_tasklet.alive or sleeper_tasklet.alive:
      stackless.schedule(None)
    sock.close()

if __name__ == '__main__':
  logging.root.setLevel(logging.INFO)
  logging.info('echo server with heartbeat initializing')
  server_socket = coio.new_realsocket(socket.AF_INET, socket.SOCK_STREAM)
  server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server_socket.bind(('127.0.0.1', 5454))
  server_socket.listen(100)
  logging.info('connect with:  telnet %s %s' % server_socket.getsockname()[:2])
  while True:
    client_socket, addr = server_socket.accept()
    logging.info('connection from %r, runcount=%d' %
                 (addr, stackless.runcount))
    stackless.tasklet(Worker)(client_socket, addr)
    client_socket = addr = None  # Free memory early.
