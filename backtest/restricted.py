# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import numpy as np
import operator
from typing import List
from abc import ABC, abstractmethod
from functools import reduce
from collections.abc import Iterable


class Restricted(ABC):
    """
    Abstract restricted list interface, representing a set of asset that an
    algorithm is restricted from trading.
         --- used for pipe which filter asset list
    """

    @abstractmethod
    def is_restricted(self, assets, dt):
        """
        Is the asset restricted (RestrictionStates.FROZEN) on the given dt?

        Parameters
        ----------
        assets : Asset of iterable of Assets
            The asset(s) for which we are querying a restriction
        dt : pd.Timestamp
            The timestamp of the restriction query

        Returns
        -------
        is_restricted : bool or pd.Series[bool] indexed by asset
            Is the asset or asset restricted on this dt?

        """
        raise NotImplementedError('is_restricted')


class NoRestricted(Restricted):
    """
    A no-op restrictions that contains no restrictions.
    """
    def is_restricted(self, assets: List[Asset], dt: int):
        return assets


class Untradeable(Restricted):
    """
        remove suspended or delisted assets on the given dt
        delist_assets:  base on asset delist_date
        suspended_assets: base high-low < epsilon
    """
    def __init__(self, epsilon: float = 0.05):
        self.epsilon = epsilon

    def on_suspended(self, metadata):
        """
            price restricted  high - low < epison
        """
        low = np.min(np.array([item["low"] for item in metadata]))
        high = np.max(np.array([item["high"] for item in metadata]))
        pct = (high - low)/low
        flag = True if pct <= self.p.epsilon else False
        return flag 

    def is_restricted(self, assets, dt):
        assets = assets if isinstance(assets, Iterable) else [assets]
        filter_assets = [asset for asset in assets if asset.delist != 0 and asset.delist > dt]
        filter_assets = [asset for asset in filter_assets if not self.on_suspended(asset.metadata)]
        return filter_assets


class UnionRestricted:
    """
    A union of a number of sub restrictions.

    Parameters
    ----------
    sub_restrictions : iterable of Restrictions (but not _UnionRestrictions)
        The Restrictions to be added together

    Notes
    -----
    - Consumers should not construct instances of this class directly, but
      instead use the `|` operator to combine restrictions
    """

    def __init__(self, restrictions):
        restrictions = restrictions if isinstance(restrictions, Iterable) else [restrictions]
        # Filter out NoRestrictions and deal with resulting cases involving
        # one or zero sub_restrictions
        self.restrictions = [r for r in self.restrictions if not isinstance(r, NoRestricted)]

    def __or__(self, other):
        """
        Overrides the base implementation for combining two restrictions, of
        which the left side is a _UnionRestrictions.
        """
        # Flatten the underlying sub restrictions of _UnionRestrictions
        # If the right side is a _UnionRestrictions, defers to the
        # _UnionRestrictions implementation of `|`, which intelligently
        # flattens restricted lists
        # 调用 _UnionRestrictions 的__or__
        if isinstance(other, UnionRestricted):
            self.restrictions.extend(other.restrictions)
        elif isinstance(other, Restricted):
            self.restrictions.append(other)
        else:
            raise ValueError("Invalid type for restriction")

    def is_restricted(self, assets, dt):
        if isinstance(assets, Asset):
            return assets if len(set(r.is_restricted(assets, dt)
                                     for r in self.restrictions)) == 1 else None
        return reduce(
            operator.and_,
            (r.is_restricted(assets, dt) for r in self.restrictions)
        )
