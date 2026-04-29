# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from libc.stdint cimport int32_t, int64_t

from .sizers import _sizers
from .utils.dateintern import ts2intdt


cdef class TraderPlan:
    
    cdef public str sid
    cdef public double weight
    cdef public bint isbuy
    cdef public int32_t priority

    def __init__(self, str sid, double weight, bint isbuy, int priority=1):
        self.sid = sid
        self.weight = weight
        self.isbuy = isbuy
        # small --> high
        self.priority = priority 

    def __repr__(self):
        action = "BUY" if self.isbuy else "SELL"
        return f"[{action} (Pri:{self.priority})] {self.sid} -> {self.weight*100:.1f}%"

    # __lt__ --> .sort() 
    def __lt__(self, object other):
        return self.priority < (<TraderPlan>other).priority


cdef class Pnc:
    """
    sell first and buy after / risk control priority
    """

    def __init__(self, int32_t lock_days, str sizer_name):
        self.interval = lock_days
        self.sizer = _sizers[sizer_name]
        self.sells = []
        self.buys =[]
        self.pending_sells = {}

    cpdef void generate_plan(self, dict topk_info, object snapshot, double risk_tl):
        cdef str sid
        cdef int days_held, current_day
        cdef double pnl, wgt_ratio
        cdef object pos
        cdef list positions = snapshot.positions # msgspec List 

        self.sells.clear()
        self.buys.clear()
        
        current_day = ts2intdt(snapshot.account.datetime)

        # ==========================================
        # selling first
        # ==========================================
        s_wgt = self.sizer.getsizing(topk_info, snapshot, False)

        for pos in positions: # 遍历 msgspec list
            
            if isinstance(pos.sid, bytes):
                sid = pos.sid.decode('utf-8')
            else:
                sid = pos.sid
            
            pnl = topk_info[sid]["close"] / pos.cost_basis - 1.0
            days_held = current_day - ts2intdt(pos.datetime) 
            wgt_ratio = s_wgt.get(sid, 0.0)

            # risk_tl 
            if pnl <= risk_tl:
                continue
                
            # lock control
            if days_held < self.interval:
                continue
                
            # avoid conflict
            if sid in topk_info:
                continue
        
            self.sells.append(TraderPlan(sid, wgt_ratio, False, priority=1))
            self.pending_sells[sid] = pos.size

        self.sells.sort()

        # ==========================================
        # buy second
        # ==========================================
        b_wgt = self.sizer.getsizing(topk_info, snapshot, True)

        for sid in topk_info:
            wgt_ratio = b_wgt.get(sid, 0.0)
            self.buys.append(TraderPlan(sid, wgt_ratio, True, priority=1))

        self.buys.sort()

    cpdef void on_filled(self, object strades):
        cdef str sid
        cdef int32_t filled_vol
        cdef object trade

        for trade in strades:
            if isinstance(trade.sid, bytes):
                sid = trade.sid.decode('utf-8')
            else:
                sid = trade.sid
                
            filled_vol = trade.executed_size

            if sid in self.pending_sells:
                self.pending_sells[sid] -= filled_vol
                if self.pending_sells[sid] <= 0:
                    del self.pending_sells[sid]

    cpdef dict get_pending_sells(self):
        return self.pending_sells

    cpdef dict to_plan(self):
        return {"sell": self.sells, "buy": self.buys}


#cdef class MultiPnc:
#    # resolve differenct stratgey conflicts
#    pass
