                                        Fake it until you make it

backtrader:
    metaclass __new__ ---> __call__ 
    __new__ dct meaning class attributes(property, method) / __call__ **kwargs meaning instance 

    dataflow cerebro runnext ---> data[0] 变化 ---> strategy ---> indicator

    addbings to sync datas minperiod

    _owner lines ---> Indicator / Indicator ---> Strategy / DataFeed ---> Cerebro

    coupler align dt

    lineaction ---> makeoperation / coupler

    lines _derive / lineseries __new__ update cls.lines

    AutoInfoParam similar to lines _derive aims to update

    add feed ---> based on lineseries preload ---> while load ---> _load

    indicator ---> datas (lineseries) to update self.lines / next method

    indicator ---> datas / IndType / self.lines

    _clock ---> _clock._clock (high level clock)

    slave is used for unchanged action

    owner is used to connnect with strategy or cerebro obj

    exactbars control the memory usage of strategy

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

    filter (nanpercentile / ~ / & / isin /frozenset / ().view(uint8)) --> bsplitter / day splitter

    resample used for strategy / replay used for broker

    strategy different mode depends on the data type ( islive / runonce )

    _once ---> strategy._once() origin from lineiterator _once method 

    _runonce_old ---> _once ---> _oncepost buflen 

    _runonce ---> _once / reset ---> while _oncepost_open / _oncepost

    _runnext_old ---> _next while

    _runnext ---> _next_open / _next while

    _minperiod ---> datas ---> line 

    # strategy ---> indicate and lineaction (addindcator to _ltype.Ind) _once / _next  list(Indicator and Lineaction) 递归
    # observer (addindcator to _ltype.Obs) / analyzers.owner.register prenext ---> next

    # makeoperation 针对于二元的表达树 / 多元表达式会存在构建多元表达树 不同节点  = 右侧表达式 关键定义运算符返回的节点对象 
    # 针对于backtrader 多元表示树就是 line对象

    # 元类”在类定义时注册
    # auto register meaning subclass of type __init__ will be triggered when __import__ only intended for metaclass 
    # model.py
    # __class__ means metaclass introspection / dynamic behavior
    <!-- from .base import Meta  # 这行不会触发 Meta.__init__

    class MyClass(metaclass=Meta):  # 这里才触发 Meta.__init__
        pass -->

    # strategy._next() tirgger _next --- indicator / _next_anlayzer / _next_observer


