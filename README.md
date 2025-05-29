                                        Fake it until you make it

prototype

1\ backtest

2\ live trade

3\ ai agent construct strategy and deploy to live trade / wechat timer

4\ mr visual 


framework:

    strategy infrastructure:
        a. Ind --> Term --> Pipeline --> Strategy (indicator + pymc)

        b. strategy ---> signal ---> size ---> control --> execution ---> next

        c. build on Dag
            sequential_feature_factory --> penetrate layer by layer
            concurrent_feature_factory --> intersect between same node
            indicator + pymc

    caution and conflict:
        a. to exclude the position asset which to need to be sold
        b. trading_control ---> quantity / avaiable according to existing position
        c. before execute the strategy , setup universe_mask
        e. position need to be sold but the strategy signal tiggers the same asset
        f. risk control 

    extend:
        a. ray to scale
        b. sam model
        c. mcp to agent

backtrader:

    addbindings

    indicators linesiterator lineseries
  
    dataflow cerebro runnext ---> data[0] 变化 ---> strategy ---> indicator

    addbings to sync datas minperiod

    _owner lines ---> Indicator / Indicator ---> Strategy / DataFeed ---> Cerebro

    coupler align dt

    lineaction ---> makeoperation / coupler

    feed load ---> _load (while)

    __getitem__ keys starting from 0 , also can be used in for loop

    lines _derive / lineseries __new__ update cls.lines

    AutoInfoParam similar to lines _derive aims to update

    metaclass __new__ ---> __call__ 

    __new__ dct meaning class attributes(property, method) / __call__ **kwargs meaning instance 

    add feed ---> based on lineseries preload ---> while load ---> _load

    indicator ---> datas (lineseries) to update self.lines / next method

    indicator ---> datas / IndType / self.lines

    _clock ---> _clock._clock (high level clock)

    slave is used for unchanged action

    owner is used to connnect with strategy or cerebro obj

    exactbars control the memory usage of strategy

    _runonce_old ---> strategy._once() ---> strategy._oncepost()

    _runonce ---> strategy._once() ---> strategy._oncepost()

    _runnext_old ---> strategy._next()

    _runnext ---> strategy._next()

    strategy different mode depends on the data type ( islive / runonce )

    _once ---> strategy._once() origin from lineiterator _once method 

    every indicator has its own _once method (preonce > once > oncestart > oncebinding) inherit from linebuffer

    line operation ---> LineOperation ---> inherit from linebuffer

    _owner / addindicator is key to implement indicator _once / _next method (from base to compound)

    plot also based on line object

    data _check /_last method

    LineCoupler (align different line length)

    resample logic cerebro resampledata ---> resample ---> addfilter

    feed + resample ---> while True ---> load ---> self._load ---> filter ---> stash popleft

    componly --- means not intraday (compression only)

    timer ---> checkmonth / checkweek (via bisect left / right) 
    compare with nexteos / compare with checkmonth / checkweek / update dtwen

    strategy ---> signal ---> size ---> control --> execution ---> next

    strategy lineroot / linebuffer / op

    filter (nanpercentile / ~ / & / isin /frozenset / ().view(uint8)) --> bsplitter / day splitter

    resample used for strategy / replay used for broker

    core component: strategy and analyze 

    plugin: visual / web / 

    _runonce_old ---> _once ---> _oncepost buflen 

    _runonce ---> _once / reset ---> while _oncepost_open / _oncepost

    _runnext_old ---> _next while

    _runnext ---> _next_open / _next while

    lines / datas 区别 datas original from feeds

    _minperiod ---> datas ---> line 

    # strategy ---> indicate and lineaction (addindcator to _ltype.Ind) _once / _next  list(Indicator and Lineaction) 递归
    # observer (addindcator to _ltype.Obs) / analyzers.owner.register prenext ---> next

    # makeoperation 针对于二元的表达树 / 多元表达式会存在构建多元表达树 不同节点  = 右侧表达式 关键定义运算符返回的节点对象 
    # 针对于backtrader 多元表示树就是 line对象

    # priority queue / binary tree where parent node is smaller than child node
    # heapop the smallest element
    from heapq import heappush, heappop

    restrict of mp:
        1. apply_async ---> func must be defined outside of class (not class method)
        2. get() ---> must be called before close() or terminate()

    from multiprocessing import Pool
         pool = Pool(4)
         res = [pool.apply_async(func,(i,)) for i in range(10)]
         for r in res:
             print(r.get())

    # yield func to generator / generator is iterator
    # next method, each time execute to yield stop
    # iter(iterator) ---> convert non-iterable to iterator

    # apply --- function axis = 0 or axis = 1 / map --- function on series
    # applymap ---- function value of dataframe

    memory : joblib.Memory interface used to cache the fitted transformers of
        the Pipeline. By default,no caching is performed. If a string is given,
        it is the path to the caching directory. Enabling caching triggers a clone
        of the transformers before fitting.Caching the transformers is advantageous
        when fitting is time consuming.

    量化交易系统:
        a.策略识别（搜索策略 , 挖掘优势 , 交易频率）
        b.回测测试（获取数据 , 分析策略性能 ,剔除偏差）
        c.交割系统（经纪商接口 ,交易自动化 , 交易成本最小化）
        d.风险管理（最优资本配置 , 最优赌注或者凯利准则 , 海龟仓位管理）
    
    # 优化点 策路不止二元操作 / 多元操作

    # revise bt_sdk version and poetry lock --no-update and poetry install

    # construct store module and incomporate into mdapi feed module
    # construct tdbroker with tdapi
    
    # revise cerebro
    # test observer and analyzer
    # test strategy

    # 元类”在类定义时注册
    # auto register meaning subclass of type __init__ will be triggered when __import__ only intended for metaclass 
    # e.g
    # model.py
    # __class__ means metaclass introspection / dynamic behavior
    <!-- from .base import Meta  # 这行不会触发 Meta.__init__

    class MyClass(metaclass=Meta):  # 这里才触发 Meta.__init__
        pass -->

    # strategy._next() tirgger _next --- indicator / _next_anlayzer / _next_observer

    # store / data / broker 

telnet 127.0.0.1 8888 测试 TCP

nc -u 127.0.0.1 8888 测试 UDP（或写个客户端）

tcp and udp 可以复用同一端口

系统使用五元组 (协议, 源 IP, 源端口, 目标 IP, 目标端口) 来唯一标识一个网络连接或会话

get_notification key is notification mechanism


# add analyzer start stop next notify_order notify_trade strategy _addnotification / _notify / _next_analyzers / _next_observers / store  



梳理 m_execId
1  store == mdapi + tdapi
2  test cerebro and strategy
3  store.data is the cerebro default data

np.iinfo(np.int_) 返回一个对象，包含了 np.int_ 类型（通常是 64 位整数）的信息
这个对象有几个重要的属性：
.max: 该类型可以表示的最大值
.min: 该类型可以表示的最小值
.bits: 该类型使用的位数
.dtype: 该类型的数据类型

notify:
a.  data and broker put_notification 
b.  store get_notification
c.  strategy add_notification ( process data from store get_nofication)

datas:
1\  store data and datas how to solve
2\  timer start of session and end of session

