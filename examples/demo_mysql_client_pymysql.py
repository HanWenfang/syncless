#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Apr 18 22:12:39 CEST 2010

import re
import sys
import warnings

# This warning hack needs Python2.6.
with warnings.catch_warnings():
  warnings.simplefilter('ignore', DeprecationWarning)
  import pymysql.connections
  import pymysql as mysql_dbapi
from syncless.best_stackless import stackless
from syncless import patch

# Hotfix.
#import pymysql.converters
#pymysql.converters.encoders[tuple] = \
#pymysql.converters.encoders[list] = \
#pymysql.converters.escape_sequence = lambda val: (
#    tuple(map(pymysql.converters.escape_item, val)))
#pymysql.converters.ESCAPE_REGEX = re.compile(r'[\0\n\r\032\'\"\\]')
#pymysql.converters.ESCAPE_MAP = {'\0': '\\0', '\n': '\\n', '\r': '\\r',
#                                 '\032': '\\Z', '\'': '\\\'', '"': '\\"',
#                                 '\\': '\\\\'}
#pymysql.converters.encoders[str] = \
#pymysql.converters.escape_string = lambda val: (
#    "'%s'" % pymysql.converters.ESCAPE_REGEX.sub(
#    lambda match: pymysql.converters.ESCAPE_MAP.get(match.group(0)), val))


try:
  from mysql_config import MYSQL_CONFIG
except IMPORT_ERROR:
  MYSQL_CONFIG = {
      'host': None,  # '127.0.0.1'
      'port': None,  # '3306'
      'unix_socket': '/tmp/mysqld.sock',
      'user': 'mysql_user',
      'password': 'mysql_password',
      'database': 'mysql_database',
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
  # Without patch.patch_socket() or patch.patch_pymysql() the
  # counter below would jump from 0 to 1000 in one big step. With this
  # patch, MySQL socket communication is done with Syncless, so the counter
  # increases in little steps.
  patch.patch_pymysql()
  # patch_socket() works instead of patch_pymysql(), but it effects more
  # Python modules.
  #patch.patch_socket()
  patch.patch_stderr()

  mysql_config = dict(MYSQL_CONFIG)
  if 'password' in mysql_config:
    mysql_config['passwd'] = mysql_config.pop('password')
  if 'database' in mysql_config:
    mysql_config['db'] = mysql_config.pop('database')
  if mysql_config.get('unix_socket'):
    mysql_config['host'] = '127.0.0.1'
  #mysql_config['charset'] = 'utf8'
  db_conn = mysql_dbapi.connect(**mysql_config)
  assert mysql_dbapi.paramstyle == 'format'
  cursor = db_conn.cursor()
  cursor.execute('SET NAMES %s COLLATE %s', ('utf8', 'utf8_general_ci'))
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
  stackless.main.insert()
  sys.exit(0)


if __name__ == '__main__':
  # We need this before we create the first stackless.tasklet if
  # syncless.greenstackless is used.
  __import__('syncless.coio')
  # Moving all work to another tasklet because stackless.main is not allowed
  # to be blocked on a channel.receive() (StopIteration would be raised).
  stackless.tasklet(main)()
  stackless.schedule_remove(None)
