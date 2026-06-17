from libcpp.string cimport string as cpp_string
from libcpp.unordered_map cimport unordered_map
from bt_core.execution.core.finance.asset cimport AssetCore


cdef class AssetCache:
    # cdef unordered_map[int, AssetCore] _c_cache # only support C/C++ `int`, `float`, `struct`
    cdef dict _c_cache 

    cdef object _sharded_lock

    cdef void _add_to_cache(self, object table)
