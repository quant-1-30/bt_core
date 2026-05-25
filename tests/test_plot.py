import pandas as pd
import numpy as np
from bokeh.plotting import figure, show
from bokeh.layouts import column
from bokeh.models import (ColumnDataSource, HoverTool, CrosshairTool, 
                          Span, CustomJS, PanTool, WheelZoomTool, NumeralTickFormatter,
                          TabPanel, Tabs)


tableau20 = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', 
    '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#aec7e8', '#ffbb78'
]


def load_and_align(file_path: str, file_type: str = 'parquet', tick_unit: str = 's') -> pd.DataFrame:
        """
            metrics, value, datetime
        """
        if file_type == 'parquet':
            df = pd.read_parquet(file_path)
        elif file_type == 'csv':
            df = pd.read_csv(file_path)
        elif file_type == 'jsonl':
            df = pd.read_json(file_path, lines=True)
        else:
            raise ValueError("Unsupported file type")

        if not {'metrics', 'value', 'datetime'}.issubset(df.columns):
            raise ValueError("Data must contain 'metrics', 'value', 'tick' columns")

        import pdb; pdb.set_trace()
        df['datetime'] = pd.to_datetime(df['datetime'], unit=tick_unit)

        align_df = df.pivot_table(
            index='datetime', 
            columns='metrics', 
            values='value', 
            aggfunc='last' # keep last in same tick of metrics
        )

        # align notify_timer and on_dt_over
        align_df = align_df.ffill()
        
        if 'close' in align_df.columns:
            align_df = align_df.dropna(subset=['close'])

        align_df.reset_index(inplace=True)
        return align_df


class PlotScheme(object):
    def __init__(self):
        self.figure_width = 1200
        self.main_height = 400   
        self.ind_height = 250    # Indicator 选项卡的高度
        self.sub_height = 200    # Analyzer 子图的高度

        self.vbar_width = 0.6 * 24 * 60 * 60 * 1000 
        self.line_width = 1.5 
        self.scaling_factor = 0.15 
        self.location = "top_left"


class Plot(object):
    def __init__(self, scheme=None):
        self.scheme = scheme or PlotScheme()
        
        self.fig_main = None
        self.fig_ind_tabs = None
        self.fig_analyzers = []
        
        self.all_figures = [] 
        # Crosshair and Hover 
        self.bt_tooltips = {} 
        self.bt_renderers = {} 
        self.datasource = None

    def plot_from_wide_df(self, df: pd.DataFrame, candle: bool = True):
        
        df = df.rename(columns=lambda x: x.decode('utf-8') if isinstance(x, bytes) else str(x))
        if not pd.api.types.is_datetime64_any_dtype(df['datetime']):
            df['datetime'] = pd.to_datetime(df['datetime'])

        self.datasource = ColumnDataSource(df)
        available_cols = set(df.columns)

        feed_cols = {'datetime', 'open', 'high', 'low', 'close', 'volume'} 
        df_feed_cols = list(feed_cols.intersection(available_cols))
        ind_cols = [c for c in df.columns if c.startswith('ind_')]
        analyzer_cols = [c for c in df.columns if c not in df_feed_cols and not c.startswith('ind_') and c != 'datetime']

        if 'close' in df.columns:
            self._plot_main(candle)

        if ind_cols:
            self._plot_indicators_tabbed(ind_cols)

        if analyzer_cols:
            self._plot_analyzers(analyzer_cols)

        c_lt = self._build_layout()
        show(c_lt)
        
    def _plot_main(self, candle):
        dmaster = self.datasource
        
        self.fig_main = figure(
            width=self.scheme.figure_width, height=self.scheme.main_height,
            title="Price & Volume", x_axis_type="datetime",
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )
        
        self.all_figures.append(self.fig_main)
        _tooltip = [("Date", "@datetime{%F %T}")]
        renderers = []
        
        # --- Volume ---
        if 'volume' in dmaster.data:
            vol_data = np.array(dmaster.data['volume'])
            v_max = np.nanmax(vol_data) if not np.all(np.isnan(vol_data)) else 1
            p_min = np.nanmin(dmaster.data['low']) if 'low' in dmaster.data else np.nanmin(dmaster.data['close'])
            p_max = np.nanmax(dmaster.data['high']) if 'high' in dmaster.data else np.nanmax(dmaster.data['close'])
            p_range = p_max - p_min if p_max > p_min else 1
            
            dmaster.data['volume_scaled'] = p_min + (vol_data / v_max) * (p_range * self.scheme.scaling_factor)
            self.fig_main.vbar(x='datetime', top='volume_scaled', bottom=p_min, width=self.scheme.vbar_width,
                               source=dmaster, fill_alpha=0.3, line_alpha=0, color="gray", legend_label="Volume")
            _tooltip.append(("Volume", "@volume{0.00}"))

        # --- Price / Candle ---
        close_line = self.fig_main.line("datetime", "close", source=dmaster, line_width=self.scheme.line_width, color='#1f77b4', legend_label="Close")
        renderers.append(close_line)
        _tooltip.append(("Close", "@close{0.00}"))

        if candle and {'open', 'high', 'low'}.issubset(dmaster.data.keys()):
            _tooltip.insert(1, ("Open", "@open{0.00}"))
            _tooltip.insert(2, ("High", "@high{0.00}"))
            _tooltip.insert(3, ("Low", "@low{0.00}"))

            op, cl = np.array(dmaster.data['open']), np.array(dmaster.data['close'])
            dmaster.data['top_body'] = np.maximum(op, cl)
            dmaster.data['bottom_body'] = np.minimum(op, cl)
            dmaster.data['line_color'] = np.where(cl >= op, '#D32F2F', '#009624')
            dmaster.data['fill_color'] = np.where(cl >= op, '#FF5252', '#00C853')

            self.fig_main.segment(x0='datetime', y0='top_body', x1='datetime', y1='high', color='line_color', source=dmaster)
            self.fig_main.segment(x0='datetime', y0='bottom_body', x1='datetime', y1='low', color='line_color', source=dmaster)
            self.fig_main.vbar(x='datetime', width=self.scheme.vbar_width, top='top_body', bottom='bottom_body',
                               source=dmaster, fill_color='fill_color', line_color="line_color", legend_label="Candle")

        self.fig_main.legend.location = self.scheme.location
        self.bt_tooltips[self.fig_main] = _tooltip
        self.bt_renderers[self.fig_main] = renderers

    def _plot_indicators_tabbed(self, ind_cols):
        panels = []
        
        for i, col in enumerate(ind_cols):
            # Indicator Figure
            p_ind = figure(
                width=self.scheme.figure_width, 
                height=self.scheme.ind_height,
                x_axis_type="datetime",
                x_range=self.fig_main.x_range,  # shared x
                tools="pan,wheel_zoom,box_zoom,reset,save",
            )
            
            color = tableau20[i % len(tableau20)]
            ind_line = p_ind.line('datetime', col, source=self.datasource, line_width=self.scheme.line_width, color=color)
            
            # Hover
            self.all_figures.append(p_ind)
            # self.bt_tooltips[p_ind] = [("Date", "@datetime{%F %T}"), (col, f"@{col}{{0.000}}")]
            self.bt_tooltips[p_ind] = [("Date", "@datetime{%F %T}"), (col, f"@{{{col}}}{{0.000}}")]
            self.bt_renderers[p_ind] = [ind_line]

            # bokeh Panel / 3.0 TabPanel
            panel = TabPanel(child=p_ind, title=col)
            panels.append(panel)
            
        self.fig_ind_tabs = Tabs(tabs=panels)

    def _plot_analyzers(self, analyzers):
        for i, col in enumerate(analyzers):
            p_sub = figure(
                title=f"Analyzer: {col}",
                width=self.scheme.figure_width, 
                height=self.scheme.sub_height,
                x_axis_type="datetime",
                x_range=self.fig_main.x_range, 
                tools="pan,wheel_zoom,box_zoom,reset,save",
            )

            color = tableau20[i % len(tableau20)]
            sub_line = p_sub.line('datetime', col, source=self.datasource, line_width=2, color=color)

            if i < len(analyzers) - 1:
                p_sub.xaxis.visible = False

            self.all_figures.append(p_sub)
            # self.bt_tooltips[p_sub] = [("Date", "@datetime{%F %T}"), (col, f"@{col}{{0.0000}}")] 
            self.bt_tooltips[p_sub] = [("Date", "@datetime{%F %T}"), (col, f"@{{{col}}}{{0.0000}}")] 
            self.bt_renderers[p_sub] = [sub_line]
            self.fig_analyzers.append(p_sub)

    def _build_layout(self):
        """ Column vertical UI Tabs"""
        _vlines = []
        for _plt in self.all_figures:
            vline = Span(location=0, dimension='height', line_color='red', line_width=1, line_alpha=0)
            _plt.add_layout(vline)
            _vlines.append(vline)
    
        # JavaScript 
        hover_callback = CustomJS(args=dict(vlines=_vlines), code="""
            for (let i = 0; i < vlines.length; i++) {
                vlines[i].line_alpha = 0.5;
                vlines[i].location = cb_data.geometry.x;
            }
        """)
        
        for _plt in self.all_figures:
            hover = HoverTool(
                tooltips=self.bt_tooltips[_plt],
                formatters={'@datetime': 'datetime'},
                mode='vline', 
                callback=hover_callback,
                renderers=self.bt_renderers[_plt]
            )
            _plt.add_tools(hover, CrosshairTool(dimensions='both', line_alpha=0.5))
            _plt.yaxis.formatter = NumeralTickFormatter(format="0,0.00")
            _plt.toolbar.active_scroll = _plt.select_one(WheelZoomTool)
 
        layout_items = [self.fig_main]
        if self.fig_ind_tabs:
            layout_items.append(self.fig_ind_tabs)
        layout_items.extend(self.fig_analyzers)
        
        return column(layout_items, sizing_mode='stretch_width')



if __name__ == "__main__":
    
    _p = Plot()

    # p_str = "/Users/hengxinliu/startup/bt_core/tests/logs/log_cerebro_0.parquet"
    p_str = "/Users/hengxinliu/startup/bt_core/tests/experiment/logs/log_cerebro_0.parquet"
    df = load_and_align(p_str)

    _p.plot_from_wide_df(df)
