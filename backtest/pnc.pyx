# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=F

from libc.stdint cimport int32_t, int64_t


cdef class Pnc:
    """
        严格按照先卖后买 / 风控优先
    """
    
    def __init__(self, object sizer, int32_t lock_days):
        self.sizer = sizer
        self.lock_days = lock_days
        
        self.sells =[]
        self.buys =[]

    cpdef void generate_plan(self, 
                        dict topk_info,
                        dict current_positions, 
                        double rish_tl,
                        double ratio=1.0):   
        cdef str sid
        cdef int days_held
        cdef double pnl
        cdef dict pos_info, portfolio_wgt
        cdef list sid_keys = list(topk_info.keys())

        self.sells.clear()
        self.buys.clear()
        
        # ==========================================
        # selling first
        # ==========================================

        for sid, pos_info in current_positions.items():
            pnl = topk_info[sid]["close"] / pos_info["cost_basis"] - 1.0
            days_held = int2dt(pos_info["datetime"]) - topk_info[sid]["day"]
        
            # risk
            if pnl <= rish_tl:
                continue
                
            # lock control
            if days_held < lock_days:
                continue
                
            # evaluate at lock expiration
            if sid in topk_info:
                continue
        
            self.sells.append(TradePlan(sid, ratio, True, priority=1))
            self.pending_sells[sid] = int(pos_info["available"] * ratio)

        self.sells.sort(key=lambda x: x.priority)

        # ==========================================
        # buy second
        # ==========================================

        portfolio_wgt = self.sizer.getsizing(sid_keys)

        for sid in sid_keys:
            current_weight = portfolio_wgt[sid]
            self.buys.append(TradePlan(sid, current_weight, False, priority=1))

        self.buys.sort(key=lambda x: x.priority)

    cpdef void on_filled(self, object sell_trades):
        for trade in sell_trades:
            sid = trade.sid
            if sid in self.pending_sells:
                self.pending_sells[sid] -= filled_vol
                if self.pending_sells[sid] <= 0:
                    del self.pending_sells[sid]

    cpdef dict get_pending_sells(self):
        """
            used for sell on next opening with left selling
        """
        return self.pending_sells

    cpdef to_plan(self):
        return {"sell": self.sells, "buy": self.buys}
