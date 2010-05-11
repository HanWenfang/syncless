/*
 * coio_minihdns.h: asynchronous DNS resolver copied from libevent1 1.4.13
 * by pts@fazekas.hu at Tue May 11 19:20:26 CEST 2010
 */

#ifndef COIO_MINIHDNS_H
#define COIO_MINIHDNS_H

/** Error codes 0-5 are as described in RFC 1035. */
#define DNS_ERR_NONE 0
/** The name server was unable to interpret the query */
#define DNS_ERR_FORMAT 1
/** The name server was unable to process this query due to a problem with the
 * name server */
#define DNS_ERR_SERVERFAILED 2
/** The domain name does not exist */
#define DNS_ERR_NOTEXIST 3
/** The name server does not support the requested kind of query */
#define DNS_ERR_NOTIMPL 4
/** The name server refuses to reform the specified operation for policy
 * reasons */
#define DNS_ERR_REFUSED 5
/** The reply was truncated or ill-formated */
#define DNS_ERR_TRUNCATED 65
/** An unknown error occurred */
#define DNS_ERR_UNKNOWN 66
/** Communication with the server timed out */
#define DNS_ERR_TIMEOUT 67
/** The request was canceled because the DNS subsystem was shut down. */
#define DNS_ERR_SHUTDOWN 68

#define DNS_IPv4_A 1
#define DNS_PTR 2
#define DNS_IPv6_AAAA 3

#define DNS_QUERY_NO_SEARCH 1

#define DNS_OPTION_SEARCH 1
#define DNS_OPTION_NAMESERVERS 2
#define DNS_OPTION_MISC 4
#define DNS_OPTIONS_ALL 7

#define DNS_NO_SEARCH 1

/**
 * The callback that contains the results from a lookup.
 * - type is either DNS_IPv4_A or DNS_PTR or DNS_IPv6_AAAA
 * - count contains the number of addresses of form type
 * - ttl is the number of seconds the resolution may be cached for.
 * - addresses needs to be cast according to type
 */
typedef void (*evdns_callback_type)(int result, char type, int count, int ttl, void *addresses, void *arg);
struct in_addr;
struct in6_addr;
typedef void (*evdns_debug_log_fn_type)(int is_warning, const char *msg);
void evdns_set_log_fn(evdns_debug_log_fn_type fn);
int evdns_resolv_conf_parse(int flags, const char *const filename);
int evdns_resolve_ipv4(const char *name, int flags, evdns_callback_type callback, void *ptr);
int evdns_resolve_ipv6(const char *name, int flags, evdns_callback_type callback, void *ptr);
int evdns_resolve_reverse(const struct in_addr *in, int flags, evdns_callback_type callback, void *ptr);
int evdns_resolve_reverse_ipv6(const struct in6_addr *in, int flags, evdns_callback_type callback, void *ptr);
int evdns_init(void);
const char *evdns_err_to_string(int err);
void evdns_shutdown(int fail_requests);

#endif
