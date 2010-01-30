PYTHON=stackless2.6

.PHONY: all install clean

all: ptsevent.c
	$(PYTHON) setup.py build

install:
	$(PYTHON) setup.py install

clean:
	$(PYTHON) setup.py clean
	rm -rf build

test:
	$(PYTHON) test.py

#ptsevent.c: event.pyx nbevent.pxi evdns.pxi evhttp.pxi simple.pxi
ptsevent.c: ptsevent.pyx event.pxi nbevent.pxi evdns.pxi
	$(PYTHON) -c "from Pyrex.Compiler.Main import main; main(command_line=1)" ptsevent.pyx
