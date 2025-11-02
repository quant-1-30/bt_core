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


    # sizer ---> intended to multistrategy binding to strategy not sid
    # cerebro ---> executor singelton
    # GPE 帕累托优化

    # poetry lock --no-update / poetry update

# **kwargs ---> key=value pack dict  / 解包 传入字典
# three level a. construct  / b.base api class / instance
# plugin webrtc / ws /


# gunicorn.conf.py
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:11000"
timeout = 60
accesslog = "access.log"
errorlog = "error.log"

# indicator period via addminperiod ---> update _minperiod
# strategy _getminperstatus 
# 策略由指标组成，指标嵌套实在strategy 体现， indicator 保持原子性， 因此 strategy 返回的_minperiod就是feed buflen

# poetry env remove --all

对于暂停上市 delist_date 为None 作为一种长期停盘的情况来考虑不能存在后视误差不清楚是否能重新上市
asset status 由于吸收合并代码可能会消失但是主体继续上市存在 e.g. T00018

# indicator period --> _minperiod 基于 basicops.py PeriodN 

# plot 3level  multicursor /  ticker locate / 2grid

# plot from notify

# store and notify


# utm https://docs.getutm.app/guides/windows/

# memview -> np.frombuffer for process

# store --- multi_strategies / 扩展store多个sids (pair trade)


# 不同策略, minperiod 不一样

# hashlib.pbkdf2_hmac()
# crpyted = hashlib.sha256()
# crpyted.update(uname)
# crpyted.hexdigest()
    
cloudpickle and loky  ---> pickle and mp

# 存在问题 store datacls / brokercls

# LineAction 当只有单个指标计算对应对象是LineBuffer需要封装为LineAction (keep _next / _once api consistent with lineiterator)

# LineSeries getattr ---> ex sma.get / _LineDelay (sma ---> LineAction  ---> addbinding ----> self[0] = a[ago])

# analyzer _on_dt_over api / feed _on_dt_over

# cash intended for client_id and experiment_id accociated with cash with client_id

# integrate store / set_cash into cerebro

# solve observer next bug 

# 类的 __class__ 返回元类的与继承无关系

