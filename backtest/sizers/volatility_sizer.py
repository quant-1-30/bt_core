#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-

import numpy as np
from ..sizer import Sizer

__all__ = ['VolatilitySizer']


def calc_volatility(prices, annual=True, log_return=True):
    """
    计算价格序列的波动率
    
    :param prices: 价格序列 (numpy array or list)
    :param window: 计算窗口期 (默认20天)
    :param annual: 是否年化 (默认True)
    :param method: 计算方法 ('log_returns' 或 'simple_returns')
    :return: 波动率值
    """
    prices = np.asarray(prices, dtype=float)
    
    # 数据验证
    if len(prices) < 2:
        return 0.0
    
    returns = np.log(prices[1:] / prices[:-1]) if log_return else (prices[1:] - prices[:-1]) / prices[:-1]
    volatility = np.std(returns, ddof=1)  # 使用样本标准差
    
    if annual:
        volatility *= np.sqrt(252)  # 年化
    return volatility


def calc_rolling_volatility(prices, window=20, annual=True):
    """
    计算滚动波动率
    
    :param prices: 价格序列
    :param window: 滚动窗口
    :param annual: 是否年化
    :return: 滚动波动率序列
    """
    prices = np.asarray(prices, dtype=float)
    
    if len(prices) < window + 1:
        return np.array([calc_volatility(prices, len(prices)-1, annual)])
    
    volatilities = []
    for i in range(window, len(prices)):
        vol = calc_volatility(prices[i-window:i+1], window, annual)
        volatilities.append(vol)
    
    return np.array(volatilities)


class VolatilitySizer(Sizer):
    """
    基于波动率的头寸大小调整器
    
    根据资产的波动率反向分配资金：
    - 低波动率资产获得更多资金
    - 高波动率资产获得较少资金
    
    Params:
        - volatility_window: 波动率计算窗口 (default: 20)
        - target_volatility: 目标组合波动率 (default: 0.15)
        - min_allocation: 最小分配比例 (default: 0.05)
        - max_allocation: 最大分配比例 (default: 0.5)
        - retint: 是否返回整数头寸 (default: False)
    """
    
    params = (
        ("default", 0.01), # default volatility
        ("min_wgt", 0.05),     
        ("max_wgt", 0.75),
    )

    def __init__(self):
        super(VolatilitySizer, self).__init__()

    def _calculate_volatilities(self, datas, sids):
        """计算各资产的波动率"""
        volatilities = {}
        for sid in sids:
            if sid in datas and len(datas[sid]) > 1:
                prices = np.array(datas[sid])
                vol = calc_volatility(
                    prices, 
                    annual=True
                )
                # 避免零波动率
                volatilities[sid] = max(vol, self.p.default)
            else:
                volatilities[sid] = self.p.default
        return volatilities

    def _calculate_inverse_volatility_weights(self, volatilities):
        """
        计算反向波动率权重
        
        低波动率 -> 高权重
        高波动率 -> 低权重
        """
        # 计算反向波动率
        inverse_vols = {sid: 1.0 / vol for sid, vol in volatilities.items()}
        
        # 归一化权重
        total_inverse_vol = sum(inverse_vols.values())
        weights = {sid: inv_vol / total_inverse_vol 
                  for sid, inv_vol in inverse_vols.items()}
        
        for sid in weights: # filter and normalize
            weights[sid] = np.clip(
                weights[sid], 
                self.p.min_wgt, 
                self.p.max_wgt
            )
        
        total_weight = sum(weights.values())
        weights = {sid: w / total_weight for sid, w in weights.items()}
        return weights

    def _getsizing(self, meta, sids, isbuy):
        """获取头寸大小"""
        if isbuy:
            # 计算波动率
            volatilities = self._calculate_volatilities(meta["datas"], sids)
            # 计算权重（使用反向波动率方法）
            weights = self._calculate_inverse_volatility_weights(volatilities)
            
            # 计算分配金额
            total_cash = meta["cash"]
            allocation = {}
            
            for sid in sids:
                cash_amount = total_cash * weights.get(sid, 0.0)
                if self.p.retint:
                    allocation[sid] = int(cash_amount)
                else:
                    allocation[sid] = cash_amount
            return allocation
        else:
            return self._sellout_sizing(meta["positions"])
