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

cdef enum SlipType:
    Perc = 0
    Fixed = 1
    Smooth = 2
    Likehood = 3


cdef class Slippage:
    
    cdef double slip_perc

    cdef double get_slip_price(self, double order_price, double open, double high, double low, double close, bint is_buy) noexcept nogil
    

cdef class FixedPercSlip(Slippage):

    cdef double get_slip_price(self, double order_price, double open, double high, double low, double close, bint is_buy) noexcept nogil
    

cdef class SmoothSlip(Slippage):

    cdef double get_slip_price(self, double order_price, double open, double high, double low, double close, bint is_buy) noexcept nogil


cdef class LikehoodSlip(Slippage):
    
    cdef double get_slip_price(self, double order_price, double open, double high, double low, double close, bint is_buy) noexcept nogil
