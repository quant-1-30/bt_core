

cdef class OrderPlan:
    """每日交易计划：清晰指示要卖多少、要买谁"""
    cdef public str sid
    cdef public double weight
    cdef public bint is_sell
    cdef public int32_t entry_day_idx
    cdef public int priority  # 数字越小优先级越高 

    def __init__(self, str sid, double weight, bint is_sell, int priority=1):
        self.sid = sid
        self.weight = weight
        self.is_sell = is_sell
        self.priority = priority

    def __repr__(self):
        action = "SELL" if self.is_sell else "BUY"
        return f"[{action} (Pri:{self.priority})] {self.sid} -> {self.weight*100:.1f}%"


cdef class Pnc:
    cdef public list sells
    cdef public list buys
    cdef public dict pending_sells  


    cpdef void generate_plan(self, 
                        dict topk_info,
                        dict current_positions, 
                        double rish_tl,
                        double ratio=1.0)

    cpdef void on_filled(self, object sell_trades)

    cpdef dict get_pending_sells(self)

    cpdef to_plan(self)

    