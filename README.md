                                        Fake it until you make it

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

    indicator next logic / line + line / line + ind
    minperiod
    update minperiod 
     __getitem__ --> next 方法 / prenext
    feed / ind 分开
    linealias 
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

    python class protect property via property func method() instead __init__

    preload may cause performance problem

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

    trategy lineroot / linebuffer / op

    filter (nanpercentile / ~ / & / isin /frozenset / ().view(uint8)) --> bsplitter / day splitter

    resample used for strategy / replay used for broker

    line multiple coef if adjustment is True

    adjustment event apply start of tradingday

    # priority queue / binary tree where parent node is smaller than child node
    # heapop the smallest element
    from heapq import heappush, heappop

    restriction of mp:
        1. apply_async ---> func must be defined outside of class (not class method)
        2. get() ---> must be called before close() or terminate()

    from multiprocessing import Pool
         pool = Pool(4)
         res = [pool.apply_async(func,(i,)) for i in range(10)]
         for r in res:
             print(r.get())

    # yield func to generator 
    # generator is iterator
    # next method, each time execute to yield stop
    # iter(iterator) ---> convert non-iterable to iterator

    # apply --- function axis = 0 or axis = 1
    # applymap ---- function value of dataframe
    # map ---- function on series

    memory : joblib.Memory interface used to cache the fitted transformers of
        the Pipeline. By default,no caching is performed. If a string is given,
        it is the path to the caching directory. Enabling caching triggers a clone
        of the transformers before fitting.Caching the transformers is advantageous
        when fitting is time consuming.

    descriptor:
        __get__(self, instance, owner)
        __set__(self, instance, value)
        __delete__(self, instance)

    property ---> descriptor

    property(fget=None, fset=None, fdel=None, doc=None)
