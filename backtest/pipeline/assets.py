# Copyright 2016 Quantopian, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import weakref
import numpy as np
import pandas as pd
# import quoteapi
import array
import struct
import binascii
from abc import ABC
from numbers import Integral
from functools import partial
from collections import deque, namedtuple
from operator import itemgetter, attrgetter

from pandas import isnull
from toolz import (
    compose,
    concat,
    concatv,
    curry,
    groupby,
    merge,
    partition_all,
    sliding_window,
    valmap,
)
from lib._assets import Asset # type: ignore

# A set of fields that need to be converted to strings before building an
# Asset to avoid unicode fields
_asset_str_fields = frozenset({
    'symbol',
    'asset_name',
    'exchange',
})

# A set of fields that need to be converted to timestamps in UTC
_asset_timestamp_fields = frozenset({
    'start_date',
    'end_date',
    'first_traded',
    'notice_date',
    'expiration_date',
    'auto_close_date',
})


Ownership = namedtuple('Ownership', 'first_tradeing_date delist_date sid value')

def merge_ownership_periods(mappings):
    """
    Given a dict of mappings where the values are lists of
    OwnershipPeriod objects, returns a dict with the same structure with
    new OwnershipPeriod objects adjusted so that the periods have no
    gaps.

    Orders the periods chronologically, and pushes forward the end date
    of each period to match the start date of the following period. The
    end date of the last period pushed forward to the max Timestamp.
    """
    return valmap(
        lambda v: tuple(
            Ownership(
                a.start,
                b.start,
                a.sid,
                a.value,
            ) for a, b in sliding_window(
                2,
                concatv(
                    sorted(v),
                    # concat with a fake ownership object to make the last
                    # end date be max timestamp
                    [Ownership(
                        pd.Timestamp.max.tz_localize('utc'),
                        None,
                        None,
                        None,
                    )],
                ),
            )
        ),
        mappings,
    )


def _build_ownership_map_from_rows(rows, key_from_row, value_from_row):
    mappings = {}
    for row in rows:
        mappings.setdefault(
            key_from_row(row),
            [],
        ).append(
            Ownership(
                pd.Timestamp(row.start_date, unit='ns', tz='utc'),
                pd.Timestamp(row.end_date, unit='ns', tz='utc'),
                row.sid,
                value_from_row(row),
            ),
        )

    return merge_ownership_periods(mappings)


def build_ownership_map(metadata, key_from_row, value_from_row):
    """
    Builds a dict mapping to lists of OwnershipPeriods, from a db table.
    """
    return _build_ownership_map_from_rows(
        metadata,
        key_from_row,
        value_from_row,
    )


def build_grouped_ownership_map(metadata,
                                key_from_row,
                                value_from_row,
                                group_key):
    """
    Builds a dict mapping group keys to maps of keys to lists of
    OwnershipPeriods, from a db table.
    """
    grouped_rows = groupby(
        group_key,
        metadata,
    )
    return {
        key: _build_ownership_map_from_rows(
            rows,
            key_from_row,
            value_from_row,
        )
        for key, rows in grouped_rows.items()
    }


@curry
def _filter_kwargs(names, dict_):
    """Filter out kwargs from a dictionary.

    Parameters
    ----------
    names : set[str]
        The names to select from ``dict_``.
    dict_ : dict[str, any]
        The dictionary to select from.

    Returns
    -------
    kwargs : dict[str, any]
        ``dict_`` where the keys intersect with ``names`` and the values are
        not None.
    """
    return {k: v for k, v in dict_.items() if k in names and v is not None}


equity_kwargs = ['symbol', 'asset_name', 'exchange', 'start_date', 'end_date', 'first_traded', 'notice_date', 'expiration_date', 'auto_close_date']

_filter_equity_kwargs = _filter_kwargs(equity_kwargs)


# Fuzzy symbol delimiters that may break up a company symbol and share class
_delimited_symbol_delimiters_regex = re.compile(r'[./\-_]')
_delimited_symbol_default_triggers = frozenset({np.nan, None, ''})


def split_delimited_symbol(symbol):
    """
    Takes in a symbol that may be delimited and splits it in to a company
    symbol and share class symbol. Also returns the fuzzy symbol, which is the
    symbol without any fuzzy characters at all.

    Parameters
    ----------
    symbol : str
        The possibly-delimited symbol to be split

    Returns
    -------
    company_symbol : str
        The company part of the symbol.
    share_class_symbol : str
        The share class part of a symbol.
    """
    # return blank strings for any bad fuzzy symbols, like NaN or None
    if symbol in _delimited_symbol_default_triggers:
        return '', ''

    symbol = symbol.upper()

    split_list = re.split(
        pattern=_delimited_symbol_delimiters_regex,
        string=symbol,
        maxsplit=1,
    )

    # Break the list up in to its two components, the company symbol and the
    # share class symbol
    company_symbol = split_list[0]
    if len(split_list) > 1:
        share_class_symbol = split_list[1]
    else:
        share_class_symbol = ''

    return company_symbol, share_class_symbol


def _convert_asset_timestamp_fields(dict_):
    """
    Takes in a dict of Asset init args and converts dates to pd.Timestamps
    """
    for key in _asset_timestamp_fields & dict_.keys():
        value = pd.Timestamp(dict_[key], tz='UTC')
        dict_[key] = None if isnull(value) else value
    return dict_


Lifetimes = namedtuple('Lifetimes', 'sid start end')

# ? --- non-greed match, * 0 or more, + 1 or more
Regex = {"equity": r"^[603].+?",
         "etf": r"^[51|15|58].+?"} 

Exchange = {"SZ": "0",
            "SH": "6",
            "ChiNext": "3",
            "STAR": "688"}

# np.iinfo(int).max


class AssetFinder(object):
    """
    An AssetFinder is an interface to a qutoeapi, supported asset present

    This class provides methods for looking up assets by unique integer id or
    by symbol.  For historical reasons, we refer to these unique ids as 'sids'.

    Parameters
    ----------
    quoteapi : class similar to xtp.quote

    See Also
    --------
    :class:`zipline.assets.AssetDBWriter`
    """
    _cache_weakref = weakref.WeakValueDictionary()
    _default_fields = set(["location", "exchange", "country_code"])

    def __new__(cls, *args, **kwargs):

        key = tuple(args) + tuple(kwargs.items())
        if key not in cls._cache_weakref:
            instance = super().__new__(cls, *args, **kwargs)
            cls._cache_weakref[key] = instance

        cls.supplement_fields = kwargs.get("supplement_fields", set()) & cls._default_fields
        return cls._cache_weakref[key]._init(*args, **kwargs)

    # @preprocess(engine=coerce_string_to_eng(require_exists=True))
    def _init(self, *args, **kwargs):

        # retrieve all asset metadata from quoteapi
        # metadata = quoteapi.onSubAsset()
        metadata = {}
        # Cache for lookup of assets by sid, the objects in the asset lookup
        self._asset_metadata = build_ownership_map(metadata)
        self._asset_cache = {}
        # Populated on first call to `lifetimes`.
        self._asset_lifetimes = {}

    def lookup_by_supplementary_field(self, field_name:str, regex:str):
        """Return all of the sids for a given country / register location / exchange.

        Parameters
        ----------
        country_code : str
            An ISO 3166 alpha-2 country code.

        register_location : str
            The register location of the equity.
        """
        assert field_name in self.supplement_fields, f"field_name {field_name} not in {self.supplement_fields}"
        # pattern = re.compile(r"^.*?\.{field_name}$")
        pattern = re.compile(regex)
        meta_sids = [row for row in self._asset_metadata if pattern.match(row['symbol'])]
        hits = {}
        for meta_sid in meta_sids:
            try:
                asset = self._asset_cache[meta_sid['sid']]
                hits[meta_sid['sid']] = asset
            except KeyError:
                asset = Asset(**_filter_equity_kwargs(meta_sid))
                self._asset_cache[meta_sid['sid']] = asset
                hits[meta_sid['sid']] = asset
        return hits

    def retrieve_equities(self, sids, fuzzy=False):
        """
        Retrieve Equity objects for a list of sids.

        Users generally shouldn't need to this method (instead, they should
        prefer the more general/friendly `retrieve_assets`), but it has a
        documented interface and tests because it's used upstream.

        Parameters
        ----------
        sids : iterable[int]
            Asset ids to look up.
        fuzzy : bool
            Whether to use fuzzy matching.

        Returns
        -------
        equities : dict[int -> Equity]

        Raises
        ------
        EquitiesNotFound
            When any requested asset isn't found.
        """
        return self._retrieve_assets(sids, "equity", fuzzy)
    
    def retrieve_etfs(self, sids, fuzzy=False):
        """
        Retrieve ETF objects for a list of sids.
        """
        return self._retrieve_assets(sids, "etf", fuzzy)
    
    def _retrieve_assets(self, sids, asset_type, fuzzy=False):
        """
        Internal function for loading assets from a table.

        This should be the only method of `AssetFinder` that writes Assets into
        self._asset_cache.

        Parameters
        ---------
        sids : iterable of int
            Asset ids to look up.
        asset_tbl : sqlalchemy.Table
            Table from which to query assets.
        asset_type : type
            Type of asset to be constructed.
        fuzzy : bool
            Whether to use fuzzy matching.

        Returns
        -------
        assets : dict[int -> Asset]
            Dict mapping requested sids to the retrieved assets.
        """
        metadata = self._asset_metadata
        if fuzzy:
            sids = [split_delimited_symbol(sid.upper())[0] for sid in sids]

        pattern = re.compile(Regex[asset_type])
        assets_cache = [row for row in metadata if pattern.match(row['symbol'])]
        if sids:
            assets_cache = [row for row in assets_cache if row["symbol"] in sids] 
        # valmap(lambda row: asset_type(**_filter_equity_kwargs(row)), cache)
        hits = self._asset_cache
        for row in assets_cache:
            sid = row['sid']
            asset = asset_type(**_filter_equity_kwargs(row))
            hits[sid] = asset

        return hits

    def incoming_assets(self, sids_meta):
        """
        update asset in cache

        Parameters
        ----------
        sids_meta : iterable of dict
            Assets to update.
        default_none : bool
            If True, return None for failed lookups.
            If False, raise `SidsNotFound`.

        Returns
        -------
        assets : list[Asset or None]
            A list of the same length as `sids` containing Assets (or Nones)
            corresponding to the requested sids.

        Raises
        ------
        SidsNotFound
            When a requested sid is not found and default_none=False.
        """
        add_sids = set(sids_meta) - set(self._asset_cache.keys())
        for sid in add_sids:
            asset = Asset(**_filter_equity_kwargs(sids_meta[sid]))
            self._asset_cache[sid] = asset
        # type_to_assets = self.group_by_type(missing)

    def _active(self, reference_date_value, asset):
        """
        Whether or not `asset` was active at the time corresponding to
        `reference_date_value`.

        Parameters
        ----------
        reference_date_value : int
            Date, represented as nanoseconds since EPOCH, for which we want to know
            if `asset` was alive.  This is generally the result of accessing the
            `value` attribute of a pandas Timestamp.
        asset : Asset
            The asset object to check.

        Returns
        -------
        was_active : bool
            Whether or not the `asset` existed at the specified time.
        """
        delist_date = asset.delist_date
        if asset.first_trading_date > reference_date_value:
            return False
        elif not delist_date:
            return True
        elif delist_date < reference_date_value:
            return False
        else:
            return True

    def only_active_assets(self, reference_date_value, sids=[]):
        """
        Filter an iterable of Asset objects down to just assets that were alive at
        the time corresponding to `reference_date_value`.

        Parameters
        ----------
        reference_date_value : int
            Date, represented as nanoseconds since EPOCH, for which we want to know
            if `asset` was alive.  This is generally the result of accessing the
            `value` attribute of a pandas Timestamp.
        assets : iterable[Asset]
            The assets to filter.

        Returns
        -------
        active_assets : list
            List of the active assets from `assets` on the requested date.
        """
        assets = self.retrieve_equities(sids)
        return [a for a in assets if self._active(reference_date_value, a)]

    def _make_sids(meta):
        def _(self):
            return tuple(map(
                itemgetter('sid'),
                meta,
            ))

        return _

    sids = property(
        _make_sids('asset_router'),
        doc='All the sids in the asset finder.',
    )
    equities_sids = property(
        _make_sids('equities'),
        doc='All of the sids for equities in the asset finder.',
    )

    del _make_sids


# # extension
# class AssetConvertible(with_metaclass(ABCMeta)):
#     """
#     ABC for types that are convertible to integer-representations of
#     Assets.

#     Includes Asset, six.string_types, and Integral
#     """
#     pass


# AssetConvertible.register(Integral)
# AssetConvertible.register(Asset)
# # Use six.string_types for Python2/3 compatibility
# for _type in string_types:
#     AssetConvertible.register(_type)
