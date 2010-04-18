#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Apr 18 12:44:36 CEST 2010

import sys
import stackless

import mysql.connector as mysql_dbapi
from syncless import patch

MYSQL_CONFIG = {
    'host': None,  # '127.0.0.1'
    'port': None,  # '3306'
    'unix_socket': '/mnt/asz/d/E/D/re/hep/movemetafs/mysqldbdir/our.sock',
    'user': 'movemetafs_rw',
    'password': 'croablE4OaqL0tiu',
    'database': 'movemetafs',
    'use_unicode': False,  # Use str() instead of unicode() objects.
}

def Worker(db_conn, num_iterations, progress_channel):
  """Repeat the same query num_iteration times, reporting progress."""
  i = 0
  while i < num_iterations:
    cursor = db_conn.cursor()
    cursor.execute('SHOW FULL TABLES')
    list(cursor)  # Fetch all the values.

    i += 1
    if i == num_iterations:
      progress_channel.send(i)  # Send that we're done.
    else:
      # Only send if there is a receiver waiting.
      b = progress_channel.balance
      while b < 0:
        # channel.send blocks if there is no receiver waiting.
        progress_channel.send(i)
        b += 1


def main():
  # Without patch.patch_socket() or patch.patch_mysql_connector() the
  # counter below would jump from 0 to 1000 in one big step. With this
  # patch, MySQL socket communication is done with Syncless, so the counter
  # increases in little steps.
  patch.patch_mysql_connector()
  # patch_socket() works instead of patch_mysql_connector(), but it effects more
  # Python modules.
  #patch.patch_socket()
  patch.patch_stderr()

  db_conn = mysql_dbapi.connect(**MYSQL_CONFIG)
  assert mysql_dbapi.paramstyle == 'pyformat'
  assert db_conn.charset_name == 'utf8'
  assert db_conn.collation_name == 'utf8_general_ci'

  #query = 'SELECT CONNECTION_ID()'
  #query = 'SELECT LENGTH("\xC3\xA1")'  # :2
  #query = 'SELECT CHAR_LENGTH("\xC3\xA1")'  #: 1
  #query = 'SELECT UPPER("\xC3\xA1")'  #: '\xC3\x81'
  # Would raise e.g. mysql.connector.errors.ProgrammingError on SQL error.
  cursor = db_conn.cursor()
  # In SQLite, this would be:
  # for row in cursor.execute('SELECT LENGTH(?), ('\xC3\xA1',)): print row
  cursor.execute('SELECT CHAR_LENGTH(%s)', ('\xC3\xA1',))
  #for row in cursor:  # Fetch results.
  #  print >>sys.stderr, row
  assert list(cursor) == [(1,)]

  if len(sys.argv) > 1:
    num_iterations = int(sys.argv)
  else:
    num_iterations = 1000

  progress_channel = stackless.channel()
  progress_channel.preference = 1  # Prefer the sender.
  stackless.tasklet(Worker)(db_conn, num_iterations, progress_channel)
  done_count = 0
  receive_count = 0
  while True:
    sys.stderr.write('\r%s of %s ' % (done_count, num_iterations))
    if done_count >= num_iterations:
      break
    done_count = progress_channel.receive()
    receive_count += 1
  # receive_count might be smaller than done_count (e.g. 993 < 1000) here
  # (but sometims it's equal), because sometimes the main tasklet was slow
  # to receive, so Worker did multiple iterations per one
  # progress_channel.receive().
  sys.stderr.write('done, receive_count=%d\n' % receive_count)
  # Needed for exit because we might have done DNS lookups with coio (evdns).
  sys.exit(0)


if __name__ == '__main__':
  # Moving all work to another tasklet because stackless.main is not allowed
  # to be blocked on a channel.receive() (StopIteration would be raised).
  stackless.tasklet(main)()
  stackless.schedule_remove()
