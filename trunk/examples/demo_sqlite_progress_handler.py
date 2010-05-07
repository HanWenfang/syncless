#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Apr 18 23:45:16 CEST 2010
#
# SQLite doesn't work with Syncless, because it blocks too much.
# This file is a demonstration how long time SQLite might spend on a single
# query.

import sqlite3
from syncless.best_stackless import stackless
import sys

def ProgressHandler():
  sys.stderr.write('.')

db_conn = sqlite3.connect(':memory:')

# SUXX: Specifying 700 (or 1000) instead of 600 here would suppress the dot
# in the first few rows.
db_conn.set_progress_handler(ProgressHandler, 600)

cursor = db_conn.cursor()
cursor.execute('PRAGMA journal_mode = off')
cursor.execute('CREATE TABLE t (i integer)')
for i in xrange(200):
  cursor.execute('INSERT INTO t (i) VALUES (?)', (i,))
sys.stderr.write('I')

query = ('SELECT t1.i, t2.i, t3.i FROM t AS t1, t AS t2, t AS T3 '
         'WHERE t1.i < t2.i AND t2.i < t3.i')
for row in cursor.execute(query):
  if row[1] == 198 and row[2] == 199: sys.stderr.write('/')

sys.stderr.write('S')
sys.stderr.write('\n')
