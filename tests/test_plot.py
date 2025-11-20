import pandas as pd
import numpy as np
from bokeh.plotting import figure, show
from bokeh.layouts import gridplot, column
from bokeh.models import ColumnDataSource, Range1d


# parse_csv

data = pd.read_csv("out_1.csv", header=1, sep=";")
import pdb; pdb.set_trace()