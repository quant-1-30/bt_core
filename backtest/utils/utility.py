# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import os
import inspect
import numpy as np
import pandas as pd
import logging
from copy import deepcopy
from functools import partial
from .wrapper import  ignore_pandas_nan_categorical_warning


def unstack_value(result, assets, missing_value):
    """
    Called with a column of the result of a pipe. This needs to put
    the data into a format that can be used in a workspace to continue
    doing computations.

    Parameters
    ----------
    result : pd.Series
        A multiindexed series with (dates, assets) whose values are the
        results of running this pipe term over the dates.
    assets : pd.Index
        All of the assets being requested. This allows us to correctly
        shape the workspace value.

    Returns
    -------
    workspace_value : array-like
        An array like value that the engine can consume.
    """
    return result.unstack().fillna(missing_value).reindex(
        columns=assets,
        fill_value=missing_value,
    ).values


# def asymmetric_round_price(price, prefer_round_down, tick_size, diff=0.95):
#     """
#         Asymmetric rounding function for adjusting prices to the specified number
#         of places in a way that "improves" the price. For limit prices, this means
#         preferring to round down on buys and preferring to round up on sells.
#         For stop prices, it means the reverse.

#         If prefer_round_down == True:
#             When .05 below to .95 above a specified decimal place, use it.
#         If prefer_round_down == False:
#             When .95 below to .05 above a specified decimal place, use it.

#         In math-speak:

#         If prefer_round_down: [<X-1>.0095, X.0195) -> round to X.01.
#         If not prefer_round_down: (<X-1>.0005, X.0105] -> round to X.01.
#     """
#     precision = zp_math.number_of_decimal_places(tick_size)
#     multiplier = int(tick_size * (10 ** precision))
#     diff -= 0.5  # shift the difference down
#     diff *= (10 ** -precision)  # adjust diff to precision of tick size
#     diff *= multiplier  # adjust diff to value of tick_size

#     # Subtracting an epsilon from diff to enforce the open-ness of the upper
#     # bound on buys and the lower bound on sells.  Using the actual system
#     # epsilon doesn't quite get there, so use a slightly less epsilon-ey value.
#     epsilon = float_info.epsilon * 10
#     diff = diff - epsilon

#     # relies on rounding half away from zero, unlike numpy's bankers' rounding
#     rounded = tick_size * consistent_round(
#         (price - (diff if prefer_round_down else -diff)) / tick_size
#     )
#     if zp_math.tolerant_equals(rounded, 0.0):
#         return 0.0
#     return rounded


def vectorized_is_element(array, choices):
    """
    Check if each element of ``array`` is in choices.

    Parameters
    ----------
    array : np.ndarray
    choices : object
        Object implementing __contains__.

    Returns
    -------
    was_element : np.ndarray[bool]
        Array indicating whether each element of ``array`` was in ``choices``.
    """
    return np.vectorize(choices.__contains__, otypes=[bool])(array)


def getargspec(f):
    full_argspec = inspect.getfullargspec(f)
    return inspect.ArgSpec(
        args = full_argspec.args,
        varargs = full_argspec.varargs,
        keywords = full_argspec.varkw,
        defaults = full_argspec.defaults)


def signature():
    """
        sig = signature(foo)
        str(sig)
        #'(a, *, b:int, **kwargs)'
        str(sig.parameters['b'])
        #'b:int'
        sig.parameters['b'].annotation
        #<class 'int'>
    """


def display():
    """
        pandas DataFrame表格最大显示行数
        pd.options.display.max_rows = 20
        pandas DataFrame表格最大显示列数
        pd.options.display.max_columns = 20
        pandas精度浮点数显示4位
        pd.options.display.precision = 4
        numpy精度浮点数显示4位, 不使用科学计数法
        np.set_printoptions(precision=4, suppress=True)
    """


def encrypt(obj):

    """
        method : md5(), sha1(), sha224(), sha256(), sha384(), and sha512()
        algorithms may be available depending upon the OpenSSL library that Python uses on your platform.
        e.g. : hashlib.sha224("Nobody inspects the spammish repetition").hexdigest()
    """
    import hashlib
    m = hashlib.md5()
    m.update(obj)
    if hex :
        res = m.hexdigest()
    else:
        res = m.digest()
    return res


def extract(_p_dir,file='RomDataBu/df_kl.h5.zip'):
    """
    解压数据
    """
    data_example_zip = os.path.join(_p_dir, file)
    try:
        from zipfile import ZipFile

        zip_h5 = ZipFile(data_example_zip, 'r')
        unzip_dir = os.path.join(_p_dir, 'RomDataBu/')
        for h5 in zip_h5.namelist():
            zip_h5.extract(h5, unzip_dir)
        zip_h5.close()
    except Exception as e:
        print('example env failed! e={}'.format(e))


def verify_indices_all_unique(obj):

    axis_names = [
        ('index',),                            # Series
        ('index', 'columns'),                  # DataFrame
        ('items', 'major_axis', 'minor_axis')  # Panel
    ][obj.ndim - 1]  # ndim = 1 should go to entry 0,

    for axis_name, index in zip(axis_names, obj.axes):
        if index.is_unique:
            continue

        raise ValueError(
            "Duplicate entries in {type}.{axis}: {dupes}.".format(
                type=type(obj).__name__,
                axis=axis_name,
                dupes=sorted(index[index.duplicated()]),
            )
        )
    return obj


def validate_keys(dict_, expected, funcname):
    """Validate that a dictionary has an expected set of keys.
    """
    expected = set(expected)
    received = set(dict_)

    missing = expected - received
    if missing:
        raise ValueError(
            "Missing keys in {}:\n"
            "Expected Keys: {}\n"
            "Received Keys: {}".format(
                funcname,
                sorted(expected),
                sorted(received),
            )
        )

    unexpected = received - expected
    if unexpected:
        raise ValueError(
            "Unexpected keys in {}:\n"
            "Expected Keys: {}\n"
            "Received Keys: {}".format(
                funcname,
                sorted(expected),
                sorted(received),
            )
        )


# @deprecated(msg=DATAREADER_DEPRECATION_WARNING)
def cache_dir(environ):
    try:
        return environ['EMPYRICAL_CACHE_DIR']
    except KeyError:
        return os.path.join(

            environ.get(
                'XDG_CACHE_HOME',
                os.path.expanduser('~/.cache/'),
            ),
            'empyrical',
        )


# @deprecated(msg=DATAREADER_DEPRECATION_WARNING)
def data_path(name):
    return os.join(cache_dir(), name)


# @deprecated(msg=DATAREADER_DEPRECATION_WARNING)
def ensure_directory(path):
    """
    Ensure that a directory named "path" exists.
    """

    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != os.errno.EEXIST or not os.isdir(path):
            raise


def get_utc_timestamp(dt):
    """
    Returns the Timestamp/DatetimeIndex
    with either localized or converted to UTC.

    Parameters
    ----------
    dt : Timestamp/DatetimeIndex
        the date(s) to be converted

    Returns
    -------
    same type as input
        date(s) converted to UTC
    """

    dt = pd.to_datetime(dt)
    try:
        dt = dt.tz_localize('UTC')
    except TypeError:
        dt = dt.tz_convert('UTC')
    return dt


# if not os.path.exists(g_project_kl_df_data_example):
#     # 如果还没有进行解压，开始解压df_kl.h5.zip
#     data_example_zip = os.path.join(_p_dir, 'RomDataBu/df_kl.h5.zip')
#     try:
#         from zipfile import ZipFile
#         zip_h5 = ZipFile(data_example_zip, 'r')
#         unzip_dir = os.path.join(_p_dir, 'RomDataBu/')
#         for h5 in zip_h5.namelist():
#             zip_h5.extract(h5, unzip_dir)
#         zip_h5.close()
#     except Exception as e:
#         # 解压测试数据zip失败，就不开启测试数据模式了
#         print('example env failed! e={}'.format(e))
#     return

def check_indexes_all_same(indexes, message="Indexes are not equal."):
    """Check that a list of Index objects are all equal.

    Parameters
    ----------
    indexes : iterable[pd.Index]
        Iterable of indexes to check.
    message : string

    Raises
    ------
    ValueError
        If the indexes are not all the same.
    """
    iterator = iter(indexes)
    first = next(iterator)
    for other in iterator:
        same = (first == other)
        if not same.all():
            # 返回非0元素的位置
            bad_loc = np.flatnonzero(~same)[0]
            raise ValueError(
                "{}\nFirst difference is at index {}: "
                "{} != {}".format(
                    message, bad_loc, first[bad_loc], other[bad_loc]
                ),
            )


g_project_log_dir = 'c_test'


def init_logging(g_project_log_info):
    """
    logging相关初始化工作, 配置log级别, 默认写入路径, 输出格式
    """
    if not os.path.exists(g_project_log_dir):
        # 创建log文件夹
        os.makedirs(g_project_log_dir)

    # 输出格式规范
    # file_handler = logging.FileHandler(g_project_log_info, 'a', 'utf-8')
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                        datefmt='%a, %d %b %Y %H:%M:%S',
                        filename=g_project_log_info,
                        filemode='a'
                        # handlers=[file_handler]
                        )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # 屏幕打印只显示message
    formatter = logging.Formatter('%(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)


def quantiles(data, nbins_or_partition_bounds):
    """
    Compute rowwise array quantiles on an input.
    """
    return np.apply_along_axis(
        np.qcut,
        1,
        data,
        q=nbins_or_partition_bounds, labels=False,
    )


def is_sorted_ascending(a):
    """Check if a numpy array is sorted."""
    return (np.fmax.accumulate(a) <= a).all()


def explode(df):
    """
    Take a DataFrame and return a triple of

    (df.index, df.columns, df.values)
    """
    return df.index, df.columns, df.values


def find_in_sorted_index(dts, dt):
    """
    Find the index of ``dt`` in ``dts``.

    This function should be used instead of `dts.get_loc(dt)` if the index is
    large enough that we don't want to initialize a hash table in ``dts``. In
    particular, this should always be used on minutely trading calendars.

    Parameters
    ----------
    dts : pd.DatetimeIndex
        Index in which to look up ``dt``. **Must be sorted**.
    dt : pd.Timestamp
        ``dt`` to be looked up.

    Returns
    -------
    ix : int
        Integer index such that dts[ix] == dt.

    Raises
    ------
    KeyError
        If dt is not in ``dts``.
    """
    # searchsorted(a,v,side = 'left',sorter = None) left:a[i-1] < v <= a[i] ; right a[i-1] <= v <a[i]
    ix = dts.searchsorted(dt)
    if ix == len(dts) or dts[ix] != dt:
        raise LookupError("{dt} is not in {dts}".format(dt=dt, dts=dts))
    return ix


def nearest_unequal_elements(dts, dt):
    """
    Find values in ``dts`` closest but not equal to ``dt``.

    Returns a pair of (last_before, first_after).

    When ``dt`` is less than any element in ``dts``, ``last_before`` is None.
    When ``dt`` is greater any element in ``dts``, ``first_after`` is None.

    ``dts`` must be unique and sorted in increasing order.

    Parameters
    ----------
    dts : pd.DatetimeIndex
        Dates in which to search.
    dt : pd.Timestamp
        Date for which to find bounds.
    """
    if not dts.is_unique:
        raise ValueError("dts must be unique")

    if not dts.is_monotonic_increasing:
        raise ValueError("dts must be sorted in increasing order")

    if not len(dts):
        return None, None

    sortpos = dts.searchsorted(dt, side='left')
    try:
        sortval = dts[sortpos]
    except IndexError:
        # dt is greater than any value in the array.
        return dts[-1], None

    if dt < sortval:
        lower_ix = sortpos - 1
        upper_ix = sortpos
    elif dt == sortval:
        lower_ix = sortpos - 1
        upper_ix = sortpos + 1
    else:
        lower_ix = sortpos
        upper_ix = sortpos + 1

    lower_value = dts[lower_ix] if lower_ix >= 0 else None
    upper_value = dts[upper_ix] if upper_ix < len(dts) else None
    return lower_value, upper_value


def categorical_df_concat(df_list, inplace=False):
    """
    Prepare list of pandas DataFrames to be used as input to pd.concat.
    Ensure any columns of type 'category' have the same categories across each
    dataframe.

    Parameters
    ----------
    df_list : list
        List of dataframes with same columns.
    inplace : bool
        True if input list can be modified. Default is False.

    Returns
    -------
    concatenated : df
        Dataframe of concatenated list.
    """

    if not inplace:
        df_list = deepcopy(df_list)

    # Assert each dataframe has the same columns/dtypes
    df = df_list[0]
    if not all([(df.dtypes.equals(df_i.dtypes)) for df_i in df_list[1:]]):
        raise ValueError("Input DataFrames must have the same columns/dtypes.")

    categorical_columns = df.columns[df.dtypes == 'category']
    # 基于类别获取不同DataFrame分类 --- 重新分类
    for col in categorical_columns:
        new_categories = sorted(
            set().union(
                *(frame[col].cat.categories for frame in df_list)
            )
        )

        with ignore_pandas_nan_categorical_warning():
            for df in df_list:
                df[col].cat.set_categories(new_categories, inplace=True)

    return pd.concat(df_list)


def changed_locations(a, include_first):
    """
    Compute indices of values in ``a`` that differ from the previous value.

    Parameters
    ----------
    a : np.ndarray
        The array on which to indices of change.
    include_first : bool
        Whether or not to consider the first index of the array as "changed".

    Example
    -------
    >>> import numpy as np
    >>> changed_locations(np.array([0, 0, 5, 5, 1, 1]), include_first=False)
    array([2, 4])

    >>> changed_locations(np.array([0, 0, 5, 5, 1, 1]), include_first=True)
    array([0, 2, 4])
    """
    if a.ndim > 1:
        raise ValueError("indices_of_changed_values only supports 1D arrays.")
    indices = np.flatnonzero(np.diff(a)) + 1

    if not include_first:
        return indices

    return np.hstack([[0], indices])


def naive_grouped_rowwise_apply(data,
                                group_labels,
                                func,
                                func_args=(),
                                out=None):
    """
    Simple implementation of grouped row-wise function application.

    Parameters
    ----------
    data : ndarray[ndim=2]
        Input array over which to apply a grouped function.
    group_labels : ndarray[ndim=2, dtype=int64]
        Labels to use to bucket inputs from array.
        Should be the same shape as array.
    func : function[ndarray[ndim=1]] -> function[ndarray[ndim=1]]
        Function to apply to pieces of each row in array.
    func_args : tuple
        Additional positional arguments to provide to each row in array.
    out : ndarray, optional
        Array into which to write output.  If not supplied, a new array of the
        same shape as ``data`` is allocated and returned.

    Examples
    --------
    >>> data = np.array([[1., 2., 3.],
    ...                  [2., 3., 4.],
    ...                  [5., 6., 7.]])
    >>> labels = np.array([[0, 0, 1],
    ...                    [0, 1, 0],
    ...                    [1, 0, 2]])
    >>> naive_grouped_rowwise_apply(data, labels, lambda row: row - row.min())
    array([[ 0.,  1.,  0.],
           [ 0.,  0.,  2.],
           [ 0.,  0.,  0.]])
    """
    if out is None:
        out = np.empty_like(data)

    for (row, label_row, out_row) in zip(data, group_labels, out):
        for label in np.unique(label_row):
            locs = (label_row == label)
            out_row[locs] = func(row[locs], *func_args)
    return out


def compare_datetime_arrays(x, y):
    """
    Compare datetime64 ndarrays, treating NaT values as equal.
    """

    return np.array_equal(x.view('int64'), y.view('int64'))


object_dtype = np.dtype('O')
# We use object arrays for strings.
categorical_dtype = object_dtype


def ffill_across_cols(df, columns, name_map):
    """
    Forward fill values in a DataFrame with special logic to handle cases
    that pd.DataFrame.ffill cannot and cast columns to appropriate types.
    """
    df.ffill(inplace=True)

    # Fill in missing values specified by each column. This is made
    # significantly more complex by the fact that we need to work around
    # two pandas issues:

    # 1) When we have sids, if there are no records for a given sid for any
    #    dates, pandas will generate a column full of NaNs for that sid.
    #    This means that some of the columns in `dense_output` are now
    #    float instead of the intended dtype, so we have to coerce back to
    #    our expected type and convert NaNs into the desired missing value.

    # 2) DataFrame.ffill assumes that receiving None as a fill-value means
    #    that no value was passed.  Consequently, there's no way to tell
    #    pandas to replace NaNs in an object column with None using fillna,
    #    so we have to roll our own instead using df.where.
    for column in columns:
        column_name = name_map[column.name]
        # Special logic for strings since `fillna` doesn't work if the
        # missing value is `None`.
        if column.dtype == categorical_dtype:
            df[column_name] = df[
                column.name
            ].where(pd.notnull(df[column_name]),
                    column.missing_value)
        else:
            df[column_name] = df[
                column_name
            ].fillna(column.missing_value).astype(column.dtype)


def as_column(a):
    """
    Convert an array of shape (N,) into an array of shape (N, 1).

    This is equivalent to `a[:, np.newaxis]`.

    Parameters
    ----------
    a : np.ndarray

    Example
    -------
    >>> import numpy as np
    >>> a = np.arange(5)
    >>> a
    array([0, 1, 2, 3, 4])
    >>> as_column(a)
    array([[0],
           [1],
           [2],
           [3],
           [4]])
    >>> as_column(a).shape
    (5, 1)
    """
    if a.ndim != 1:
        raise ValueError(
            "as_column expected an 1-dimensional array, "
            "but got an array of shape %s" % a.shape
        )
    return a[:, None]


#
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

import pandas as pd, numpy as np

ANNUALIZATION_FACTORS = {
                        'monthly': 12,
                        'weekly': 52,
                        'daily': 252,
                        }


def _flatten(arr):
    return arr if not isinstance(arr, pd.Series) else arr.values


def _adjust_returns(returns, adjustment_factor):
    """
    Returns the returns series adjusted by adjustment_factor. Optimizes for the
    case of adjustment_factor being 0 by returning returns itself, not a copy!

    Parameters
    ----------
    returns : pd.Series or np.ndarray
    adjustment_factor : pd.Series or np.ndarray or float or int

    Returns
    -------
    adjusted_returns : array-like
    """
    if isinstance(adjustment_factor, (float, int)) and adjustment_factor == 0:
        return returns
    return returns - adjustment_factor


def annualization_factor(period, annualization):
    """
    Return annualization factor from period entered or if a custom
    value is passed in.

    Parameters
    ----------
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.

    Returns
    -------
    annualization_factor : float
    """
    if annualization is None:
        try:
            factor = ANNUALIZATION_FACTORS[period]
        except KeyError:
            raise ValueError(
                "Period cannot be '{}'. "
                "Can be '{}'.".format(
                    period, "', '".join(ANNUALIZATION_FACTORS.keys())
                )
            )
    else:
        factor = annualization
    return factor


def _to_pandas(ob):
    """Convert an array-like to a pandas object.

    Parameters
    ----------
    ob : array-like
        The object to convert.

    Returns
    -------
    pandas_structure : pd.Series or pd.DataFrame
        The correct structure based on the dimensionality of the data.
    """
    if isinstance(ob, (pd.Series, pd.DataFrame)):
        return ob

    if ob.ndim == 1:
        return pd.Series(ob)
    elif ob.ndim == 2:
        return pd.DataFrame(ob)
    else:
        raise ValueError(
            'cannot convert array of dim > 2 to a pandas structure',
        )


def _create_unary_vectorized_roll_function(function):
    def unary_vectorized_roll(arr, window, out=None, **kwargs):
        """
        Computes the {human_readable} measure over a rolling window.

        Parameters
        ----------
        arr : array-like
            The array to compute the rolling {human_readable} over.
        window : int
            Size of the rolling window in terms of the periodicity of the data.
        out : array-like, optional
            Array to use as output buffer.
            If not passed, a new array will be created.
        **kwargs
            Forwarded to :func:`~empyrical.{name}`.

        Returns
        -------
        rolling_{name} : array-like
            The rolling {human_readable}.
        """
        allocated_output = out is None

        if len(arr):
            out = function(
                rolling_window(_flatten(arr), min(len(arr), window)).T,
                out=out,
                **kwargs
            )
        else:
            out = np.empty(0, dtype='float64')

        if allocated_output and isinstance(arr, pd.Series):
            out = pd.Series(out, index=arr.index[-len(out):])

        return out

    unary_vectorized_roll.__doc__ = unary_vectorized_roll.__doc__.format(
        name=function.__name__,
        human_readable=function.__name__.replace('_', ' '),
    )

    return unary_vectorized_roll


def _create_binary_vectorized_roll_function(function):
    def binary_vectorized_roll(lhs, rhs, window, out=None, **kwargs):
        """
        Computes the {human_readable} measure over a rolling window.

        Parameters
        ----------
        lhs : array-like
            The first array to pass to the rolling {human_readable}.
        rhs : array-like
            The second array to pass to the rolling {human_readable}.
        window : int
            Size of the rolling window in terms of the periodicity of the data.
        out : array-like, optional
            Array to use as output buffer.
            If not passed, a new array will be created.
        **kwargs
            Forwarded to :func:`~empyrical.{name}`.

        Returns
        -------
        rolling_{name} : array-like
            The rolling {human_readable}.
        """
        allocated_output = out is None

        if window >= 1 and len(lhs) and len(rhs):
            out = function(
                rolling_window(_flatten(lhs), min(len(lhs), window)).T,
                rolling_window(_flatten(rhs), min(len(rhs), window)).T,
                out=out,
                **kwargs
            )
        elif allocated_output:
            out = np.empty(0, dtype='float64')
        else:
            out[()] = np.nan

        if allocated_output:
            if out.ndim == 1 and isinstance(lhs, pd.Series):
                out = pd.Series(out, index=lhs.index[-len(out):])
            elif out.ndim == 2 and isinstance(lhs, pd.Series):
                out = pd.DataFrame(out, index=lhs.index[-len(out):])
        return out

    binary_vectorized_roll.__doc__ = binary_vectorized_roll.__doc__.format(
        name=function.__name__,
        human_readable=function.__name__.replace('_', ' '),
    )

    return binary_vectorized_roll


def _roll_pandas(func, window, *args, **kwargs):
    data = {}
    index_values = []
    for i in range(window, len(args[0]) + 1):
        rets = [s.iloc[i-window:i] for s in args]
        index_value = args[0].index[i - 1]
        index_values.append(index_value)
        data[index_value] = func(*rets, **kwargs)
    return pd.Series(data, index=type(args[0].index)(index_values))


def rolling_window(array, length, mutable=False):
    """
    Restride an array of shape

        (X_0, ... X_N)

    into an array of shape

        (length, X_0 - length + 1, ... X_N)

    where each slice at index i along the first axis is equivalent to

        result[i] = array[length * i:length * (i + 1)]

    Parameters
    ----------
    array : np.ndarray
        The base array.
    length : int
        Length of the synthetic first axis to generate.
    mutable : bool, optional
        Return a mutable array? The returned array shares the same memory as
        the input array. This means that writes into the returned array affect
        ``array``. The returned array also uses strides to map the same values
        to multiple indices. Writes to a single index may appear to change many
        values in the returned array.

    Returns
    -------
    out : np.ndarray

    Example
    -------
    >>> from numpy import arange
    >>> a = arange(25).reshape(5, 5)
    >>> a
    array([[ 0,  1,  2,  3,  4],
           [ 5,  6,  7,  8,  9],
           [10, 11, 12, 13, 14],
           [15, 16, 17, 18, 19],
           [20, 21, 22, 23, 24]])

    >>> rolling_window(a, 2)
    array([[[ 0,  1,  2,  3,  4],
            [ 5,  6,  7,  8,  9]],
    <BLANKLINE>
           [[ 5,  6,  7,  8,  9],
            [10, 11, 12, 13, 14]],
    <BLANKLINE>
           [[10, 11, 12, 13, 14],
            [15, 16, 17, 18, 19]],
    <BLANKLINE>
           [[15, 16, 17, 18, 19],
            [20, 21, 22, 23, 24]]])
    """
    if not length:
        raise ValueError("Can't have 0-length window")

    orig_shape = array.shape
    if not orig_shape:
        raise IndexError("Can't restride a scalar.")
    elif orig_shape[0] < length:
        raise IndexError(
            "Can't restride array of shape {shape} with"
            " a window length of {len}".format(
                shape=orig_shape,
                len=length,
            )
        )

    num_windows = (orig_shape[0] - length + 1)
    #三维
    new_shape = (num_windows, length) + orig_shape[1:]
    new_strides = (array.strides[0],) + array.strides
    out = np.lib.stride_tricks.as_strided(array, new_shape, new_strides)
    out.setflags(write=mutable)
    return out


def _roll_ndarray(func, window, *args, **kwargs):
    data = []
    for i in range(window, len(args[0]) + 1):
        rets = [s[i-window:i] for s in args]
        data.append(func(*rets, **kwargs))
    return np.array(data)


def roll(*args, **kwargs):
    """
    Calculates a given statistic across a rolling time period.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns (optional): float / series
        Benchmark return to compare returns against.
    function:
        the function to run for each rolling window.
    window (keyword): int
        the number of periods included in each calculation.
    (other keywords): other keywords that are required to be passed to the
        function in the 'function' argument may also be passed in.

    Returns
    -------
    np.ndarray, pd.Series
        depends on input type
        ndarray(s) ==> ndarray
        Series(s) ==> pd.Series

        A Series or ndarray of the results of the stat across the rolling
        window.

    """
    func = kwargs.pop('function')
    window = kwargs.pop('window')
    if len(args) > 2:
        raise ValueError("Cannot pass more than 2 return sets")

    if len(args) == 2:
        if not isinstance(args[0], type(args[1])):
            raise ValueError("The two returns arguments are not the same.")

    if isinstance(args[0], np.ndarray):
        return _roll_ndarray(func, window, *args, **kwargs)
    return _roll_pandas(func, window, *args, **kwargs)


# roll_max_drawdown = _create_unary_vectorized_roll_function(max_drawdown)

def _make_metrics_set_core():
    """Create a family of metric sets functions that read from the same
    metric set mapping.

    Returns
    -------
    metrics_sets : mappingproxy
        The mapping of metric sets to load functions.
    register : callable
        The function which registers new metric sets in the ``metrics_sets``
        mapping.
    unregister : callable
        The function which deregisters metric sets from the ``metrics_sets``
        mapping.
    load : callable
        The function which loads the ingested metric sets back into memory.
    """
    _metrics_sets = {}
    # Expose _metrics_sets through a proxy so that users cannot mutate this
    # accidentally. Users may go through `register` to update this which will
    # warn when trampling another metric set.

    def register(name, function=None):
        """Register a new metric set.

        Parameters
        ----------
        name : str
            The name of the metric set
        function : callable
            The callable which produces the metric set.

        Notes
        -----
        This may be used as a decorator if only ``name`` is passed.

        See Also
        --------
        zipline.finance.metric.get_metrics_set
        zipline.finance.metric.unregister_metrics_set
        """
        if function is None:
            # allow as decorator with just name.
            return partial(register, name)

        if name in _metrics_sets:
            raise ValueError('metric set %r is already registered' % name)

        _metrics_sets[name] = function

        return function

    def unregister(name):
        """Unregister an existing metric set.

        Parameters
        ----------
        name : str
            The name of the metric set

        See Also
        --------
        zipline.finance.metric.register_metrics_set
        """
        try:
            del _metrics_sets[name]
        except KeyError:
            raise ValueError(
                'metric set %r was not already registered' % name,
            )

    def load(name):
        """Return an instance of the metric set registered with the given name.

        Returns
        -------
        metric : set[Metric]
            A new instance of the metric set.

        Raises
        ------
        ValueError
            Raised when no metric set is registered to ``name``
        """
        try:
            function = _metrics_sets[name]
        except KeyError:
            raise ValueError(
                'no metric set registered as %r, options are: %r' % (
                    name,
                    sorted(_metrics_sets),
                ),
            )

        return function()

    return _metrics_sets, register, unregister, load


metrics_sets, register, unregister, load = _make_metrics_set_core()

