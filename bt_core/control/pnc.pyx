# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from libc.stdint cimport int32_t, int64_t

from bt_core.sizers import _sizers
from bt_core.utils.dateintern import ts2intdt


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

    def __lt__(self, object other): # .sort() 
        return self.core.priority < (<TraderPlan>other).core.priority


cdef class Pnc:
    """
        a. sell first 
        b. buy after 
    """

    def __init__(self, str sizer_name, **kwargs):
        self.interval = kwargs.pop("days_held", 5)
        self.stake = kwargs.pop("stake", 0.9)
        self.dd = kwargs.pop("dd", 0.25)
        self.sizer = _sizers[sizer_name](**kwargs)

        self.pending_sells = {}

    # ==========================================================
    # risk control on tick
    # ==========================================================
    cpdef list check_risk(self, dict current_prices, object snapshot, dict stats):
        cdef double pnl
        cdef TraderPlan tmp
        cdef list positions = snapshot.positions, sells_by_risk=None
        
        # ==========================================
        # 1. Macro Control --- Drawdown
        # ==========================================

        if stats["drawdown"].maxdd >= self.dd:
            print("reach maxdd and execute sell all")
            sells_by_risk = [TraderPlan(pos.sid, 1.0, False, pos.available, priority=1) for pos in positions if pos.size > 0]
            return sells_by_risk
        
        # ==========================================
        # 2. Asset Risk Control
        # ==========================================

        for pos in positions:
            sid = pos.sid
            
            if pos.size == 0 or sid in self.pending_sells:
                continue

            # PnL
            current_price = current_prices.get(sid, pos.cost_basis) 
            pnl = current_price / pos.cost_basis 

            if pnl <= self.stake: 
                tmp = TraderPlan(sid, 1.0, False, pos.available, priority=0) 
                sells_by_risk.append(tmp) 
                self.pending_sells[sid] = tmp
                
        return sells_by_risk
    
    # ==========================================================
    # generate execution plan
    # ==========================================================

    cpdef dict generate_plan(self, dict topk_info, dict current_prices, object snapshot, dict stats): 
        # topk_info sort by score
        cdef bytes sid
        cdef int32_t days_held, current_day, slots, buy_count=0
        cdef double pnl, wgt_ratio
        cdef TraderPlan tmp
        
        cdef object pos
        cdef list positions = snapshot.positions , sells=[], buys=[]
        cdef object account = snapshot.account  
        
        
        current_day = ts2intdt(snapshot.account.datetime) 
        
        s_wgt = self.sizer.getsizing(topk_info, snapshot, False)

        for pos in positions:
            sid = pos.sid

            if pos.size == 0 or sid in self.pending_sells:
                continue
            # ------------------------------------------
            # 1. HoldingDays and Conflict
            # ------------------------------------------
            days_held = current_day - ts2intdt(pos.created_dt)
            
            if days_held < self.interval - 1:
                continue
                
            if sid in topk_info:
                continue
        
            wgt_ratio = s_wgt.get(sid, 1.0)
            tmp = TraderPlan(sid, wgt_ratio, False, pos.available, priority=1)
            sells.append(tmp)
            self.pending_sells[sid] = tmp

        sells.sort()

        # ==========================================
        # 2. Slot Control ---> Available Slots = TopK - (Positions - Sells)
        # ==========================================
        slots = len(topk_info) - (len(positions) - len(self.pending_sells))
        
        if slots <= 0:
            return {"sell": sells, "buy": []}

        # ==========================================
        # 3. Cash Control
        # ==========================================
         
        if account.cash <= 10000: # cash safety
            return {"sell": sells, "buy": []}
        
        # ==========================================
        # 4. Buy Control
        # ==========================================

        b_wgt = self.sizer.getsizing(topk_info, snapshot, True)

        for sid in topk_info: 
            if sid in self.pending_sells:
                continue

            wgt_ratio = b_wgt.get(sid, 0.0)
            if wgt_ratio > 0:
                tmp = TraderPlan(sid, wgt_ratio, True, 0, priority=1)
                buys.append(tmp)
            
            buy_count +=1
            if buy_count >= slots:
                break

        buys.sort()
        return {"sell": sells, "buy": buys}

    cpdef void on_updt(self, dict mtrades): # TradeBody
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

# how to extend to multistrategy and MultiPnc
