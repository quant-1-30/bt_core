from libc.stdint cimport int32_t
from libcpp.vector cimport vector
from libcpp.string cimport string as cpp_string
from libcpp.unordered_map cimport unordered_map
from libcpp.algorithm cimport sort as c_sort

from bt_core.sizer cimport Sizer


cdef struct TraderPlan:
    cpp_string sid
    double weight
    int32_t size
    int32_t priority
    int32_t execType
    cpp_string filler


cdef struct Pair:
    cpp_string sid
    int32_t days_held
    int32_t out_of_topk
    int32_t size
    int32_t total_size


cdef struct BuyCandidate:
    cpp_string sid
    double weight
    int32_t already_held
    int32_t order_idx


cdef struct PlanCtx:
    int32_t current_day
    int32_t excess_count
    bint force_matured_only
    TraderPlan proto


cdef class Pnc:
    cdef Sizer sizer

    cdef int32_t interval
    cdef double dd
    cdef double stop_loss
    cdef int32_t max_positions
    cdef bint exit_on_risk

    cdef vector[int32_t] v_trading_days
    cdef int32_t _last_trade_day
    cdef bint _halted

    cdef unordered_map[cpp_string, TraderPlan] pending_sells

    cpdef void _start(self, list days_list)

    cdef int32_t _get_days_held(self, int32_t created_day, int32_t current_day) noexcept nogil
    
    cdef void _clean_pending_sells(self, list positions)
    
    cdef bint _is_pending_full(self, cpp_string sid) noexcept
    
    cdef void _push_full_exit(
        self,
        cpp_string sid,
        int32_t avail_size,
        TraderPlan proto,
        vector[TraderPlan]& out_sells,
    )
    
    cdef void _enforce_max_positions(
        self,
        list positions,
        dict topk_info,
        PlanCtx ctx,
        vector[TraderPlan]& out_sells,
        unordered_map[cpp_string, int32_t]& scheduled_sells,
    )
    cdef void _process_matured_and_pending_sells(
        self,
        object snapshot,
        dict topk_info,
        PlanCtx ctx,
        vector[TraderPlan]& out_sells,
        unordered_map[cpp_string, int32_t]& scheduled_sells,
    )

    cpdef vector[TraderPlan] on_risk(
        self, object snapshot, dict stats, int32_t current_day,
        int32_t execType=?, bytes filler=?
    )

    cpdef unordered_map[cpp_string, vector[TraderPlan]] generate_plan(
        self, int32_t current_day, dict topk_info,
        object snapshot, int32_t execType=?, bytes filler=?
    )

    cpdef void on_execute(self, dict sell_trades)
