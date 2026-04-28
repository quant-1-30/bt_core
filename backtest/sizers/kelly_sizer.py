# cython: language_level=3, boundscheck=False, wraparound=False

from libc.stdint cimport int32_t
from libcpp.vector cimport vector


cdef class Sizer:
    cpdef int32_t getsizing(self, bint is_buy):
        return 0

    cpdef void reset(self):
        pass


cdef class Fixed(Sizer):
    '''This is the default sizer used by ``backtrader`` if no other sizer is
    set

    It will simply return a size of ``1`` for each operation
    '''
    cpdef int32_t getsizing(self, bint isbuy):
        return 100


class CrossSectionalSizer(bt.Sizer):
    """一个能够同时处理单/多标的、并动态分配权重的终极 Sizer"""
    params = (('method', 'score_weighted'), ('budget_ratio', 0.2)) # 每天用 20% 资金

    def _getsizing(self, comminfo, cash, data, isbuy):
        # 由于你的自定义 buy() API 期望 Sizer 返回 dict 比例：
        # 我们重写 _getsizing 使其返回 {sid: ratio}
        context = getattr(self.strategy, "sizing_context", {})
        if not context: return {}, False

        target_ratios = {}
        total_score = sum(max(score, 0) for score in context.values())

        for sid, score in context.items():
            if self.p.method == 'equal':
                target_ratios[sid] = self.p.budget_ratio / len(context)
            elif self.p.method == 'score_weighted':
                target_ratios[sid] = self.p.budget_ratio * (max(score, 0) / total_score)
                
        return target_ratios, True


cdef class Pyramid(Sizer):

    def __init__(self, list ratios=None):
        if ratios is None:
            ratios = [40, 40, 20]  
        
        self.max_step = len(ratios)
        self.step = 0
        
        for r in ratios:
            self.ratios.push_back(r)

    cpdef int32_t getsizing(self, bint is_buy):
        cdef int32_t r

        if is_buy:
            if self.step >= self.max_step:
                return 0
            
            r = self.ratios[self.step]
            
            self.step += 1
            return r
        else:
            return 100

    cpdef void reset(self):
        self.step = 0


# cdef class Kelly(Sizer):
#     '''This sizer will return a size based on the Kelly Criterion
# 
#     The Kelly Criterion is a formula used to determine the optimal size of a
#     series of bets in order to maximize the logarithm of wealth. It is often
#     used in gambling and investing to help manage risk and maximize returns.
# 
#     The formula for the Kelly Criterion is:
# 
#     f* = (bp - q) / b
# 
#     where:
# 
#       - f* is the fraction of the current bankroll to wager
# 
#       - b is the net odds received on the wager (i.e., "b to 1") - this is
#         calculated as (1 / (price - 1)) for buy operations and (1 / price) for
#         sell operations
# 
#       - p is the probability of winning (i.e., the probability that the bet
#         will pay off)
# 
#       - q is the probability of losing, which is equal to 1 - p
# 
#     The Kelly Criterion suggests that you should bet a fraction of your
#     bankroll equal to f* in order to maximize your long-term growth rate. If
#     f* is negative, it means that you should not place the bet at all.
# 
#     Note that the Kelly Criterion assumes that you have an edge over the house
#     or market, meaning that your probability of winning (p) is greater than
#     your probability of losing (q). If you do not have an edge, then betting
#     according to the Kelly Criterion may lead to losses over time.
# 
#     This sizer requires that ``self.strategy`` has two methods implemented:
# 
#       - ``kelly_p(self, data)``: returns the probability of winning for the
#         given data
# 
#       - ``kelly_q(self, data)``: returns the probability of losing for the
#         given data
# 
#     '''


def calculate_gpd_cvar(returns, confidence_level=0.99):
    """基于 GPD 计算 99% 极值条件在险价值 (CVaR)"""
    # ====== 在仓位管理中的应用 ======
    # position_rate = tolerance / GPD_CVaR = 5% / 12% = 41.6% 
    losses = -np.array(returns)
    threshold_percentile = 95
    u = np.percentile(losses, threshold_percentile)
    
    tail_losses = losses[losses > u] - u
    # c 是形状参数 (xi), loc 是位置参数(固定为0), scale 是尺度参数 (beta)
    shape_xi, loc, scale_beta = genpareto.fit(tail_losses, floc=0)
    
    # GPD CVar 相比于正态分布的 VaR
    tail_prob = 1.0 - (threshold_percentile / 100.0)
    alpha = 1.0 - confidence_level
    
    cvar_gpd = u + (scale_beta / (1 - shape_xi)) * ( ((tail_prob / alpha) ** shape_xi) - 1 )
    return cvar_gpd


class CrossSectionalSizer(bt.Sizer):
    """
    原生的截面 Sizer 基类：
    巧妙利用 dt 缓存机制，实现 O(1) 的全市场权重分配
    """
    params = (
        ('max_weight_per_asset', 0.15), # 单只标的最大持仓上限 15%
    )

    def __init__(self):
        self._target_weights = {}  # 缓存当前 Bar 的目标权重 {data._name: weight}
        self._last_dt = None       # 记录上一次计算的时间戳

    def _getsizing(self, comminfo, cash, data, isbuy):
        # 1. 检查是否到了新的 K 线时间切片
        current_dt = self.strategy.datetime.datetime(0)
        if current_dt != self._last_dt:
            # 如果是新的时间，触发全市场截面权重计算
            self._compute_cross_sectional_weights()
            self._last_dt = current_dt

        # 2. 从缓存中拿取该股票的目标权重
        target_weight = self._target_weights.get(data._name, 0.0)

        # 3. 将权重转化为具体的股数 (Shares)
        # 获取账户总权益
        broker = self.strategy.broker
        total_value = broker.getvalue()
        
        # 计算目标金额
        target_value = total_value * target_weight
        
        # 计算当前的实际持仓价值
        position = broker.getposition(data)
        current_value = position.size * data.close[0]
        
        # 计算需要买卖的差额金额
        diff_value = target_value - current_value
        
        # 转化为股数 (忽略了 A 股 100 股一手的取整逻辑，实际可加 math.floor(shares/100)*100)
        shares = int(diff_value / data.close[0])
        
        # 兜底：如果是 buy 且计算出 shares <= 0，或者 sell 且 shares >= 0，返回 0
        if isbuy and shares <= 0: return 0
        if not isbuy and shares >= 0: return 0
        
        return abs(shares)

    def _compute_cross_sectional_weights(self):
        """
        子类必须实现此方法：
        从 self.strategy.current_candidates 中获取当天的选股池并计算字典。
        """
        raise NotImplementedError


# ==========================================
# 算法 1：等权重 (Equal Weight Sizer)
# ==========================================
class EqualWeightSizer(CrossSectionalSizer):
    def _compute_cross_sectional_weights(self):
        self._target_weights = {}
        # strategy 每天会在 next() 里把选出的备选字典扔给 candidates
        candidates = getattr(self.strategy, 'current_candidates', {})
        
        if not candidates:
            return
            
        # 等权重分配，并受制于单只股票最大仓位
        weight = min(1.0 / len(candidates), self.p.max_weight_per_asset)
        
        for sid in candidates.keys():
            self._target_weights[sid] = weight


# ==========================================
# 算法 2：凯利/期望收益加权 (Kelly / Score Weighted)
# ==========================================
class KellyScoreSizer(CrossSectionalSizer):
    def _compute_cross_sectional_weights(self):
        self._target_weights = {}
        candidates = getattr(self.strategy, 'current_candidates', {})
        if not candidates:
            return
            
        # candidates 格式: { '000001': {'pred_score': 0.08, 'beta': 1.2}, ... }
        sids = list(candidates.keys())
        
        # 获取所有分数的正数部分 (过滤掉负数)
        scores = np.array([max(candidates[sid]['pred_score'], 1e-5) for sid in sids])
        
        # Kelly 变体：权重 = Score / 方差 (这里我们用 beta 近似替代方差)
        # 预测收益越高、系统性波动越小的股票，买的越多！
        betas = np.array([max(abs(candidates[sid].get('beta', 1.0)), 0.1) for sid in sids])
        kelly_ratios = scores / (betas ** 2)
        
        # 归一化
        raw_weights = kelly_ratios / np.sum(kelly_ratios)
        
        # 风控：削顶 (Clipping)
        clipped_weights = np.minimum(raw_weights, self.p.max_weight_per_asset)
        
        # 分配到缓存
        for i, sid in enumerate(sids):
            self._target_weights[sid] = clipped_weights[i]

