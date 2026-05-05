# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from libc.stdint cimport int32_t, int64_t
from libcpp.string cimport string as cpp_string

from .sizers import _sizers
from .utils.dateintern import ts2intdt


cdef class TraderPlan:
    
    def __init__(self, bytes sid, double weight, bint isbuy, int priority=1):
        self.core.sid = sid
        self.core.weight = weight
        self.core.isbuy = isbuy
        # small --> high
        self.core.priority = priority 

    def __repr__(self):
        action = "BUY" if self.core.isbuy else "SELL"
        return f"[{action} (Pri:{self.core.priority})] {self.core.sid} -> {self.core.weight*100:.1f}%"

    # __lt__ --> .sort() 
    def __lt__(self, object other):
        return self.core.priority < (<TraderPlan>other).core.priority


cdef class Pnc:
    """
    sell first and buy after / risk control priority
    """

    def __init__(self, int32_t lock_days, str sizer_name, **kwargs):

        self.interval = lock_days
        self.p_tolerance = kwargs.pop("p_thres", -0.1)
        self.act_tolerance = kwargs.pop("act_thres",  -0.25)
        self.sizer = _sizers[sizer_name](**kwargs)

        self.sells = []
        self.buys =[]
        self.pending_sells = {}

    cpdef dict generate_plan(self, dict topk_info, dict current_prices, object snapshot, dict stats):
        cdef bytes sid
        cdef int days_held, current_day
        cdef double pnl, wgt_ratio
        cdef bint signal
        cdef object pos
        cdef list positions = snapshot.positions # msgspec List
        cdef object account = snapshot.account 

        self.sells.clear()
        self.buys.clear()
        
        print("account ", account)
        current_day = ts2intdt(snapshot.account.datetime)
        
        # ==========================================
        # risk control
        # ==========================================

        drawdown_obs = stats["drawdown"] # lowercase
        signal = drawdown_obs.lines.drawdown[0] > self.act_tolerance

        print("signal :", drawdown_obs.lines.drawdown[0], signal)

        # if signal:
        #     self.sells = [TraderPlan(pos.sid, 1.0, False, priority=1) for pos in positions]
        #     return {} 

        # ==========================================
        # selling first
        # ==========================================
        s_wgt = self.sizer.getsizing(topk_info, snapshot, False)

        for pos in positions: # msgspec list
            sid = pos.sid

            current_price = current_prices.get(sid, pos.cost_basis) # suspending / missiong 
            pnl = current_price / pos.cost_basis - 1.0

            # ------------------------------------------
            # Priority A: hard control
            # ------------------------------------------
            if pnl <= self.p_tolerance: 
                wgt_ratio = s_wgt.get(sid, 1.0) 
                self.sells.append(TraderPlan(sid, wgt_ratio, False, priority=0)) # priority=0 最高级
                self.pending_sells[sid] = pos.size
                continue # 风控卖出已计划，直接看下一个持仓
                
            # ------------------------------------------
            # Priority B: normal switch
            # ------------------------------------------
            days_held = current_day - ts2intdt(pos.datetime) 
            if days_held < self.interval:
                continue
                
            if sid in topk_info:
                continue
        
            wgt_ratio = s_wgt.get(sid, 0.0)
            self.sells.append(TraderPlan(sid, wgt_ratio, False, priority=1))
            self.pending_sells[sid] = pos.size

        self.sells.sort()
        
        # ==========================================
        # buy second
        # ==========================================
        b_wgt = self.sizer.getsizing(topk_info, snapshot, True)
        print("b_wgt: ", b_wgt)

        if account.cash <= 10000:
            self.buys = []

        for sid in topk_info:
            wgt_ratio = b_wgt.get(sid, 0.0)
            self.buys.append(TraderPlan(sid, wgt_ratio, True, priority=1))

        self.buys.sort()
        
        return {"sell": self.sells, "buy": self.buys}

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


#cdef class MultiPnc:
#    # resolve differenct stratgey conflicts
#    pass

    