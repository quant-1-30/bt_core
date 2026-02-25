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
from libcpp.string cimport string as cpp_string

from backtest.execution.core.finance.common cimport CashData


cdef struct AccountCoreData:
    cpp_string experiment_id
    int64_t datetime
    double  portfolio_value
    double  cash
    double  pnl
    double  leverage
    double  margin
    

cdef class Account:
    cdef readonly AccountCoreData core

    cdef void set_cash(self, CashData body, bint reset=*)
    
    cdef void restore(self)

    cdef void add_cash(self, double cash)

    cdef void update(self, dict p_obj)
    
    cdef sync_dt(self, int64_t tick)

    cdef Account clone(self)
    
    cdef object serialize(self)
    
    cdef object to_schema(self)
