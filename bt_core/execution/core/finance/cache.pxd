from libcpp.unordered_map cimport unordered_map
from bt_core.execution.core.finance.asset cimport Asset


cdef class AssetCache:
    # cdef unordered_map only support C/C++ `int`, `float`, `struct`
    cdef dict _c_cache 
    cdef object _sharded_lock

    cdef void _add_to_cache(self, object table)
    
    cdef Asset get_cache_info(self, bytes sid, object loop)
