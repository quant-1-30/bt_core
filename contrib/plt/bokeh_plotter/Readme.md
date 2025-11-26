
    # # 创建两个标签页
    # tab1 = Panel(child=trend_grid, title="趋势指标")
    # tab2 = Panel(child=oscillator_grid, title="震荡指标")
    # # 将标签页组合在一起
    # tabs = Tabs(tabs=[tab1, tab2])
    # show(tabs)
    
    # width=16, height=9, dpi=300, tight=True # dpi 用于计算 打印尺寸 --- 像素/dpi 单位英寸

    # p.triangle / p.inverted_triangle circle square triangle diamond
    # main_p.triangle(
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
    
    # # 在服务器模式下，可以使用 Python 回调实现更复杂的联动逻辑
    # def update_selection(attr, old, new):
    #     # 这里可以添加基于选中点的联动逻辑
    #     # 例如更新其他图表的高亮等
    #     pass

    # # 监听数据源的选中变化
    # ind_source.selected.on_change('indices', update_selection)

    # # 设置自定义 JavaScript 回调实现"只显示一条线"
    # callback = CustomJS(args=dict(renderers=renderers), code="""
    #     // 获取所有渲染器
    #     const allRenderers = Object.values(renderers);
        
    #     // 获取被点击的图例项对应的渲染器
    #     const activeRenderer = this.source;
        
    #     // 隐藏所有线条
    #     allRenderers.forEach(renderer => {
    #         renderer.visible = false;
    #     });
        
    #     // 只显示被点击的线条
    #     activeRenderer.visible = true;
    # """)

    # # 为每个渲染器添加回调
    # for renderer in renderers.values():
    #     renderer.js_on_change('visible', callback)
