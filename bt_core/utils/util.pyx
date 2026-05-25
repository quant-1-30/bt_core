# distutils: language = c++
# cython: language_level=3


# C typedef / cython ctypedef
cdef extern from "<uuid/uuid.h>" nogil:
    ctypedef uint8_t uuid_t[16]
    void uuid_generate(uuid_t out)
    void uuid_unparse_lower(const uuid_t uu, char *out)

cdef inline uuid128 fast_uuid4_c() nogil:
    cdef uuid128 uu
    uuid_generate(uu.data)
    return uu

cpdef inline bytes fast_uuid4_bytes():
    cdef uuid_t uu
    uuid_generate(uu)
    return (<char*>uu)[:16]

cpdef inline str fast_uuid4_str(): 
    cdef uuid_t uu
    cdef char out[37] # 36byte + \0
    with nogil:
        uuid_generate(uu)
        uuid_unparse_lower(uu, out)
    return out[:36].decode('ascii')
