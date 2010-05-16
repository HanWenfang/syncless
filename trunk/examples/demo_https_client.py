#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Apr 18 15:00:18 CEST 2010
#
# This demo needs Python2.6 because Python2.5 doesn't have proper SSL support.

import re
import sys
import urllib2

from syncless.best_stackless import stackless
from syncless import coio
from syncless import patch


def FetchWorker(url, result_channel):
  try:
    # This will use nbsslsocket and nbsslsocket.makefile()
    f = urllib2.urlopen(url)
    try:
      data = f.read()
    finally:
      f.close()
  except Exception, e:
    raise
    # So result_channel.receive() can catch it.
    # SUXX: A new exception object gets propagated, and the traceback gets
    # lost.
    result_channel.send_exception(type(e), e)
    return
  result_channel.send(data)


def ProgressReporter(delta_sec):
  while True:
    sys.stderr.write('.')
    coio.sleep(delta_sec)


def main():
  patch.patch_socket()
  patch.patch_ssl()
  result_channel = stackless.channel()
  result_channel.preference = 1  # Prefer the sender.
  stackless.tasklet(FetchWorker)('https://www.facebook.com/', result_channel)
  progress_reporter_tasklet = stackless.tasklet(ProgressReporter)(0.02)
  # This blocks the current tasklet, while FetchWorker and ProgressReporter are
  # running.
  data = result_channel.receive()
  progress_reporter_tasklet.kill()
  sys.stderr.write("\n")
  match = re.search(r'(?is)<title>(.*?)</title>', data)
  if match:
    data = match.group(1).strip()
  print 'Downloaded:', data
  # Needed for exit because we did DNS lookups with coio (evdns).
  # !! Remove stackless.main.insert() once the segfault bug is fixed.
  stackless.main.insert()
  sys.exit(0)


if __name__ == '__main__':
  # Moving all work to another tasklet because stackless.main is not allowed
  # to be blocked on a channel.receive() (StopIteration would be raised).
  stackless.tasklet(main)()
  stackless.schedule_remove(None)
