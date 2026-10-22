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
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from .autodict import *
from .util import *
from .dateintern import *

from bt_sdk.core.factor import *

import os
import glob


def resolve_scan_source(path):
    """Resolve a Parquet file or directory path for Polars scan_parquet."""
    if not path:
        return None
    p_str = os.fspath(path)
    if os.path.isdir(p_str):
        files = sorted(glob.glob(os.path.join(p_str, "*.parquet")))
        return files if files else None
    if os.path.exists(p_str):
        return p_str
    return None
