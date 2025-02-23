#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
from abc import ABC, abstractmethod
from typing import List, Mapping, Any


class Sizer(ABC):

    @abstractmethod
    def addsizer(self, sizercls, *args, **kwargs):
        '''Adds a ``Sizer`` class (and args) which is the default sizer for any
        strategy added to cerebro
        '''
        raise NotImplementedError("addsizer")


class FixedSizer(Sizer):

    def addsizer(self, sids: List[str], meta: Mapping[str, Any]):
        ratio = 1/ len(sids)
        return {sid: ratio for sid in sids}

    
class TurtleSizer:

    def __init__(self, capital):
        self.capital = capital

    def calc_volatility(self, metadata):
        # atr
        close = [item[5] for item in metadata]
        return np.std(close)

    def addsizer(self, sids: List[str], meta: Mapping[str, Any]):
        theta = {k: self.calc_volatility(v) for k, v in meta.items()}
            
 

class KellySizer:

    def __init__(self, capital):
        self.capital = capital

    def addsizer(self, asset, dts):
        return self.capital

