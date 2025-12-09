#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import pandas as pd
import numpy as np

from bokeh.models import Range1d, ColumnDataSource


def resample(ns, df, data, freq):
    # resmaple 生成连续日期
    df = df.astype("float")
    if "datetime" in df.columns:
        data.index = df.index = df.loc[:, "datetime"].apply(lambda x: pd.to_datetime(float(x), unit="s"))
    else:
        df.index = data.index

    if ns == "Feed":
        sample = df.resample(freq, closed="left", label="left").agg({
                'open': 'first',     
                'high': 'max',       
                'low': 'min',         
                'close': 'last',      
                'volume': 'mean',
                'datetime': 'max'
            })
    elif ns == "Strategy":
        sample = df.resample(freq, closed="left", label="left").max()
        # import pdb; pdb.set_trace()
    else:
        sample = df.resample(freq, closed="left", label="left").last()

    # sample.dropna(axis=0, how="any", inplace=True) 
    sample.dropna(axis=0, how="all", inplace=True) 

    if "datetime" in sample.columns: 
        sample.drop(columns=["datetime"], inplace=True)
    sample["datetime"] = sample.index
    return sample

def create_datasource(csv_path, freq):
    data = pd.read_csv(csv_path, header=1, sep=";")
    datasource = {}
    datasource["id"] = data.iloc[:,0].to_numpy()
    
    names_col = data.columns[1::2]
    datas_col = data.columns[2::2]

    for n_c, d_c in zip(names_col, datas_col):
        _src = {} 
        c_v = data.loc[:, d_c].astype(str)
        split_c_v = c_v.str.split(',', expand=True) 
        split_c_v.columns = d_c.split(',')
        resample_c_v = resample(n_c, split_c_v, data, freq)
        
        for key, v in resample_c_v.items():
            arr = v.to_numpy()
            if key != "datetime":
                arr = np.where(np.isnan(arr), 0.0, arr)

            _src[key] = arr
        datasource[n_c] = ColumnDataSource(data=_src, name=n_c)
    return datasource

def merge_cds(*sources, on='datetime'):
    """
    使用 pandas 合并多个数据源
    
    参数:
    sources: 多个 ColumnDataSource 对象
    on: 合并的键列
    
    返回:
    合并后的 ColumnDataSource
    """
    tooltips = [("Date", "@datetime{%F}")]
    
    dfs = []
    for i, source in enumerate(sources):
        df = pd.DataFrame(source.data)
        chain_tooltip = [f" {key}: @{{{key}}}{{0.2f}}<br>" for key in source.column_names if  key != "datetime"]
        tooltips.append((source.name, ''.join(chain_tooltip)))
        dfs.append(df)
    
    # 合并所有 DataFrame
    merged_df = dfs[0]
    for df in dfs[1:]:
        if on in merged_df.columns and on in df.columns:
            merged_df = pd.merge(merged_df, df, on=on, how='outer')
        else:
            merged_df = pd.concat([merged_df, df], axis=1)
    
    # 排序（如果是时间序列）
    if on in merged_df.columns and pd.api.types.is_datetime64_any_dtype(merged_df[on]):
        merged_df = merged_df.sort_values(on)
    
    _source = ColumnDataSource(merged_df.reset_index(drop=True)) # remove index
    del _source.data["index"]
    
    return _source, tooltips
