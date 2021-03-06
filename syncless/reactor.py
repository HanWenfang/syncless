#! /usr/local/bin/python2.4

"""A Syncless-based implementation of the Twisted main loop.

This Python module was written by reusing the source code of
libevent.reactor v0.3, available from http://launchpad.net/python-libevent
(simple BSD license).

To install the event loop (and you should do this before any connections,
listeners or connectors are added):

    import syncless.reactor
    syncless.reactor.install()

API Stability: stable

Maintainer of LibEventReactor: U{Thomas Herve <mailto:therve@free.fr>}
Copyright (c) 2007-2008 Twisted Matrix Laboratories.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import sys

from zope.interface import implements

from twisted.internet.error import ConnectionFdescWentAway
from twisted.internet.posixbase import PosixReactorBase
from twisted.internet.main import installReactor
from twisted.python import log
from twisted.internet.interfaces import IReactorFDSet
from twisted.python.runtime import platform
from twisted.python.runtime import platformType

# We don't want to import anything from syncless at the top-level (so the
# Syncless event wakeup tasklet won't be created). We only import syncless
# from within the install() function.

class SynclessReactor(PosixReactorBase):
    """
    A reactor that uses Syncless (which uses libevent).

    @ivar _selectables: A dictionary mapping integer file descriptors to
        instances of L{FileDescriptor} which have been registered with the
        reactor.  All L{FileDescriptors} which are currently receiving read or
        write readiness notifications will be present as values in this
        dictionary.

    @ivar _reads: A dictionary mapping integer file descriptors to libevent
        event objects.  Keys in this dictionary will be registered with
        libevent for read readiness notifications which will
        be dispatched to the corresponding L{FileDescriptor} instances in
        C{_selectables}.

    @ivar _writes: A dictionary mapping integer file descriptors to libevent
        event objects.  Keys in this dictionary will be registered with
        libevent for write readiness notifications which will
        be dispatched to the corresponding L{FileDescriptor} instances in
        C{_selectables}.
    """
    implements(IReactorFDSet)

    def __init__(self):
        """Initialize reactor and local fd storage."""
        # These inits really ought to be before
        # L{PosixReactorBase.__init__} call, because it adds the
        # waker in the process
        self._reads = {}
        self._writes = {}
        self._selectables = {}
        self._signal_handlers = []
        from syncless import coio
        self._wakeup_info = coio.wakeup_info()
        self._pending_events = self._wakeup_info.pending_events
        PosixReactorBase.__init__(self)


    def _add(self, xer, mode, mdict):
        """Create the event for reader/writer."""
        fd = xer.fileno()
        if fd not in mdict:
            mdict[fd] = self._wakeup_info.create_event(fd, mode)
            self._selectables[fd] = xer


    def addReader(self, reader):
        """Add a FileDescriptor for notification of data available to read."""
        self._add(reader, 1, self._reads)


    def addWriter(self, writer):
        """Add a FileDescriptor for notification of data available to write."""
        self._add(writer, 2, self._writes)


    def _remove(self, selectable, mdict, other):
        """Remove an event if found."""
        fd = selectable.fileno()
        if fd == -1:
            for fd, fdes in self._selectables.items():
                if selectable is fdes:
                    break
            else:
                return
        if fd in mdict:
            # Call event_del() on the event object.
            mdict.pop(fd).delete()
            if fd not in other:
                del self._selectables[fd]


    def removeReader(self, reader):
        """Remove a selectable for notification of data available to read."""
        return self._remove(reader, self._reads, self._writes)


    def removeWriter(self, writer):
        """Remove a selectable for notification of data available to write."""
        return self._remove(writer, self._writes, self._reads)


    def removeAll(self):
        """Remove all selectables, and return a list of them."""
        if self.waker is not None:
            self.removeReader(self.waker)
        result = self._selectables.values()
        events = self._reads.copy()
        events.update(self._writes)

        self._reads.clear()
        self._writes.clear()
        self._selectables.clear()

        for event in events.values():
            event.delete()
        if self.waker is not None:
            self.addReader(self.waker)
        return result


    def getReaders(self):
        return [self._selectables[fd] for fd in self._reads]


    def getWriters(self):
        return [self._selectables[fd] for fd in self._writes]


    def _handleSigchld(self, signum, frame, _threadSupport=platform.supportsThreads()):
        from twisted.internet.process import reapAllProcesses
        if _threadSupport:
            self.callFromThread(reapAllProcesses)
        else:
            self.callLater(0, reapAllProcesses)

    def _handleSignals(self):
        import signal
        from syncless import coio
        self._signal_handlers.append(coio.signal(signal.SIGINT,  self.sigInt))
        self._signal_handlers.append(coio.signal(signal.SIGTERM, self.sigTerm))

        # Catch Ctrl-Break in windows
        if hasattr(signal, 'SIGBREAK'):
            self._signal_handlers.append(
                coio.signal(signal.SIGBREAK, self.sigBreak))
        if platformType == 'posix':
            # Install a dummy SIGCHLD handler, to shut up warning. We could
            # install the normal handler, but it would lead to unnecessary reap
            # calls
            signal.signal(signal.SIGCHLD, lambda *args: None)
            self._signal_handlers.append(
                coio.signal(signal.SIGCHLD, self._handleSigchld))

    def _doReadOrWrite(self, fd, mode, selectable):
        """
        C{fd} is available for read or write, make the work and raise errors
        if necessary.
        """
        why = None
        inRead = False
        try:
            if mode & 1:
                why = selectable.doRead()
                inRead = True
            if not why and mode & 2:
                why = selectable.doWrite()
                inRead = False
            if selectable.fileno() != fd:
                why = ConnectionFdescWentAway('Filedescriptor went away')
                inRead = False
        except:
            log.err()
            why = sys.exc_info()[1]
        if why:
            self._disconnectSelectable(selectable, why, inRead)

    def _runPendingEvents(self, pending_events):
        # pending_events is a list of (fd, mode) pairs.
        while pending_events:
            fd, mode = pending_events.pop()
            if fd in self._selectables:
                selectable = self._selectables[fd]
                log.callWithLogger(selectable,
                        self._doReadOrWrite, fd, mode, selectable)

    def doIteration(self, timeout):
        """Call one iteration of the Syncless loop."""
        self._runPendingEvents(self._wakeup_info.tick(timeout))

    def crash(self):
        PosixReactorBase.crash(self)
        for handler in self._signal_handlers:
            handler.delete()
        del self._signal_handlers[:]


def install():
    """Install the Syncless reactor."""
    # As a side effect, this calls `from syncless import coio', which
    # creates and starts the coio.main_loop_tasklet, which calls
    # event_loop() indefinitely.
    installReactor(SynclessReactor())


__all__ = ["SynclessReactor", "install"]
