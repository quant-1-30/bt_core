from libcpp.string cimport string as cpp_string
from libcpp.unordered_map cimport unordered_map
from backtest.execution.core.finance.asset cimport AssetInfo


cdef class AssetCache:
    cdef unordered_map[int, AssetInfo] _c_cache
    cdef object _sharded_lock

    cdef void _add_to_cache(self, bytes sid, object data)
