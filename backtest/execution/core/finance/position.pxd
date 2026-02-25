# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------
from libcpp.string cimport string as cpp_string
from libcpp.vector cimport vector
from libc.stdint cimport int64_t, int32_t

from backtest.execution.core.finance.common cimport EventItem
from backtest.execution.core.finance.trade cimport OrderExecutionBit
from backtest.execution.core.finance.asset cimport AssetInfo


cdef struct PositionCoreData:
    cpp_string experiment_id
    cpp_string sid
    int64_t datetime
    int size
    int available
    double cost_basis
    double pnl
    double pval
    double cash
    

cdef class Position:
    cdef readonly PositionCoreData core
    cdef AssetInfo asset_info

    cdef int get_available(self)
    
    cdef void update(self, OrderExecutionBit orderbit)
    
    cdef _update(self, OrderExecutionBit orderbit)
    
    cdef double process_events(self, vector[EventItem]& events)
    
    cdef double _process_event(self, EventItem item)

    cdef void on_dt_over(self, int end_dt, double close)

    cdef void _on_dt_over(self, int end_dt, double close)
    
    cdef Position clone(self)
    
    cdef object serialize(self)
    
    cdef object to_schema(self)
    