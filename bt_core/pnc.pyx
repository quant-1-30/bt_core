# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False

from libc.stdint cimport int32_t
from libcpp.unordered_map cimport unordered_map
from libcpp.algorithm cimport lower_bound, sort as c_sort
from cython.operator cimport dereference as deref

from bt_core.sizer cimport Sizer
from bt_core.utils.dateintern import ts2intdt


cdef inline bint compare_trader_plans_desc(TraderPlan a, TraderPlan b) noexcept:
    """Descending priority comparator: higher priority score executes first."""
    return a.priority > b.priority


cdef inline bint compare_pairs_desc(Pair a, Pair b) noexcept:
    """Descending liquidation urgency: out_of_topk (1 > 0) first, then longest days_held (larger > smaller)."""
    if a.out_of_topk != b.out_of_topk:
        return a.out_of_topk > b.out_of_topk
    return a.days_held > b.days_held


cdef inline bint compare_buy_candidates_desc(BuyCandidate a, BuyCandidate b) noexcept:
    """Descending buy conviction: larger target weight first, preserving higher upstream rank on ties."""
    if a.weight != b.weight:
        return a.weight > b.weight
    return a.order_idx > b.order_idx


cdef class Pnc:
    """Portfolio Navigation & Risk Controller (sell-first, buy-after)."""

    def __init__(self, Sizer sizer_obj, *args, **kwargs):
        self.sizer = sizer_obj
        self.interval = kwargs.pop("days_held", 5)
        self.dd = kwargs.pop("dd", 0.25)
        self.stop_loss = kwargs.pop("stop_loss", -0.1)
        self.max_positions = kwargs.pop("max_positions", 5)
        self.exit_on_risk = bool(kwargs.pop("exit_on_risk", False))
        self._last_trade_day = 0
        self._halted = False

    cpdef void _start(self, list trading_days):
        cdef int32_t d
        self.v_trading_days.clear()
        for d in trading_days:
            self.v_trading_days.push_back(d)
        self.pending_sells.clear()
        self._last_trade_day = 0
        self._halted = False

    cdef int32_t _get_days_held(self, int32_t created_day, int32_t current_day) noexcept nogil:
        if self.v_trading_days.empty():
            return 0
        cdef vector[int32_t].iterator it_created = lower_bound(
            self.v_trading_days.begin(), self.v_trading_days.end(), created_day
        )
        cdef vector[int32_t].iterator it_current = lower_bound(
            self.v_trading_days.begin(), self.v_trading_days.end(), current_day
        )
        return <int32_t>(it_current - it_created)

    cdef void _clean_pending_sells(self, list positions):
        cdef unordered_map[cpp_string, int32_t] current_available
        cdef vector[cpp_string] keys_to_remove
        cdef cpp_string pos_sid
        cdef size_t i
        for pos in positions:
            current_available[<cpp_string>pos.sid] = pos.available
        for it_sell in self.pending_sells:
            pos_sid = it_sell.first
            if current_available.find(pos_sid) == current_available.end() or current_available[pos_sid] == 0:
                keys_to_remove.push_back(pos_sid)
        for i in range(keys_to_remove.size()):
            self.pending_sells.erase(keys_to_remove[i])

    cdef void _push_full_exit(
        self,
        cpp_string sid,
        int32_t avail_size,
        TraderPlan proto,
        vector[TraderPlan]& out_sells,
    ):
        """Register a full exit, replacing any earlier (partial) intent for the same sid.

        Risk exits must override a matured/dropped partial sell instead of
        being silently skipped; dropping the old plan entry also guarantees
        that the same shares are never sold twice in one plan.
        """
        cdef TraderPlan tmp = proto
        cdef size_t i
        cdef bint replaced = False
        tmp.sid = sid
        tmp.weight = 1.0
        tmp.size = avail_size
        tmp.priority = 100
        
        for i in range(out_sells.size()):
            if out_sells[i].sid == sid:
                out_sells[i] = tmp
                replaced = True
                break
        if not replaced:
            out_sells.push_back(tmp)
        self.pending_sells[sid] = tmp

    cdef bint _is_pending_full(self, cpp_string sid) noexcept:
        cdef unordered_map[cpp_string, TraderPlan].iterator pit = self.pending_sells.find(sid)
        if pit == self.pending_sells.end():
            return False
        # 全清 = weight 恰好 1.0 (pnc 内字面赋值); 部分意图 weight < 1, sizer 比例恒 < 1
        return deref(pit).second.weight >= 1.0

    cdef void _enforce_max_positions(
        self,
        list positions,
        dict topk_info,
        PlanCtx ctx,
        vector[TraderPlan]& out_sells,
        unordered_map[cpp_string, int32_t]& scheduled_sells,
    ):
        """Force-liquidate excess positions in descending urgency (out_of_topk=1, larger days_held)."""
        cdef vector[Pair] pos_with_days
        cdef Pair p_pair
        cdef cpp_string pos_sid
        cdef size_t i
        cdef int32_t needed = ctx.excess_count
        cdef int32_t sold_count = 0

        # Positions already scheduled for a full exit still occupy a slot, so
        # they resolve part of the excess without needing another order.
        # Only *partial* pending intents stay eligible and may be escalated.
        for pos in positions:
            if pos.available > 0 and self._is_pending_full(<cpp_string>pos.sid):
                needed -= 1
        if needed <= 0:
            return

        for pos in positions:
            pos_sid = <cpp_string>pos.sid
            if pos.available <= 0 or self._is_pending_full(pos_sid):
                continue
            p_pair.sid = pos_sid
            p_pair.days_held = self._get_days_held(<int32_t>ts2intdt(pos.created_dt), ctx.current_day)
            p_pair.out_of_topk = 0 if (topk_info and (<bytes>pos.sid in topk_info)) else 1
            p_pair.size = pos.available
            p_pair.total_size = pos.size
            pos_with_days.push_back(p_pair)

        c_sort(pos_with_days.begin(), pos_with_days.end(), compare_pairs_desc)

        for i in range(pos_with_days.size()):
            if sold_count >= needed:
                break
            p_pair = pos_with_days[i]
            self._push_full_exit(p_pair.sid, p_pair.size, ctx.proto, out_sells)
            # Value 1 = fully liquidated (frees a slot today); value 0 = only
            # the available T+1-unlocked shares are sold (slot still held).
            scheduled_sells[p_pair.sid] = 1 if p_pair.size >= p_pair.total_size else 0
            sold_count += 1

    cdef void _process_matured_and_pending_sells(
        self,
        object snapshot,
        dict topk_info,
        PlanCtx ctx,
        vector[TraderPlan]& out_sells,
        unordered_map[cpp_string, int32_t]& scheduled_sells,
    ):
        """Re-issue stuck pending sells (priority=100) and schedule matured/dropped exits (priority=50)."""
        cdef TraderPlan tmp
        cdef cpp_string c_sid
        cdef list positions = snapshot.positions
        cdef unordered_map[cpp_string, double] s_wgt
        cdef unordered_map[cpp_string, TraderPlan].iterator pit
        cdef unordered_map[cpp_string, double].iterator it_wgt
        cdef int32_t remain_intent, avail_now, days_held
        cdef double wgt_ratio
        cdef bint should_sell, has_topk = bool(topk_info)
        cdef dict sizer_topk

        if self.sizer is not None and positions:
            sizer_topk = topk_info if has_topk else {<bytes>pos.sid: 0.0 for pos in positions}
            s_wgt = self.sizer.getsizing(sizer_topk, snapshot, False)

        for pos in positions:
            if pos.available <= 0:
                continue
            c_sid = <cpp_string>pos.sid

            # Exit already emitted by _enforce_max_positions in this same call;
            # never push a second plan entry for the same shares.
            if scheduled_sells.find(c_sid) != scheduled_sells.end():
                continue

            pit = self.pending_sells.find(c_sid)
            if pit != self.pending_sells.end():
                remain_intent = deref(pit).second.size
                avail_now = pos.available
                if remain_intent <= 0:
                    self.pending_sells.erase(pit)
                    continue
                tmp = ctx.proto
                tmp.sid = c_sid
                if deref(pit).second.weight >= 1.0:
                    # Preserve the full-liquidation intent: T+1 locks or a
                    # partial fill must not downgrade it to a partial exit.
                    tmp.weight = 1.0
                    tmp.size = avail_now
                else:
                    tmp.weight = min(1.0, <double>remain_intent / <double>avail_now)
                    tmp.size = remain_intent if remain_intent < avail_now else avail_now
                tmp.priority = 100
                out_sells.push_back(tmp)
                self.pending_sells[c_sid] = tmp
                continue

            should_sell = False
            days_held = self._get_days_held(<int32_t>ts2intdt(pos.created_dt), ctx.current_day)
            if days_held >= self.interval:
                should_sell = True
            if (not ctx.force_matured_only) and has_topk and (<bytes>pos.sid not in topk_info):
                should_sell = True
            if not should_sell:
                continue

            it_wgt = s_wgt.find(c_sid)
            wgt_ratio = deref(it_wgt).second if it_wgt != s_wgt.end() else 1.0
            if wgt_ratio <= 0.0:
                continue

            remain_intent = <int32_t>(pos.available * wgt_ratio)
            if remain_intent <= 0:
                continue

            tmp = ctx.proto
            tmp.sid = c_sid
            tmp.weight = wgt_ratio
            tmp.size = remain_intent
            tmp.priority = 50
            out_sells.push_back(tmp)
            self.pending_sells[c_sid] = tmp
            if wgt_ratio >= 1.0 and remain_intent >= pos.size:
                scheduled_sells[c_sid] = 1

    cpdef vector[TraderPlan] on_risk(
        self, object snapshot, dict stats, int32_t current_day,
        int32_t execType=0, bytes filler=b"default"
    ):
        cdef PlanCtx ctx
        cdef list positions = snapshot.positions
        cdef vector[TraderPlan] sells_by_risk
        cdef unordered_map[cpp_string, int32_t] scheduled_sells
        cdef int32_t active_count = 0

        ctx.current_day = current_day
        ctx.excess_count = 0
        ctx.force_matured_only = True
        ctx.proto.execType = execType
        ctx.proto.filler = filler
        self._clean_pending_sells(positions)

        if self.exit_on_risk:
            self._process_matured_and_pending_sells(
                snapshot, None, ctx, sells_by_risk, scheduled_sells
            )

        # Slot occupancy is driven by shares held, not by whether an exit was
        # already scheduled: a partial sell leaves the position in place.
        for pos in positions:
            if pos.size > 0:
                active_count += 1
        if active_count > self.max_positions:
            ctx.excess_count = active_count - self.max_positions
            self._enforce_max_positions(positions, None, ctx, sells_by_risk, scheduled_sells)

        # Stop loss must override an already scheduled partial/matured exit;
        # _push_full_exit replaces that entry instead of double-selling.
        for pos in positions:
            if pos.available > 0 and pos.pnl_ratio <= self.stop_loss:
                self._push_full_exit(
                    <cpp_string>pos.sid, pos.available, ctx.proto, sells_by_risk
                )

        # Drawdown is a hard latch: stay flat and keep re-issuing exits until
        # every position is gone. It overrides every earlier sell intent.
        if "drawdown" in stats and stats["drawdown"].maxdd >= self.dd:
            self._halted = True
            for pos in positions:
                if pos.available > 0:
                    self._push_full_exit(
                        <cpp_string>pos.sid, pos.available, ctx.proto, sells_by_risk
                    )

        c_sort(sells_by_risk.begin(), sells_by_risk.end(), compare_trader_plans_desc)
        return sells_by_risk

    cpdef unordered_map[cpp_string, vector[TraderPlan]] generate_plan(
        self, int32_t current_day, dict topk_info,
        object snapshot, int32_t execType=0, bytes filler=b"default"
    ):
        cdef bytes py_sid
        cdef cpp_string c_sid
        cdef int32_t slots, total_topk, buy_prio, occupied_slots = 0
        cdef double wgt_ratio
        cdef TraderPlan tmp
        cdef PlanCtx ctx

        cdef vector[TraderPlan] sells
        cdef vector[TraderPlan] buys
        cdef unordered_map[cpp_string, vector[TraderPlan]] plan

        cdef unordered_map[cpp_string, double] b_wgt
        cdef unordered_map[cpp_string, double].iterator it_wgt
        cdef unordered_map[cpp_string, int32_t] scheduled_sells
        cdef unordered_map[cpp_string, int32_t].iterator it_flag

        cdef list positions = snapshot.positions
        cdef object pos, account = snapshot.account
        cdef int32_t active_positions_count = 0
        cdef bint already_held, has_full_exit = False
        cdef bint has_topk = bool(topk_info)
        cdef vector[BuyCandidate] buy_cands
        cdef BuyCandidate bc
        cdef size_t k

        if self._last_trade_day == current_day or (not has_topk and not positions):
            plan[<cpp_string>b"sell"] = sells
            plan[<cpp_string>b"buy"] = buys
            return plan

        ctx.current_day = current_day
        ctx.excess_count = 0
        ctx.force_matured_only = False
        ctx.proto.execType = execType
        ctx.proto.filler = filler
        self._clean_pending_sells(positions)

        # A drawdown halt only disables *new entries*: existing exits (including
        # limit-down stuck sells) must keep being re-issued until flat.
        if self._halted:
            for pos in positions:
                if pos.available > 0:
                    self._push_full_exit(
                        <cpp_string>pos.sid, pos.available, ctx.proto, sells
                    )
            c_sort(sells.begin(), sells.end(), compare_trader_plans_desc)
            self._last_trade_day = current_day
            plan[<cpp_string>b"sell"] = sells
            plan[<cpp_string>b"buy"] = buys
            return plan

        # Held shares occupy a slot even when a partial exit is pending.
        for pos in positions:
            if pos.size > 0:
                active_positions_count += 1

        if active_positions_count > self.max_positions:
            ctx.excess_count = active_positions_count - self.max_positions
            self._enforce_max_positions(
                positions, topk_info, ctx, sells, scheduled_sells
            )

        self._process_matured_and_pending_sells(
            snapshot, topk_info, ctx, sells, scheduled_sells
        )
        c_sort(sells.begin(), sells.end(), compare_trader_plans_desc)

        if not has_topk:
            self._last_trade_day = current_day
            plan[<cpp_string>b"sell"] = sells
            plan[<cpp_string>b"buy"] = buys
            return plan

        for pos in positions:
            c_sid = <cpp_string>pos.sid
            if pos.size <= 0:
                continue
            it_flag = scheduled_sells.find(c_sid)
            # Value 1 marks a full exit that frees the slot today; value 0 is a
            # partial (T+1-limited) exit that leaves the position held.
            if it_flag == scheduled_sells.end() or deref(it_flag).second == 0:
                occupied_slots += 1

        total_topk = <int32_t>len(topk_info)
        slots = self.max_positions - occupied_slots
        if slots > total_topk:
            slots = total_topk

        for pos in positions:
            c_sid = <cpp_string>pos.sid
            it_flag = scheduled_sells.find(c_sid)
            if it_flag != scheduled_sells.end() and deref(it_flag).second == 1:
                has_full_exit = True
                break

        if account.cash <= 10000 and not has_full_exit:
            self._last_trade_day = current_day
            plan[<cpp_string>b"sell"] = sells
            plan[<cpp_string>b"buy"] = buys
            return plan

        if self.sizer is not None:
            b_wgt = self.sizer.getsizing(topk_info, snapshot, True)

        buy_prio = total_topk
        for py_sid in topk_info:
            c_sid = <cpp_string>py_sid
            buy_prio -= 1
            if self.pending_sells.find(c_sid) != self.pending_sells.end():
                continue
            it_wgt = b_wgt.find(c_sid)
            wgt_ratio = deref(it_wgt).second if it_wgt != b_wgt.end() else 0.0
            if wgt_ratio <= 0.0:
                continue

            already_held = False
            for pos in positions:
                if <cpp_string>pos.sid == c_sid and pos.size > 0:
                    already_held = True
                    break

            bc.sid = c_sid
            bc.weight = wgt_ratio
            bc.already_held = 1 if already_held else 0
            bc.order_idx = buy_prio
            buy_cands.push_back(bc)

        c_sort(buy_cands.begin(), buy_cands.end(), compare_buy_candidates_desc)

        buy_prio = <int32_t>buy_cands.size()
        for k in range(buy_cands.size()):
            bc = buy_cands[k]
            if bc.already_held == 0:
                if slots <= 0:
                    continue
                slots -= 1
            tmp = ctx.proto
            tmp.sid = bc.sid
            tmp.weight = bc.weight
            tmp.size = 0
            tmp.priority = buy_prio
            buy_prio -= 1
            buys.push_back(tmp)

        c_sort(buys.begin(), buys.end(), compare_trader_plans_desc)
        self._last_trade_day = current_day

        plan[<cpp_string>b"sell"] = sells
        plan[<cpp_string>b"buy"] = buys
        return plan

    cpdef void on_execute(self, dict mtrades):
        cdef bytes py_sid
        cdef cpp_string c_sid
        cdef int32_t remain, executed_size
        cdef object trades
        cdef unordered_map[cpp_string, TraderPlan].iterator it_sell

        for py_sid, trades in mtrades.items():
            c_sid = <cpp_string>py_sid
            executed_size = (
                <int32_t>trades
                if isinstance(trades, int)
                else sum([trade.executed_size for trade in trades])
            )
            it_sell = self.pending_sells.find(c_sid)
            if it_sell != self.pending_sells.end():
                remain = deref(it_sell).second.size - executed_size
                if remain <= 0:
                    self.pending_sells.erase(it_sell)
                else:
                    self.pending_sells[c_sid].size = remain
