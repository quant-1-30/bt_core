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
from libc.stdint cimport int32_t, int64_t
from libcpp.string cimport string as cpp_string

from backtest.execution.core.finance.trade cimport OrderExecutionBit, OrderExbitData
from backtest.execution.core.finance.cache cimport AssetCore

cdef enum ExecType:
    Open = 0
    Market = 1
    Close = 2
    Limit = 3
    Stop = 4
    StopLimit = 5
    StopTrail = 6
    StopTrailLimit = 7
    Historical = 8


cdef enum OrderType:
    Buy = 0
    Sell = 1


cdef enum OrderStatus:
    Created = 0
    Submitted = 1
    Accepted = 2
    Partial = 3
    Completed = 4
    Canceled = 5
    Expired = 6
    Rejected = 7


cdef struct OrderCoreData:
     cpp_string experiment_id # bytes in python
     cpp_string sid
     cpp_string vtorder_id
     int32_t size
     double sizer_ratio
     double price
     double pricelimit
     int32_t order_type
     int32_t exec_type
     int32_t created_dt


cdef class Order:
    cdef readonly OrderCoreData core
    cdef readonly bytes filler
    cdef AssetCore info
    cdef int32_t status
    cdef int32_t _exchange
    cdef object _exbits

    cdef void addinfo(self, dict asset_info)
    
    cdef on_fix(self, double price)

    cdef void execute(self, int32_t size, double price, OrderExecutionBit order_bit)
    
    cdef void submit(self)

    cdef void accept(self)

    cdef void reject(self)

    cdef void partial(self)

    cdef void expire(self)

    cdef void completed(self)

    cdef void cancel(self)

    cdef Order clone(self)
    
    cdef list serialize(self)
    
    cdef object to_schema(self)
