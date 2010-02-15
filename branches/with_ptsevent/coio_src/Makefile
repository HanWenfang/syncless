PYTHON=stackless2.6

# Ignoring DeprecationWarning since Pyrex does an `import md5'
PYREXC=$(PYTHON) -W ignore::DeprecationWarning -c "from Pyrex.Compiler.Main import main; main(command_line=1)"
CYTHON=$(PYTHON) -c "from Cython.Compiler.Main import main; main(command_line = 1)"

.PHONY: all install clean

all: coio.c
	cd .. && $(PYTHON) setup.py build

install:
	cd .. && $(PYTHON) setup.py install

clean:
	cd .. && $(PYTHON) setup.py clean
	rm -rf ../build

# Doesn't work yet.
#test:
#	$(PYTHON) test.py

# Compile with Cython instead of Pyrex because Pyrex has the bug
# http://code.google.com/p/pts-mini-gpl/source/browse/trunk/excbug/README.txt
coio.c: coio.pyx event.pxi nbevent.pxi evdns.pxi
	$(CYTHON) coio.pyx
