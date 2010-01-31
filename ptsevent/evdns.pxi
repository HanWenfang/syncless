# ### pts #### This file has been highly modified by pts@fazekas.hu.
#
# Example:
# import ptsevent
# 
# print ptsevent.dns_resolve_ipv4('www.google.com', 0)
# #: <dnsresult code=0, t=1, ttl=273 value=['74.125.43.147', '74.125.43.99', '74.125.43.104', '74.125.43.105', '74.125.43.106', '74.125.43.103'] at 0xb7bd9734>
# 
# print ptsevent.dns_resolve_ipv6('www.ipv6.org')
# #$ host -t AAAA www.ipv6.org
# #www.ipv6.org is an alias for shake.stacken.kth.se.
# #shake.stacken.kth.se has IPv6 address 2001:6b0:1:ea:202:a5ff:fecd:13a6
# #: <dnsresult code=0, t=3, ttl=2936 value=['2001:6b0:1:ea:202:a5ff:fecd:13a6'] at 0xb7d76d24>

# These are some Pyrex magic declarations which will enforce type safety in
# our *.pxi files by turning GCC warnings about const and signedness to Pyrex
# errors.
cdef extern from "evdns.h":
    ctypedef struct inaddr_const:
        pass
    ctypedef struct in6addr_const:
        pass
    ctypedef inaddr_const* inaddr_constp "struct in_addr const*"
    ctypedef in6addr_const* in6addr_constp "struct in6_addr const*"

    ctypedef void (*evdns_handler)(int result, char t, int count, int ttl,
                                   void *addrs, void *arg)

cdef extern from "evdns.h":
    int evdns_init()
    char *evdns_err_to_string(int err)
    int evdns_resolve_ipv4(char *name, int flags, evdns_handler callback,
                           void *arg)
    int evdns_resolve_ipv6(char *name, int flags, evdns_handler callback,
                           void *arg)
    int evdns_resolve_reverse(inaddr_constp ip, int flags, evdns_handler callback,
                              void *arg)
    int evdns_resolve_reverse_ipv6(in6addr_constp ip, int flags, evdns_handler callback,
                                   void *arg)
    void evdns_shutdown(int fail_requests)

# !! TODO(pts): Get it from C.
# Result codes
DNS_ERR_NONE		= 0
DNS_ERR_FORMAT		= 1
DNS_ERR_SERVERFAILED	= 2
DNS_ERR_NOTEXIST	= 3
DNS_ERR_NOTIMPL		= 4
DNS_ERR_REFUSED		= 5
DNS_ERR_TRUNCATED	= 65
DNS_ERR_UNKNOWN		= 66
DNS_ERR_TIMEOUT		= 67
DNS_ERR_SHUTDOWN	= 68

# Types
DNS_IPv4_A		= 1
DNS_PTR			= 2
DNS_IPv6_AAAA		= 3

# Flags
DNS_QUERY_NO_SEARCH	= 1

cdef char dns_initialized
dns_initialized = 0

def dns_init():
    """Initialize async DNS resolver unless already intitialized.

    The resolver functions call this automatically if needed.    
    """
    if not dns_initialized:
        evdns_init()
        dns_initialized = 1

def dns_init_force():
    """Initialize async DNS resolver, force reinit"""
    if dns_initialized:
        evdns_shutdown(1)
        dns_initialized = 0
    evdns_init()
    dns_initialized = 1

def dns_shutdown(int fail_requests=1):
    """Shutdown the async DNS resolver and terminate all active requests."""
    if dns_initialized:
        evdns_shutdown(fail_requests)
        dns_initialized = 0


cdef class dnsresult:
    cdef int _code
    cdef char _t
    cdef int _ttl
    cdef object _value

    property code:
        def __get__(self):
            return self._code

    property t:
        def __get__(self):
            return self._t

    property ttl:
        def __get__(self):
            return self._ttl

    property value:
        def __get__(self):
            return self._value

    def __cinit__(evbufferobj self, int code, char t, int ttl, list value):
        self._code = code
        self._t = t
        self._ttl = ttl
        self._value = value

    def __repr__(evbufferobj self):
        return '<dnsresult code=%d, t=%d, ttl=%d value=%r at 0x%x>' % (
            self._code, self._t, self._ttl, self._value, <unsigned>self)

cdef object format_ipv6_word(unsigned hi, unsigned lo):
    lo += hi << 8
    if lo:
        # TODO(pts): Faster.
        return PyString_FromFormat(<char_constp>'%x', lo)
    else:
        return ''

cdef void dns_callback(int resultcode, char t, int count, int ttl,
                       void *addrs, void *arg) with gil:
    cdef dnsresult result
    cdef int i
    cdef unsigned char *p
    cdef list xlist
    if t == DNS_IPv4_A:
        xlist = []
        p = <unsigned char*>addrs
        for i from 0 <= i < count:
            # TODO(pts): Replace all % by PyString_FromFormat.
            xlist.append(PyString_FromFormat(
                <char_constp>'%d.%d.%d.%d', p[0], p[1], p[2], p[3]))
            p += 4
        x = xlist
    elif t == DNS_IPv6_AAAA:
        xlist = []
        p = <unsigned char*>addrs
        for i from 0 <= i < count:
            words = [format_ipv6_word(p[0], p[1]),
                     format_ipv6_word(p[2], p[3]),
                     format_ipv6_word(p[4], p[5]),
                     format_ipv6_word(p[6], p[7]),
                     format_ipv6_word(p[8], p[9]),
                     format_ipv6_word(p[10], p[11]),
                     format_ipv6_word(p[12], p[13]),
                     format_ipv6_word(p[14], p[15])]
            p += 16
            xlist.append(':'.join(words))
        x = xlist
    elif t == DNS_PTR and count == 1:  # only 1 PTR possible
        x = PyString_FromString((<char_constp*>addrs)[0])
    else:
        x = None
    (<tasklet>arg).tempval = dnsresult(resultcode, t, ttl, x)
    PyTasklet_Insert(<tasklet>arg)

def dns_resolve_ipv4(char *name, int flags=0):
    """Lookup an A record (IPV4) for a given name.

    Args:
      name     -- DNS hostname
      flags    -- either 0 or DNS_QUERY_NO_SEARCH
      callback -- callback with (result, type, ttl, addrs, *args) prototype
      args     -- option callback arguments
    Returns:
      A dnsresult() object.
    """
    cdef tasklet wakeup_tasklet
    if not dns_initialized:
        evdns_init()
        dns_initialized = 1
    wakeup_tasklet = PyStackless_GetCurrent()
    wakeup_tasklet.tempval = None
    evdns_resolve_ipv4(name, flags, dns_callback, <void*>wakeup_tasklet)
    if wakeup_tasklet.tempval is None:
        return PyStackless_Schedule(None, 1)  # remove=1
    else:
        return wakeup_tasklet.tempval

def dns_resolve_ipv6(char *name, int flags=0):
    """Lookup an AAAA record (IPV6) for a given name.

    Args:
      name     -- DNS hostname
      flags    -- either 0 or DNS_QUERY_NO_SEARCH
      callback -- callback with (result, type, ttl, addrs, *args) prototype
      args     -- option callback arguments
    Returns:
      A dnsresult() object.
    """
    cdef tasklet wakeup_tasklet
    if not dns_initialized:
        evdns_init()
        dns_initialized = 1
    wakeup_tasklet = PyStackless_GetCurrent()
    wakeup_tasklet.tempval = None
    evdns_resolve_ipv6(name, flags, dns_callback, <void*>wakeup_tasklet)
    if wakeup_tasklet.tempval is None:
        return PyStackless_Schedule(None, 1)  # remove=1
    else:
        return wakeup_tasklet.tempval

# TODO(pts): Implement these with callbacks as well.
#def dns_resolve_reverse(char *ip, int flags, callback, *args):
#    """Lookup a PTR record for a given IPv4 address.
#
#    Arguments:
#
#    name     -- IPv4 address (as 4-byte binary string)
#    flags    -- either 0 or DNS_QUERY_NO_SEARCH
#    callback -- callback with (result, type, ttl, addrs, *args) prototype
#    args     -- option callback arguments
#    """
#    cdef int i
#    t = (callback, args)
#    i = id(t)
#    __evdns_cbargs[i] = t
#    # TODO(pts): Test the type safety here.
#    evdns_resolve_reverse(<inaddr_constp>ip, flags, __evdns_callback, <void *>i)
#
#def dns_resolve_reverse_ipv6(char *ip, int flags, callback, *args):
#    """Lookup a PTR record for a given IPv6 address.
#
#    Arguments:
#
#    name     -- IPv6 address (as 16-byte binary string)
#    flags    -- either 0 or DNS_QUERY_NO_SEARCH
#    callback -- callback with (result, type, ttl, addrs, *args) prototype
#    args     -- option callback arguments
#    """
#    cdef int i
#    t = (callback, args)
#    i = id(t)
#    __evdns_cbargs[i] = t
#    # TODO(pts): Test the type safety here.
#    evdns_resolve_reverse_ipv6(<in6addr_constp>ip, flags, __evdns_callback, <void *>i)
