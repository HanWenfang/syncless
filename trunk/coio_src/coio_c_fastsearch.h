/* String search routines
 * copied from the sources of Stackless Python 2.6.5 (Objects/stringlib/ *.h)
 * by pts@fazekas.hu at Thu May 13 20:06:55 CEST 2010
 */

#define COIO_STRINGLIB_CMP memcmp
#define COIO_STRINGLIB_LEN PyString_GET_SIZE
#define COIO_STRINGLIB_NEW PyString_FromStringAndSize
#define COIO_STRINGLIB_STR PyString_AS_STRING

/* fast search/count implementation, based on a mix between boyer-
   moore and horspool, with a few more bells and whistles on the top.
   for some more background, see: http://effbot.org/stringlib */

/* note: fastsearch may access s[n], which isn't a problem when using
   Python's ordinary string types, but may cause problems if you're
   using this code in other contexts.  also, the count mode returns -1
   if there cannot possible be a match in the target string, and 0 if
   it has actually checked for matches, but didn't find any.  callers
   beware! */

#define FAST_COUNT 0
#define FAST_SEARCH 1

static inline Py_ssize_t fastsearch(const char* s, Py_ssize_t n,
                                    const char* p, Py_ssize_t m,
                                    int mode) {
    long mask;
    Py_ssize_t skip, count = 0;
    Py_ssize_t i, j, mlast, w;

    w = n - m;

    if (w < 0)
        return -1;

    /* look for special cases */
    if (m <= 1) {
        if (m <= 0)
            return -1;
        /* use special case for 1-character strings */
        if (mode == FAST_COUNT) {
            for (i = 0; i < n; i++)
                if (s[i] == p[0])
                    count++;
            return count;
        } else {
            for (i = 0; i < n; i++)
                if (s[i] == p[0])
                    return i;
        }
        return -1;
    }

    mlast = m - 1;

    /* create compressed boyer-moore delta 1 table */
    skip = mlast - 1;
    /* process pattern[:-1] */
    for (mask = i = 0; i < mlast; i++) {
        mask |= (1 << (p[i] & 0x1F));
        if (p[i] == p[mlast])
            skip = mlast - i - 1;
    }
    /* process pattern[-1] outside the loop */
    mask |= (1 << (p[mlast] & 0x1F));

    for (i = 0; i <= w; i++) {
        /* note: using mlast in the skip path slows things down on x86 */
        if (s[i+m-1] == p[m-1]) {
            /* candidate match */
            for (j = 0; j < mlast; j++)
                if (s[i+j] != p[j])
                    break;
            if (j == mlast) {
                /* got a match! */
                if (mode != FAST_COUNT)
                    return i;
                count++;
                i = i + mlast;
                continue;
            }
            /* miss: check if next character is part of pattern */
            if (!(mask & (1 << (s[i+m] & 0x1F))))
                i = i + m;
            else
                i = i + skip;
        } else {
            /* skip: check if next character is part of pattern */
            if (!(mask & (1 << (s[i+m] & 0x1F))))
                i = i + m;
        }
    }

    if (mode != FAST_COUNT)
        return -1;
    return count;
}

static inline Py_ssize_t coio_stringlib_find(
    const char* str, Py_ssize_t str_len,
    const char* sub, Py_ssize_t sub_len,
    Py_ssize_t offset) {
    Py_ssize_t pos;

    if (str_len < 0)
        return -1;
    if (sub_len == 0)
        return offset;

    pos = fastsearch(str, str_len, sub, sub_len, FAST_SEARCH);

    if (pos >= 0)
        pos += offset;

    return pos;
}

static inline Py_ssize_t coio_stringlib_rfind(
    const char* str, Py_ssize_t str_len,
    const char* sub, Py_ssize_t sub_len,
    Py_ssize_t offset) {
    /* XXX - create reversefastsearch helper! */
    if (sub_len == 0) {
        if (str_len < 0)
            return -1;
	return str_len + offset;
    } else {
	Py_ssize_t j, pos = -1;
	for (j = str_len - sub_len; j >= 0; --j)
            if (COIO_STRINGLIB_CMP(str+j, sub, sub_len) == 0) {
                pos = j + offset;
                break;
            }
        return pos;
    }
}
