#! /usr/bin/python2.5

# by pts@fazekas.hu at Thu May  6 21:00:13 CEST 2010
import sys
print 'HELLO'
assert 'stackless' not in sys.modules
from syncless import greenstackless
sys.modules['stackless'] = greenstackless

