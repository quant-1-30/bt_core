#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-

import pandas as pd
import numpy as np
from bokeh.plotting import figure, show
from bokeh.layouts import gridplot, column
from bokeh.models import ColumnDataSource, Range1d


def extract_from_csv(csv_path):

    data = pd.read_csv(csv_path, header=1)
    return data


def create_three_panel_layout():
    # 创建数据源
    dates = np.arange(100)
    prices = 100 + np.cumsum(np.random.randn(100))
    indicator1 = np.sin(dates * 0.1) * 10 + 50  # 示例指标1
    indicator2 = np.cos(dates * 0.2) * 5 + 25   # 示例指标2
    
    source = ColumnDataSource(data={
        'date': dates,
        'price': prices,
        'indicator1': indicator1,
        'indicator2': indicator2
    })
    
    # 1. 上层：Observer 指标区域
    observer_fig = figure(
        title="Observer 指标",
        width=1000, 
        height=200,
        x_axis_type="datetime" if isinstance(dates[0], (np.datetime64, pd.Timestamp)) else "linear",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=Range1d(dates[0], dates[-1])
    )
    
    # 添加上层指标
    observer_fig.line('date', 'indicator1', source=source, 
                     line_width=2, color='blue', legend_label="Observer 1")
    observer_fig.line('date', 'indicator2', source=source, 
                     line_width=2, color='red', legend_label="Observer 2")
    observer_fig.legend.location = "top_left"
    
    # 2. 中层：价格曲线区域
    price_fig = figure(
        title="价格走势",
        width=1000, 
        height=400,
        x_axis_type=observer_fig.x_axis_type,
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=observer_fig.x_range  # 共享x轴范围
    )
    
    # 添加价格曲线
    price_fig.line('date', 'price', source=source, 
                  line_width=2, color='green', legend_label="Price")
    price_fig.legend.location = "top_left"
    
    # 3. 下层：技术指标区域
    indicator_fig = figure(
        title="技术指标",
        width=1000, 
        height=300,
        x_axis_type=observer_fig.x_axis_type,
        tools="pan,wheel_zoom,box_zoom,reset,save",
        x_range=observer_fig.x_range  # 共享x轴范围
    )
    
    # 添加技术指标
    indicator_fig.line('date', 'indicator1', source=source, 
                      line_width=2, color='purple', legend_label="Indicator 1")
    indicator_fig.line('date', 'indicator2', source=source, 
                      line_width=2, color='orange', legend_label="Indicator 2")
    indicator_fig.legend.location = "top_left"

    tools="pan,wheel_zoom,box_zoom,reset,save"  # 基础工具

    # # 使用 add_tools() 添加需要配置的工具
    # hover = HoverTool(
    #     tooltips=[("x", "@x"), ("y", "@y")],
    #     mode='vline'
    # )

    # hover = HoverTool(
    #     tooltips=[
    #         ("日期", "@date{%F}"),
    #         ("开盘", "@open{0.2f}"),
    #         ("最高", "@high{0.2f}"),
    #         ("最低", "@low{0.2f}"),
    #         ("收盘", "@close{0.2f}"),
    #         ("MA20", "@MA_20{0.2f}"),
    #         ("MA50", "@MA_50{0.2f}")
    #     ],
    #     formatters={'@date': 'datetime'},
    #     mode='vline'
    # )

    # crosshair = CrosshairTool()

    # fig.add_tools(hover, crosshair)  # 添加自定义工具


    # 计算实体顶部和底部
    # df['top_body'] = df[['open', 'close']].max(axis=1)
    # df['bottom_body'] = df[['open', 'close']].min(axis=1)

    # # 计算影线长度和实体高度
    # df['body_height'] = df['top_body'] - df['bottom_body']
    # df['upper_shadow'] = df['high'] - df['top_body']
    # df['lower_shadow'] = df['bottom_body'] - df['low']

    # p = figure(x_axis_type='datetime', width=800, height=400)

    # # 绘制实体
    # p.vbar(x='date', width=0.8, top='top_body', bottom='bottom_body', 
    #     fill_color='steelblue', line_color='black', source=source)

    # # 绘制上影线：从实体顶部到最高价
    # p.segment(x0='date', y0='top_body', x1='date', y1='high', 
    #         color='upper_color', line_width=1, source=source)

    # # 绘制下影线：从实体底部到最低价
    # p.segment(x0='date', y0='bottom_body', x1='date', y1='low', 
    #         color='lower_color', line_width=1, source=source)

    # show(p)

    # # 堆叠柱状图
    # p.vbar_stack(['sales_online', 'sales_store'], x='months', source=source,
    #             width=0.8, color=['blue', 'green'],
    #             legend_label=["线上销售", "门店销售"])

    # 使用 gridplot 创建垂直布局
    layout = gridplot([
        [observer_fig],
        [price_fig], 
        [indicator_fig]
    ], sizing_mode='stretch_width')
    
    return layout

# 使用示例
layout = create_three_panel_layout()
show(layout)



# parse csv ---> columnDataSource
