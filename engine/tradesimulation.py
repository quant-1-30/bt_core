# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import pandas as pd
from datetime import datetime
from contextlib import ExitStack
from _calendar.trading_calendar import calendar
from util.api_support import AlgoAPI
from trade import (
    SESSION_START,
    SESSION_END,
    BEFORE_TRADING_START
)
from trade import (
    DEFAULT_DELAY_BASE,
    DEFAULT_CAPITAL_BASE,
    DEFAULT_PER_CAPITAL_BASE
)
from error.errors import (
    ZeroCapitalError
)


class AlgorithmSimulator(object):
    """
        initialization a.初始化相关模块以及参数
        before trading:
                        a. 针对ledger预处理
                        b. pipelineEngine计算的结果
                        c. 9:25(撮合价格) --- cancelPolicy过滤pipelineEngine的标的集合 -- 筛选可行域
                        d. 实施具体的执行计划(非bid_mechnasim --- 创建订单）
        session start:
                        a.基于可行域 -- 调用blotter模块(orders --- transactions)
                        b.transactions --- update ledger
        session end:
                        a.调用metrics_tracker --- generate metrics_perf
        simulation_end:
                        a. plot and generate pdf
    """
    EMISSION_TO_PERF_KEY_MAP = {
        'minute': 'minute_perf',
        'daily': 'daily_perf'
    }

    def __init__(self,
                 algorithm,
                 clock):

        self.algorithm = algorithm
        self.clock = clock

    def transform(self):
        """
        Main generator work loop.
        """
        ledger = self.algorithm.ledger
        broker = self.algorithm.broker
        metrics_tracker = self.algorithm.tracker

        def once_a_day(dts):
            dts = dts.strftime('%Y-%m-%d') if isinstance(dts, pd.Timestamp) else dts
            broker.implement_broke(ledger, dts)

        def on_exit():
            # Remove references to algo, data portal, et al to break cycles
            # and ensure deterministic cleanup of these objects
            self.algorithm = None

        with ExitStack() as stack:
            """
            由于已注册的回调是按注册的相反顺序调用的, 因此最终行为就好像with 已将多个嵌套语句与已注册的一组回调一起使用。
            这甚至扩展到异常处理-如果内部回调抑制或替换异常，则外部回调将基于该更新状态传递自变量。
            enter_context  输入一个新的上下文管理器, 并将其__exit__()方法添加到回调堆栈中。返回值是上下文管理器自己的__enter__()方法的结果。
            callback(回调, * args, ** kwds)接受任意的回调函数和参数, 并将其添加到回调堆栈中。
            """
            stack.callback(on_exit)
            stack.enter_context(AlgoAPI(self.algorithm))
            # print('ledger', ledger)

            metrics_tracker.handle_start_of_simulation(ledger)

            # 生成器yield方法 ，返回yield 生成的数据，next 执行yield 之后的方法
            for session_label, action in self.clock:
                print('session_label and action :', session_label, action)
                if action == BEFORE_TRADING_START:
                    metrics_tracker.handle_market_open(session_label, ledger)
                elif action == SESSION_START:
                    once_a_day(session_label)
                elif action == SESSION_END:
                    # Get a perf message for the given datetime.
                    yield metrics_tracker.handle_market_close(session_label, ledger)

            yield metrics_tracker.handle_simulation_end(ledger)


class MinuteSimulationClock(object):

    # before trading  , session start , session end 三个阶段
    def __init__(self, sim_params):

        self.sessions_nanos = sim_params.sessions
        self.trading_o_and_c = calendar.open_and_close_for_session(self.sessions_nanos)

    def __iter__(self):
        """
            If the clock property is not set, then create one based on frequency.
            session_minutes --- list , length --- 4
        """
        for session_label, session_minutes in zip(self.sessions_nanos, self.trading_o_and_c):
            yield session_label, BEFORE_TRADING_START
            for bts in session_minutes:
                if bts == pd.Timestamp(session_label) + pd.Timedelta(hours=9, minutes=30):
                    yield bts, SESSION_START
                else:
                    yield bts, SESSION_END


class SimulationParameters(object):
    """

    data_frequency : {'daily', 'minute'}, optional
        The duration of the bars.
    delay : int
        Transfer puts to calls (duals)
    """
    def __init__(self,
                 start_session,
                 end_session,
                 delay,
                 capital_base,
                 loan_base,
                 per_capital,
                 data_frequency,
                 benchmark):

        assert capital_base > 0, ZeroCapitalError()
        self._delay = delay
        self._loan = loan_base
        # per_capital used to calculate and split capital or position
        self._per_capital = per_capital
        self._capital_base = capital_base

        self._data_frequency = data_frequency
        self._benchmark = benchmark
        self._sessions = calendar.session_in_range(start_session, end_session)

    @property
    def capital_base(self):
        return self._capital_base

    @property
    def per_capital(self):
        return self._per_capital

    @property
    def loan(self):
        return self._loan

    @property
    def data_frequency(self):
        return self._data_frequency

    @property
    def benchmark(self):
        return self._benchmark

    @property
    def delay(self):
        return self._delay

    @property
    def start_session(self):
        return pd.Timestamp(min(self._sessions))

    @property
    def end_session(self):
        return pd.Timestamp(max(self._sessions))

    @property
    # @remember_last #remember_last = weak_lru_cache(1)
    def sessions(self):
        return self._sessions

    def create_new(self, start_session, end_session, data_frequency=None):
        if data_frequency is None:
            data_frequency = self.data_frequency

        return SimulationParameters(
            start_session,
            end_session,
            capital_base=self.capital_base,
            data_frequency=data_frequency)

    def __repr__(self):
        return """
{class_name}(
    start_session={start_session},
    end_session={end_session},
    capital_base={capital_base},
    data_frequency={data_frequency}
)\
""".format(class_name=self.__class__.__name__,
           start_session=self.start_session,
           end_session=self.end_session,
           capital_base=self.capital_base,
           data_frequency=self.data_frequency)


def create_simulation_parameters(start,
                                 end,
                                 loan_base,
                                 delay,
                                 per_capital,
                                 capital_base,
                                 data_frequency,
                                 benchmark):

    if start is None:
        start = "{0}-01-01".format(2004)
    elif isinstance(start, str):
        start = start
    else:
        start = start.strftime('%Y-%m-%d')

    if end is None:
        end = datetime.now().strftime('%Y-%m-%d')
    elif isinstance(end, str):
        end = end
    else:
        end = end.strftime('%Y-%m-%d')

    loan_base = loan_base or 0.0
    delay = delay or DEFAULT_DELAY_BASE
    per_capital = per_capital or DEFAULT_PER_CAPITAL_BASE
    capital_base = capital_base or DEFAULT_CAPITAL_BASE
    benchmark = benchmark or '000001'

    sim_params = SimulationParameters(
        start_session=start,
        end_session=end,
        delay=delay,
        capital_base=capital_base,
        loan_base=loan_base,
        per_capital=per_capital,
        data_frequency=data_frequency,
        benchmark=benchmark
    )
    return sim_params

