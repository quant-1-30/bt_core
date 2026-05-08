#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import msgspec
from typing import List, Union, Any, Dict, Optional


class QueryBody(msgspec.Struct, frozen=True, tag="query"):
    start_date: int
    end_date: int 
    sid: List[bytes] = []


class RegisterBody(msgspec.Struct, frozen=True, tag="register"):
    client_id: bytes
    strategy: str
    extra_info: str


class CashBody(msgspec.Struct, frozen=True, tag="cash"):
    session: int # 19900202
    cash: float


class OrderBody(msgspec.Struct, frozen=True, tag="order"):
    sid: bytes
    pricelimit: int
    sizer_ratio: int
    order_type: int
    exec_type: int
    created_dt: int
    filler: bytes # oco / occ / smooth / likehood


class Event(msgspec.Struct, frozen=True):
    topic: int
    sub_topic: int = -1
    experiment_id: bytes = b""
    body: Union[QueryBody, RegisterBody, CashBody, OrderBody, None] = None # tag to find body in Union strict
    # body: EmptyBody = msgspec.field(default_factory=EmptyBody)


class ExperimentBody(msgspec.Struct, frozen=True, tag="experiment"):
    experiment_id: bytes


class TradeBody(msgspec.Struct, frozen=True, tag="trade"):
    order_id: bytes
    executed_dt: int
    executed_size: int
    executed_price: float
    comm: float
    isbuy: bool


class PositionBody(msgspec.Struct, frozen=True, tag="position"):
    sid: bytes
    datetime: int 
    size: int
    available: int
    cost_basis: float
    pnl: float
    experiment_id: bytes


class AccountBody(msgspec.Struct, frozen=True, tag="account"):
    datetime: int
    portfolio_value: float
    cash: float
    pnl: float
    leverage: float
    margin: float
    experiment_id: bytes


class SnapshotBody(msgspec.Struct, frozen=True, tag="snapshot"):
    account: AccountBody
    positions: List[PositionBody]
    order: Union[List[TradeBody], None] = None 


class Empty(msgspec.Struct, frozen=True, tag="empty"):
    pass


class ErrMSg(msgspec.Struct, frozen=True, tag="error"):
    error: str


class Sentinel(msgspec.Struct, frozen=True, tag="sentinel"):
    pass


BodyItem = Union[
    ExperimentBody, 
    TradeBody, 
    PositionBody, 
    AccountBody,
    SnapshotBody, 
    Empty, 
    ErrMSg, 
    Sentinel
]

class Resp(msgspec.Struct, frozen=True):
    body: Union[BodyItem, List[BodyItem], None] = None


# class Resp(msgspec.Struct, frozen=True):
#     body: Union[ExperimentBody, SnapshotBody, Empty, ErrMSg, Sentinel, None]=None


ResponseTypes = List[Resp]


# global
_ENCODER = msgspec.msgpack.Encoder()
_DECODER = msgspec.msgpack.Decoder(type=Event)

_RespDECODER = msgspec.msgpack.Decoder(type=ResponseTypes) # msgspec.msgpack.Decoder(type=Resp)
