from libc.stdint cimport int64_t
from backtest.execution.core.finance.account cimport Account


cdef class AsyncCashManager:
    cdef object acct

    cdef Account get_account(self, bytes experiment_id)
    
    cdef Account set_cash(self, object event)

    cdef void add_cash(self, bytes experiment_id, double cash)
    
    cdef void sync(self, bytes experiment_id, dict pobjs)
    
    cdef void sync_no_sids(self, bytes experiment_id, int64_t sync_tick)

    cdef remove_client(self, bytes experiment_id)
    