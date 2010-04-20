# Copyright (c) 2007-2008 Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A Syncless-based implementation of the twisted main loop.

This Python module is based on libevent.reacator, available from
https://launchpad.net/python-libevent

To install the event loop (and you should do this before any connections,
listeners or connectors are added)::

    import libevent.reactor
    libevent.reactor.install()

API Stability: stable

Maintainer of LibEventReactor: U{Thomas Herve <mailto:therve@free.fr>}
"""

import sys
import stackless

from zope.interface import implements

from twisted.internet.error import ConnectionFdescWentAway
from twisted.internet.posixbase import PosixReactorBase
from twisted.internet.main import installReactor
from twisted.python import log
from twisted.internet.interfaces import IReactorFDSet
from twisted.python.runtime import platformType

import libevent

class WakeupInfo(object):
    """Information for event handlers to wake up the main loop tasklet."""
    def __init__(self):
        self.wakeup_tasklet = None
        self.pending_events = []

    def event_callback(self, fd, events, eventObj):
        """Called when an event id available."""
        if fd >= 0:  # fd is -1 for a create_timer.
            self.pending_events.append((fd, events))
        if self.wakeup_tasklet:
            self.wakeup_tasklet.insert()

    def tick(self, timeout):
        """Do one tick of the main loop iteration up to timeout.

        Returns:
          The list of pending (fd, eventmask) pairs. The caller must remove
          items from the list before the next call to tick() as it's
          processing the events, by pop()ping the item before calling the
          event handler.
        """
        assert self.wakeup_tasklet is None
        if self.pending_events or (timeout is not None and timeout <= 0):
            # Let the Syncless main loop collect more libevent events.
            stackless.schedule()
        else:
            if timeout is not None:
                libevent.create_timer(
                    self.event_callback, persist=False
                    ).add_to_loop(float(timeout))
            self.wakeup_tasklet = stackless.current
            # Event handlers call self.wakeup_tasklet.insert() to cancel this
            # stackless.schedule_remove().
            try:
                stackless.schedule_remove()
            finally:
                self.wakeup_tasklet = None
        return self.pending_events


class SynclessReactor(PosixReactorBase):
    """
    A reactor that uses libevent.

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
        """
        Initialize reactor and local fd storage.
        """
        # These inits really ought to be before
        # L{PosixReactorBase.__init__} call, because it adds the
        # waker in the process
        self._reads = {}
        self._writes = {}
        self._selectables = {}
        self._signal_handlers = []
        self._wakeup_info = WakeupInfo()
        self._pending_events = self._wakeup_info.pending_events
        PosixReactorBase.__init__(self)


    def _add(self, xer, flags, mdict):
        """
        Create the event for reader/writer.
        """
        fd = xer.fileno()
        if fd not in mdict:
            event = libevent.create_event(fd, flags,
                                          self._wakeup_info.event_callback)
            mdict[fd] = event
            event.add_to_loop()
            self._selectables[fd] = xer


    def addReader(self, reader):
        """
        Add a FileDescriptor for notification of data available to read.
        """
        self._add(reader, libevent.EV_READ|libevent.EV_PERSIST, self._reads)


    def addWriter(self, writer):
        """
        Add a FileDescriptor for notification of data available to write.
        """
        self._add(writer, libevent.EV_WRITE|libevent.EV_PERSIST, self._writes)


    def _remove(self, selectable, mdict, other):
        """
        Remove an event if found.
        """
        fd = selectable.fileno()
        if fd == -1:
            for fd, fdes in self._selectables.items():
                if selectable is fdes:
                    break
            else:
                return
        if fd in mdict:
            event = mdict.pop(fd)
            try:
                event.remove_from_loop()
            except libevent.EventError:
                pass
            if fd not in other:
                del self._selectables[fd]


    def removeReader(self, reader):
        """
        Remove a selectable for notification of data available to read.
        """
        return self._remove(reader, self._reads, self._writes)


    def removeWriter(self, writer):
        """
        Remove a selectable for notification of data available to write.
        """
        return self._remove(writer, self._writes, self._reads)


    def removeAll(self):
        """
        Remove all selectables, and return a list of them.
        """
        if self.waker is not None:
            self.removeReader(self.waker)
        result = self._selectables.values()
        events = self._reads.copy()
        events.update(self._writes)

        self._reads.clear()
        self._writes.clear()
        self._selectables.clear()

        for event in events.values():
            event.remove_from_loop()
        if self.waker is not None:
            self.addReader(self.waker)
        return result


    def getReaders(self):
        return [self._selectables[fd] for fd in self._reads]


    def getWriters(self):
        return [self._selectables[fd] for fd in self._writes]


    def _handleSignals(self):
        # !!!
        import signal

        evt = libevent.create_signal_handler(signal.SIGINT, self.sigInt, True)
        evt.add_to_loop()
        self._signal_handlers.append(evt)

        evt = libevent.create_signal_handler(
            signal.SIGTERM, self.sigTerm, True)
        evt.add_to_loop()
        self._signal_handlers.append(evt)

        # Catch Ctrl-Break in windows
        if hasattr(signal, "SIGBREAK"):
            evt = libevent.create_signal_handler(
                signal.SIGBREAK, self.sigBreak, True)
            evt.add_to_loop()
            self._signal_handlers.append(evt)
        if platformType == "posix":
            # Install a dummy SIGCHLD handler, to shut up warning. We could
            # install the normal handler, but it would lead to unnecessary reap
            # calls
            signal.signal(signal.SIGCHLD, lambda *args: None)
            evt = libevent.create_signal_handler(signal.SIGCHLD,
                                                 self._handleSigchld, True)
            evt.add_to_loop()
            self._signal_handlers.append(evt)


    def _doReadOrWrite(self, fd, eventmask, selectable):
        """
        C{fd} is available for read or write, make the work and raise errors
        if necessary.
        """
        why = None
        inRead = False
        try:
            if eventmask & libevent.EV_READ:
                why = selectable.doRead()
                inRead = True
            if not why and eventmask & libevent.EV_WRITE:
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
        # pending_events is a list of (fd, eventmask) pairs.
        while pending_events:
            fd, eventmask = pending_events.pop()
            if fd in self._selectables:
                selectable = self._selectables[fd]
                log.callWithLogger(selectable,
                        self._doReadOrWrite, fd, eventmask, selectable)

    def doIteration(self, timeout):
        """
        Call one iteration of the libevent loop.
        """
        # !!! no need for reactor.run() == twisted.internet.base.mainLoop.
        self._runPendingEvents(self._wakeup_info.tick(timeout))

    def crash(self):
        PosixReactorBase.crash(self)
        for handler in self._signal_handlers:
            handler.remove_from_loop()
        self._signal_handlers[:] = []


# !! use the coio main loop instead
def mainLoop():
    while True:
        if stackless.runcount > 1:
            libevent.loop(libevent.EVLOOP_ONCE | libevent.EVLOOP_NONBLOCK)
        else:
            libevent.loop(libevent.EVLOOP_ONCE)
        stackless.schedule()


def install():
    """
    Install the libevent reactor.
    """
    p = SynclessReactor()
    installReactor(p)
    # As a side effect, this import creates and starts the
    # coio.main_loop_tasklet.
    #from syncless import coio
    stackless.tasklet(mainLoop)()


__all__ = ["SynclessReactor", "install"]
