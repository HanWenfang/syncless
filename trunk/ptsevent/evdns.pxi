#
# evdns.pxi: Non-blocking DNS lookup routines
# by pts@fazekas.hu at Sat Feb  6 20:04:13 CET 2010
# ### pts #### This file has been highly modified by pts@fazekas.hu.
#
# Example:
# import ptsevent
# 
# print ptsevent.dns_resolve_ipv4('www.google.com', 0)
# #: <dnsresult code=0, t=1, ttl=273 values=['74.125.43.147', '74.125.43.99', '74.125.43.104', '74.125.43.105', '74.125.43.106', '74.125.43.103'] at 0xb7bd9734>
# 
# print ptsevent.dns_resolve_ipv6('www.ipv6.org')
# #$ host -t AAAA www.ipv6.org
# #www.ipv6.org is an alias for shake.stacken.kth.se.
# #shake.stacken.kth.se has IPv6 address 2001:6b0:1:ea:202:a5ff:fecd:13a6
# #: <dnsresult code=0, t=3, ttl=2936 values=['2001:6b0:1:ea:202:a5ff:fecd:13a6'] at 0xb7d76d24>

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

    ctypedef void (*evdns_callback_type)(
        int result, char t, int count, int ttl,
        void *addrs, void *arg)

ctypedef int (*_evdns_call_t)(char_constp name, int flags,
                              evdns_callback_type callback,
                              void *arg)

cdef extern from "evdns.h":
    int evdns_init()
    char *evdns_err_to_string(int err)
    int evdns_resolve_ipv4(char_constp name, int flags,
                           evdns_callback_type callback, void *arg)
    int evdns_resolve_ipv6(char_constp name, int flags,
                           evdns_callback_type callback, void *arg)
    int evdns_resolve_reverse(inaddr_constp ip, int flags,
                              evdns_callback_type callback, void *arg)
    int evdns_resolve_reverse_ipv6(in6addr_constp ip, int flags,
                                   evdns_callback_type callback, void *arg)
    void evdns_shutdown(int fail_requests)

    int c_DNS_ERR_NONE "DNS_ERR_NONE"
    int c_DNS_ERR_FORMAT "DNS_ERR_FORMAT"
    int c_DNS_ERR_SERVERFAILED "DNS_ERR_SERVERFAILED"
    int c_DNS_ERR_NOTEXIST "DNS_ERR_NOTEXIST"
    int c_DNS_ERR_NOTIMPL "DNS_ERR_NOTIMPL"
    int c_DNS_ERR_REFUSED "DNS_ERR_REFUSED"
    int c_DNS_ERR_TRUNCATED "DNS_ERR_TRUNCATED"
    int c_DNS_ERR_UNKNOWN "DNS_ERR_UNKNOWN"
    int c_DNS_ERR_TIMEOUT "DNS_ERR_TIMEOUT"
    int c_DNS_ERR_SHUTDOWN "DNS_ERR_SHUTDOWN"
    int c_DNS_IPv4_A "DNS_IPv4_A"
    int c_DNS_PTR "DNS_PTR"
    int c_DNS_IPv6_AAAA "DNS_IPv6_AAAA"
    int c_DNS_QUERY_NO_SEARCH "DNS_QUERY_NO_SEARCH"

cdef extern from "netdb.h":
    # NETDB_INTERNAL == -1 (see errno)
    # NETDB_SUCCESS == 0
    int c_HERROR_HOST_NOT_FOUND "HOST_NOT_FOUND"  # 1
    int c_HERROR_TRY_AGAIN "TRY_AGAIN"  # 2
    int c_HERROR_NO_RECOVERY "NO_RECOVERY"  # 3
    int c_HERROR_NO_DATA "NO_DATA"  # 4
    int c_HERROR_NO_ADDRESS "NO_ADDRESS"  # == "NO_DATA"

HERROR_HOST_NOT_FOUND = c_HERROR_HOST_NOT_FOUND
HERROR_TRY_AGAIN = c_HERROR_TRY_AGAIN
HERROR_NO_RECOVERY = c_HERROR_NO_RECOVERY
HERROR_NO_DATA = c_HERROR_NO_DATA
HERROR_NO_ADDRESS = c_HERROR_NO_ADDRESS

# Result codes
DNS_ERR_NONE = c_DNS_ERR_NONE
DNS_ERR_FORMAT = c_DNS_ERR_FORMAT
DNS_ERR_SERVERFAILED = c_DNS_ERR_SERVERFAILED
DNS_ERR_NOTEXIST = c_DNS_ERR_NOTEXIST
DNS_ERR_NOTIMPL = c_DNS_ERR_NOTIMPL
DNS_ERR_REFUSED = c_DNS_ERR_REFUSED
DNS_ERR_TRUNCATED = c_DNS_ERR_TRUNCATED
DNS_ERR_UNKNOWN = c_DNS_ERR_UNKNOWN
DNS_ERR_TIMEOUT = c_DNS_ERR_TIMEOUT
DNS_ERR_SHUTDOWN = c_DNS_ERR_SHUTDOWN

# Types
DNS_IPv4_A = c_DNS_IPv4_A
DNS_PTR = c_DNS_PTR
DNS_IPv6_AAAA = c_DNS_IPv6_AAAA

# Flags
DNS_QUERY_NO_SEARCH = c_DNS_QUERY_NO_SEARCH

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
    """Result of a DNS lookup call.

    Attributes;
      t: DNS record type constant, e.g. DNS_IPv4_A
      ttl: time-to-live: number of seconds the result can be cached until
      values: Nonempty list of ASCII strings containing result values. The
        first value should be used by default. Repeating the query might
        return the same values in different order.
    """
    cdef char _t
    cdef int _ttl
    cdef list _values

    property t:
        def __get__(self):
            return self._t

    property ttl:
        def __get__(self):
            return self._ttl

    property values:
        def __get__(self):
            return self._values

    def __cinit__(dnsresult self, char t, int ttl, list values):
        self._t = t
        self._ttl = ttl
        self._values = values

    def __repr__(dnsresult self):
        return '<dnsresult t=%d, ttl=%d values=%r at 0x%x>' % (
            self._t, self._ttl, self._values, <unsigned>self)

cdef object format_ipv6_word(unsigned hi, unsigned lo):
    lo += hi << 8
    if lo:
        # TODO(pts): Faster.
        return PyString_FromFormat(<char_constp>'%x', lo)
    else:
        return ''

class DnsLookupError(IOError):
    pass

class DnsResultParseError(Exception):
    pass

cdef void _dns_callback(int resultcode, char t, int count, int ttl,
                        void *addrs, void *arg) with gil:
    cdef object exc
    cdef int i
    cdef unsigned char *p
    cdef list xlist

    if resultcode:  # not c_DNS_ERR_NONE:
        # Make it negative to prevent confusion with errno objects,
        # just like socket.gaierror (gethostbyname).
        exc = DnsLookupError(-resultcode, evdns_err_to_string(resultcode))
        (<tasklet>arg).tempval = bomb(
            type(exc), exc, None)
        PyTasklet_Insert(<tasklet>arg)
        return
    if t == c_DNS_IPv4_A and count > 0:
        xlist = []
        p = <unsigned char*>addrs
        for i from 0 <= i < count:
            # TODO(pts): Replace all % by PyString_FromFormat.
            xlist.append(PyString_FromFormat(
                <char_constp>'%d.%d.%d.%d', p[0], p[1], p[2], p[3]))
            p += 4
        x = xlist
    elif t == c_DNS_IPv6_AAAA and count > 0:
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
    elif t == c_DNS_PTR and count == 1:  # only 1 PTR possible, for reverse
        x = [PyString_FromString((<char_constp*>addrs)[0])]
    else:
        x = None
    if x is None:
        (<tasklet>arg).tempval = bomb(
            DnsResultParseError, 'unknown type', None)
    else:
        (<tasklet>arg).tempval = dnsresult(t, ttl, x)
    PyTasklet_Insert(<tasklet>arg)

cdef char is_valid_hex_digit(char p):
    if p >= c'0' and p <= c'9':
        return 1
    elif p >= c'a' and p <= c'f':
        return 1
    elif p >= c'A' and p <= c'F':
        return 1
    else:
        return 0

cdef char is_valid_ipv6(char *p):
    # TODO(pts): Parse properly, according to
    # http://en.wikipedia.org/wiki/IPv6_address
    # ::, ::1, ff02::2,
    cdef int i
    if not is_valid_hex_digit(p[0]):
        return 0  # as far as socket.gethostbyaddr is concerned
    for i from 1 <= i < 8:
        while is_valid_hex_digit(p[0]):
            p += 1
        if p[0] != c':':
            return 0
        p += 1
    while is_valid_hex_digit(p[0]):
        p += 1
    return p[0] == c'\0'

cdef char is_valid_ipv4(char *p):
    cdef int i
    for i from 1 <= i < 4:
        if p[0] < c'0' or p[0] > c'9':
            return 0
        p += 1
        while p[0] >= c'0' and p[0] <= c'9':
            p += 1
        if p[0] != c'.':
            return 0
        p += 1
    if p[0] < c'0' or p[0] > c'9':
        return 0
    p += 1
    while p[0] >= c'0' and p[0] <= c'9':
        p += 1
    return p[0] == c'\0'

cdef dnsresult dns_call(_evdns_call_t call, char_constp name, int flags):
    cdef tasklet wakeup_tasklet
    cdef object tempval
    cdef int result
    cdef dnsresult dnsresult_obj
    if not dns_initialized:
        evdns_init()
        dns_initialized = 1
    wakeup_tasklet = PyStackless_GetCurrent()
    wakeup_tasklet.tempval = None
    result = call(name, flags, _dns_callback, <void*>wakeup_tasklet)
    if result:
        raise DnsLookupError(-err, evdns_err_to_string(err))
    if wakeup_tasklet.tempval is None:
        tempval = PyStackless_Schedule(None, 1)  # remove=1
    else:  # Not a single wait was needed. 
        # TODO(pts): Test this.
        tempval = wakeup_tasklet.tempval
        wakeup_tasklet.tempval = None
        if isinstance(tempval, bomb):
            raise tempval.type, tempval.value, tempval.traceback
    dnsresult_obj = tempval
    if call == &evdns_resolve_ipv4:
        if dnsresult_obj.t != c_DNS_IPv4_A:
             raise DnsResultParseError('bad type for ipv4')
    elif call == &evdns_resolve_ipv6:
        if dnsresult_obj.t != c_DNS_IPv6_AAAA:
             raise DnsResultParseError('bad type for ipv6')
    elif (call == <_evdns_call_t>evdns_resolve_reverse or
          call == <_evdns_call_t>evdns_resolve_reverse_ipv6):
        if dnsresult_obj.t != c_DNS_PTR:
             raise DnsResultParseError('bad type for reverse')
    return dnsresult_obj

def dns_resolve_ipv4(char *name, int flags=0):
    """Lookup an A record (IPV4) for a given name.

    Args:
      name     -- DNS hostname
      flags    -- either 0 (default) or DNS_QUERY_NO_SEARCH
    Returns:
      A dnsresult() object.
    """
    return dns_call(evdns_resolve_ipv4, <char_constp>name, flags)

def dns_resolve_ipv6(char *name, int flags=0):
    """Lookup an AAAA record (IPV6) for a given name.

    Args:
      name     -- DNS hostname
      flags    -- either 0 (default) or DNS_QUERY_NO_SEARCH
    Returns:
      A dnsresult() object.
    """
    return dns_call(evdns_resolve_ipv6, <char_constp>name, flags)

def dns_resolve_reverse(object ip, int flags=0):
    """Lookup a PTR record for a given IPv4 address.

    Arguments:

    ip       -- IPv4 or IPv6 address in ASCII
    flags    -- either 0 (default) or DNS_QUERY_NO_SEARCH
    """
    cdef list items
    cdef object tmp
    cdef char* p
    cdef int i
    cdef int j
    if not isinstance(ip, str):
        raise TypeError('ip must be a string')
    if '.' in ip:  # TODO(pts): Faster, for strings.
       items = ip.split('.')
       if len(items) != 4:
           raise ValueError('bad ipv4 address')
       tmp = PyString_FromStringAndSize(NULL, 4)
       p = tmp
       for i from 0 <= i < 4:
           # This also ValueError. TODO(pts): Proper parsing.
           p[i] = PyInt_FromString(items[i], NULL, 10)
       return dns_call(<_evdns_call_t>evdns_resolve_reverse,
                       <char_constp>p, flags)
    elif ':' in ip:  # TODO(pts): Faster, for strings.
       items = ip.split(':')
       if len(items) != 8:
           raise ValueError('bad ipv6 address')
       tmp = PyString_FromStringAndSize(NULL, 16)
       p = tmp
       for i from 0 <= i < 8:
           # This also ValueError. TODO(pts): Proper parsing.
           j = PyInt_FromString(items[i], NULL, 16)
           p[i * 2] = j >> 8
           p[i * 2 + 1] = j & 255
       return dns_call(<_evdns_call_t>evdns_resolve_reverse_ipv6,
                       <char_constp>p, flags)
    else:
        raise ValueError('unknown ip address syntax')

# --- socket.gethostbyname etc. emulations

# Maps IP addresses to list of host names from /etc/hosts.
names_by_ip = {}

# Maps IP addresses and host names to list of host names from /etc/hosts.
names_by_nameip = {}

# TODO(pts): Move this to pure Python to save memory and disk space.
def read_etc_hosts(filename='/etc/hosts', f=None):
    """Load IPv4 addresses and hostnames from /etc/hosts.

    Data already loaded to names_by_ip and names_by_nameip is not overridden.

    Raises:
      IOError:
    """
    if f is None:
        f = open(filename)
    try:
        for line in f:
            items = line.strip().split()
            if len(items) > 1 and not items[0].startswith('#'):
                ip = items[0]
                if is_valid_ipv4(ip):  # TODO(pts): Support IPv6 addresses.
                    # TODO(pts): Normalize IP address in items[0].
                    names_by_ip.setdefault(ip, items)
                    names_by_nameip.setdefault(ip, items)
                    for name in items:
                        names_by_nameip.setdefault(name, items)
    finally:
        f.close()

cdef object raise_gaierror(object exc_info, char is_name):
    cdef int result
    exc_type, exc_value, exc_tb = exc_info
    # -9 == socket.EAI_ADDRFAMILY
    # -5 == socket.EAI_NODATA
    # -2 == socket.EAI_NONAME  'Name or service not known'
    result = exc_value[0]
    result = -result
    # TODO(pts): Substitute more.
    # Substitute with Linux-specific values.
    if result == c_DNS_ERR_NOTEXIST:
        if is_name:
            exc_value = socket.gaierror(
                socket.EAI_NONAME, 'Name or service not known')
        else:
            exc_value = socket.gaierror(
                socket.EAI_NODATA, 'No address associated with hostname')
    else:
        exc_value = socket.gaierror(-result - 900, exc_value[1])
    raise type(exc_value), exc_value, exc_tb

cdef object raise_herror(object exc_info):
    cdef int result
    exc_type, exc_value, exc_tb = exc_info
    # 1 == c_HERROR_HOST_NOT_FOUND
    result = exc_value[0]  # <int>exc_value[0] is different.
    result = -result
    # TODO(pts): Substitute more.
    # Substitute with Linux-specific values.
    if result == c_DNS_ERR_NOTEXIST:
        exc_value = socket.herror(
            HERROR_HOST_NOT_FOUND, 'Unknown host')
    else:
        exc_value = socket.herror(-result - 900, exc_value[1])
    raise type(exc_value), exc_value, exc_tb

def gethostbyname(char *name):
    """Non-blocking drop-in replacement for socket.gethostbyname.

    This function returns data from /etc/hosts as read at module load time.

    Returns:
      An IPv4 address as an ASCII string (e.g. '192.168.1.2').
    Raises:
      socket.gaierror: The error names and codes may be different.
    """
    # TODO(pts): Do proper binary string parsing (everywhere).
    if is_valid_ipv4(name):
        return name
    if is_valid_ipv6(name):
        raise socket.gaierror(
            socket.EAI_ADDRFAMILY, 'Address family for hostname not supported')
    if name in names_by_nameip:
        return names_by_nameip[name][0]
    try:
        return dns_resolve_ipv4(name).values[0]
    except DnsLookupError:
        raise_gaierror(sys.exc_info(), 0)

cdef object c_gethostbyname(object address, int family):
    """Helper function for the connect() methods in nbevent.pyx.

    Raises:
      socket.gaierror: The error names and codes may be different.
    """
    cdef char *name
    if family == AF_INET:
        name = address[0]
        if is_valid_ipv4(name):
            return address
        if not is_valid_ipv6(name):
            try:
                return (dns_resolve_ipv4(name).values[0], address[1])
            except DnsLookupError:
                raise_gaierror(sys.exc_info(), 0)
    elif family == AF_INET6:
        name = address[0]
        if is_valid_ipv6(name):
            return address
        if not is_valid_ipv4(name):
            try:
                return (dns_resolve_ipv6(name).values[0], address[1])
            except DnsLookupError:
                raise_gaierror(sys.exc_info(), 0)
    else:
        return address  # for AF_UNIX etc.
    raise socket.gaierror(socket.EAI_ADDRFAMILY,
                          'Address family for hostname not supported')

def gethostbyaddr(char *name):
    """Non-blocking drop-in replacement for socket.gethostbyaddr.

    This function returns data from /etc/hosts as read at module load time.

    Raises:
      socket.herror: The error names and codes may be different.
      socket.gaierror: The error names and codes may be different.
    """
    if is_valid_ipv4(name) or is_valid_ipv6(name):
        ip = name
    elif name in names_by_nameip:
        ip = names_by_nameip[name][0]
    else:
        try:
            ip = dns_resolve_ipv4(name).values[0]
        except DnsLookupError:
            raise_gaierror(sys.exc_info(), 0)
    if ip in names_by_ip:
        items = names_by_ip[ip]
        return (items[1], items[2:], [ip])
    try:
        return (dns_resolve_reverse(ip).values[0], [], [ip])
    except DnsLookupError:
        raise_herror(sys.exc_info())

def getfqdn(name=''):
    """Non-blocking drop-in replacement for socket.getfqdn.

    This function returns data from /etc/hosts as read at module load time.
    """
    cdef char* cname
    cname = NULL
    if not name:
      name = socket.gethostname()
    cname = name
    if is_valid_ipv4(cname) or is_valid_ipv6(cname):
        ip = cname
    elif cname in names_by_nameip:
        ip = names_by_nameip[cname][0]
    else:
        try:
            ip = dns_resolve_ipv4(cname).values[0]
        except DnsLookupError:
            return cname
    if ip in names_by_ip:
        return names_by_ip[ip][1]
    try:
        return dns_resolve_reverse(ip).values[0]
    except DnsLookupError:
        return cname

def gethostbyname_ex(char *name):
    """Non-blocking drop-in replacement for socket.gethostbyname_ex.

    This function returns data from /etc/hosts as read at module load time.

    Avoid using this function if possible.
    Please note that this function is less faithful to its socket.*
    counterpart than the other functions in this module. This is because the
    underlying DNS lookup mechanism (evdns) can't return the CNAME records
    in evdns_resolve_ipv4(). The CNAME emulation here is inaccurate (see the
    unit tests) and slower (needs 2 DNS requests).
    """
    if is_valid_ipv4(name):
        return (name, [], [name])
    if is_valid_ipv6(name):
        raise socket.gaierror(
            socket.EAI_ADDRFAMILY, 'Address family for hostname not supported')
    if name in names_by_nameip:
        items = names_by_nameip[name]
        return (items[1], items[2:], [items[0]])
    try:
        ips = dns_resolve_ipv4(name).values
    except DnsLookupError:
        raise_gaierror(sys.exc_info(), 0)

    if ips[0] in names_by_ip:
        canonical = names_by_ip[ips[0]][1]
    else:
        try:
            canonical = dns_resolve_reverse(ips[0]).values[0]
        except DnsLookupError:
            raise_gaierror(sys.exc_info(), 0)
    if canonical == name:
        return (name, [], ips)
    else:
        return (canonical, [name], ips)

# TODO(pts): Implement socket.getaddrinfo()
# >>> socket.getaddrinfo('www.ipv6.org', 0, socket.AF_INET6)
# [(10, 1, 6, '', ('2001:6b0:1:ea:202:a5ff:fecd:13a6', 0, 0, 0)), (10, 2, 17, '', ('2001:6b0:1:ea:202:a5ff:fecd:13a6', 0, 0, 0)), (10, 3, 0, '', ('2001:6b0:1:ea:202:a5ff:fecd:13a6', 0, 0, 0))]
# TODO(pts): Implement socket.getnameinfo()
