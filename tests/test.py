
import sys
import warnings
import inspect
import numpy as np
from scipy.optimize import fsolve
# flip --- 反转参数
from toolz import flip
from functools import wraps
from sys import float_info
from textwrap import dedent
from collections import namedtuple
from collections import deque
from bisect import bisect_left, bisect_right
from operator import methodcaller
from collections import namedtuple
from textwrap import dedent

from .iface import PipelineHooks, PIPELINE_HOOKS_CONTEXT_MANAGERS

from interface import implements

from zipline.utils.compat import contextmanager, wraps


Call = namedtuple('Call', 'method_name args kwargs')


class ContextCall(namedtuple('ContextCall', 'state call')):

    @property
    def method_name(self):
        return self.call.method_name

    @property
    def args(self):
        return self.call.args

    @property
    def kwargs(self):
        return self.call.kwargs


def testing_hooks_method(method_name):
    """Factory function for making testing methods.
    """
    if method_name in PIPELINE_HOOKS_CONTEXT_MANAGERS:
        # Generate a method that enters the context of all sub-hooks.
        @wraps(getattr(PipelineHooks, method_name))
        @contextmanager
        def ctx(self, *args, **kwargs):
            call = Call(method_name, args, kwargs)
            self.trace.append(ContextCall('enter', call))
            yield
            self.trace.append(ContextCall('exit', call))
        return ctx

    else:
        # Generate a method that calls methods of all sub-hooks.
        @wraps(getattr(PipelineHooks, method_name))
        def method(self, *args, **kwargs):
            self.trace.append(Call(method_name, args, kwargs))
        return method


class TestingHooks(implements(PipelineHooks)):
    """A hooks implementation that keeps a trace of hook method calls.
    """
    def __init__(self):
        self.trace = []

    def clear(self):
        self.trace = []

    # Implement all interface methods by delegating to corresponding methods on
    # input hooks.
    locals().update({
        name: testing_hooks_method(name)
        # TODO: Expose this publicly on interface.
        for name in PipelineHooks._signatures
    })


class classproperty(object):
    """Class property
    """
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, instance, owner):
        return self.fget(owner)

class DummyMapping(object):
    """
    Dummy object used to provide a mapping interface for singular values.
    """
    def __init__(self, value):
        self._value = value

    def __getitem__(self, key):
        return self._value


class IDBox(object):
    """A wrapper that hashs to the id of the underlying object and compares
    equality on the id of the underlying.

    Parameters
    ----------
    ob : any
        The object to wrap.

    Attributes
    ----------
    ob : any
        The object being wrapped.

    Notes
    -----
    This is useful for storing non-hashable values in a set or dict.
    """
    def __init__(self, ob):
        self.ob = ob

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        if not isinstance(other, IDBox):
            return NotImplemented

        return id(self.ob) == id(other.ob)


def getargspec(f):
    full_argspec = inspect.getfullargspec(f)
    return inspect.ArgSpec(
        args=full_argspec.args,
        varargs=full_argspec.varargs,
        keywords=full_argspec.varkw,
        defaults=full_argspec.defaults,
    )

NO_DEFAULT = object()

args, varargs, varkw, defaults = argspec = getargspec(_parse_url)
print('varargs',varargs)
print('varkw',varkw)
if defaults is None:
    defaults = ()
no_defaults = (NO_DEFAULT,) * (len(args) - len(defaults))
print('args',args)
print('no_defaults',no_defaults)
args_defaults = list(zip(args, no_defaults + defaults))
if varargs:
    args_defaults.append((varargs, NO_DEFAULT))
if varkw:
    args_defaults.append((varkw, NO_DEFAULT))
print('args_defaults',args_defaults)
print('varargs',varargs)
print('varkw',varkw)

# argset = set(args) | {varargs, varkw} - {None}
argset = set(args) | {varargs, varkw}
#
print('argset',argset)



# adjustments = adjustments.reindex_axis(ADJUSTMENT_COLUMNS, axis=1)
# row_loc = dates.get_loc(apply_date, method='bfill')
# date_ix = np.searchsorted(dates, dividends.ex_date.values)
# date_ix = np.searchsorted(dates, dividends.ex_date.values)
# mask = date_ix > 0

# date_ix = date_ix[mask]
# sids_ix = sids_ix[mask]
# input_dates = dividends.ex_date.values[mask]

# # subtract one day to get the close on the day prior to the merger
# previous_close = close[date_ix - 1, sids_ix]
# input_sids = input_sids[mask]

# amount = dividends.amount.values[mask]
# ratio = 1.0 - amount / previous_close


def cartesian(arrays, out=None):
    """
        参数组合 不同于product
    """
    arrays = [np.asarray(x) for x in arrays]
    print('arrays',arrays)
    shape = (len(x) for x in arrays)
    print('shape',shape)
    dtype = arrays[0].dtype

    ix = np.indices(shape)
    print('ix',ix)
    ix = ix.reshape(len(arrays), -1).T
    print('ix_:',ix)

    if out is None:
        out = np.empty_like(ix, dtype=dtype)
        print('out',out.shape)

    for n, arr in enumerate(arrays):
        print('array',arrays[n])
        print(ix[:,n])
        out[:, n] = arrays[n][ix[:, n]]
        print(out[:,n])

    return out


def deprecated(msg=None, stacklevel=2):
    """
    Used to mark a function as deprecated.
    Parameters
    ----------
    msg : str
        The message to display in the deprecation warning.
    stacklevel : int
        How far up the stack the warning needs to go, before
        showing the relevant calling lines.
    Usage
    -----
    @deprecated(msg='function_a is deprecated! Use function_b instead.')
    def function_a(*args, **kwargs):
    """
    def deprecated_dec(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            warnings.warn(
                msg or "Function %s is deprecated." % fn.__name__,
                category=DeprecationWarning,
                stacklevel=stacklevel
            )
            return fn(*args, **kwargs)
        return wrapper
    return deprecated_dec


def contextmanager(f):
    """
    Wrapper for contextlib.contextmanager that tracks which methods of
    PipelineHooks are contextmanagers in CONTEXT_MANAGER_METHODS.
    """
    PIPELINE_HOOKS_CONTEXT_MANAGERS.add(f.__name__)
    return contextmanager(f)


def _create_clock(self):
    """
    If the clock property is not set, then create one based on frequency.
    """
    trading_o_and_c = self.trading_calendar.schedule.ix[
        self.sim_params.sessions]
    market_closes = trading_o_and_c['market_close']
    minutely_emission = False

    if self.sim_params.data_frequency == 'minute':
        market_opens = trading_o_and_c['market_open']
        minutely_emission = self.sim_params.emission_rate == "minute"

        # The _calendar's execution times are the minutes over which we
        # actually want to run the clock. Typically the execution times
        # simply adhere to the market open and close times. In the case of
        # the futures _calendar, for example, we only want to simulate over
        # a subset of the full 24 hour _calendar, so the execution times
        # dictate a market open time of 6:31am US/Eastern and a close of
        # 5:00pm US/Eastern.
        execution_opens = \
            self.trading_calendar.execution_time_from_open(market_opens)
        execution_closes = \
            self.trading_calendar.execution_time_from_close(market_closes)
    else:
        # in daily mode, we want to have one bar per session, timestamped
        # as the last minute of the session.
        execution_closes = \
            self.trading_calendar.execution_time_from_close(market_closes)
        execution_opens = execution_closes

    # FIXME generalize these values
    before_trading_start_minutes = days_at_time(
        self.sim_params.sessions,
        time(8, 45),
        "US/Eastern"
    )

    return MinuteSimulationClock(
        self.sim_params.sessions,
        execution_opens,
        execution_closes,
        before_trading_start_minutes,
        minute_emission=minutely_emission,
    )


# Copied from Position and renamed.  This is used to handle cases where a user
# does something like `context.portfolio.positions[100]` instead of
# `context.portfolio.positions[sid(100)]`.
class _DeprecatedSidLookupPosition(object):
    def __init__(self, sid):
        self.sid = sid
        self.amount = 0
        self.cost_basis = 0.0  # per share
        self.last_sale_price = 0.0
        self.last_sale_date = None

    def __repr__(self):
        return "_DeprecatedSidLookupPosition({0})".format(self.__dict__)

    # If you are adding new attributes, don't update this set. This method
    # is deprecated to normal attribute access so we don't want to encourage
    # new usages.
    __getitem__ = _deprecated_getitem_method(
        'position', {
            'sid',
            'amount',
            'cost_basis',
            'last_sale_price',
            'last_sale_date',
        },
    )

# def is_restricted(self, asset, dt):
#     if isinstance(asset, Asset):
#         return any(
#             r.is_restricted(asset, dt) for r in self.sub_restrictions
#         )
#
#     return reduce(
#         operator.or_,
#         (r.is_restricted(asset, dt) for r in self.sub_restrictions)
#     )

# # exec eval compile将字符串转化为可执行代码 , exec compile source into code or AST object ,if filename is None ,'<string>' is used
# # code = compile(self.algoscript, algo_filename, 'exec')
# # exec_(code, self.namespace)

def func(paramlist):

    a,b =paramlist[0],paramlist[1]
    return [a / (a+b) - 0.0476,
            (a*b) /((a+b+1) * (a+b) ** 2) - 0.0021]
c1,c2=fsolve(func,[0,0])
print(c1,c2)
e = c1 / (c1+c2)

#代码高亮
try:
    from pygments import highlight
    from pygments.lexers import PythonLexer
    from pygments.formatters import TerminalFormatter
    PYGMENTS = True
except ImportError:
    PYGMENTS = False


class AlgorithmSimulator(object):

    EMISSION_TO_PERF_KEY_MAP = {
        'minute': 'minute_perf',
        'daily': 'daily_perf'
    }

    def __init__(self, algo, sim_params, data_portal, clock, benchmark_source,
                 restrictions, universe_func):

        # ==============
        # ArkQuant
        # Param Setup
        # ==============
        self.sim_params = sim_params
        self.data_portal = data_portal
        self.restrictions = restrictions

        # ==============
        # Algo Setup
        # ==============
        self.algo = algo

        # ==============
        # Snapshot Setup
        # ==============

        # We don't have a datetime for the current snapshot until we
        # receive a message.
        self.simulation_dt = None

        self.clock = clock

        self.benchmark_source = benchmark_source

        # =============
        # Logging Setup
        # =============

        # Processor function for injecting the algo_dt into
        # user prints/logs.
        # def inject_algo_dt(record):
        #     if 'algo_dt' not in record.extra:
        #         record.extra['algo_dt'] = self.simulation_dt
        # self.processor = Processor(inject_algo_dt)

        # This object is the way that user algorithms interact with OHLCV data,
        # fetcher data, and some API methods like `data.can_trade`.
        self.current_data = self._create_bar_data(universe_func)

    def get_simulation_dt(self):
        return self.simulation_dt

    #获取日数据，封装为一个API(fetch process flush other api)
    def _create_bar_data(self, universe_func):
        return BarData(
            data_portal=self.data_portal,
            simulation_dt_func=self.get_simulation_dt,
            data_frequency=self.sim_params.data_frequency,
            trading_calendar=self.algo.trading_calendar,
            restrictions=self.restrictions,
            universe_func=universe_func
        )

    def transform(self):
        """
        Main generator work loop.
        """
        algo = self.algo
        metrics_tracker = algo.metrics_tracker
        emission_rate = metrics_tracker.emission_rate

        #生成器yield方法 ，返回yield 生成的数据，next 执行yield 之后的方法
        def every_bar(dt_to_use, current_data=self.current_data,
                      handle_data=algo.event_manager.handle_data):
            for capital_change in calculate_minute_capital_changes(dt_to_use):
                yield capital_change

            self.simulation_dt = dt_to_use
            # called every tick (minute or day).
            algo.on_dt_changed(dt_to_use)

            broker = algo.broker

            # handle any transactions and commissions coming out new orders
            # placed in the last bar
            new_transactions, new_commissions, closed_orders = \
                broker.get_transactions(current_data)

            broker.prune_orders(closed_orders)

            for transaction in new_transactions:
                metrics_tracker.process_transaction(transaction)

                # since this order was modified, record it
                order = broker.orders[transaction.order_id]
                metrics_tracker.process_order(order)

            for commission in new_commissions:
                metrics_tracker.process_commission(commission)

            handle_data(algo, current_data, dt_to_use)

            # grab any new orders from the broker, then clear the list.
            # this includes cancelled orders.
            new_orders = broker.new_orders
            broker.new_orders = []

            # if we have any new orders, record them so that we know
            # in what perf period they were placed.
            for new_order in new_orders:
                metrics_tracker.process_order(new_order)

        def once_a_day(midnight_dt, current_data=self.current_data,
                       data_portal=self.data_portal):
            # process any capital changes that came overnight
            for capital_change in algo.calculate_capital_changes(
                    midnight_dt, emission_rate=emission_rate,
                    is_interday=True):
                yield capital_change

            # set all the timestamps
            self.simulation_dt = midnight_dt
            algo.on_dt_changed(midnight_dt)

            metrics_tracker.handle_market_open(
                midnight_dt,
                algo.data_portal,
            )

            # handle any splits that impact any positions or any open orders.
            assets_we_care_about = (
                viewkeys(metrics_tracker.positions) |
                viewkeys(algo.broker.open_orders)
            )

            if assets_we_care_about:
                splits = data_portal.get_splits(assets_we_care_about,
                                                midnight_dt)
                if splits:
                    algo.broker.process_splits(splits)
                    metrics_tracker.handle_splits(splits)

        def on_exit():
            # Remove references to algo, data portal, et al to break cycles
            # and ensure deterministic cleanup of these objects when the
            # ArkQuant finishes.
            self.algo = None
            self.benchmark_source = self.current_data = self.data_portal = None

        with ExitStack() as stack:
            """
            由于已注册的回调是按注册的相反顺序调用的，因此最终行为就好像with 已将多个嵌套语句与已注册的一组回调一起使用。
            这甚至扩展到异常处理-如果内部回调抑制或替换异常，则外部回调将基于该更新状态传递自变量。
            enter_context  输入一个新的上下文管理器，并将其__exit__()方法添加到回调堆栈中。返回值是上下文管理器自己的__enter__()方法的结果。
            callback（回调，* args，** kwds ）接受任意的回调函数和参数，并将其添加到回调堆栈中。
            """
            stack.callback(on_exit)
            stack.enter_context(self.processor)
            stack.enter_context(ZiplineAPI(self.algo))

            if algo.data_frequency == 'minute':
                def execute_order_cancellation_policy():
                    algo.broker.execute_cancel_policy(SESSION_END)

                def calculate_minute_capital_changes(dt):
                    # process any capital changes that came between the last
                    # and current minutes
                    return algo.calculate_capital_changes(
                        dt, emission_rate=emission_rate, is_interday=False)
            else:
                def execute_order_cancellation_policy():
                    pass

                def calculate_minute_capital_changes(dt):
                    return []

            for dt, action in self.clock:
                if action == BAR:
                    for capital_change_packet in every_bar(dt):
                        yield capital_change_packet
                elif action == SESSION_START:
                    for capital_change_packet in once_a_day(dt):
                        yield capital_change_packet
                elif action == SESSION_END:
                    # End of the session.
                    positions = metrics_tracker.positions
                    position_assets = algo.asset_finder.retrieve_all(positions)
                    self._cleanup_expired_assets(dt, position_assets)

                    execute_order_cancellation_policy()
                    algo.validate_account_controls()

                    yield self._get_daily_message(dt, algo, metrics_tracker)
                elif action == BEFORE_TRADING_START_BAR:
                    self.simulation_dt = dt
                    algo.on_dt_changed(dt)
                    algo.before_trading_start(self.current_data)
                elif action == MINUTE_END:
                    minute_msg = self._get_minute_message(
                        dt,
                        algo,
                        metrics_tracker,
                    )

                    yield minute_msg

            risk_message = metrics_tracker.handle_simulation_end(
                self.data_portal,
            )
            yield risk_message

    def _cleanup_expired_assets(self, dt, position_assets):
        """
        Clear out any asset that have expired before starting a new sim day.

        Performs two functions:

        1. Finds all asset for which we have open orders and clears any
           orders whose asset are on or after their auto_close_date.

        2. Finds all asset for which we have positions and generates
           close_position events for any asset that have reached their
           auto_close_date.
        """
        algo = self.algo

        def past_auto_close_date(asset):
            acd = asset.auto_close_date
            return acd is not None and acd <= dt

        # Remove positions in any sids that have reached their auto_close date.
        assets_to_clear = \
            [asset for asset in position_assets if past_auto_close_date(asset)]
        metrics_tracker = algo.metrics_tracker
        data_portal = self.data_portal
        for asset in assets_to_clear:
            metrics_tracker.process_close_position(asset, dt, data_portal)

        # Remove open orders for any sids that have reached their auto close
        # date. These orders get processed immediately because otherwise they
        # would not be processed until the first bar of the next day.
        broker = algo.broker
        assets_to_cancel = [
            asset for asset in broker.open_orders
            if past_auto_close_date(asset)
        ]
        for asset in assets_to_cancel:
            broker.cancel_all_orders_for_asset(asset)

        # Make a copy here so that we are not modifying the list that is being
        # iterated over.
        for order in copy(broker.new_orders):
            if order.status == ORDER_STATUS.CANCELLED:
                metrics_tracker.process_order(order)
                broker.new_orders.remove(order)

    def _get_daily_message(self, dt, algo, metrics_tracker):
        """
        Get a perf message for the given datetime.
        """
        perf_message = metrics_tracker.handle_market_close(
            dt,
            self.data_portal,
        )
        perf_message['daily_perf']['recorded_vars'] = algo.recorded_vars
        return perf_message

    def _get_minute_message(self, dt, algo, metrics_tracker):
        """
        Get a perf message for the given datetime.
        """
        rvars = algo.recorded_vars

        minute_message = metrics_tracker.handle_minute_close(
            dt,
            self.data_portal,
        )

        minute_message['minute_perf']['recorded_vars'] = rvars
        return minute_message

        # =============
        # Logging Setup
        # =============

        # Processor function for injecting the algo_dt into
        # user prints/logs.
        # def inject_algo_dt(record):
        #     if 'algo_dt' not in record.extra:
        #         record.extra['algo_dt'] = self.simulation_dt
        # self.processor = Processor(inject_algo_dt)


class PeriodLabel(object):
    """Backwards compat, please kill me.
    """
    def start_of_session(self, ledger, session, data_portal):
        self._label = session.strftime('%Y-%m')

    def end_of_bar(self, packet, *args):
        packet['cumulative_risk_metrics']['period_label'] = self._label

    end_of_session = end_of_bar


# def asymmetric_round_price(price, prefer_round_down, tick_size, diff=0.95):
#     """
#     Asymmetric rounding function for adjusting prices to the specified number
#     of places in a way that "improves" the price. For limit prices, this means
#     preferring to round down on buys and preferring to round up on sells.
#     For stop prices, it means the reverse.

#     If prefer_round_down == True:
#         When .05 below to .95 above a specified decimal place, use it.
#     If prefer_round_down == False:
#         When .95 below to .05 above a specified decimal place, use it.

#     In math-speak:
#     If prefer_round_down: [<X-1>.0095, X.0195) -> round to X.01.
#     If not prefer_round_down: (<X-1>.0005, X.0105] -> round to X.01.
#     """
#     # 返回位数
#     precision = zp_math.number_of_decimal_places(tick_size)
#     multiplier = int(tick_size * (10 ** precision))
#     diff -= 0.5  # shift the difference down
#     diff *= (10 ** -precision)  # adjust diff to precision of tick size
#     diff *= multiplier  # adjust diff to value of tick_size

#     # Subtracting an epsilon from diff to enforce the open-ness of the upper
#     # bound on buys and the lower bound on sells.  Using the actual system
#     # epsilon doesn't quite get there, so use a slightly less epsilon-ey value.
#     epsilon = float_info.epsilon * 10
#     diff = diff - epsilon

#     # relies on rounding half away from zero, unlike numpy's bankers' rounding
#     rounded = tick_size * consistent_round(
#         (price - (diff if prefer_round_down else -diff)) / tick_size
#     )
#     if zp_math.tolerant_equals(rounded, 0.0):
#         return 0.0
#     return rounded


# getter  ---- property ;  setter --- @func.setter

# __delete__(instance), __get__(instance,owner) , __set__(instance,value) 描述器 , 实例为类的类属性
# __getattribute__ --- __getattr__ (显式访问不存在饿属性,除非显示调用或引发AttributeError异常） ）

# __delete__(self,instance) ,__del__(self)


# 字典键值对转换
def _invert(d):
    return dict(zip(d.values(), d.keys()))


def copy_process_env(self):
    """为子进程拷贝主进程中的设置执行,在add_process_env_sig装饰器中调用,外部不应主动使用"""
    for module in self.register_module():
        # 迭代注册了的需要拷贝内存设置的模块, 筛选模块中以g_或者_g_开头的, 且不能callable，即不是方法
        sig_env = list(filter(
            lambda sig: not callable(sig) and (sig.startswith('g_') or sig.startswith('_g_')), dir(module)))
        module_name = module.__name__
        for _sig in sig_env:
            # 格式化类变量中对应模块属性的key
            name = '{}_{}'.format(module_name, _sig)
            # 根据应模块属性的key（name）getattr获取属性值
            val = getattr(self, name)
            # 为子模块内存变量进行值拷贝
            module.__dict__[_sig] = val

def add_process_env_sig(func):
    """
    初始化装饰器时给被装饰函数添加env关键字参数,在wrapper中将env对象进行子进程copy
    由于要改方法签名，多个装饰器的情况要放在最下面
    :param func:
    :return:
    """
    # 获取原始函数参数签名，给并行方法添加env参数
    sig = signature(func)

    if 'env' not in list(sig.parameters.keys()):
        parameters = list(sig.parameters.values())
        # 通过强制关键字参数，给方法加上env
        parameters.append(Parameter('env', Parameter.KEYWORD_ONLY, default=None))
        # wrapper的__signature__进行替换
        wrapper.__signature__ = sig.replace(parameters=parameters)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # env = kwargs.pop('env', None)
        if 'env' in kwargs:
            """
                实际上linux, mac os上并不需要进行进程间模块内存拷贝，
                子进程fork后携带了父进程的内存信息，win上是需要的，
                暂时不做区分，都进行进程间的内存拷贝，如特别在乎效率的
                情况下基于linux系统，mac os可以不需要拷贝，如下：
                if kwargs['env'] is not None and not ABuEnv.g_is_mac_os:
                    # 只有windows进行内存设置拷贝
                    env.copy_process_env()
            """
            # if kwargs['env'] is not None and not ABuEnv.g_is_mac_os:
            env = kwargs.pop('env', None)
            if env is not None:
                # 将主进程中的env拷贝到子进程中
                env.copy_process_env()
        return func(*args, **kwargs)

    return wrapper


# def _compute(self, arrays, dates, assets, mask):
#     data = arrays[0]
#     bins = self.params['bins']
#     to_bin = where(mask, data, nan)
#     result = quantiles(to_bin, bins)
#     # Write self.missing_value into nan locations, whether they were
#     # generated by our input mask or not.
#     result[isnan(result)] = self.missing_value
#     return result.astype(int64_dtype)

def example_function():
    # Get the current frame
    current_frame = sys._getframe(0)
    
    # Print information about the current frame
    print("Current function name:", current_frame.f_code.co_name)
    print("Current line number:", current_frame.f_lineno)
    print("Local variables:", current_frame.f_locals)

    cur_1 = sys._getframe(1)
    print("Current function name1:", cur_1.f_code.co_name)
    print("Current line number1:", cur_1.f_lineno)
    print("Local variables1:", cur_1.f_locals)

example_function()
