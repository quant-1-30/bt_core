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
from libc.stdint cimport int64_t

cdef struct OrderExbitData:
    cpp_string order_id
    int64_t executed_dt
    int64_t executed_size
    double executed_price
    double comm
    bint isbuy

cdef class OrderExecutionBit:
    cdef readonly OrderExbitData core

    cdef OrderExecutionBit clone(self)
    
    cdef object serialize(self)
    
    cdef object to_schema(self)
    
    cdef OrderExbitData get_snapshot(self)