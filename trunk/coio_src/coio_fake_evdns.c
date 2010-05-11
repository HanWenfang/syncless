/* --- Faking a nonfunctional evdns emulation, which returns DNS_ERR_NOTEXIST */

#define DNS_ERR_NONE 0
#define DNS_ERR_NOTEXIST 3
#define DNS_QUERY_NO_SEARCH 1
#define DNS_IPv4_A 1
#define DNS_PTR 2
#define DNS_IPv6_AAAA 3
typedef void (*evdns_callback_type)(int result, char type, int count, int ttl,
                                    void *addresses, void *arg);
struct in_addr;
struct in6_addr;

int evdns_init(void) {
  return 0;
}

void evdns_shutdown(int fail_requests) {
}

const char *evdns_err_to_string(int err) {
  if (err == DNS_ERR_NONE)
    return "no error";
  if (err == DNS_ERR_NOTEXIST)
    return "name does not exist";
  return "[Unknown error code]";
}

/* TODO(pts): Make these functions return a proper error code */
int evdns_resolve_ipv4(char const *name, int flags,
                       evdns_callback_type callback, void *arg) {
  return DNS_ERR_NOTEXIST;
}
int evdns_resolve_ipv6(char const *name, int flags,
                       evdns_callback_type callback, void *arg) {
  return DNS_ERR_NOTEXIST;
}
int evdns_resolve_reverse(struct in_addr const *ip, int flags,
                          evdns_callback_type callback, void *arg) {
  return DNS_ERR_NOTEXIST;
}
int evdns_resolve_reverse_ipv6(struct in6_addr const *ip, int flags,
                               evdns_callback_type callback,
                               void *arg) {
  return DNS_ERR_NOTEXIST;
}
