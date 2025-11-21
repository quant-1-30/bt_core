import pandas as pd
import numpy as np
from bokeh.plotting import figure, show
from bokeh.layouts import gridplot, column
from bokeh.models import ColumnDataSource, Range1d, HoverTool, LinearAxis, Tabs, Span, CrosshairTool, CustomJS

from scheme import tableau10


def resample(ns, df, freq="D"):
    # resmaple 生成连续日期
    df = df.astype("float")
    if ns == "MetaBtData":
        sample = df.resample(freq, closed="left", label="left").agg({
                'open': 'first',     
                'high': 'max',       
                'low': 'min',         
                'close': 'last',      
                'volume': 'mean',
                'datetime': 'max'
            })
    else:
        sample = df.resample(freq, closed="left", label="left").first()
    sample.dropna(axis=0, how="all", inplace=True)
    return sample


if __name__ == "__main__":

    # 缺少 indicator 与 observer 个数 与 plotinfo 配置 需要单独写入文件 或者 csv 注释行
    data = pd.read_csv("out.csv", header=1, sep=";")
    # df = df.set_index(datetime_col)
    data.index = data.loc[:, "datetime"].apply(lambda x: pd.to_datetime(float(x), unit="s"))

    datasource = {}
    datasource["id"] = data.iloc[:,0].to_numpy()
    
    names_col = data.columns[1::2]
    datas_col = data.columns[2::2]

    for n_c, d_c in zip(names_col, datas_col):
        _source = {} 
        c_v = data.loc[:, d_c].fillna(0.0).astype(str)
        split_c_v = c_v.str.split(',', expand=True) 
        split_c_v.columns = d_c.split(',')
        resample_c_v = resample(n_c, split_c_v)

        resample_c_v["datetime"] = resample_c_v.index # add datetime to all datasource
        for key, v in resample_c_v.items():
            arr = v.to_numpy()
            if key != "datetime":
                arr = np.where(np.isnan(arr), 0.0, arr)

            _source[key] = arr
        datasource[n_c] = ColumnDataSource(data=_source)

    # 同步x轴
    shared_x_range = Range1d(data.index[0], data.index[-1])
      
# -------------------------------------------------------------------------- feed ------------------------------------------------------------------------------

    # title = "MetaBtData"
    # ohlc = datasource[title] # MetaBtData
    

    # # # 创建主图表
    # p_feed = figure(
    #     width=1200,
    #     height=400,
    #     title=title,
    #     x_axis_type="datetime",
    #     tools="pan,wheel_zoom,box_zoom,reset,save", # 基础工具
    #     active_drag='pan',
    #     active_scroll='wheel_zoom',
    #     tooltips=None
    # )
    
    # # # 绘制上下影线
    # # p_feed.segment('datetime', 'high', 'datetime', 'low', 
    # #          source=ohlc, color='black', line_width=1)
        
    # # # 绘制实体（涨为红色，跌为绿色）
    # # inc = ohlc.data['close'] > ohlc.data['open']
    # # dec = ohlc.data['close'] <= ohlc.data['open']
        
    # # # 涨K线
    # # p_feed.vbar(ohlc.data['datetime'][inc], 0.8, 
    # #        ohlc.data['open'][inc], ohlc.data['close'][inc],
    # #        fill_color="#D5E1DD", line_color="black")
        
    # # # 跌K线
    # # p_feed.vbar(ohlc.data['datetime'][dec], 0.8,
    # #        ohlc.data['open'][dec], ohlc.data['close'][dec], 
    # #        fill_color="#F2583E", line_color="black")
    

    # # 计算实体顶部和底部
    # ohlc.data['top_body'] = np.maximum(ohlc.data['open'], ohlc.data['close'])
    # ohlc.data['bottom_body'] = np.minimum(ohlc.data['open'], ohlc.data['close'])

    # # 计算影线长度和实体高度
    # ohlc.data['body_height'] = ohlc.data['top_body'] - ohlc.data['bottom_body']
    # ohlc.data['upper_shadow'] = ohlc.data['high'] - ohlc.data['top_body']
    # ohlc.data['lower_shadow'] = ohlc.data['bottom_body'] - ohlc.data['low']

    # # 添加 rect 所需的计算列
    # ohlc.data['body_center'] = (ohlc.data['top_body'] + ohlc.data['bottom_body']) / 2
    # ohlc.data['body_height'] = ohlc.data['top_body'] - ohlc.data['bottom_body']

    # ohlc.data['color'] = np.where(ohlc.data['close'] >= ohlc.data['open'], 'green', 'red')
    # ohlc.data['line_color'] = np.where(ohlc.data['close'] >= ohlc.data['open'], 'darkgreen', 'darkred')

    # # 绘制上影线：从实体顶部到最高价
    # upper = p.segment(x0='datetime', y0='top_body', x1='datetime', y1='high', 
    #         color='line_color', line_width=1, source=ohlc)

    # # 绘制下影线：从实体底部到最低价
    # bottom = p.segment(x0='datetime', y0='bottom_body', x1='datetime', y1='low', 
    #         color='line_color', line_width=1, source=ohlc)
    
    # # 绘制实体
    # # body_renderer = p.vbar(
    # #     x='datetime', width=0.8, top='top_body', bottom='bottom_body', 
    # #     fill_color='color', line_color='line_color', source=ohlc)
   
    # # # p_feed.vbar_stack(['sales_online', 'sales_store'], x='months', source=source,
    # # #            width=0.8, color=['blue', 'green'],
    # # #            legend_label=["线上销售", "门店销售"])

    # # 转换为 rect 的代码
    # body_renderer = p.rect(
    #     x='datetime', 
    #     y='body_center',  # 计算中心点y坐标
    #     width=0.8, 
    #     height='body_height',  # 计算高度
    #     fill_color='color', 
    #     line_color='line_color', 
    #     source=ohlc,
    # )

    # # # 分别创建上涨和下跌的数据源
    # # inc_mask = ohlc.data['close'] >= ohlc.data['open']
    # # dec_mask = ohlc.data['close'] < ohlc.data['open']

    # # source_inc = ColumnDataSource(ohlc.data[inc_mask])
    # # source_dec = ColumnDataSource(ohlc.data[dec_mask])

    # # # 绘制上涨K线的实体（绿色）
    # # p_feed.rect(
    # #     x='datetime', 
    # #     y='body_center', 
    # #     width=0.8, 
    # #     height='body_height',
    # #     fill_color='green', 
    # #     line_color='darkgreen', 
    # #     source=source_inc,
    # #     legend_label="上涨"  # 上涨图例
    # # )

    # # # 绘制下跌K线的实体（红色）
    # # p_feed.rect(
    # #     x='datetime', 
    # #     y='body_center', 
    # #     width=0.8, 
    # #     height='body_height',
    # #     fill_color='red', 
    # #     line_color='darkred', 
    # #     source=source_dec,
    # #     legend_label="下跌"  # 下跌图例
    # # )
    
    # # p_feed.legend.location = "top_left"
    # # p_feed.legend.click_policy = "hide" 
 
    # # 添加交互工具
    # hover = HoverTool(
    #     tooltips=[
    #         ("Date", "@datetime{%F}"), # %Y%m%d
    #         ("Open", "@open{0.2f}"),
    #         ("High", "@high{0.2f}"),
    #         ("Low", "@low{0.2f}"),
    #         ("Close", "@close{0.2f}"),
    #         ("Volume", "@volume{0,0}"),
    #     ],
    #     formatters={
    #         '@datetime': 'datetime'
    #     },
    #     mode='vline',
    #     renderers=[upper] # 不支持 rect / vbar
    # )

    # p_feed.add_tools(hover)
    # # p.add_tools(CrosshairTool())

    # p_feed.yaxis.axis_label = "价格"

    # show(p)
# -------------------------------------------------------------------------- strategy -------------------------------------------------------------------------

    # 主要考虑 买入与卖出点 ---> sell / buy 并与feed在一张图里

    # p.triangle / p.inverted_triangle circle square triangle diamond
    # p.triangle(x, y, size=15, color="navy", alpha=0.6, legend_label="正三角形")
    # p.inverted_triangle(x, y, size=15, color="firebrick", alpha=0.6, legend_label="倒三角形")

    # # 完整的三角形绘制示例
    # p.triangle(
    #     x,                          # x坐标（必需）
    #     y,                          # y坐标（必需）
    #     size=10,                    # 大小（像素）
    #     color="blue",               # 填充颜色
    #     line_color="black",         # 边框颜色
    #     line_width=1,               # 边框宽度
    #     line_alpha=1.0,             # 边框透明度
    #     fill_alpha=0.6,             # 填充透明度
    #     angle=0,                    # 旋转角度（弧度）
    #     angle_units="rad",          # 角度单位 ("rad", "deg")
    #     hatch_pattern=None,         # 填充图案
    #     hatch_color="black",        # 图案颜色
    #     hatch_weight=1,             # 图案粗细
    #     hatch_scale=12,             # 图案缩放
    #     hatch_alpha=1.0,            # 图案透明度
    #     name=None,                  # 名称
    #     tags=[]                     # 标签
    # )

# -------------------------------------------------------------------------- indicator gridplots --------------------------------------------------------------

    n_inds = ['SMA(close,period=15)', 'SMA(SMA(close,period=15),period=5)', 'SMA(SMA(SMA(close,period=15),period=5),period=5)', 
    'SMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)', 'EMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)']

    tooltips = []
    ind_plots = []
    ind_vlines = []

    for i, name in enumerate(n_inds):
        ind_source = datasource[name]

        p_ind = figure(
            # title=name,
            title='',
            width=1000, 
            height=100,
            x_axis_type="datetime", # x_axis_type="datetime" if isinstance(dates[0], (np.datetime64, pd.Timestamp)) else "linear",
            x_range=shared_x_range, # p_feed.x_range 
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )

        # # 在服务器模式下，可以使用 Python 回调实现更复杂的联动逻辑
        # def update_selection(attr, old, new):
        #     # 这里可以添加基于选中点的联动逻辑
        #     # 例如更新其他图表的高亮等
        #     pass

        # # 监听数据源的选中变化
        # ind_source.selected.on_change('indices', update_selection)

        vline = Span(location=0, dimension='height', line_color='red', line_width=1, line_alpha=0)
        ind_vlines.append(vline)
        p_ind.add_layout(vline)

        ind_tooltip = [("Date", "@datetime{%F}")]
        for idx, col in enumerate(ind_source.column_names):
            if col != "datetime":
                color_idx = idx % len(tableau10)
                p_ind.line(
                    'datetime', col, source=ind_source, 
                    line_width=2, color=tableau10[color_idx], legend_label=col)
                # ind_tooltip.append((col, f"@{{{col}}}{{0.2f}}"))
        chain_tooltip = [f" {key}: @{{{key}}}{{0.2f}}" for key in ind_source.column_names if  key != "datetime"]
        ind_tooltip.insert(0, (name, ','.join(chain_tooltip)))
        tooltips.append(ind_tooltip)
 
        p_ind.legend.location = "top_left"
        p_ind.legend.background_fill_alpha = 0.3  # 0-1之间的值，0为完全透明，1为完全不透明
        p_ind.legend.border_line_alpha = 0.3

        p_ind.yaxis.axis_label = "指标"

        if i < len(n_inds) - 1:
            p_ind.xaxis.visible = False

        ind_plots.append(p_ind)


    # 创建统一的回调
    hover_callback = CustomJS(
        args=dict(vlines=ind_vlines), 
        code="""
            // 悬停时显示所有参考线
            for (let i = 0; i < vlines.length; i++) {
                vlines[i].line_alpha = 0.5;
                vlines[i].location = cb_data.geometry.x;
            }
        """
    )

    for idx, _plt in enumerate(ind_plots):
        _tooltip = tooltips[idx]

        hover = HoverTool(
            tooltips=_tooltip,
            formatters={
                '@datetime': 'datetime'
            },
            mode='vline', # 'mouse': 离散数据 'hline': 数值对比 'vline': 时间序列
            callback=hover_callback
        )

        crosshair = CrosshairTool( # 十字线联动
            dimensions='height',
            line_alpha=0.3,
            line_color='gray',
            line_width=1)
     
        _plt.add_tools(hover, crosshair)
    
    # from bokeh.layouts import gridplot

    # # 假设我们将指标分成了两组：趋势指标和震荡指标
    # trend_plots = [p_feed] + trend_plots_list  # 趋势指标图表列表
    # oscillator_plots = oscillator_plots_list   # 震荡指标图表列表

    # # 创建两个网格布局
    # trend_grid = gridplot(trend_plots, ncols=1, plot_width=800, plot_height=200)
    # oscillator_grid = gridplot(oscillator_plots, ncols=1, plot_width=800, plot_height=200)

    # # 创建两个标签页
    # tab1 = Panel(child=trend_grid, title="趋势指标")
    # tab2 = Panel(child=oscillator_grid, title="震荡指标")

    # # 将标签页组合在一起
    # tabs = Tabs(tabs=[tab1, tab2])
    # show(tabs)

    # grid = gridplot(ind_plots, ncols=1)
    # # grid = gridplot(all_plots, ncols=ncols, plot_width=400, plot_height=200, sizing_mode='stretch_width')
    # show(grid)

    layout = column(*ind_plots)
    show(layout)

# ------------------------------------------------------------------------- indicator aggregate -----------------------------------------------------------------

    # n_inds = ['SMA(close,period=15)', 'SMA(SMA(close,period=15),period=5)', 'SMA(SMA(SMA(close,period=15),period=5),period=5)', 
    #         'SMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)', 'EMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)']

    # tooltips = [("Date", "@datetime{%F}")]
    # ind_plots = []
    # ind_vlines = []

    # dfs = []
    # for name in n_inds:
    #     ind_source = datasource[name]
    #     df = pd.DataFrame(ind_source.data)
    #     dfs.append(df)
    #     chain_tooltip = [f" {key}: @{{{key}}}{{0.2f}}" for key in ind_source.column_names if  key != "datetime"]
    #     tooltips.append((name, ','.join(chain_tooltip)))

    # # 合并所有 DataFrame
    # if dfs:
    #     merged_df = dfs[0]
    #     for df in dfs[1:]:
    #         merged_df = pd.merge(merged_df, df, on="datetime", how='outer')
    # total_source = ColumnDataSource(merged_df.reset_index(drop=True)) # remove index
    # del total_source.data["index"]
    # # import pdb; pdb.set_trace()

    # p_ind = figure(
    #     title="indicator",
    #     width=1000, 
    #     height=300,
    #     x_axis_type="datetime", # x_axis_type="datetime" if isinstance(dates[0], (np.datetime64, pd.Timestamp)) else "linear",
    #     x_range=shared_x_range, # p_feed.x_range 
    #     tools="pan,wheel_zoom,box_zoom,reset,save",
    # )

    # nbins = len(total_source.column_names) - 1 # remove datetime
    # # import pdb; pdb.set_trace()
    # for color_idx, ind_col in enumerate(total_source.column_names):
    #     if ind_col != "datetime":

    #         ind_range = total_source.data[ind_col]
    #         p_ind.extra_y_ranges[ind_col] = Range1d( # multi-y_axis
    #             start=min(ind_range), 
    #             end=max(ind_range)
    #         )
        
    #         p_ind.line(
    #             'datetime', ind_col, source=total_source, 
    #             line_width=2, color=tableau10[color_idx], y_range_name=ind_col, legend_label=ind_col)

    #         y_axis = LinearAxis(y_range_name=ind_col, axis_label=ind_col)
    #         # y_axis.bounds = (color_idx/nbins, (color_idx+1)/nbins)  # 从中间到顶部
    #         p_ind.add_layout(y_axis, 'right' if color_idx % 2 == 0 else 'left')

    # # 设置图例 点击策略为"hide"（默认行为：点击隐藏，再次点击显示）
    # p_ind.legend.click_policy = "hide"
    # p_ind.legend.location = "top_left"

    # # # 设置自定义 JavaScript 回调实现"只显示一条线"
    # # callback = CustomJS(args=dict(renderers=renderers), code="""
    # #     // 获取所有渲染器
    # #     const allRenderers = Object.values(renderers);
        
    # #     // 获取被点击的图例项对应的渲染器
    # #     const activeRenderer = this.source;
        
    # #     // 隐藏所有线条
    # #     allRenderers.forEach(renderer => {
    # #         renderer.visible = false;
    # #     });
        
    # #     // 只显示被点击的线条
    # #     activeRenderer.visible = true;
    # # """)

    # # # 为每个渲染器添加回调
    # # for renderer in renderers.values():
    # #     renderer.js_on_change('visible', callback)

    # hover = HoverTool(
    #     tooltips=tooltips,
    #     formatters={
    #         '@datetime': 'datetime'
    #     },
    #     mode='vline', # 'mouse': 离散数据 'hline': 数值对比 'vline': 时间序列
    # )

    # crosshair = CrosshairTool( # 十字线联动
    #     dimensions='height',
    #     line_alpha=0.3,
    #     line_color='gray',
    #     line_width=1)

    # p_ind.add_tools(hover, crosshair)

    # show(p_ind)

# --------------------------------------------------------------- observe -----------------------------------------------------------------

    # reuse indicator logic
    n_obs = ['Broker(MetaBtData,barplot=True)', 'Trades - Net Profit/Loss', 'DrawDown(MetaBtData,barplot=True)', 
    'DrawDownLength(MetaBtData,barplot=True)', 'BuySell(MetaBtData,barplot=True)', 'Benchmark(MetaBtData,barplot=True)']
