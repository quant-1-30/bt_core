import pandas as pd
import numpy as np
from bokeh.plotting import figure, show, output_file
from bokeh.layouts import gridplot, column
from bokeh.models import CDSView, BooleanFilter, Range1d, HoverTool, CrosshairTool, LinearAxis, Tabs, Span, CustomJS, PanTool, WheelZoomTool, NumeralTickFormatter
from bokeh.io import export_png, export_svg

from .scheme import tableau10, tableau20
from .utils import resample, create_datasource, merge_cds

from backtest.metabase import with_metaclass, AutoInfoClass, MetaParams


class PlotScheme(object):
    def __init__(self):
        self.figure_width = 1500
        self.figure_height = [400, 200, 200]
        # self.line_width=1
        # self.line_alpha=0
        self.vbar_width = 3 

        self.fill_alpha = 0.05 # transparent

        # layout
        self.ncols = 1 # gridplot
        self.click_policy = "hide"
        self.location = "top_left"
        self.font_size = "8pt"

        # save figure
        self.width = 16
        self.height = 9
        self.dpi = 300
        self.tight = True

        # self.sharex = None
        # self.figs = list()
        # self.cursors = list()
        # self.daxis = collections.OrderedDict()
        # self.vaxis = list()
        # self.zorder = dict()
        # self.coloridx = collections.defaultdict(lambda: -1)
        # self.handles = collections.defaultdict(list)
        # self.labels = collections.defaultdict(list)
        # self.legpos = collections.defaultdict(int)


class Plot(with_metaclass(MetaParams, object)):
    params = (('scheme', PlotScheme()),)

    def __init__(self):
        
        self.bt_tooltips = list()
        self.bt_renderers = list()
        self.figures = list()
        
        self.datasource = None

    def plotdata(self):
        # shared_x = Range1d(data.index[0], data.index[-1]) # 同步x轴
        feed_src = self.datasource["Feed"]
        strat_src = self.datasource["Strategy"]
        feed_src, _tooltip = merge_cds(feed_src, strat_src) # 
        self.bt_tooltips.append(_tooltip)

        # 创建主图表
        p_main = figure(
            width=self.p.scheme.figure_width,
            height=self.p.scheme.figure_height[0],
            title="Backtest",
            x_axis_type="datetime", # "linear",
            tools="pan,wheel_zoom,box_zoom,reset,save", # 基础工具
            # active_drag='pan',
            # active_scroll='wheel_zoom',
            tooltips=None
        )

        # 计算实体顶部和底部
        feed_src.data['top_body'] = np.maximum(feed_src.data['open'], feed_src.data['close'])
        feed_src.data['bottom_body'] = np.minimum(feed_src.data['open'], feed_src.data['close'])

        # 计算影线长度和实体高度
        feed_src.data['body_height'] = feed_src.data['top_body'] - feed_src.data['bottom_body']
        feed_src.data['upper_shadow'] = feed_src.data['high'] - feed_src.data['top_body']
        feed_src.data['lower_shadow'] = feed_src.data['bottom_body'] - feed_src.data['low']

        feed_src.data['color'] = np.where(feed_src.data['close'] >= feed_src.data['open'], 'green', 'red')
        feed_src.data['line_color'] = np.where(feed_src.data['close'] >= feed_src.data['open'], 'darkgreen', 'darkred')
    
        price_line = p_main.line("datetime", "close", source=feed_src,
                    line_width=2, color=tableau10[0], legend_label="close")
        self.bt_renderers.append(price_line)

        # 绘制上影线：从实体顶部到最高价
        p_main.segment(x0='datetime', y0='top_body', x1='datetime', y1='high', 
                color='line_color', line_width=1, source=feed_src, legend_label="上影线")

        # 绘制下影线：从实体底部到最低价
        p_main.segment(x0='datetime', y0='bottom_body', x1='datetime', y1='low', 
                color='line_color', line_width=1, source=feed_src, legend_label="下影线")
    
        # 绘制实体
        p_main.vbar(
            x='datetime', 
            width=self.p.scheme.vbar_width,
            top='top_body',
            bottom='bottom_body',
            source=feed_src,
            fill_color='color',
            # fill_alpha=0.7,
            line_color="line_color",
            line_width=1,
            legend_label="实体"
        )
    
        # 绘制 策略买入与卖出点
        price_range = (feed_src.data['high'] - feed_src.data['low']).mean()
        feed_src.data['buy_price'] = feed_src.data['low'] - price_range * 0.05
        feed_src.data['sell_price'] = feed_src.data['high'] + price_range * 0.05

        b_mask = feed_src.data["buy"] > 0.0
        bview = CDSView(name="buy_filter", filter=BooleanFilter(b_mask))
        p_main.scatter("datetime", "buy_price", marker="triangle", source=feed_src, view=bview, size=15, color="navy", alpha=0.6, legend_label="正三角形")

        s_mask = feed_src.data["sell"] < -0.0
        sview = CDSView(name="sell_filter", filter=BooleanFilter(s_mask))
        p_main.scatter("datetime", "sell_price", marker="inverted_triangle", source=feed_src, view=sview, size=15, color="firebrick", alpha=0.6, legend_label="倒三角形")
        
        self.figures.append(p_main)
 
# ------------------------------------------------------------------------ indicator ----------------------------------------------------------------

    def plotind(self):
        # n_inds = ['SMA(close,period=15)', 'SMA(SMA(close,period=15),period=5)', 'SMA(SMA(SMA(close,period=15),period=5),period=5)', 
        #         'SMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)', 'EMA(SMA(SMA(SMA(close,period=15),period=5),period=5),period=10)']
        n_inds = ['SMA(close,period=25)', 'SMA(SMA(close,period=25),period=5)']

        subind_src = [self.datasource[name] for name in n_inds]
        ind_src, ind_tooltip = merge_cds(*subind_src)

        self.bt_tooltips.append(ind_tooltip)

        p_indicator = figure(
            title="Indicator",
            width=self.p.scheme.figure_width, 
            height=self.p.scheme.figure_height[1],
            x_axis_type="datetime",
            x_range=self.figures[0].x_range,  
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
                    axis_label_text_font_size=self.p.scheme.font_size, 
                    major_label_text_font_size=self.p.scheme.font_size)   # 设置刻度标签字体大小
                # y_axis.bounds = (color_idx/nbins, (color_idx+1)/nbins)  # 从中间到顶部
                p_indicator.add_layout(y_axis, 'left' if color_idx % 2 == 0 else 'right')

        self.bt_renderers.append(ind_line) # keep main indicator
        self.figures.append(p_indicator)

# --------------------------------------------------------------------- observe gridplots ----------------------------------------------------------------------
    
    def plotobs(self):
        # or reuse indicator in one figure
        n_obs = ['Broker(Feed,barplot=True)', 'Trades - Net Profit/Loss', 'DrawDown(Feed,barplot=True)', 
         'DrawDownLength(Feed,barplot=True)', 'BuySell(Feed,barplot=True)', 'Benchmark(Feed,barplot=True)']

        p_observers = []

        for i, name in enumerate(n_obs):
            obs_src = self.datasource[name]
            title = "" if i > 0 else "Observer" # f'Observer: {name.split("(")[0]}',

            p_obs = figure(
                title = title,
                width=self.p.scheme.figure_width, 
                height=self.p.scheme.figure_height[2],
                x_axis_type="datetime",
                x_range=self.figures[0].x_range,
                tools="pan,wheel_zoom,box_zoom,reset,save",
            )

            obs_tooltip = [("Date", "@datetime{%F}")]

            for idx, col in enumerate(obs_src.column_names):
                if col != "datetime":
                    color_idx = idx % len(tableau20)
                    obs_line = p_obs.line('datetime', col, source=obs_src, line_width=2, color=tableau20[color_idx], legend_label=col)

            chain_tooltip = [f" {key}: @{{{key}}}{{0.2f}}<br>" for key in obs_src.column_names if  key != "datetime"]
            obs_tooltip.insert(0, (name, ''.join(chain_tooltip)))

            self.bt_tooltips.append(obs_tooltip)
 
            if i < len(n_obs) - 1:
                p_obs.xaxis.visible = False
            p_observers.append(p_obs)

            self.bt_renderers.append(obs_line)

        self.figures.extend(p_observers)

# --------------------------------------------------------------------------- plt ----------------------------------------------------------------------

    def show(self):

        # add vline
        _vlines = []
        for _plt in self.figures:
            vline = Span(location=0, dimension='height', line_color='red', line_width=1, line_alpha=0)
            _plt.add_layout(vline)
            _vlines.append(vline)
    
        # set HoverTool and CrosshairTool
        hover_callback = CustomJS(
            args=dict(vlines=_vlines), 
            code="""
                // 悬停时显示所有参考线
                for (let i = 0; i < vlines.length; i++) {
                    vlines[i].line_alpha = 0.5;
                    vlines[i].location = cb_data.geometry.x;
                }
            """
        )
        
        for idx, _plt in enumerate(self.figures):
            _tooltip = self.bt_tooltips[idx]
            hover = HoverTool(
                tooltips=_tooltip,
                formatters={
                    '@datetime': 'datetime'
                },
                mode='vline', 
                callback=hover_callback,
                renderers = [self.bt_renderers[idx]],
                point_policy="follow_mouse"
            )

            crosshair = CrosshairTool(
                dimensions='both',
                line_alpha=0.5,
                line_color='black',
                line_width=1)

            _plt.add_tools(hover, crosshair)
            _plt.legend.click_policy = self.p.scheme.click_policy
            _plt.legend.location = self.p.scheme.location
            _plt.background_fill_alpha = self.p.scheme.fill_alpha
            _plt.border_fill_alpha = self.p.scheme.fill_alpha    
            _plt.yaxis.formatter = NumeralTickFormatter(format="0,0.00")  # 保留两位小数
 
        # plot gridplot
        grid = gridplot(self.figures, ncols=self.p.scheme.ncols, sizing_mode='stretch_width') # layout = column(bt_plts)
        grid.toolbar.active_drag=PanTool()
        grid.toolbar.active_scroll=WheelZoomTool()

        show(grid)
        return grid

    def savefig(self, fig, filename):
        # 保存为 HTML 文件
        output_file(f"{filename}.html")
        save(grid)

        # fig.set_size_inches(self.p.scheme.width, self.p.scheme.height)
        # bbox_inches = 'tight' * self.p.scheme.tight or None
        # fig.savefig(filename, dpi=self.p.scheme.dpi, bbox_inches=bbox_inches) 
        # # 导出为 PNG，设置分辨率
        # for e_p in show_p:
        #     export_png(e_p, filename=f"{filename}.png", scale_factor=1, 
        #             width=self.p.scheme.width, height=self.p.scheme.heigh) # export_svg / need selenium driver

    def plot(self, csv_path, freq, filename=None, save=False):
        self.datasource = create_datasource(csv_path, freq)

        self.plotdata() # Feed and Strategy 整合
        self.plotind() # Indicator
        self.plotobs() # Observer

        grid_plot = self.show()
        
        if save:
            self.savefig(grid_plot, filename)
