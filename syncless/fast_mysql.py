#! /usr/local/bin/stackless2.6

"""Fast MySQL client binding for Syncless, using geventmysql.

To use this module, replace the first occurrence of your imports:

  # Old import: import geventmysql
  from syncless.fast_mysql import geventmysql

See examples/demo_mysql_client_geventmysql.py for an example.
"""
from syncless import patch
# Patch first to avoid importing the real gevent (might not be available).
patch.patch_geventmysql()
import geventmysql
del patch