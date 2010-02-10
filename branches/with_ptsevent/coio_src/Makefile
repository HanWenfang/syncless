PYTHON=stackless2.6

.PHONY: all install clean

all: coio.c
	$(PYTHON) setup.py build

install:
	$(PYTHON) setup.py install

clean:
	$(PYTHON) setup.py clean
	rm -rf build

test:
	$(PYTHON) test.py

#coio.c: event.pyx nbevent.pxi evdns.pxi evhttp.pxi simple.pxi
# Ignoring DeprecationWarning since Pyrex does an `import md5'
coio.c: coio.pyx event.pxi nbevent.pxi evdns.pxi
	$(PYTHON) -W ignore::DeprecationWarning -c "from Pyrex.Compiler.Main import main; main(command_line=1)" coio.pyx
