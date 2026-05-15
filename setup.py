import os
import glob
import numpy as np
from setuptools import setup, Extension
from Cython.Build import cythonize

# sources = glob.glob("**/*.pyx", recursive=True) # **/*.pyx 会搜索当前目录及其所有子目录下的 .pyx 文件
current_dir = os.path.abspath(os.getcwd())

extensions = [ 
    Extension(
        name="backtest.timer", 
        sources=["backtest/timer.pyx"],
        include_dirs=[np.get_include(), current_dir],
        language="c++", # vector/map
        extra_compile_args=["-O3", "-std=c++11"],
        # "-Wno-unused-function",
        # "-Wno-unused-variable",
        # "-Wno-unused-but-set-variable",
        # "-Wno-unused-parameter",
        # "-Wno-sign-compare" 
    ),
    Extension(
        name="backtest.pnc", 
        sources=["backtest/pnc.pyx"],
        include_dirs=[np.get_include(), current_dir],
        language="c++", # vector/map
        extra_compile_args=["-O3", "-std=c++11"],
    ),
    Extension(
        name="backtest.shm", 
        sources=["backtest/shm.pyx"],
        include_dirs=[np.get_include(), current_dir],
        language="c++", # vector/map
        extra_compile_args=["-O3", "-std=c++11"],
    ),
    Extension(
        name="backtest.sink", 
        sources=["backtest/sink.pyx"],
        include_dirs=[np.get_include(), current_dir],
        language="c++", # vector/map
        extra_compile_args=["-O3", "-std=c++11"],
    ),
    Extension(
        name="backtest.utils.dateintern", 
        sources=["backtest/utils/dateintern.pyx"],
        include_dirs=[np.get_include(), current_dir],
        language="c++", # vector/map
        extra_compile_args=["-O3", "-std=c++11"],
        ),
    Extension(
        name="backtest.utils.dt_cmp", 
        sources=["backtest/utils/dt_cmp.pyx"],
        include_dirs=[np.get_include(), current_dir],
        language="c++", # vector/map
        extra_compile_args=["-O3", "-std=c++11"],
    ),
    Extension(
        name="backtest.execution.actor.writer_actor", 
        sources=["backtest/execution/actor/writer_actor.pyx"],
        include_dirs=[np.get_include(), "."],  
        language="c++",                         # vector/map
        extra_compile_args=["-O3", "-std=c++11"]
    ),
    Extension(
        name="backtest.execution.utils.util", 
        sources=["backtest/execution/utils/util.pyx"],
        include_dirs=[np.get_include(), "."],  
        language="c++",                         # vector/map
        extra_compile_args=["-O3", "-std=c++11"]
    ),
    Extension(
        name="backtest.execution.gateway.interface", 
        sources=["backtest/execution/gateway/interface.pyx"],
        include_dirs=[np.get_include(), current_dir, "."], # . root 
        language="c++",
        extra_compile_args=["-O3", "-std=c++11"]
    ),
    Extension(
        name="backtest.execution.core.engine.engine", 
        sources=["backtest/execution/core/engine/engine.pyx"],
        include_dirs=[np.get_include(), current_dir, "."],
        language="c++",
    ),
    Extension(
        name="backtest.execution.trade_api", 
        sources=["backtest/execution/trade_api.pyx"],
        include_dirs=[np.get_include(), current_dir, "."],
        language="c++",
    ),

]

# finance 
finance_sources = glob.glob("backtest/execution/core/finance/*.pyx")

for src in finance_sources:
    # "core/finance/account.pyx" -> "core.finance.account"
    module_name = src.replace("/", ".").replace(".pyx", "")
    
    extensions.append(
        Extension(
            name=module_name,
            sources=[src],
            include_dirs=[np.get_include(), current_dir],
            language="c++",
            extra_compile_args=["-O3", "-std=c++11"]
        )
    )


setup(
    name="backtest_lib",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': "3",       # Python3
            'boundscheck': False,        # 关闭数组越界检查（提升性能）
            'wraparound': False,         # 关闭负索引支持（提升性能）
            'initializedcheck': False,   # 关闭内存视图初始化检查
            'cdivision': True,           # 开启 C 级别除法（不检查除零，极快）
        },
        annotate=False # .html 文件，方便查看代码是否实现C 级加速
    )
)
