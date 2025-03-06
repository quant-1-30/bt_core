# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import pandas as pd
import numpy as np
from indicator import (
     BaseFeature,
     MA,
     SMA,
     EMA,
     ExponentialMovingAverage
)
from util.math_utils import zoom


ema = EMA()
sma = SMA()
ma = MA()


# HF=（开盘价+收盘价+最高价+最低价）/4
# TR =∣最高价 - 最低价∣，∣最高价 - 昨收∣，∣昨收 - 最低价∣中的最大值(np.abs(preclose.shift(1))
# 市场宽度上涨股票数量 /（上涨股票数量 + 下跌股票数量）
# a / d = 上涨股票数量 /（上涨股票数量 + 下跌股票数量） STIX a / d的22EMA
# 上涨股票的交易量之和除以下跌股票的交易量之和
# 正常的牛市伴随大量的价格适度上涨；而变弱的牛市少数股票大涨(背离信号) 上涨 - 下跌）的10 % EMA - 5 % 的EMA
# 创出52周新高的股票 - 52周新低的股票  10日MA来平滑指标
# 中位值滤波法
# Fibonacci黄金分割点golden: 0.191 0.382 0.5 0.618 0.809 1 1.382可视化技术线黄金分割

# 不同ETF之间的配对交易 ;相当于个股来讲更加具有稳定性
# 1、价格比率交易(不具备协整关系,但是具有优势)g
# 2、计算不同ETF的比率的平稳性(不具备协整关系,但是具有优势)g
# 3、平稳性 --- 协整检验
# 4、半衰期 : -log2/r --- r为序列的相关系数
# 单位根检验、协整模型
# pval = ADF.calc_feature(ratio_etf)
# coef = _fit_statsmodel(np.array(raw_y), np.array(raw_x))
# residual = raw_y - raw_x * coef
# acf = ACF.calc_feature(ratio_etf)[0]
# if pval <= 0.05 and acf < 0:
#     half = - np.log(2) / acf
# zscore = (nowdays - ratio_etf.mean()) / ratio_etf.std()


# 主要针对于ETF或者其他的自定义指数
# 度量动量配对交易策略凸优化(Convex Optimization)
# 1、etf 国内可以卖空
# 2、构建一个协整关系的组合与etf 进行多空交易
# 逻辑:
# 1、以ETF50为例,找出成分股中与指数具备有协整关系的成分股
# 2、买入具备协整关系的股票集,并卖出ETF50指数
# 3、如果考虑到交易成本,微弱的价差刚好覆盖成本,没有利润空间
# 筛选etf成分股中与指数具备有协整关系的成分股
# 将具备协整关系的成分股组合买入,同时卖出对应ETF
# 计算固定周期内对冲收益率,定期去更新_coint_test

# 波动率 --- 并非常数，均值回复，聚集，存在长期记忆性的
# 大收益率会发生的相对频繁 --- 存在后续的波动
# 在大多数市场中，波动率与收益率呈现负相关，在股票市场中的最为明显
# 波动率和成交量之间存在很强的正相关性
# 波动率分布接近正太分布

# 基于大类过滤
# 标的 --- 按照市值排明top 10% 标的标的集合 --- 度量周期的联动性
# a 计算每个月的月度收益率,筛选出10%集合 / 12的个数
# b 获取每个月的集合 --- 作为当月的强周期集合
# c 基于技术指标等技术获取对应的标的

# 1、序列中基于中位数的性质更加能代表趋势动向
# 2、预警指标的出现股票集中容易出现后期的大黑马, 由此推导出异动逻辑以及在持续性
# 3、统计套利:(pt > pt-1) / (pt-1 > m) 概率为75% 引发的思考(close - pre_high)


class TEMA(BaseFeature):
    """
        三重指数移动平均 --- 3 * EMA - 3 * EMA的EMA + EMA的EMA的EMA
    """
    def _calc_feature(self, frame, kwargs):
        kw = kwargs.copy()
        ema_1 = np.array(ema.compute(frame, kw))
        kw.update({'recursion': 2})
        ema_2 = np.array(ema.compute(frame, kw))
        kw.update({'recursion': 3})
        ema_3 = np.array(ema.compute(frame, kw))
        tema = 3 * ema_1[-len(ema_3):] - ema_2[-len(ema_3):] + ema_3
        return tema


class DEMA(BaseFeature):
    """
        双指数移动平均线,一个单指数移动平均线和一个双指数移动平均线 : 2 * n日EMA - n日EMA的EMA
    """
    def _calc_feature(self, frame, kwargs):
        kw = kwargs.copy()
        ema_1 = np.array(ema.compute(frame,  kw))
        kw.update({'recursion': 2})
        ema_2 = np.array(ema.compute(frame, kw))
        dema = 2 * ema_1[-len(ema_2):] - ema_2
        return dema


class IMI(BaseFeature):
    """
        日内动量指标
        类似于CMO,ISu /(ISu + ISd), 其中ISu表示收盘价大于开盘价的交易日的收盘价与开盘价之差
        ISd则与ISu相反
    """
    def _calc_feature(self, frame, kwargs):
        diff = frame['close'] - frame['open']
        isu = diff[frame['close'] > frame['open']]
        try:
            imi = isu.sum() / abs(diff).sum()
        except ZeroDivisionError:
            imi = - np.inf
        return imi

    def compute(self, feed, kwargs):
        frame = feed.copy()
        imi = self._calc_feature(frame, kwargs)
        return imi


class ER(BaseFeature):
    """
        效率系数,净价格移动除以总的价格移动(位移除以路程绝对值之和),表明趋势的有效性
        基于几何原理 两点之间直线距离最短,位移量 / 直线距离判断效率
        ER(i) = Sinal(i) / Noise(i)
        ER(i) ― 效率比率的当前值;
        Signal(i) = ABS(Price(i) - Price(i - N)) ― 当前信号值,当前价格和N周期前的价格差的绝对值;
        Noise(i) = Sum(ABS(Price(i) - Price(i - 1)), N) ― 当前噪声值,对当前周期价格和前一周期价格差的绝对值求N周期的和。
        在很强趋势下效率比倾向于1;如果无定向移动,则稍大于0
    """
    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        displacement = frame - frame.shift(window)
        distance = np.abs(frame.diff()).rolling(window=window).sum()
        er_windowed = displacement / distance
        print('er_window', len(er_windowed))
        return er_windowed


class CMO(BaseFeature):
    """
        钱德动量摆动指标 归一化
        Su(上涨日的收盘价之差之和) Sd(下跌日的收盘价之差的绝对值之和) (Su - Sd) / (Su + Sd)
    """
    @staticmethod
    def _calc(frame):
        data = (frame - frame.min())/(frame.max() - frame.min())
        data_diff = data - data.shift(1)
        su = data[data_diff > 0].sum()
        sd = data[data_diff < 0].sum()
        cmo = (su + sd) / (su - sd)
        return cmo

    def _calc_feature(self, frame, kwargs):
        cmo = frame.rolling(window=kwargs['window']).apply(self._calc)
        return cmo


class Gap(BaseFeature):
    """
        gap : 低开上破昨日收盘价(preclose > open and close > preclose)
              高开高走 (open > preclose and close > open)
        gap power :delta vol * gap
        逻辑:
        1、统计出现次数
        2、计算跳空能量
    """
    def _calc_feature(self, frame, kwargs):
        frame['delta_vol'] = frame['volume'] - frame['volume'].shift(1)
        frame['gap'] = (frame['close'] - frame['close'].shift(1)) / (frame['open'] - frame['close'].shift(1)) - 1
        gap_power = frame['gap'] * frame['delta_vol'] * np.sign(frame['close'] - frame['close'].shift(1))
        return gap_power

    def compute(self, feed, kwargs):
        frame = feed.copy()
        gap = self._calc_feature(frame, kwargs)
        return gap


class Jump(BaseFeature):
    """
        跳空动能量化 jump threshold --- 度量跳空能量(21D change_pct 均值)
        jump diff --- preclose * jump threshold
        向上跳空 low - preclose > jump diff
        向下跳空 preclose  - high > jump diff
        fields :'close','low','high'
    """
    def _calc_feature(self, frame, window):
        pct = frame['close'] / frame['close'].shift(1) - 1
        pct_mean = pct.rolling(window=window).mean()
        jump_diff = pct_mean * frame['close'].shift(1)
        jump_up = frame['low'] - frame['close'].shift(1)
        jump_down = frame['close'].shift(1) - frame['high']
        power_up = np.sum(jump_up > jump_diff) / window
        power_down = np.sum(jump_down < jump_diff) / window
        power = power_up - power_down
        return power

    def compute(self, feed, kwargs):
        window = kwargs['window']
        frame = feed.copy()
        jump = self._calc_feature(frame, window)
        return jump


class Power(BaseFeature):
    """
        momenum — measure  (high close)— vwap(成交量加权价格)
        logic : power = (close - vwap )* volume
                       ratio  = power / amount
       (增加的动能占总成交金额的比例衡量动能强度)
         window 中如果增加的power站区间的平均的成交金额的比例达到一定阈值,表明动能强度)
        —- stability (市值大,惯性越强;反之小市值的标的,波动性较大)
        剥离stability属性得出能量 , amount / mkv
    """
    def _calc_feature(self, feed, kwargs):
        frame = feed.copy()
        power = frame['volume'] * (frame['close'] - frame['vwap']) / frame['amount']
        return power

    def compute(self, feed, kwargs):
        frame = feed.copy()
        power = self._calc_feature(frame, kwargs)
        return power


class BreakPower(BaseFeature):
    """
        close -- pre_high
    """
    def _calc_feature(self, frame, kwargs):
        power = frame['volume'] * (frame['close'] - frame['high'].shift(1)) / frame['close'].shift(1)
        return power

    def compute(self, feed, kwargs):
        frame = feed.copy()
        brk_power = self._calc_feature(frame, kwargs)
        return brk_power


class Speed(BaseFeature):
    """
    趋势速度跟踪策略 基于符号来定义定义趋势变化的速度值(比率),波动中前进,总会存在回调,度量回调的个数
    计算曲线跟随趋势的速度,由于速度是相对的,所以需要在相同周期内与参数曲线进行比对
    符号相同的占所有和的比例即为趋势变化敏感速度值,注意如果没有在相同周期内与参数曲线进行比对的曲线,本速度值即无意义
    所对应的趋势变化敏感速度数值, 以及相关性＊敏感度＝敏感度置信度
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        window = kwargs['window']
        trend = (frame.rolling(window=window).mean()).diff()
        trend.dropna(inplace=True)
        trend_signal = pd.Series(np.where(trend > 0, 1, -1))
        trend_speed = trend_signal * trend_signal.shift(-1)
        speed = trend_speed[trend_speed == 1].sum() / len(trend_speed)
        return speed


class MassIndex(BaseFeature):
    """
    质量指标计算公式
    sum((最高价 - 最低价)的9日指数移动平均 / (最高价 - 最低价)的9日指数移动平均的9日指数移动平均)
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        high_low = frame['high'] - frame['low']
        ema_1 = np.array(ema.compute(high_low, kwargs))
        kwargs.update({'recursion': 2})
        ema_2 = np.array(ema.compute(high_low, kwargs))
        mass = ema_1[-len(ema_2):] - ema_2
        return mass

    def compute(self, feed, kwargs):
        frame = feed.copy()
        mass_index = self._calc_feature(frame, kwargs)
        return mass_index


class Dpo(BaseFeature):
    """
        非趋势价格摆动指标 --- 收盘价减去 (n / 2) +1的平均移动平均数具有将DPO后移(n / 2) + 1的效果
    """
    def _calc_feature(self, feed, kwargs):
        window = int(kwargs['window']/2) + 1
        moving = ma.compute(feed, {'window': window})
        dpo_window = feed[-len(moving):] - moving
        return dpo_window


class RVI(BaseFeature):
    """
        相对活力指标,衡量活跃度 --- 度量收盘价处于的位置
        代表当前技术线值在当前的位置,非停盘 (self.close - self.low) / (self.high - self.low)
    """
    def _calc_feature(self, frame, kwargs):
        rvi = (frame['close'] - frame['low'])/(frame['high'] - frame['low'])
        return rvi

    def compute(self, feed, kwargs):
        frame = feed.copy()
        rvi = self._calc_feature(frame, kwargs)
        return rvi


class RI(BaseFeature):
    """期间之间曲线(收盘价之间变化) 与平均期的期间内区域(最高价与最低价)比值 判断先行趋势是否结束结束"""
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        window = kwargs['window']
        close_pct = frame['close'] / frame['close'].shift(window)
        high_windowed = frame['high'].rolling(window=window).max()
        low_windowed = frame['low'].rolling(window=window).min()
        ri_windowed = close_pct / (high_windowed - low_windowed)
        return ri_windowed

    def compute(self, feed, kwargs):
        frame = feed.copy()
        ri = self._calc_feature(frame, kwargs)
        return ri


class Stochastic(BaseFeature):
    """
        stochastic momentum index 随意摆动指收盘价相对于近期的最高价 / 最低价区间的位置进行两次EMA平滑
    """
    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        rolling_high = frame['high'].rolling(window=window).max()
        rolling_low = frame['low'].rolling(window=window).min()
        stochastic = (frame['close'] - rolling_low) / rolling_high
        return stochastic

    def compute(self, feed, kwargs):
        frame = feed.copy()
        stochastic_momentum = self._calc_feature(frame, kwargs)
        return stochastic_momentum


class SMI(BaseFeature):
    """
        stochastic momentum index 随意摆动指收盘价相对于近期的最高价 / 最低价区间的位置进行两次EMA平滑
    """
    def _calc_feature(self, feed, kwargs):
        smi = Stochastic().compute(feed, kwargs)
        kwargs.update({'recursion': 2})
        smi_ema = ema.compute(smi, kwargs)
        return smi_ema

    def compute(self, feed, kwargs):
        frame = feed.copy()
        smi = self._calc_feature(frame, kwargs)
        return smi


class RPower(BaseFeature):
    """
        动量指标度量证券价格变化
        收盘价 / n期前收盘价
        动能指标计算:1、价格涨,动能为+1,价格跌,动能为-1;2、价格与成交量的变动乘积作为动能
        (score ** 2) *delta_vol
    """
    def _calc_feature(self, feed, kwargs):
        frame = feed.copy()
        rvi = RVI().compute(feed, kwargs)
        delta_vol = frame['volume'].diff()
        momentum = (rvi ** 2) * delta_vol
        return momentum

    def compute(self, feed, kwargs):
        frame = feed.copy()
        rpower = self._calc_feature(frame, kwargs)
        return rpower


class DPower(BaseFeature):
    """
        动量策略 --- 基于价格、成交量等指标量化动能定义,同时分析动能 ;属于趋势范畴 -- 惯性特质 ,不适用于反弹
        逻辑:
        1、价格 --- 收盘价、最高价,与昨天相比判断方向,交集
        2、成交量 --- 与昨天成交量比值
        3、1与2结果相乘极为动量
        4、计算累计动量值
    """
    def _calc_feature(self, frame, kwargs):
        delta = frame['volume'] / frame['volume'].shift(1)
        delta.fillna(0, inplace=True)
        direction = (frame['close'] > frame['close'].shift(1)) & (frame['high'] > frame['high'].shift(1))
        sign = direction.apply(lambda x: 1 if x else -1)
        momentum = (sign * delta).cumsum()
        return momentum

    def compute(self, feed, kwargs):
        frame = feed.copy()
        dpower = self._calc_feature(frame, kwargs)
        return dpower


class MFI(BaseFeature):
    """
        price = (最高价 + 最低价 + 收盘价) / 3  ; 货币流量 = price * 成交量  ; 货币比率 = 正的货币流量 / 负的货币流量
        货币流量指标 = 100(1 - 1 /(1 + 货币比率))
        如果price大于preprice 正流入 ,否则为流出
    """
    def _calc_feature(self, frame, kwargs):
        avg = frame.loc[:, ['high', 'low', 'close']].mean(axis=1)
        signal = avg > avg.shift(1)
        positive = avg[signal] * frame['volume'][signal]
        negative = avg[~signal] * frame['volume'][~signal]
        ratio = positive.sum() / negative.sum()
        mfi = 100 * (1 - 1 / (1 + ratio))
        return mfi

    def compute(self, feed, kwargs):
        frame = feed.copy()
        mfi = self._calc_feature(frame, kwargs)
        return mfi


class VHF(BaseFeature):
    """
         vertical horizonal filter 判断处于趋势阶段还是盘整阶段hcp: n期内最高收盘价lcp: n期内最低收盘价分子hcp - lcp,
        分母:n期内的收盘价变动绝对值之和
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        window = kwargs['window']
        vertical = frame.rolling(window=window).max() - frame.rolling(window=window).min()
        pct = abs(frame - frame.shift(1))
        horizonal = pct.rolling(window=window).sum()
        vhf_window = vertical / horizonal
        return vhf_window


class VCK(BaseFeature):
    """
            蔡金: 波动性增加表示底部临近,而波动性降低表示顶部临近
        hl平均值 = (high - low)的指数移动平均
        蔡金波动率 = ( hl平均值 - n期前的hl平均值 ) / n期前的hl平均值
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        hl = frame['high'] - frame['low']
        ema_1 = np.array(ema.compute(hl, kwargs))
        window = kwargs['window']
        vck = ema_1[window:] / ema_1[:len(ema_1) - window] - 1
        return vck

    def compute(self, feed, kwargs):
        frame = feed.copy()
        vck = self._calc_feature(frame, kwargs)
        return vck


class Rsi(BaseFeature):
    """
        RSI(相对强弱指数)是通过比较一段时期内的平均收盘涨数和平均收盘跌数来分析市场买沽盘的意向和实力
        1. 根据收盘价格计算价格变动
        2.
        分别筛选gain交易日的价格变动序列gain,和loss交易日的价格变动序列loss
        3.
        分别计算gain和loss的N日移动平均
    """
    @staticmethod
    def _calculate(data):
        dif = np.diff(data, axis=0)
        ups = np.nanmean(np.clip(dif, 0, np.inf), axis=0)
        downs = abs(np.nanmean(np.clip(dif, -np.inf, 0), axis=0))
        # eval (expression, globals , locals)
        return eval(
            "100 - (100 / (1 + (ups / downs)))",
            {}, {'ups': ups, 'downs': downs}
           )

    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        rsi = frame.rolling(window).apply(self._calculate)
        return rsi


class Aroon(BaseFeature):
    """
        阿隆指标价格达到近期最高价和最低价以来经过的期间数预测证券价格从趋势性到交易性区域
        阿隆上升线: (n - (n + 1 到达最高价的期间数) ) / n;
        而阿隆下降线: (n - (n + 1 到达最低价的期间数)) / n 平行、交叉穿行
    """
    @staticmethod
    def _calculate(data):
        # reset
        data.index = range(len(data))
        max_point = data.index[data.idxmax()]
        min_point = data.index[data.idxmin()]
        try:
            rate = (len(data) - max_point) / (max_point - min_point)
        except ZeroDivisionError:
            rate = None
        return rate

    def _calc_feature(self, frame, kwargs):
        aroon = frame.rolling(kwargs['window']).apply(self._calculate)
        return aroon


class WAD(BaseFeature):
    """
        威廉姆斯累积 / 派发指标 A / D 指标累积
        TRH = max(preclose, high)  TRL = min(preclose, min) 如果收盘价大于昨日收盘价: A / D = close - TRL
        如果收盘价小于昨日收盘价:A / D = close - TRH
        通过计算平滑移动避免个别极值影响
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        window = kwargs['window']
        frame['pre_close'] = frame['close'].shift(1)
        trh = frame['close'] - frame.loc[:, ['pre_close', 'high']].max(axis=1)
        trl = frame['close'] - frame.loc[:, ['pre_close', 'low']].min(axis=1)
        wad = frame['close'].diff()
        wad[wad > 0] = trh
        wad[wad < 0] = trl
        wad_windowed = wad.rolling(window=window).mean()
        return wad_windowed

    def compute(self, feed, kwargs):
        frame = feed.copy()
        wad = self._calc_feature(frame, kwargs)
        return wad


class WR(BaseFeature):
    """
    威廉姆斯 % R:预期价格反转的力量在证券价格达到顶峰的时候转为下跌的时候,提前下跌了;在达到谷底之后转为上涨,并且维持一段时间
    公式:- 100 * (n期内最高价 - 当期收盘价) / (n期最高价 - n期内最低价)
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        window = kwargs['window']
        rolling_max = frame.rolling(window=window).max()
        rolling_min = frame.rolling(window=window).min()
        wr = -100 * (rolling_max - frame) / (rolling_max - rolling_min)
        return wr


class SO(BaseFeature):
    """
        随机:共同分布的随机变量的无穷过程。随意摆动指标:收盘价相对于给定时间内价格区间的位置
        公式(今天收盘价 - % K期间内最低价) / ( % K最高价 - % K最低价)
        指定 % K进行处理(MA、EMA、变动移动平均、三角移动等等)
    """
    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        so = (frame['close'] - frame['low'].rolling(window=window).min()) / \
              (frame['high'].rolling(window=window).max() - frame['low'].rolling(window=window).min())
        return so

    def compute(self, feed, kwargs):
        frame = feed.copy()
        so = self._calc_feature(frame, kwargs)
        return so


class ADX(BaseFeature):
    """
        N: = 14; REF代表过去, 用法是: REF(X, A), 引用A周期前的X值例如: REF(CLOSE, 1)
        TR1: = SMA(TR, N, 1);
        HD: = HIGH - REF(HIGH, 1);
        LD: = REF(LOW, 1) - LOW;
        DMP: = SMA(IF(HD > 0 AND HD > LD, HD, 0), N, 1);
        DMM: = SMA(IF(LD > 0 AND LD > HD, LD, 0), N, 1);
        PDI: DMP * 100 / TR1;
        MDI: DMM * 100 / TR1;
        ADX: SMA(ABS(MDI - PDI) / (MDI + PDI) * 100, N, 1)
    """
    @staticmethod
    def _calc(frame, kwargs):
        dmp = frame['high'] - frame['high'].shift(1)
        dmm = frame['low'].shift(1) - frame['low']
        dmp_sign = (dmp > 0) & (dmp > dmm)
        dmm_sign = (dmm > 0) & (dmp < dmm)
        dmp[~dmp_sign] = 0
        dmm[~dmm_sign] = 0
        pdi = np.array(sma._calc_feature(dmp, kwargs))
        mdi = np.array(sma._calc_feature(dmm, kwargs))
        return pdi, mdi

    def _calc_feature(self, frame, kwargs):
        pdi, mdi = self._calc(frame, kwargs)
        out = 100 * (mdi - pdi)/(mdi + pdi)
        adx = sma._calc_feature(out, kwargs)
        return adx

    def compute(self,feed, kwargs):
        frame = feed.copy()
        adx = self._calc_feature(frame, kwargs)
        return adx


class TRIX(BaseFeature):
    """
        1. TR=收盘价的N日指数移动平均;
        2.TRIX=(TR-昨日TR)/昨日TR*100;
    """
    @classmethod
    def _calc_feature(cls, feed, kwargs):
        ema_windowed = np.array(ema.compute(feed, kwargs))
        trix_windowed = 100 * (ema_windowed[1:] / ema_windowed[:-1] - 1)
        return trix_windowed


class PVT(ExponentialMovingAverage):
    """
        价量趋势指标,累积成交量: pvi(t) = pvi(t - 1) + (收盘价 - 前期收盘价) / 前期收盘价 * pvi
        pvi为初始交易量
    """

    @staticmethod
    def _calc(frame, kwargs):
        rates = frame['close'] / frame['close'].shift(1) - 1
        return rates

    def _calc_feature(self, frame, kwargs):
        ratio = self._calc(frame, kwargs)
        ratio = ratio.fillna(1.0)
        delta = ratio * frame['volume']
        pvt = delta.cumsum()
        return pvt

    def compute(self, feed, kwargs):
        frame = feed.copy()
        pvt = self._calc_feature(frame, kwargs)
        return pvt


class KDJ(BaseFeature):
    """
        反映价格走势的强弱和超买超卖现象。主要理论依据是:当价格上涨时,收市价倾向于接近当日价格区间的
        上端;相反,在下降趋势中收市价趋向于接近当日价格区间的下端
        % K的方程式: % K = 100 * (CLOSE - LOW( % K)) / (HIGH( % K) - LOW( % K))
        注释:
        CLOSE — 当天的收盘价格
        LOW( % K) — % K的最低值
        HIGH( % K) — % K的最高值
        根据公式,我们可以计算出 % D的移动平均线:
        % D = SMA( % K, N)
    """
    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        k = (frame['close'] - frame['low'].rolling(window=window).min()) /\
            (frame['high'].rolling(window=window).max() - frame['low'].rolling(window=window).min())
        kdj = k.rolling(window=window).mean()
        return kdj

    def compute(self, feed, kwargs):
        frame = feed.copy()
        kdj = self._calc_feature(frame, kwargs)
        return kdj


class CurveScorer(BaseFeature):
    """
        intergrate under curve
        input : array or series
        output : float --- area under curve
        logic : if the triangle area exceed curve area means positive
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        _normalize = zoom(frame)
        width = len(_normalize)
        area = np.trapz(np.array(_normalize), np.array(range(1, width + 1)))
        ratio = area / width
        return ratio


# dual window
class RAVI(BaseFeature):
    """
        区间运动辨识指数(RAVI)7日的SMA与65 天的SMA之差占65天的SMA绝对值,一般来讲,RAVI被限制在3 % 以下,市场做区间运动
    """

    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        assert isinstance(window, (tuple, list)), 'two different windows needed'
        short = np.array(sma.compute(frame, {'window': min(window)}))
        long = np.array(sma.compute(frame, {'window': max(window)}))
        ravi_windowed = (short[-len(long):] - long) / long
        return ravi_windowed


class DMI(BaseFeature):
    """
    DMI中的时间区间变化受到价格波动的控制,在平稳的市场较多的时间区间数,在活跃的市场采取较少的时间区间数
    时间区间数 = 14 / 波动性指标 波动性指标 = 收盘价5日标准差除以收盘价5日标准差10日移动平均数
    """
    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        std = frame.rolling(window=min(window)).std()
        std_ma = std.rolling(window=max(window)).mean()
        dmi = std / std_ma
        return dmi


class DMA(BaseFeature):
    """
        DMA: 收盘价的短期平均与长期平均的差得DMA;DMA的M日平均为AMA;
        DMA与AMA比较判断交易方向,参数:12、50、14
    """

    @classmethod
    def _calc_feature(cls, frame, kwargs):
        window = kwargs['window']
        short = ma.compute(frame, {'window': min(window)})
        long = ma.compute(frame, {'window': max(window)})
        dma_windowed = short[-len(long):] - long
        return dma_windowed


class VO(BaseFeature):
    """
    成交量提供给定价格运动的交易密集程度,高成交量水平是顶部特征,在底部之前也会因为恐慌而放大
    VO(volume oscillator)  vol的短期移动平均值与长期移动平均值之差的比率
    """
    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        short = ma.compute(frame, {'window': min(window)})
        long = ma.compute(frame, {'window': max(window)})
        vo = short / long
        return vo


class MAO(BaseFeature):
    """
        MA oscillator 价格摆动, 短期MA / 长期MA的百分比
    """

    @classmethod
    def _calc_feature(cls, frame, kwargs):
        window = kwargs['window']
        ma_short = ma.compute(frame, {'window': min(window)})
        ma_long = ma.compute(frame, {'window': max(window)})
        mao = ma_short / ma_long
        return mao


class KVO(BaseFeature):
    """
        成交量动力 = V * abs(2 * DM / CM  - 1 ) *T * 100
        V为成交量,DM每日度量值(最高价减去最低价) CM(DM的累积度量值),
        T趋势(high low close 的均值与前一天的均值比较大于为1 ,否则 - 1)
        KVO : 成交量动力的34指数移动平均线减去55的指数移动平均线
    """
    @staticmethod
    def _calc(frame):
        frame.loc[:, 'strat'] = -1
        print('frame', frame)
        dm = frame['high'] - frame['low']
        cm = dm.cumsum()
        print('cm', cm)
        avg = frame.loc[:, ['high', 'low', 'close']].mean(axis=1)
        frame.loc[avg > avg.shift(1), 'strat'] = 1
        print('frame - strat', frame)
        vo = frame['volume'] * abs(2 * dm / cm - 1) * frame['strat'] * 100
        print('vo', vo)
        return vo

    def _calc_feature(self, feed, kwargs):
        window = kwargs['window']
        vo = self._calc(feed)
        short = np.array(ema.compute(vo, {'window': min(window)}))
        long = np.array(ema.compute(vo, {'window': max(window)}))
        kvo = short[-len(long):] - long
        return kvo

    def compute(self, feed, kwargs):
        frame = feed.copy()
        kvo = self._calc_feature(frame, kwargs)
        return kvo


class Macd(BaseFeature):
    """
    Moving Average Convergence/Divergence (MACD) Signal line
    https://en.wikipedia.org/wiki/MACD

    A technical indicator originally developed by Gerald Appel in the late
    1970's. MACD shows the relationship between two moving averages and
    reveals changes in the strength, direction, momentum, and duration of a
    trend in a stock's price.

    **Default Inputs:** :data:`zipline.pipe.data.EquityPricing.close`

    Parameters
    ----------
    fast_period : int > 0, optional
        The window length for the "fast" EWMA. Default is 12.
    slow_period : int > 0, > fast_period, optional
        The window length for the "slow" EWMA. Default is 26.
    signal_period : int > 0, < fast_period, optional
        The window length for the strat line. Default is 9.

    DIF : MACD称为指数平滑异动移动平均线,是从双指数移动平均线发展而来的,由快的加权移动均线(EMA12)减去慢的加权移动均线(EMA26)
    DEA : DIF - (快线 - 慢线的9日加权移动均线DEA(时间远的赋予小权重,进的赋予大权重))得到MACD柱
    MACD --- 即由快、慢均线的离散、聚合表征当前的多空状态和股价可能的发展变化趋势,
             MACD从负数转向正数,是买的信号。当MACD从正数转向负数,是卖的信号
             MACD以大角度变化,表示快的移动平均线和慢的移动平均线的差距非常迅速的拉开表示转变
    """
    @classmethod
    def _calc_feature(cls, frame, kwargs):
        slow_ema = np.array(ema.compute(frame, {'window': kwargs['slow']}))
        fast_ema = np.array(ema.compute(frame, {'window': kwargs['fast']}))
        dif = fast_ema[-len(slow_ema):] - slow_ema
        dea = ema.compute(dif, {'window': kwargs['period']})
        macd = dif[-len(dea):] - dea
        return macd


# transform ema
class AMA(ExponentialMovingAverage):
    """
        指数平滑公式:EMA(i) = Price(i) * SC + EMA(i - 1) * (1 - SC),SC = 2 / (n + 1) ― EMA平滑常数
        对于快速市场平滑比必须是关于EMA的2周期(fast SC = 2 / (2 + 1) = 0.6667), 而无趋势EMA周期必须等于30(
        slow SC = 2 / (30 + 1) = 0.06452)
        新的变化中的平滑常量为SSC(成比例的平滑常量):
        SSC(i) = (ER(i) * (fast SC - slow SC) + slow SC
        AMA(i) = AMA(i - 1) * (1 - SSC(i) ^ 2) + Price(i) * (SSC(i) ^ 2)
    """

    @staticmethod
    def _calculate_weights(frame, kwargs):
        er_windowed = ER().compute(frame, kwargs)
        print('er', er_windowed)
        fast_sc = 2 / (kwargs['fast'] + 1)
        slow_sc = 2 / (kwargs['slow'] + 1)
        ssc = er_windowed * (fast_sc - slow_sc) + slow_sc
        print('ssc', ssc)
        return ssc

    def _calc_feature(self, frame, kwargs):
        exponential_weights = self._calculate_weights(frame, kwargs)
        print('exponential_weights', exponential_weights)
        window = kwargs['window']
        array = np.array(frame)
        out = [np.average(array[loc: loc+window:], axis=0,  weights=self._reformat_wgt(exponential_weights[loc: loc + window]))
               for loc in range(window, len(array) - window)]
        return out


class VEMA(ExponentialMovingAverage):
    """
        变量移动平均线基于数据系列的波动性而调整百分比的指数移动平均线
        (SM * VR) *收盘价 + (1 - SM * VR) * (昨天)MA
        SM = 2 / (n + 1);
        VR可以采用钱德勒摆动指标绝对值 / 100
    """

    @staticmethod
    def _calculate_weights(frame, window):
        rolling_std = frame.rolling(window=window).std()
        rates = rolling_std * 2 / (window + 1)
        rates = rates * 2 / (window + 1)
        return rates

    def _calc_feature(self, frame, kwargs):
        window = kwargs['window']
        exponential_weights = self._calculate_weights(frame, window)
        print('exponential_weights', exponential_weights)
        array = np.array(frame)
        out = [np.average(array[loc: loc+window], axis=0, weights=self._reformat_wgt(exponential_weights[loc: loc + window]))
               for loc in range(window, len(array) - window)]
        return out


class Vidya(ExponentialMovingAverage):
    """
        变量指数动态平均线技术指标(VIDYA): 计算平均周期动态变化的指数移动平均线(EMA)
        平均周期取决于市场波动情况;振荡器(CMO) /100
        CMO值用作平滑因素EMA比率
    """
    @staticmethod
    def _calculate_weights(frame, kwargs):
        cmo = CMO().compute(frame, kwargs)
        vidya_ratio = cmo * 2 / (kwargs['window'] + 1)
        return vidya_ratio

    def _calc_feature(self, frame, kwargs):
        exponential_weights = self._calculate_weights(frame, kwargs)
        print('exponential_weights', exponential_weights)
        array = np.array(frame)
        window = kwargs['window']
        out = [np.average(array[loc: loc+window], axis=0,  weights=self._reformat_wgt(exponential_weights[loc: loc + window]))
               for loc in range(window, len(array))]
        return out



# """
# Technical Analysis Factors
# --------------------------
# """
# from __future__ import division

# from numpy import (
#     abs,
#     average,
#     clip,
#     diff,
#     dstack,
#     inf,
# )
# from numexpr import evaluate

# # from zipline.pipeline.data import EquityPricing
# # from zipline.pipeline.factors import CustomFactor
# # from zipline.pipeline.mixins import SingleInputMixin
# # from zipline.utils.input_validation import expect_bounded
# # from zipline.utils.math_utils import (
# #     nanargmax,
# #     nanargmin,
# #     nanmax,
# #     nanmean,
# #     nanstd,
# #     nanmin,
# # )
# # from zipline.utils.numpy_utils import rolling_window

# # from ..pipeline.factors.basic import exponential_weights
# # from ..pipeline.factors.basic import (  # noqa reexport
# #     # These are re-exported here for backwards compatibility with the old
# #     # definition site.
# #     LinearWeightedMovingAverage,
# #     MaxDrawdown,
# #     SimpleMovingAverage,
# #     VWAP,
# #     WeightedAverageValue
# # )


# class RSI(SingleInputMixin, CustomFactor):
#     """
#     Relative Strength Index

#     **Default Inputs**: :data:`zipline.pipeline.data.EquityPricing.close`

#     **Default Window Length**: 15
#     """
#     window_length = 15
#     inputs = (EquityPricing.close,)
#     window_safe = True

#     def compute(self, today, assets, out, closes):
#         diffs = diff(closes, axis=0)
#         ups = nanmean(clip(diffs, 0, inf), axis=0)
#         downs = abs(nanmean(clip(diffs, -inf, 0), axis=0))
#         return evaluate(
#             "100 - (100 / (1 + (ups / downs)))",
#             local_dict={'ups': ups, 'downs': downs},
#             global_dict={},
#             out=out,
#         )


# class BollingerBands(CustomFactor):
#     """
#     Bollinger Bands technical indicator.
#     https://en.wikipedia.org/wiki/Bollinger_Bands

#     **Default Inputs:** :data:`zipline.pipeline.data.EquityPricing.close`

#     Parameters
#     ----------
#     inputs : length-1 iterable[BoundColumn]
#         The expression over which to compute bollinger bands.
#     window_length : int > 0
#         Length of the lookback window over which to compute the bollinger
#         bands.
#     k : float
#         The number of standard deviations to add or subtract to create the
#         upper and lower bands.
#     """
#     params = ('k',)
#     inputs = (EquityPricing.close,)
#     outputs = 'lower', 'middle', 'upper'

#     def compute(self, today, assets, out, close, k):
#         difference = k * nanstd(close, axis=0)
#         out.middle = middle = nanmean(close, axis=0)
#         out.upper = middle + difference
#         out.lower = middle - difference


# class Aroon(CustomFactor):
#     """
#     Aroon technical indicator.
#     https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/aroon-indicator

#     **Defaults Inputs:** :data:`zipline.pipeline.data.EquityPricing.low`, \
#                          :data:`zipline.pipeline.data.EquityPricing.high`

#     Parameters
#     ----------
#     window_length : int > 0
#         Length of the lookback window over which to compute the Aroon
#         indicator.
#     """ # noqa

#     inputs = (EquityPricing.low, EquityPricing.high)
#     outputs = ('down', 'up')

#     def compute(self, today, assets, out, lows, highs):
#         wl = self.window_length
#         high_date_index = nanargmax(highs, axis=0)
#         low_date_index = nanargmin(lows, axis=0)
#         evaluate(
#             '(100 * high_date_index) / (wl - 1)',
#             local_dict={
#                 'high_date_index': high_date_index,
#                 'wl': wl,
#             },
#             out=out.up,
#         )
#         evaluate(
#             '(100 * low_date_index) / (wl - 1)',
#             local_dict={
#                 'low_date_index': low_date_index,
#                 'wl': wl,
#             },
#             out=out.down,
#         )


# class FastStochasticOscillator(CustomFactor):
#     """
#     Fast Stochastic Oscillator Indicator [%K, Momentum Indicator]
#     https://wiki.timetotrade.eu/Stochastic

#     This stochastic is considered volatile, and varies a lot when used in
#     market analysis. It is recommended to use the slow stochastic oscillator
#     or a moving average of the %K [%D].

#     **Default Inputs:** :data:`zipline.pipeline.data.EquityPricing.close`, \
#                         :data:`zipline.pipeline.data.EquityPricing.low`, \
#                         :data:`zipline.pipeline.data.EquityPricing.high`

#     **Default Window Length:** 14

#     Returns
#     -------
#     out: %K oscillator
#     """
#     inputs = (EquityPricing.close, EquityPricing.low, EquityPricing.high)
#     window_safe = True
#     window_length = 14

#     def compute(self, today, assets, out, closes, lows, highs):

#         highest_highs = nanmax(highs, axis=0)
#         lowest_lows = nanmin(lows, axis=0)
#         today_closes = closes[-1]

#         evaluate(
#             '((tc - ll) / (hh - ll)) * 100',
#             local_dict={
#                 'tc': today_closes,
#                 'll': lowest_lows,
#                 'hh': highest_highs,
#             },
#             global_dict={},
#             out=out,
#         )


# class IchimokuKinkoHyo(CustomFactor):
#     """Compute the various metrics for the Ichimoku Kinko Hyo (Ichimoku Cloud).
#     http://stockcharts.com/school/doku.php?id=chart_school:technical_indicators:ichimoku_cloud

#     **Default Inputs:** :data:`zipline.pipeline.data.EquityPricing.high`, \
#                         :data:`zipline.pipeline.data.EquityPricing.low`, \
#                         :data:`zipline.pipeline.data.EquityPricing.close`

#     **Default Window Length:** 52

#     Parameters
#     ----------
#     window_length : int > 0
#         The length the the window for the senkou span b.
#     tenkan_sen_length : int >= 0, <= window_length
#         The length of the window for the tenkan-sen.
#     kijun_sen_length : int >= 0, <= window_length
#         The length of the window for the kijou-sen.
#     chikou_span_length : int >= 0, <= window_length
#         The lag for the chikou span.
#     """ # noqa

#     params = {
#         'tenkan_sen_length': 9,
#         'kijun_sen_length': 26,
#         'chikou_span_length': 26,
#     }
#     inputs = (EquityPricing.high, EquityPricing.low, EquityPricing.close)
#     outputs = (
#         'tenkan_sen',
#         'kijun_sen',
#         'senkou_span_a',
#         'senkou_span_b',
#         'chikou_span',
#     )
#     window_length = 52

#     def _validate(self):
#         super(IchimokuKinkoHyo, self)._validate()
#         for k, v in self.params.items():
#             if v > self.window_length:
#                 raise ValueError(
#                     '%s must be <= the window_length: %s > %s' % (
#                         k, v, self.window_length,
#                     ),
#                 )

#     def compute(self,
#                 today,
#                 assets,
#                 out,
#                 high,
#                 low,
#                 close,
#                 tenkan_sen_length,
#                 kijun_sen_length,
#                 chikou_span_length):

#         out.tenkan_sen = tenkan_sen = (
#             high[-tenkan_sen_length:].max(axis=0) +
#             low[-tenkan_sen_length:].min(axis=0)
#         ) / 2
#         out.kijun_sen = kijun_sen = (
#             high[-kijun_sen_length:].max(axis=0) +
#             low[-kijun_sen_length:].min(axis=0)
#         ) / 2
#         out.senkou_span_a = (tenkan_sen + kijun_sen) / 2
#         out.senkou_span_b = (high.max(axis=0) + low.min(axis=0)) / 2
#         out.chikou_span = close[chikou_span_length]


# class RateOfChangePercentage(CustomFactor):
#     """
#     Rate of change Percentage
#     ROC measures the percentage change in price from one period to the next.
#     The ROC calculation compares the current price with the price `n`
#     periods ago.
#     Formula for calculation: ((price - prevPrice) / prevPrice) * 100
#     price - the current price
#     prevPrice - the price n days ago, equals window length
#     """
#     def compute(self, today, assets, out, close):
#         today_close = close[-1]
#         prev_close = close[0]
#         evaluate('((tc - pc) / pc) * 100',
#                  local_dict={
#                      'tc': today_close,
#                      'pc': prev_close
#                  },
#                  global_dict={},
#                  out=out,
#                  )


# class TrueRange(CustomFactor):
#     """
#     True Range

#     A technical indicator originally developed by J. Welles Wilder, Jr.
#     Indicates the true degree of daily price change in an underlying.

#     **Default Inputs:** :data:`zipline.pipeline.data.EquityPricing.high`, \
#                         :data:`zipline.pipeline.data.EquityPricing.low`, \
#                         :data:`zipline.pipeline.data.EquityPricing.close`

#     **Default Window Length:** 2
#     """
#     inputs = (
#         EquityPricing.high,
#         EquityPricing.low,
#         EquityPricing.close,
#     )
#     window_length = 2

#     def compute(self, today, assets, out, highs, lows, closes):
#         high_to_low = highs[1:] - lows[1:]
#         high_to_prev_close = abs(highs[1:] - closes[:-1])
#         low_to_prev_close = abs(lows[1:] - closes[:-1])
#         out[:] = nanmax(
#             dstack((
#                 high_to_low,
#                 high_to_prev_close,
#                 low_to_prev_close,
#             )),
#             2
#         )


# class MovingAverageConvergenceDivergenceSignal(CustomFactor):
#     """
#     Moving Average Convergence/Divergence (MACD) Signal line
#     https://en.wikipedia.org/wiki/MACD

#     A technical indicator originally developed by Gerald Appel in the late
#     1970's. MACD shows the relationship between two moving averages and
#     reveals changes in the strength, direction, momentum, and duration of a
#     trend in a stock's price.

#     **Default Inputs:** :data:`zipline.pipeline.data.EquityPricing.close`

#     Parameters
#     ----------
#     fast_period : int > 0, optional
#         The window length for the "fast" EWMA. Default is 12.
#     slow_period : int > 0, > fast_period, optional
#         The window length for the "slow" EWMA. Default is 26.
#     signal_period : int > 0, < fast_period, optional
#         The window length for the signal line. Default is 9.

#     Notes
#     -----
#     Unlike most pipeline expressions, this factor does not accept a
#     ``window_length`` parameter. ``window_length`` is inferred from
#     ``slow_period`` and ``signal_period``.
#     """
#     inputs = (EquityPricing.close,)
#     # We don't use the default form of `params` here because we want to
#     # dynamically calculate `window_length` from the period lengths in our
#     # __new__.
#     params = ('fast_period', 'slow_period', 'signal_period')

#     @expect_bounded(
#         __funcname='MACDSignal',
#         fast_period=(1, None),  # These must all be >= 1.
#         slow_period=(1, None),
#         signal_period=(1, None),
#     )
#     def __new__(cls,
#                 fast_period=12,
#                 slow_period=26,
#                 signal_period=9,
#                 *args,
#                 **kwargs):

#         if slow_period <= fast_period:
#             raise ValueError(
#                 "'slow_period' must be greater than 'fast_period', but got\n"
#                 "slow_period={slow}, fast_period={fast}".format(
#                     slow=slow_period,
#                     fast=fast_period,
#                 )
#             )

#         return super(MovingAverageConvergenceDivergenceSignal, cls).__new__(
#             cls,
#             fast_period=fast_period,
#             slow_period=slow_period,
#             signal_period=signal_period,
#             window_length=slow_period + signal_period - 1,
#             *args, **kwargs
#         )

#     def _ewma(self, data, length):
#         decay_rate = 1.0 - (2.0 / (1.0 + length))
#         return average(
#             data,
#             axis=1,
#             weights=exponential_weights(length, decay_rate)
#         )

#     def compute(self, today, assets, out, close, fast_period, slow_period,
#                 signal_period):
#         slow_EWMA = self._ewma(
#             rolling_window(close, slow_period),
#             slow_period
#         )
#         fast_EWMA = self._ewma(
#             rolling_window(close, fast_period)[-signal_period:],
#             fast_period
#         )
#         macd = fast_EWMA - slow_EWMA
#         out[:] = self._ewma(macd.T, signal_period)


# # Convenience aliases.
# MACDSignal = MovingAverageConvergenceDivergenceSignal
