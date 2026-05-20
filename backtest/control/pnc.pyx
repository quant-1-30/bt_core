# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from libc.stdint cimport int32_t, int64_t
from libcpp.string cimport string as cpp_string

from backtest.sizers import _sizers
from backtest.utils.dateintern import ts2intdt


cdef class TraderPlan:
    
    def __init__(self, bytes sid, double weight, bint isbuy, int32_t size=0, int32_t priority=1):
        self.core.sid = sid
        self.core.weight = weight
        self.core.isbuy = isbuy
        # small --> high
        self.core.size = size
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

    def __init__(self, str sizer_name, **kwargs):
        self.interval = kwargs.pop("days_held", 5)
        self.stake = kwargs.pop("stake", 0.9)
        self.dd = kwargs.pop("dd", 0.25)
        self.sizer = _sizers[sizer_name](**kwargs)

        self.sells = []
        self.buys =[]
        self.pending_sells = {}

    cpdef dict generate_plan(self, dict topk_info, dict current_prices, object snapshot, dict stats): # topk_info sort by score
        cdef bytes sid
        cdef int32_t days_held, current_day, slots, buy_count=0
        cdef double pnl, wgt_ratio
        cdef bint signal
        cdef TraderPlan tmp
        
        cdef object pos
        cdef list positions = snapshot.positions # msgspec List
        cdef object account = snapshot.account  # msgspec
        
        self.sells.clear()
        self.buys.clear()
        
        current_day = ts2intdt(snapshot.account.datetime) # lastday account
        
        # ==========================================
        # 1. Macro Control --- Drawdown
        # ==========================================
        drawdown = stats["drawdown"].maxdd
        signal = drawdown >= self.dd
        
        if signal:
            print("reach maxdd and sell all")
            self.sells =[TraderPlan(pos.sid, 1.0, False, pos.available, priority=1) for pos in positions if pos.size > 0]
            return {"sell": self.sells, "buy":[]}

        # ==========================================
        # 2. Selling First
        # ==========================================
        s_wgt = self.sizer.getsizing(topk_info, snapshot, False)

        for pos in positions:
            if pos.size == 0:
                continue

            sid = pos.sid
            current_price = current_prices.get(sid, pos.cost_basis) # lastday closes
            pnl = current_price / pos.cost_basis 

            # ------------------------------------------
            # Priority A Hard Stop-Loss
            # ------------------------------------------
            if pnl <= self.stake: 
                wgt_ratio = s_wgt.get(sid, 1.0) 
                tmp = TraderPlan(sid, wgt_ratio, False, pos.available, priority=0) # 0 最高级
                self.sells.append(tmp) 
                self.pending_sells[sid] = tmp
                
                # avoid conflict with buy 
                topk_info.pop(sid, None)
                continue 
                
            # ------------------------------------------
            # Priority B Days and Conflict
            # ------------------------------------------
            # based on created_dt(no change) not datetime
            days_held = current_day - ts2intdt(pos.created_dt)
            
            if days_held < self.interval - 1:
                continue
                
            if sid in topk_info:
                continue
        
            wgt_ratio = s_wgt.get(sid, 1.0)
            tmp = TraderPlan(sid, wgt_ratio, False, pos.available, priority=1)
            self.sells.append(tmp)
            self.pending_sells[sid] = tmp

        self.sells.sort()

        # ==========================================
        # 3. Slot Calculation
        # ==========================================

        # **`Available Slots = TopK - (Positions - Sells)`**
        slots = len(topk_info) - (len(positions) - len(self.pending_sells))
        
        if slots <= 0:
            return {"sell": self.sells, "buy": []}

        # ==========================================
        # 4. Buy Second & Slots Control
        # ==========================================
         
        if account.cash <= 10000: # cash safety
            return {"sell": self.sells, "buy": []}

        b_wgt = self.sizer.getsizing(topk_info, snapshot, True)

        for sid in topk_info: # rebuy reasonable
            wgt_ratio = b_wgt.get(sid, 0.0)
            if wgt_ratio > 0:
                tmp = TraderPlan(sid, wgt_ratio, True, 0, priority=1)
                self.buys.append(tmp)
            
            buy_count +=1
            if buy_count >= slots:
                break

        self.buys.sort()

        return {"sell": self.sells, "buy": self.buys}

    cpdef void on_filled(self, dict mtrades): # TradeBody
        cdef bytes sid
        cdef int32_t remain
        cdef TraderPlan tp
        cdef object trade

        for sid, trades in mtrades.items():
            executed_size = sum([trade.executed_size for trade in trades])

            if sid in self.pending_sells:
                tp = self.pending_sells[sid]
                remain = tp.core.size - executed_size
                if remain <= 0:
                    del self.pending_sells[sid]

    cpdef dict get_pending_sells(self):
        return self.pending_sells


# how to extend to multistrategy and MultiPnc
