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
from libc.stdint cimport int64_t

cdef enum RpcTopic:
    Calendar = 0
    Instrument = 1
    Index = 2
    Tick = 3 
    Close = 4
    Adjustment = 5
    Rightment = 6
    

cdef class RpcClient:
    cdef object _stub
    cdef object _channel
    cdef str host
    cdef int port
    
    cdef object _calendarCall(self, object stub_req, bint wait_for_ready=?)
    
    cdef object _instrumentCall(self, object stub_req, bint wait_for_ready=?)

    cdef object _indexCall(self, object stub_req, bint wait_for_ready=?)

    cdef object _tickCall(self, object stub_req, bint wait_for_ready=?)

    cdef object _closeCall(self, object stub_req, bint wait_for_ready=?)

    cdef object _adjustmentCall(self, object stub_req, bint wait_for_ready=?)

    cdef object _rightmentCall(self, object stub_req, bint wait_for_ready=?)
    
    cdef object _dispatch_rpc(self, int rpc_type, dict req_body)
