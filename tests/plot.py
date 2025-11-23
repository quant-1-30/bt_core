import pandas as pd
import numpy as np
from bokeh.plotting import figure, show
from bokeh.layouts import gridplot, column
from bokeh.models import ColumnDataSource, CDSView, BooleanFilter, IndexFilter, GroupFilter, Range1d, HoverTool, LinearAxis, Tabs, Span, CrosshairTool, CustomJS
from bokeh.io import export_png, export_svg

from scheme import tableau10
from util import resample


def create_datasource(csv_path):
 # 缺少 indicator 与 observer 个数 与 plotinfo 配置 需要单独写入文件 或者 csv 注释行
    data = pd.read_csv(csv_path, header=1, sep=";")

    datasource = {}
    datasource["id"] = data.iloc[:,0].to_numpy()
    
    names_col = data.columns[1::2]
    datas_col = data.columns[2::2]

    for n_c, d_c in zip(names_col, datas_col):
        _source = {} 
        c_v = data.loc[:, d_c].astype(str)
        split_c_v = c_v.str.split(',', expand=True) 
        split_c_v.columns = d_c.split(',')
        resample_c_v = resample(n_c, split_c_v, data)
        
        for key, v in resample_c_v.items():
            arr = v.to_numpy()
            if key != "datetime":
                arr = np.where(np.isnan(arr), 0.0, arr)

            _source[key] = arr
        datasource[n_c] = ColumnDataSource(data=_source)
    shared_x = Range1d(data.index[0], data.index[-1]) # 同步x轴
    return datasource, shared_x


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
        chain_tooltip = [f" {key}: @{{{key}}}{{0.2f}}" for key in source.column_names if  key != "datetime"]
        tooltips.append((name, ','.join(chain_tooltip)))
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



if __name__ == "__main__":

   
    datasource, _ = create_datasource("out.csv")

    union_source = datasource["Feed"] # MetaBtData
    strat = datasource["Strategy"] # datetime buy sell 
    # Feed and Strategy 整合
    union_source, _tooltip = merge_cds(union_source, strat)
    
    # 创建主图表
    main_p = figure(
        width=1500,
        height=400,
        title="backtest",
        x_axis_type="datetime", # x_axis_type="datetime" if isinstance(dates[0], (np.datetime64, pd.Timestamp)) else "linear",
        # x_range=shared_x_range, # main_p.x_range 
        tools="pan,wheel_zoom,box_zoom,reset,save", # 基础工具
        active_drag='pan',
        active_scroll='wheel_zoom',
        tooltips=None
    )

    # 计算实体顶部和底部
    union_source.data['top_body'] = np.maximum(union_source.data['open'], union_source.data['close'])
    union_source.data['bottom_body'] = np.minimum(union_source.data['open'], union_source.data['close'])

    # 计算影线长度和实体高度
    union_source.data['body_height'] = union_source.data['top_body'] - union_source.data['bottom_body']
    union_source.data['upper_shadow'] = union_source.data['high'] - union_source.data['top_body']
    union_source.data['lower_shadow'] = union_source.data['bottom_body'] - union_source.data['low']

    # 添加 rect 所需的计算列
    union_source.data['body_center'] = (union_source.data['top_body'] + union_source.data['bottom_body']) / 2
    union_source.data['body_height'] = union_source.data['top_body'] - union_source.data['bottom_body']

    union_source.data['color'] = np.where(union_source.data['close'] >= union_source.data['open'], 'green', 'red')
    union_source.data['line_color'] = np.where(union_source.data['close'] >= union_source.data['open'], 'darkgreen', 'darkred')

    # 绘制上影线：从实体顶部到最高价
    upper = main_p.segment(x0='datetime', y0='top_body', x1='datetime', y1='high', 
            color='line_color', line_width=1, source=union_source, legend_label="上影线")

    # 绘制下影线：从实体底部到最低价
    bottom = main_p.segment(x0='datetime', y0='bottom_body', x1='datetime', y1='low', 
            color='line_color', line_width=1, source=union_source, legend_label="下影线")

    close = main_p.line("datetime", "close", source=union_source,
                line_width=2, color=tableau10[0], legend_label="close")
    
    # 绘制实体
    # body_renderer = p.vbar(
    #     x='datetime', width=0.8, top='top_body', bottom='bottom_body', 
    #     fill_color='color', line_color='line_color', source=union_source)
   
    # 转换为 rect 的代码
    body_renderer = main_p.rect(
        x='datetime', 
        y='body_center',  # 计算中心点y坐标
        width=0.8, 
        height='body_height',  # 计算高度
        fill_color='color', 
        line_color='line_color', 
        source=union_source,
        legend_label="实体"
    )

    # strategy
    buy = union_source.data["buy"]
    # import pdb; pdb.set_trace()
    b_mask = buy > 0.0
    bview = CDSView(name="buy_filter", filter=BooleanFilter(b_mask))
    main_p.scatter("datetime", "buy", marker="triangle", source=union_source, view=bview, size=15, color="navy", alpha=0.6, legend_label="正三角形")

    sell = union_source.data["sell"]
    s_mask = sell < -0.0
    # import pdb; pdb.set_trace()
    sview = CDSView(name="sell_filter", filter=BooleanFilter(s_mask))
    main_p.scatter("datetime", "sell", marker="inverted_triangle", source=union_source, view=sview, size=15, color="firebrick", alpha=0.6, legend_label="倒三角形")

    # 添加交互工具
    hover = HoverTool(
        # tooltips=[
        #     ("Date", "@datetime{%F}"), # %Y%m%d
        #     ("Open", "@open{0.2f}"),
        #     ("High", "@high{0.2f}"),
        #     ("Low", "@low{0.2f}"),
        #     ("Close", "@close{0.2f}"),
        #     ("Volume", "@volume{0,0}"),
        #     ("Date", "@datetime{%F}"), # %Y%m%d
        #     ("buy", "@buy{0.0f}"), # 保留0为小数 四舍五入 / {0} 截断
        #     ("sell", "@sell{0.0f}"),
        # ],
        tooltips=_tooltip,
        formatters={
            '@datetime': 'datetime'
        },
        mode='vline',
        renderers=[close] # 不支持 rect / vbar
    )

    crosshair = CrosshairTool( # 十字线联动
        dimensions='height',
        line_alpha=0.3,
        line_color='gray',
        line_width=1
    )
    
    main_p.add_tools(hover)
    main_p.add_tools(CrosshairTool())
    
    main_p.legend.location = "top_left"
    main_p.legend.click_policy = "hide"  # 点击图例可隐藏/显示
    main_p.yaxis.axis_label = "价格"
    
# ------------------------------------------------------------------------ indicator ----------------------------------------------------------------

    n_inds = ['SMA(close,period=15)', 'SMA(SMA(close,period=15),period=5)', 'SMA(SMA(SMA(close,period=15),period=5),period=5)', 
            'SMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)', 'EMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)']

    ind_src = [datasource[name] for name in n_inds]
    ind_srcs = merge_cds(*ind_src)

    _p_ind = figure(
        title="indicator",
        width=1500, 
        height=400,
        x_axis_type="datetime", # x_axis_type="datetime" if isinstance(dates[0], (np.datetime64, pd.Timestamp)) else "linear",
        x_range=main_p.x_range, # 
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )

    # nbins = len(ind_srcs.column_names) - 1
    for color_idx, ind_col in enumerate(ind_srcs.column_names):
        if ind_col != "datetime":

            ind_range = ind_srcs.data[ind_col]

            _p_ind.extra_y_ranges[ind_col] = Range1d( # multi-y_axis
                start=min(ind_range), 
                end=max(ind_range)
            )
        
            _p_ind.line(
                'datetime', ind_col, source=ind_srcs,
                line_width=2, color=tableau10[color_idx], y_range_name=ind_col, legend_label=ind_col)

            y_axis = LinearAxis(y_range_name=ind_col, axis_label=ind_col)
            # y_axis.bounds = (color_idx/nbins, (color_idx+1)/nbins)  # 从中间到顶部
            _p_ind.add_layout(y_axis, 'right' if color_idx % 2 == 0 else 'left')

    hover = HoverTool(
        tooltips=tooltips,
        formatters={
            '@datetime': 'datetime'
        },
        mode='vline', # 'mouse': 离散数据 'hline': 数值对比 'vline': 时间序列
    )

    crosshair = CrosshairTool( # 十字线联动
        dimensions='height',
        line_alpha=0.3,
        line_color='gray',
        line_width=1)

    _p_ind.add_tools(hover, crosshair)
    # 设置图例 点击策略为"hide"（默认行为：点击隐藏，再次点击显示）
    _p_ind.legend.click_policy = "hide"
    _p_ind.legend.location = "top_left"

    layout = column([main_p, main_p, _p_ind])
    show(layout)

# --------------------------------------------------------------------- observe gridplots ----------------------------------------------------------------------
    
    # or reuse indicator in one figure
    n_obs = ['Broker(MetaBtData,barplot=True)', 'Trades - Net Profit/Loss', 'DrawDown(MetaBtData,barplot=True)', 
    'DrawDownLength(MetaBtData,barplot=True)', 'BuySell(MetaBtData,barplot=True)', 'Benchmark(MetaBtData,barplot=True)']

    tooltips = []
    obs_plts = []
    obs_vlines = []

    for i, name in enumerate(n_obs):
        obs_src = datasource[name]

        obs_p = figure(
            # title=name,
            title='',
            width=1500, 
            height=400,
            x_axis_type="datetime", # x_axis_type="datetime" if isinstance(dates[0], (np.datetime64, pd.Timestamp)) else "linear",
            x_range=shared_x_range, # main_p.x_range 
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )

        vline = Span(location=0, dimension='height', line_color='red', line_width=1, line_alpha=0)
        obs_vlines.append(vline)
        obs_p.add_layout(vline)

        obs_tooltip = [("Date", "@datetime{%F}")]

        for idx, col in enumerate(obs_src.column_names):
            if col != "datetime":
                color_idx = idx % len(tableau10)
                p_ind.line(
                    'datetime', col, source=ind_source, 
                    line_width=2, color=tableau10[color_idx], legend_label=col)
                # ind_tooltip.append((col, f"@{{{col}}}{{0.2f}}"))
        chain_tooltip = [f" {key}: @{{{key}}}{{0.2f}}" for key in ind_source.column_names if  key != "datetime"]
        obs_tooltip.insert(0, (name, ','.join(chain_tooltip)))
        tooltips.append(ind_tooltip)
 
        obs_p.legend.location = "top_left"
        obs_p.legend.background_fill_alpha = 0.3  # 0-1之间的值，0为完全透明，1为完全不透明
        obs_p.legend.border_line_alpha = 0.3

        obs_p.yaxis.axis_label = "指标"

        if i < len(n_inds) - 1:
            obs_p.xaxis.visible = False

        obs_plts.append(obs_p)


    # 创建统一的回调
    hover_callback = CustomJS(
        args=dict(vlines=obs_vlines), 
        code="""
            // 悬停时显示所有参考线
            for (let i = 0; i < vlines.length; i++) {
                vlines[i].line_alpha = 0.5;
                vlines[i].location = cb_data.geometry.x;
            }
        """
    )

    for idx, _plt in enumerate(obs_plots):
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
    
    grid = gridplot(obs_plots, ncols=1)
    # grid = gridplot(all_plots, ncols=ncols, plot_width=400, plot_height=200, sizing_mode='stretch_width')
    # obs_plots.insert(0, main_p)
    # layout = column(*obs_plots)
    # show(layout)
    show(grid)

    # 导出为 PNG，设置分辨率
    export_png(p, filename="plot_high_dpi.png", 
               width=1600, height=1200)  # 2倍尺寸提高有效DPI

    # 或者导出为 SVG（矢量格式，无限分辨率）
    export_svg(p, filename="plot_vector.svg")
