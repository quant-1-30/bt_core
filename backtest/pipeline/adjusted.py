#! /usr/bin/env python
# -*- coding: utf-8 -*-

import heapq
import numpy as np
import pandas as pd
from collections import namedtuple, defaultdict
from abc import ABC, abstractmethod
from numpy import iinfo, uint32, multiply

UINT32_MAX = iinfo(uint32).max


def _decorate_source(source):
    for message in source:
        yield ((message.dt, message.source_id), message)


def date_sorted_sources(*sources):
    """
    Takes an iterable of sources, generating namestrings and
    piping their output into date_sort.
    """
    sorted_stream = heapq.merge(*(_decorate_source(s) for s in sources))

    # Strip out key decoration
    for _, message in sorted_stream:
        yield message


Dividend = namedtuple(
    'Dividend',
    ['sid', 'register_date', 'ex_date', 'share', 'transfer', 'interest']
)

Right = namedtuple(
    'Right',
    ['sid', 'register_date', 'ex_date', 'price', 'ratio']
)


class AdjustedArray:
    """
    An AdjustedArray is a adjustment array.
    """
    _cache_adjustments = defaultdict(pd.DataFrame)

    def __init__(self, adjustments):

        self._merge_adjustments(adjustments)

    def _merge_adjustments(self, adjustments, should_include_dividends=True, should_include_rights=True):
        """
        Merge adjustments for a particular sid into a dictionary containing
        adjustments for all sids.

        Returns a dict of DataFrame:
        {
            # Integer index into `dates` for the date on which we should
            # apply the list of adjustments.
            1 : [
                Float64Multiply(first_row=2, last_row=4, col=3, value=0.5),
                Float64Overwrite(first_row=3, last_row=5, col=1, value=2.0),
                ...
            ],
            ...
        }
        """
        for adjust_type, metadata in adjustments.items():
            original = self._cache_adjustments[adjust_type]
            metadata["sid"] = metadata.pop("sid")
            metadata["ex_date"] = metadata.pop("ex_date")

            tuples = [(row.pop("sid"), row.pop("ex_date")) for row in metadata]
            multi_index = pd.MultiIndex.from_tuples(tuples=tuples, names=['sid', 'ex_date'])
            df_data = pd.DataFrame(metadata, index=multi_index)
            original = pd.concat([original, df_data])

    def calc_dividend_ratios_for_sid(self, sid, line, trading_dates):
        """
           股权登记日后的下一个交易日就是除权日或除息日，这一天购入该公司股票的股东不再享有公司此次分红配股
           前复权：复权后价格=(复权前价格-现金红利)/(1+流通股份变动比例)
           后复权：复权后价格=复权前价格×(1+流通股份变动比例)+现金红利
           
           配股除权价=（除权登记日收盘价+配股价*每股配股比例）/(1+每股配股比例）

           股权登记日下一个交易日就是除权日或除息日
           上交所证券的红股上市日为股权除权日的下一个交易日;深交所证券的红股上市日为股权登记日后的第3个交易日
        
        Calculate the ratios to apply to equities when looking back at pricing
        history so that the price is smoothed over the ex_date, when the market
        adjusts to the change in equity value due to upcoming dividend.

        Returns
        -------
        DataFrame
            A frame in the same format as splits and mergers, with keys
            - sid, the id of the equity
            - effective_date, the date in seconds on which to apply the ratio.
            - ratio, the ratio to apply to backwards looking pricing data.
        """
        def calc_qfq(x):
            return (1 - x['bonus']/(10 * x['pre_close'])) / \
                  (1 + (x['sid_bonus'] + x['sid_transfer']) / 10)
        
        def calc_right(x):
            return (x['pre_close'] + (x['rights_price'] * x['rights_bonus']) / 10) / \
                  (1 + x['rights_bonus']/10)

        if not isinstance(line, pd.DataFrame):
            df_line = pd.DataFrame(line)
        # trans timestamp to datetime
        df_line.loc[:, "trading_date"] = df_line.apply(lambda x: pd.to_datetime(x["tick"], utc=True).date(), axis=1)
        trading_dates = np.array(df_line["trading_date"])
        # obtain dividend and right adjustments
        df_div, df_rgt = self.adjust_metadata.loc[sid]

        # # Mask for adjustments whose apply_dates are in the requested window of
        # # dates.
        # date_bounds = self.adjustment_apply_dates.slice_indexer(
        #     min_date,
        #     max_date,
        # )
        # dates_filter = zeros(len(self.adjustments), dtype='bool')
        # dates_filter[date_bounds] = True
        # # Ignore adjustments whose apply_date is in range, but whose end_date
        # # is out of range.
        # dates_filter &= (self.adjustment_end_dates >= min_date)

        # # Mask for adjustments whose sids are in the requested assets.
        # sids_filter = self.adjustment_sids.isin(assets.values)

        # adjustments_to_use = self.adjustments.loc[
        #     dates_filter & sids_filter
        # ].set_index('apply_date')

        # filter idx of preclose
        ex_date = np.array(df_div.index)
        pre_ix = np.searchsorted(trading_dates, ex_date) -1
        mask = pre_ix > 0
        pre_ix = pre_ix[mask]
        # locate preclose
        preclose = df_line["close"].iloc[pre_ix]
        df_div.loc[:, "pre_close"] = preclose.values()
        # calculate qfq
        df_div.loc[:,"qfq"] = df_div.apply(calc_qfq, axis=1)  

        # right
        ex_date = np.array(df_rgt.index)
        pre_ix = np.searchsorted(trading_dates, ex_date) -1
        mask = pre_ix > 0
        pre_ix = pre_ix[mask]
        # locate preclose
        preclose = df_line["close"].iloc[pre_ix]
        df_rgt.loc[:, "pre_close"] = preclose.values()    
        # calculate qfq
        df_rgt.loc[:,"qfq"] = df_rgt.apply(calc_right, axis=1)
        # aggregate dividend and right
        fq = df_div["qfq"].append(df_rgt["qfq"])
        qfq = self.postprocess(fq, trading_dates)
        return qfq

    @staticmethod
    def postprocess(fq, trading_dates):
        """
        align the tick to the trading date
        """
        # itertuples
        def eof(x):
            # minutes --- 14:59
            return pd.Timestamp(x) + pd.Timedelta(hours=23, minutes=59)

        fq.index = qfq.index.map(eof)
        fq.sort_index(ascending=True, inplace=True)
        qfq = 1 / fq.cumprod()
        qfq.reindex(trading_dates, method="bfill", inplace=True)
        qfq.reindex(trading_dates, method="ffill", inplace=True)
        # qfq.fillna(1, inplace=True)
        return qfq

    def merge_adjustments(self, data):
        """

        Parameters
        ----------
        all_adjustments_for_sid : dict[int -> AdjustedArray]
            All adjustments for a particular sid.
        col_to_all_adjustments : dict[int -> AdjustedArray]
            All adjustments for all sids.
        """
        self._merge_adjustments(data)

    # def load_adjusted_array(self, domain, columns, dates, sids, mask):
    #     raise NotImplementedError("AdjustedArray does not support load_adjusted_array")
