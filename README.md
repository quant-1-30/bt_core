
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

filter ---> bsplitter / day splitter

# 策略 以bayies 为主

workflow --- based on ray and big model sam to analyse ( indicator + pymc)


    将不同的算法通过串行或者并行方式形成算法工厂 ，筛选过滤最终得出目标目标标的组合
    串行：
        1、串行特征工厂借鉴zipline或者scikit_learn Pipeline
        2、串行理论基础: 现行的策略大多数基于串行，比如多头排列\空头排列\行业龙头战法\统计指标筛选
        3、缺点: 确定存在主观去判断特征顺序,前提对于市场有一套自己的认识以及分析方法
    并行：
        1、并行的理论基础借鉴交集理论
        2、基于结果反向分类strategy
    难点：
        不同算法的权重分配


    裁决模块 基于有效的特征集，针对特定的asset进行投票抉择
    关于仲裁逻辑：
        普通选股: 针对备选池进行选股, 迭代初始选股序列, 在迭代中再迭代选股因子, 选股因子决定是否对
        symbol投出反对票, 一旦一个因子投出反对票, 即筛出序列


    组合不同算法---策略
    返回 --- Order对象
    initialize
    handle_data
    before_trading_start
        1.判断已经持仓是否卖出
        2.基于持仓限制确定是否执行买入操作

    MIFeature（构建有特征组成的接口类）, 特征按照一定逻辑组合处理为策略
            实现: 逻辑组合抽象为不同的特征的逻辑运算, 具体还是基于不同的特征的运行结果
        strategy composed of features which are logically arranged
        input: feature_list
        return: asset_list
        param: _n_field --- all needed field ,_max_window --- upper window along the window args
        core_part: _domain --- logically combine all features


波动率 --- 并非常数，均值回复，聚集，存在长期记忆性的
大收益率会发生的相对频繁 --- 存在后续的波动
在大多数市场中，波动率与收益率呈现负相关，在股票市场中的最为明显
波动率和成交量之间存在很强的正相关性
波动率分布接近正太分布

基于大类过滤
标的 --- 按照市值排明top 10% 标的标的集合 --- 度量周期的联动性
a 计算每个月的月度收益率, 筛选出10%集合 / 12的个数
b 获取每个月的集合 --- 作为当月的强周期集合
c 基于技术指标等技术获取对应的标的

1、序列中基于中位数的性质更加能代表趋势动向
2、预警指标的出现股票集中, 容易出现后期的大黑马,由此推导出异动逻辑以及在持续性
3、统计套利:(pt > pt-1) / (pt-1 > m) 概率为75% 引发的思考(close - pre_high)

        主要针对于ETF或者其他的自定义指数
        度量动量配对交易策略凸优化(Convex Optimization)
        1、etf 国内可以卖空
        2、构建一个协整关系的组合与etf 进行多空交易
        逻辑：
        1、以ETF50为例,找出成分股中与指数具备有协整关系的成分股
        2、买入具备协整关系的股票集, 并卖出ETF50指数
        3、如果考虑到交易成本, 微弱的价差刚好覆盖成本, 没有利润空间
        筛选etf成分股中与指数具备有协整关系的成分股
        将具备协整关系的成分股组合买入, 同时卖出对应ETF
        计算固定周期内对冲收益率, 定期去更新_coint_test

        不同ETF之间的配对交易; 相当于个股来讲更加具有稳定性
        1、价格比率交易(不具备协整关系,但是具有优势)
        2、计算不同ETF的比率的平稳性(不具备协整关系，但是具有优势）
        3、平稳性 --- 协整检验
        4、半衰期 : -log2/r --- r为序列的相关系数
        单位根检验、协整模型
        pval = ADF.calc_feature(ratio_etf)
        coef = _fit_statsmodel(np.array(raw_y), np.array(raw_x))
        residual = raw_y - raw_x * coef
        acf = ACF.calc_feature(ratio_etf)[0]
        if pval <= 0.05 and acf < 0:
            half = - np.log(2) / acf
        zscore = (nowdays - ratio_etf.mean()) / ratio_etf.std()

        协整检验 --- coint_similar(协整关系)
            1、筛选出相关性的两个标的
            2、判断序列是否平稳 --- 数据差分进行处理
            3、协整模块
        Coint 返回值三个如下:
            coint_t: float t - statistic of unit - root c_test on residuals
            pvalue: float MacKinnon's approximate p-value based on MacKinnon (1994)
            crit_value: dict Critical  values for the c_test statistic at the 1 %, 5 %, and 10 % levels.
        Coint 参数：
            statsmodels.tsa.stattools.coint(y0, y1, trend ='c', method ='aeg', maxlag = None, autolag ='aic'

    主成分分析法理论：选择原始数据中方差最大的方向，选择与其正交而且方差最大的方向，不断重复这个过程
    pca.fit_transform()
    具体的算法：
    PCA算法: 
    1 将原始数据按列组成n行m列矩阵X

    2 将X的每一行 代表一个属性字段 进行零均值化, 即减去这一行的均值

    3 求出协方差矩阵C=X * XT

    4 求出协方差矩阵的特征值及对应的特征向量

    5 将特征向量按对应特征值大小从上到下按行排列成矩阵,取前k行组成矩阵P

    6 Y=PX  即为降维到k维后的数据
    
        多重分形理论一个重要的应用就是Hurst指数, Hurst指数和相应的时间序列分为3种类型: 当H=0.5时，时间序列是随机游走的，序列中不同时间的
        值是随机的和不相关的,即现在不会影响将来; 当0≤H≤0.5时，这是一种反持久性的时间序列，常被称为“均值回复”。如果一个序列在前个一时期是
        向上走的，那么它在下一个时期多半是向下走,反之亦然。这种反持久性的强度依赖于H离零有多近,越接近于零,这种时间序列就具有比随机序列更
        强的突变性或易变性;当0.5≤H≤1时, 表明序列具有持续性, 存在长期记忆性的特征。即前一个时期序列是向上(下)走的，那下一个时期将多半继续
        是向上(下)走的, 趋势增强行为的强度或持久性随H接近于1而增加
        R/S(重标极差分析）:
            1、对数并差分, 价格序列转化为了对数收益率序列
            2、对数收益率序列等划分为A个子集
            3、计算相对该子集均值的累积离差
            4、计算每个子集内对数收益率序列的波动范围: 累积离差最大值和最小值的差值
            5、计算每个子集内对数收益率序列的标准差
            6、用第五步值对第4步值进行标准化
            7、增大长度并重复前六步, 得出6的序列
            8、将7步的序列对数与长度的对数进行回归, 斜率Hurst指数

        Lo和Mackinlay(1988)假定，样本区间内的随机游走增量(RW3)的方差为线性。
        若股价的自然对数服从随机游走，则方差比率与收益水平成比例,其方差比率VR期望值为1。
        由于Lo-MacKinlay方差比检验为渐近检验,其统计量的样本分布渐近服从标准正态分布，在有限样本的情况下, 其分布常常是有偏的;
        在基础上提出了一种基于秩和符号的非参数方差比检验方法。在样本量相对较小的情况下，而不依赖于大样本渐近极限分布
        方差比检验: 若股价的自然对数服从随机游走，则方差比率与收益水平成比例
        与adf搭配使用, 基于adf中的滞后项


# topology
      ________________________________________________  
     |                                                |
     |                                                |
     |                         udp                    |
history_data  -----------> sim-platform  ---------> engine --------> risk_management --------> order / portfolio -----------> metrics 
                                |                                                                                                | 
                                |                                                                                                | 
                                ----------------------------------------------------------------------------------------------- tune

# raw dataset center
db + grpc server

# sim
grpc client + udp server
replay --- simulation
latency
replay ---> udp ---> topic
latency ---> xtp 对replay进行反向优化

# engine
grpc client + udp client  ----> dataloader
indicator + topology ----> dag
dataloader + dag

# execution
risk-management
order 
portfolio

# metrics
topic

交易所官网
# 退市/暂停上市
# 分红数据
# 股票基本情况（注册地）



