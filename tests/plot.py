import pandas as pd
import numpy as np
from bokeh.plotting import figure, show
from bokeh.layouts import gridplot, column
from bokeh.models import CDSView, BooleanFilter, Range1d, HoverTool, CrosshairTool, LinearAxis, Tabs, Span, CustomJS, PanTool, WheelZoomTool, NumeralTickFormatter
from bokeh.io import export_png, export_svg

from scheme import tableau10, tableau20
from util import resample, create_datasource, merge_cds


if __name__ == "__main__":

    datasource, _ = create_datasource("out.csv")

    bt_source = datasource["Feed"]
    strat = datasource["Strategy"]
    
    bt_source, _tooltip = merge_cds(bt_source, strat) # # Feed and Strategy 整合
    bt_tooltips = [_tooltip]
    bt_renderers = []

    # 创建主图表
    p_main = figure(
        width=1500,
        height=400,
        title="Backtest",
        x_axis_type="datetime", # "linear",
        tools="pan,wheel_zoom,box_zoom,reset,save", # 基础工具
        # active_drag='pan',
        # active_scroll='wheel_zoom',
        tooltips=None
    )

    # 计算实体顶部和底部
    bt_source.data['top_body'] = np.maximum(bt_source.data['open'], bt_source.data['close'])
    bt_source.data['bottom_body'] = np.minimum(bt_source.data['open'], bt_source.data['close'])

    # 计算影线长度和实体高度
    bt_source.data['body_height'] = bt_source.data['top_body'] - bt_source.data['bottom_body']
    bt_source.data['upper_shadow'] = bt_source.data['high'] - bt_source.data['top_body']
    bt_source.data['lower_shadow'] = bt_source.data['bottom_body'] - bt_source.data['low']

    bt_source.data['color'] = np.where(bt_source.data['close'] >= bt_source.data['open'], 'green', 'red')
    bt_source.data['line_color'] = np.where(bt_source.data['close'] >= bt_source.data['open'], 'darkgreen', 'darkred')
    
    price_line = p_main.line("datetime", "close", source=bt_source,
                line_width=2, color=tableau10[0], legend_label="close")

    # 绘制上影线：从实体顶部到最高价
    p_main.segment(x0='datetime', y0='top_body', x1='datetime', y1='high', 
            color='line_color', line_width=1, source=bt_source, legend_label="上影线")

    # 绘制下影线：从实体底部到最低价
    p_main.segment(x0='datetime', y0='bottom_body', x1='datetime', y1='low', 
            color='line_color', line_width=1, source=bt_source, legend_label="下影线")
    
    # 绘制实体
    p_main.vbar(
        x='datetime', 
        width=1,
        top='top_body',
        bottom='bottom_body',
        source=bt_source,
        fill_color='color',
        # fill_alpha=0.7,
        line_color="line_color",
        line_width=1,
        legend_label="实体"
    )
    
    price_range = (bt_source.data['high'] - bt_source.data['low']).mean()
    bt_source.data['buy_price'] = bt_source.data['low'] - price_range * 0.05
    bt_source.data['sell_price'] = bt_source.data['high'] + price_range * 0.05

    b_mask = bt_source.data["buy"] > 0.0
    bview = CDSView(name="buy_filter", filter=BooleanFilter(b_mask))
    p_main.scatter("datetime", "buy_price", marker="triangle", source=bt_source, view=bview, size=15, color="navy", alpha=0.6, legend_label="正三角形")

    s_mask = bt_source.data["sell"] < -0.0
    sview = CDSView(name="sell_filter", filter=BooleanFilter(s_mask))
    p_main.scatter("datetime", "sell_price", marker="inverted_triangle", source=bt_source, view=sview, size=15, color="firebrick", alpha=0.6, legend_label="倒三角形")

    bt_renderers.append(price_line)
    
# ------------------------------------------------------------------------ indicator ----------------------------------------------------------------

    n_inds = ['SMA(close,period=15)', 'SMA(SMA(close,period=15),period=5)', 'SMA(SMA(SMA(close,period=15),period=5),period=5)', 
            'SMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)', 'EMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)']

    ind_src_tuple = [datasource[name] for name in n_inds]
    ind_src, ind_tooltip = merge_cds(*ind_src_tuple)

    bt_tooltips.append(ind_tooltip)

    p_indicator = figure(
        title="Indicator",
        width=1500, 
        height=200,
        x_axis_type="datetime",
        x_range=p_main.x_range,  
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )
    
    p_indicator.yaxis.visible = False
    p_indicator.yaxis.axis_label = ""

    # nbins = len(ind_srcs.column_names) - 1
    for color_idx, ind_col in enumerate(ind_src.column_names):
        if ind_col != "datetime":

            ind_range = ind_src.data[ind_col]

            p_indicator.extra_y_ranges[ind_col] = Range1d( # multi-y_axis
                start=min(ind_range), 
                end=max(ind_range)
            )
        
            ind_line = p_indicator.line(
                'datetime', ind_col, source=ind_src,
                line_width=2, color=tableau10[color_idx], y_range_name=ind_col, legend_label=ind_col)

            y_axis = LinearAxis(
                y_range_name=ind_col, 
                axis_label=ind_col, 
                axis_label_text_font_size='8pt', 
                major_label_text_font_size='8pt')   # 设置刻度标签字体大小
            # y_axis.bounds = (color_idx/nbins, (color_idx+1)/nbins)  # 从中间到顶部
            p_indicator.add_layout(y_axis, 'left' if color_idx % 2 == 0 else 'right')

    bt_renderers.append(ind_line)

# --------------------------------------------------------------------- observe gridplots ----------------------------------------------------------------------
    
    # or reuse indicator in one figure
    n_obs = ['Broker(Feed,barplot=True)', 'Trades - Net Profit/Loss', 'DrawDown(Feed,barplot=True)', 
    'DrawDownLength(Feed,barplot=True)', 'BuySell(Feed,barplot=True)', 'Benchmark(Feed,barplot=True)']

    p_observers = []

    for i, name in enumerate(n_obs):
        obs_src = datasource[name]
        title = "" if i > 0 else "Observer" # f'Observer: {name.split("(")[0]}',
        p_obs = figure(
            title = title,
            width=1500, 
            height=200,
            x_axis_type="datetime",
            x_range=p_main.x_range,
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )

        obs_tooltip = [("Date", "@datetime{%F}")]

        for idx, col in enumerate(obs_src.column_names):
            if col != "datetime":
                color_idx = idx % len(tableau20)
                obs_line = p_obs.line('datetime', col, source=obs_src, line_width=2, color=tableau20[color_idx], legend_label=col)

        chain_tooltip = [f" {key}: @{{{key}}}{{0.2f}}<br>" for key in obs_src.column_names if  key != "datetime"]
        obs_tooltip.insert(0, (name, ''.join(chain_tooltip)))

        bt_tooltips.append(obs_tooltip)
 
        if i < len(n_inds):
            p_obs.xaxis.visible = False
        p_observers.append(p_obs)

        bt_renderers.append(obs_line)

# --------------------------------------------------------------------------- plt ----------------------------------------------------------------------
    
    bt_plts = [p_main, p_indicator]
    bt_plts.extend(p_observers)
    bt_vlines = []
    # add vline
    for _plt in bt_plts:
        vline = Span(location=0, dimension='height', line_color='red', line_width=1, line_alpha=0)
        _plt.add_layout(vline)
        bt_vlines.append(vline)
    
    # set HoverTool and CrosshairTool
    hover_callback = CustomJS(
        args=dict(vlines=bt_vlines), 
        code="""
            // 悬停时显示所有参考线
            for (let i = 0; i < vlines.length; i++) {
                vlines[i].line_alpha = 0.5;
                vlines[i].location = cb_data.geometry.x;
            }
        """
    )

    for idx, _plt in enumerate(bt_plts):
        _tooltip = bt_tooltips[idx]
        hover = HoverTool(
            tooltips=_tooltip,
            formatters={
                '@datetime': 'datetime'
            },
            mode='vline', 
            callback=hover_callback,
            renderers = [bt_renderers[idx]],
            point_policy="follow_mouse"
        )

        crosshair = CrosshairTool(
            dimensions='both',
            line_alpha=0.5,
            line_color='black',
            line_width=1)
        
        _plt.add_tools(hover, crosshair)
        _plt.legend.click_policy = "hide"
        _plt.legend.location = "top_left"
        _plt.background_fill_alpha = 0.05  
        _plt.border_fill_alpha = 0.05    
        _plt.yaxis.formatter = NumeralTickFormatter(format="0,0.00")  # 保留两位小数
 

    # plot gridplot
    grid = gridplot(bt_plts, ncols=1, sizing_mode='stretch_width') # layout = column(bt_plts)
    grid.toolbar.active_drag=PanTool()
    grid.toolbar.active_scroll=WheelZoomTool()

    show(grid)
    # # 导出为 PNG，设置分辨率
    # for e_p in show_p:
    #     export_png(e_p, filename=f"{e_p.name}.png", scale_factor=1, 
    #             width=1600, height=1200) # export_svg / need selenium driver 
