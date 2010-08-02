#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Mon Aug  2 17:04:44 CEST 2010

"""MySQL client for Syncless using gevent-MySQL."""

import sys

from syncless.fast_mysql import geventmysql
from syncless.best_stackless import stackless
from syncless import patch

try:
  from mysql_config import MYSQL_CONFIG
except IMPORT_ERROR:
  MYSQL_CONFIG = {
      'host': None,  # '127.0.0.1'
      'port': None,  # '3306'
      'unix_socket': '/tmp/mysqld.sock',
      'user': 'mysql_user',  # e.g. 'root'
      'password': 'mysql_password',  # e.g. ''
      'database': 'mysql_database',  # e.g. 'mysql'
      'use_unicode': False,  # Use str() instead of unicode() objects.
  }

def Worker(db_conn, num_iterations, progress_channel):
  """Repeat the same query num_iteration times, reporting progress."""
  i = 0
  while i < num_iterations:
    cursor = db_conn.cursor()
    cursor.execute('SHOW FULL TABLES')
    cursor.fetchall()
    cursor.close()  # geventmysql requires this.

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
  # Without patch.geventmysql() run by importing fast_mysql, not only the
  # counter below would jump from 0 to 1000 in one big step, but maybe the
  # client wouldn't work at all, because vanilla gevenymysql expects gevent,
  # but we use Syncless here. With this patch, MySQL socket communication is
  # done with Syncless, so the counter increases in little steps.

  patch.patch_stderr()

  # Preprocess the connection information.
  mysql_config = dict(MYSQL_CONFIG)
  if mysql_config.get('unix_socket'):
    mysql_config['host'] = mysql_config.pop('unix_socket')
    mysql_config['port'] = None
    assert mysql_config['host'].startswith('/')
  if 'database' in mysql_config:
    mysql_config['db'] = mysql_config.pop('database')
  old_use_unicode = bool(mysql_config.pop('use_unicode', False))
  mysql_config['use_unicode'] = True  # Required for mysql_config['charset'].
  mysql_config.setdefault('charset', 'utf-8')
  db_conn = geventmysql.connect(**mysql_config)
  db_conn.client.set_use_unicode(old_use_unicode)
  assert geventmysql.paramstyle == 'format'

  # These are not supported by geventmysql.
  #assert db_conn.charset_name == 'utf8'
  #assert db_conn.collation_name == 'utf8_general_ci'

  #query = 'SELECT CONNECTION_ID()'
  #query = 'SELECT LENGTH("\xC3\xA1")'  # :2
  #query = 'SELECT CHAR_LENGTH("\xC3\xA1")'  #: 1
  #query = 'SELECT UPPER("\xC3\xA1")'  #: '\xC3\x81'
  # Would raise e.g. mysql.connector.errors.ProgrammingError on SQL error.
  cursor = db_conn.cursor()
  # In SQLite, this would be:
  # for row in cursor.execute('SELECT LENGTH(?), ('\xC3\xA1',)): print row
  cursor.execute('SELECT CHAR_LENGTH(%s)', ('\xC3\xA1',))

  # Since geventmysql cursors are not iterable, we have to use
  # cursor.fetchall() instead of list(cursor) here.
  assert cursor.fetchall() == [(1,)]
  cursor.close()  # geventmysql requires this.

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
  stackless.main.insert()
  sys.exit(0)


if __name__ == '__main__':
  # Moving all work to another tasklet because stackless.main is not allowed
  # to be blocked on a channel.receive() (StopIteration would be raised).
  stackless.tasklet(main)()
  stackless.schedule_remove(None)
