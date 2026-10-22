# cython: boundscheck=False
# cython: wraparound=False
# distutils: language = c++

from bt_core.tradingcal import trading_days_between

from bt_core.utils.dateintern cimport ts2intdt

cdef const int64_t CYB_CKPT = 1598232600
cdef const int64_t MAIN_ST_10PCT_CKPT = 1783296000  # 2026-07-06 主板 ST Pct 10%


cdef class Asset:
    """
        前5个交易日,科创板还设置了临时停牌制度, 当盘中股价较开盘价上涨或下跌幅度首次达到30%、60%时，都分别进行一次临时停牌
        单次盘中临时停牌的持续时间为10分钟。每个交易日单涨跌方向只能触发两次临时停牌, 最多可以触发四次共计40分钟临时停牌。
        如果跨越14:57则复盘, 之后交易日20%
        科创板盘后固定价格交易 15:00 --- 15:30
        若收盘价高于买入申报指令，则申报无效；若收盘价低于卖出申报指令同样无效

        A股主板, 中小板首日涨幅最大为44%而后10%波动，针对不存在价格笼子（科创板，创业板后期对照科创板改革）
        科创板在连续竞价机制 ---买入价格不能超过基准价格(卖一的102%, 卖出价格不得低于买入价格98%)
        设立市价委托必须设立最高价以及最低价
        科创板盘后固定价格交易 --- 以后15:00收盘价格进行交易 --- 15:00 -- 15:30 时间优先原则，逐步撮合成交

        沪深主板单笔申报不超过100万股, 创业板单笔限价30万股;市价不超过15万股;定价申报100万股
        科创板单笔申报10万股;市价5万股;定价100万股
        风险警示板单笔买入申报50万股; 单笔卖出申报100万股, 退市整理期100万股
        科创板（竞价机制要求）---买入价格不能超过基准价格 卖一的102%,卖出价格不得低于买入价格98%

        科创板 --- 申报最小200股, 递增可以以1股为单位 | 卖出不足200股一次性卖出
        创业板 --- 申报100 倍数 | 卖出不足100, 全部卖出

        2020年8月24日 创业板ST由5% 变为 20%
        20260706 主板 ST 股涨跌幅调整为 10% / 盘后固定价格交易覆盖全A --- 15:05 至 15:30 /基金收盘 14:57- 15:00 集合竞价
    """
    def __init__(self,
                bytes sid,
                bytes name,
                int32_t first_trading,
                int32_t delist,
                bytes merger,
                float merge_ratio
                ):
        self.sid = sid
        self.core.name = name
        self.core.first_trading = first_trading
        self.core.delist = delist
        self.core.merger = merger
        self.core.merge_ratio = merge_ratio

        if sid.startswith(b"68"):
            self.core.board = 2
            self.core.tick_size = 200
            self.core.increment = False
        elif sid.startswith(b"3"):
            self.core.board = 1
            self.core.tick_size = 100
            self.core.increment = True
        elif sid.startswith(b"4") or sid.startswith(b"8") or sid.startswith(b"92"):
            self.core.board = 3
            self.core.tick_size = 100
            self.core.increment = True
        else:
            self.core.board = 0  # 60 / 0
            self.core.tick_size = 100
            self.core.increment = True

    cdef double restricted(self, int64_t ts) noexcept:
        """
            涨跌幅限制:
            - 科创板(688)/创业板(3)/注册制主板(>=20230410): 上市前5个**交易日**无涨跌幅限制
            - 北交所(4/8/92): 上市首日无涨跌幅限制, 次日起 30%
            - 核准制主板新股(20140101..20230409): 上市首日 44%
            - 主板及旧制创业板 ST/*ST: 5%
            - 主板(60/00): 10%, 科创/创业(2020-08-24后): 20%
        """
        cdef int32_t ipo_days = -1
        cdef int32_t current_ymd

        if self.core.first_trading > 0:
            current_ymd = ts2intdt(<double>ts)
            if current_ymd >= self.core.first_trading:
                try:
                    ipo_days = trading_days_between(
                        self.core.first_trading, current_ymd)
                except ValueError:
                    ipo_days = -1

        if self.core.board == 2:
            return float('inf') if 1 <= ipo_days <= 5 else 0.2
        elif self.core.board == 3:
            return float('inf') if ipo_days == 1 else 0.3

        cdef int32_t reg_ckpt = 20200824 if self.core.board == 1 else 20230410
        if 1 <= ipo_days <= 5 and self.core.first_trading >= reg_ckpt:
            return float('inf')
        if ipo_days == 1 and self.core.first_trading > 0:
            return 0.44 if self.core.first_trading >= 20140101 else float('inf')

        cdef int64_t st_ckpt = CYB_CKPT if self.core.board == 1 else MAIN_ST_10PCT_CKPT
        if ts < st_ckpt and b"ST" in <bytes>self.core.name:
            return 0.05

        return 0.2 if (self.core.board == 1 and ts >= CYB_CKPT) else 0.1

    cdef AssetCore serialize(self):
        return self.core

    def __reduce__(self):#  class / args
        return (Asset, (self.sid,
                        self.core.name,
                        self.core.first_trading,
                        self.core.delist,
                        self.core.merger,
                        self.core.merge_ratio
            ))

    def __repr__(self):
        return f"Asset(sid={self.sid}, name={self.core.name}, first_trading={self.core.first_trading}, \
                        delist={self.core.delist}, merger={self.core.merger}, merge_ratio={self.core.merge_ratio})"
