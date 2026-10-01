# cython.boundscheck(False) # 关闭边界检查
# cython.wraparound(False)  # 关闭负指数索引检查
# distutils: language = c++
# cython: language_level=3

import uuid
import json

from libc.math cimport floor
from bt_core.execution.core.finance.function cimport calc_ratio, cRatio
from bt_core.execution.core.finance.trade cimport OrderExbitData

from bt_protocol._protocol import PositionBody, Resp


cdef class Position:
    '''
    Keeps and updates the size and price of a position. The object has no
    relationship to any asset. It only keeps size and price.

    Member Attributes:
      - size (int): current size of the position
      - price (float): current price of the position

    The Position instances can be tested using len(position) to see if size
    is not null
    '''
    def __init__(self, 
                bytes experiment_id, 
                bytes sid, 
                Asset asset,
                int64_t datetime=0, 
                int64_t created_dt=0,
                int32_t size=0, 
                int32_t available=0, 
                double cost_basis=0.0,
                double pnl=0.0,
                double realized_pnl=0.0
               ):
        self.core.experiment_id = experiment_id
        self.core.sid = sid
        self.core.datetime = datetime
        self.core.created_dt = created_dt

        self.core.size = size
        self.core.available = available # due to T + 1
        self.core.cost_basis = cost_basis
        self.core.pnl = pnl  # unrealized pnl
        self.core.realized_pnl = realized_pnl
        self.core.pnl_ratio = 0.0

        self.asset = asset
        self.cached_uuid = uuid.UUID(bytes=experiment_id)
    
    cdef int32_t get_available(self):
        return self.core.available

    cdef void _update_pnl_ratio(self):
        cdef double total_cost = self.core.size * self.core.cost_basis
        if total_cost > 0:
            self.core.pnl_ratio = (self.core.pnl + self.core.realized_pnl) / total_cost
        else:
            self.core.pnl_ratio = 0.0
 
    cdef void update(self, OrderExecutionBit orderbit):
        '''
        Updates the current position and returns the updated size, price and
        units used to open/close a position
        '''
        cdef OrderExbitData core = orderbit.core
        cdef int32_t sign = 1 if core.isbuy else -1
        cdef int32_t size = sign * core.executed_size 
        cdef double price = core.executed_price

        cdef double cost_basis = self.core.cost_basis
        cdef int32_t orig_size = self.core.size
        cdef int32_t available = self.core.available + size

        if available < 0:
            raise ValueError(
                f"T+1 violation: available={self.core.available}, "
                f"attempted size={size} on sid={self.core.sid}"
            )

        self.core.size += size

        if not self.core.size: # Update closed existing position
            opened, closed = 0, size
            self.core.available = 0
        elif not orig_size: # Update opened a position from 0 and available stay same
            opened, closed = size, 0
            self.core.cost_basis = price
        elif orig_size > 0:
            # existing "long" position
            if size > 0:
                # increased position  available no change and on_dt_over update
                opened, closed = size, 0
                self.core.cost_basis = (cost_basis * orig_size + size * price) / (orig_size + size)
            else : # decrease position under available
                opened, closed = 0, size
                self.core.available = available
        else:
            raise ValueError(
                f"Short position not supported for A-shares: orig_size={orig_size}, "
                f"size={size} on sid={self.core.sid}"
            )

        self._execute(orderbit)

    cdef _execute(self, OrderExecutionBit orderbit):
        cdef OrderExbitData trade_core = orderbit.core
        cdef double trade_price = trade_core.executed_price
        cdef int64_t trade_dts = trade_core.executed_dt
        cdef int32_t trade_size = trade_core.executed_size
        cdef double cost_basis = self.core.cost_basis

        # keep unix ts: multiple fills within a day must stay strictly ordered;
        # ymd normalization happens once at settlement (on_dt_over / Account.sync)
        self.core.datetime = trade_dts
        
        # sells pnl
        if not trade_core.isbuy:
            self.core.realized_pnl += trade_size * (trade_price - cost_basis)

        # unrealized pnl
        self.core.pnl = self.core.size * (trade_price - cost_basis)

        self._update_pnl_ratio()
 
    cdef double process_events(self, vector[EventItem]& events, double cash): # should update T datetime
        # right share  <= cash  
        cdef double total_bonus = 0.0
        cdef double delta
        cdef int32_t i
        cdef int32_t n = events.size()

        for i in range(n):
            if events[i].event_type == 1:
                # abandon rights entirely when subscription cost exceeds
                # running cash; cost formula must mirror _process_event
                if <double>(<int32_t>floor(self.core.size * events[i].rgt.ratio / 10.0)) * events[i].rgt.price > cash:
                    continue
            delta = self._process_event(events[i])
            total_bonus += delta
            cash += delta

        return total_bonus

    cdef double _process_event(self, EventItem item):
        cdef cRatio cr
        cdef double event_bonus = 0.0
        cdef double sizer_ratio , bonus_ratio
        cdef double cost_basis = self.core.cost_basis
        cdef int32_t origin_size = self.core.size, available = self.core.available
        cdef int32_t rights_size

        if item.event_type == 0:  # adjustment
            cr = calc_ratio(item.adj)
            sizer_ratio = cr.sizer_ratio
            bonus_ratio = cr.bonus_ratio

            # drop less > 1.0 and available <= size 
            self.core.size = <int32_t>floor(origin_size * sizer_ratio)
            self.core.available = <int32_t>floor(available * sizer_ratio)
            self.core.cost_basis = cost_basis / sizer_ratio
            event_bonus = origin_size * bonus_ratio
            return event_bonus
        else:
            # rights shares are integral: subscribe exactly the granted shares
            # and pay cash only for the shares actually received
            rights_size = <int32_t>floor(origin_size * item.rgt.ratio / 10.0)
            event_bonus = -(rights_size * item.rgt.price)

            self.core.size = origin_size + rights_size
            # right shares T + 1 available
            self.core.available = available
            if self.core.size > 0:
                self.core.cost_basis = (cost_basis * origin_size + rights_size * item.rgt.price) / self.core.size
            return event_bonus

    cdef double _handle_merger(self, bytes target_sid, double close, double ratio):
        # avoid dirty key
        self.core.sid = target_sid

        cdef int32_t size = self.core.size
        if size <= 0:
            return 0.0

        cdef double old_cost = self.core.cost_basis
        cdef double total_new = size * <double>ratio
        cdef int32_t merger_size = <int32_t>total_new
        cdef double frac = total_new - merger_size   # 0 <= frac < 1
        cdef double px = close if close > 0.0 else old_cost
        cdef double theo_price = px / <double>ratio
        cdef double comp_cash = 0.0

        if merger_size <= 0:
            comp_cash = size * px
            self.core.realized_pnl += comp_cash - size * old_cost
            self._zero_out()
            return comp_cash

        if frac > 0.0:
            comp_cash = frac * theo_price
            self.core.realized_pnl += comp_cash - (old_cost / <double>ratio) * frac

        self.core.size = merger_size
        self.core.available = merger_size
        self.core.cost_basis = old_cost / <double>ratio
        return comp_cash

    cdef void merge_from(self, Position other):
        '''
        Merges another position's size, cost basis, and PnL into this position.
        Used during corporate actions such as stock mergers
        '''
        cdef int32_t other_size = other.core.size
        cdef int32_t orig_size = self.core.size
        cdef int32_t total_size = orig_size + other_size

        if total_size > 0:
            # Weighted average cost basis
            self.core.cost_basis = (
                (self.core.cost_basis * orig_size) + (other.core.cost_basis * other_size)
            ) / <double>total_size
        else:
            self.core.cost_basis = 0.0

        self.core.size = total_size
        self.core.available += other.core.available
        self.core.pnl += other.core.pnl
        self.core.realized_pnl += other.core.realized_pnl

        self._update_pnl_ratio()

    cdef double _dt_over(self, int32_t end_dt, double close):
        cdef int32_t size = self.core.size
        cdef double cost_basis = self.core.cost_basis
        cdef AssetCore asset_core = self.asset.core
        cdef double comp_cash = 0.0

        if asset_core.delist > 0 and asset_core.delist <= end_dt:
            if not asset_core.merger.empty():
                if self.core.sid != asset_core.merger:
                    comp_cash = self._handle_merger(asset_core.merger, close, asset_core.merge_ratio)
                elif close > 0:
                    self.core.pnl = size * (close - cost_basis)
            else:
                self.core.realized_pnl -= size * cost_basis
                self._zero_out()

        elif close > 0:
            self.core.pnl = size * (close - cost_basis)
        else:
            pass # means suspend stay

        self._update_pnl_ratio()
        self.core.datetime = end_dt
        return comp_cash

    cdef double on_dt_over(self, int32_t end_dt, double close):
        # T+1 unlock: end_dt (the settled day) is guaranteed >= the trade day
        # of every fill processed so far — fills are synchronous with bars and
        # end_dt is the day of the last bar before the rollover gap. Hence the
        # unconditional unlock is exact. If fills ever become asynchronous
        # (event-driven clock, async execution), this must become day-aware.
        self.core.available = self.core.size
        return self._dt_over(end_dt, close)

    cdef void _zero_out(self):
        self.core.size = 0
        self.core.available = 0
        self.core.pnl = 0.0

        self.core.cost_basis = 0.0  

    cdef Position clone(self):
        cdef Position obj = Position.__new__(Position)
        cdef PositionCoreData core 

        core.experiment_id = self.core.experiment_id
        core.sid = self.core.sid
        core.datetime = self.core.datetime
        core.created_dt = self.core.created_dt
        core.size = self.core.size
        core.available = self.core.available
        core.pnl = self.core.pnl
        core.realized_pnl = self.core.realized_pnl
        core.pnl_ratio = self.core.pnl_ratio
        core.cost_basis = self.core.cost_basis

        obj.core = core
        obj.asset = self.asset
        return obj
       
    cdef object serialize(self):
        cdef object body, resp
        cdef double total_pnl = self.core.realized_pnl + self.core.pnl

        body = PositionBody(experiment_id=self.core.experiment_id, sid=self.core.sid, size=self.core.size,
                            available=self.core.available, cost_basis=self.core.cost_basis, datetime=self.core.datetime,
                            pnl=total_pnl, pnl_ratio=self.core.pnl_ratio, created_dt=self.core.created_dt,
                            realized_pnl=self.core.realized_pnl)
        resp = Resp(body=body)
        return resp

    cdef PositionCoreData get_snapshot(self):
        return self.core

    def __len__(self):
        return self.core.size

    def __bool__(self):
        return bool(self.core.size != 0)

    def __reduce__(self):
        return (Position, (self.core.experiment_id, self.core.sid, self.asset, 
                        self.core.datetime, self.core.created_dt, self.core.size, 
                        self.core.available, self.core.cost_basis, self.core.pnl, self.core.realized_pnl))
    
    def __repr__(self):
        template = "Position(experiment_id={experiment_id} ," \
                   "sid={sid} ," \
                   "asset={asset} , "\
                   "datetime={datetime} ," \
                   "created_dt={created_dt} ," \
                   "size={size} ," \
                   "available={available} ," \
                   "cost_basis={cost_basis} ," \
                   "pnl={pnl} ," \
                   "realized_pnl={realized_pnl})"
        formatted_asset_info = json.dumps(self.asset.core, ensure_ascii=False)

        return template.format(
            experiment_id=self.core.experiment_id,
            sid=self.core.sid,
            asset=formatted_asset_info,
            datetime=self.core.datetime,
            created_dt=self.core.created_dt,
            size=self.core.size,
            available=self.core.available,
            cost_basis=self.core.cost_basis,
            pnl=self.core.pnl,
            realized_pnl=self.core.realized_pnl
        )