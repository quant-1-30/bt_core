#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import inspect
import datetime
from typing import List
from typing import Any, Dict, Type, Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import Integer, String, ForeignKey, BigInteger, Text, LargeBinary, Sequence, Float, text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.schema import PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.inspection import inspect

from bt_sdk.core.protocol import Resp, ExperimentBody, PositionBody, AccountBody, TradeBody


class Base(DeclarativeBase):

    # id primary key and autoincrement will come to effect / not primary key , sequence will be used to implement effect of autoincrement
    # PrimaryKeyConstraint will ignore column setting -- autoincrement and PrimaryKeyConstraint name is unique
    # backref在主类里面申明 / back_populates显式两个类申明 ;  default lazy="select" / "joined" / "selectin" 
    # one to many all, delete-orphan / many to many  all, delete  / uselist False -对一
    
    def to_dict(self, include_id=False) -> dict: # asyncpg support UUID
        result = {}
        for c in inspect(self).mapper.column_attrs:
            if not include_id and c.key == "id":
                continue
            
            value = getattr(self, c.key)
            if value is None:
                result[c.key] = None
            elif isinstance(value, datetime.datetime):
                result[c.key] = int(value.timestamp())
            elif isinstance(value, Decimal):
                result[c.key] = float(value)
            else:
                result[c.key] = value
        return result


class User(Base):

    __tablename__ = "user_info"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    # id_sequence = Sequence('client_id_seq', start=1000, increment=5)
    user_id: Mapped[str] = mapped_column(String(255,collation='C'), nullable=False)
    # default is client side (python side to generate uuid) default=uuid.uuid4 / server side postgres generate uuid_generate_v4() / gen_random_uuid()
    client_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), unique=True, server_default=text("gen_random_uuid()")) # server_default=text("uuid_send(gen_random_uuid())")) UUID 16 byte / uuid_send from uuid to bytea 

    __table_args__ = (
        PrimaryKeyConstraint("id", "user_id", "client_id", name="pd_id_user_client_id"),
        # {"extend_existing": True}
        )
 
    def __repr__(self) -> str:
        return f"User(id={self.id!r}, user_id={self.user_id!r}, client_id={self.client_id!r})"


class Experiment(Base):
    
    __tablename__ = "experiment"

    # id_sequence = Sequence('client_id_seq', start=1000, increment=1)
    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("user_info.client_id", ondelete="CASCADE"))
    strategy: Mapped[str] = mapped_column(Text(collation='C'), nullable=False) # Mapped[str] ---> postgres `String`, `VARCHAR`, `Text`
    extra_info: Mapped[str] = mapped_column(Text(collation='C'), nullable=False)
    # experiment_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False) # PostgreSQL BYTEA ---> Binary
    experiment_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), unique=True, server_default=text("gen_random_uuid()")) # UUID 16 byte / uuid_send from uuid to bytea 

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pd_experiment_id"),
        UniqueConstraint("client_id", "strategy", "extra_info", name="uq_client_strategy_extra_info"), # avoid Index 
        # {"extend_existing": True}
        )
    
    vtorders: Mapped[List["vtOrder"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )

    vtpositions: Mapped[List["vtPosition"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )

    account: Mapped["vtAccount"] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )

    def serialize(self, include_id=False) -> dict:
        body = ExperimentBody(experiment_id=self.experiment_id.bytes)
        return Resp(body=body)

    def __repr__(self) -> str:
        return f"Experiment(id={self.id!r}, experiment_id={self.experiment_id!r}, client_id={self.client_id!r}, strategy={self.strategy!r}, extra_info={self.extra_info!r})"


class vtOrder(Base):

    __tablename__ = "vtorder"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sid: Mapped[bytes] = mapped_column(LargeBinary, nullable=False) 
    price: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    order_type: Mapped[int] = mapped_column(Integer, nullable=False)
    exec_type: Mapped[int] = mapped_column(Integer, nullable=False)
    created_dt: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    # order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), unique=True, server_default=text("gen_random_uuid()")) # UUID 16 byte / uuid_send from uuid to bytea 
    order_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False) 

    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiment.experiment_id", ondelete="CASCADE"))
 
    __table_args__ = (
        # PrimaryKeyConstraint("id", "order_id", name="pk_order_id"),
        # UniqueConstraint("sid", "created_dt", "experiment_id", name="uq_order_sid_created_dt_experiment_id"), 
        UniqueConstraint("order_id", "experiment_id", name="uq_order_id_experiment_id"), 
    )

    experiment: Mapped["Experiment"] = relationship(
        back_populates="vtorders")
    
    order_bits: Mapped[List["OrderBit"]] = relationship(
        back_populates="vtorder", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"vtOrder(id={self.id!r}, sid={self.sid!r}, price={self.price!r}, size={self.size!r}, \
            order_type={self.order_type!r}, exec_type={self.exec_type!r}, order_id={self.order_id!r}, created_dt={self.created_dt!r})"


class OrderBit(Base):

    __tablename__ = "order_bit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # id: Mapped[int] = mapped_column(Integer, Sequence('vtorder_id_seq'), nullable=False)
    order_id: Mapped[bytes] = mapped_column(ForeignKey("vtorder.order_id", ondelete="CASCADE"), unique=True)
    # server_default=func.now()
    executed_dt: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    executed_price: Mapped[float] = mapped_column(Float, nullable=False)
    executed_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comm: Mapped[float] = mapped_column(Float, nullable=False)
    isbuy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("order_id", "executed_dt", name="uq_order_executed_dt"),
    )

    vtorder: Mapped["vtOrder"] = relationship(back_populates="order_bits")

    def serialize(self, include_id=False) -> dict:      
        body = TradeBody(order_id=self.order_id, executed_dt=self.executed_dt, executed_size=self.executed_size, 
                        executed_price=self.executed_price, comm=self.comm, isbuy=self.isbuy)

        return Resp(body=body)
    
    def __repr__(self) -> str:
        return f"OrderBit(id={self.id!r}, order_id={self.order_id!r}, executed_dt={self.executed_dt!r}, \
            executed_price={self.executed_price!r}, executed_size={self.executed_size!r}, comm={self.comm!r})"
    

class vtPosition(Base):

    __tablename__ = "vtposition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # id: Mapped[int] = mapped_column(Integer, Sequence('vtposition_id_seq'), nullable=False)
    sid: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    datetime: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    available: Mapped[int] = mapped_column(Integer, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=False)
    created_dt: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)

    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiment.experiment_id", ondelete="CASCADE"))

    __table_args__ = (
        UniqueConstraint("datetime", "sid", "experiment_id", name="uq_position_datetime_sid_experiment_id"),
    )

    experiment: Mapped["Experiment"] = relationship(
        back_populates="vtpositions"
    )

    def serialize(self, include_id=False) -> dict:
        body = PositionBody(sid=self.sid, datetime=self.datetime, size=self.size,
                            available=self.available, cost_basis=self.cost_basis,
                            pnl=self.pnl, experiment_id=self.experiment_id.bytes)
        return Resp(body=body)
    
    def __repr__(self) -> str:
        return f"vtPosition(id={self.id!r}, sid={self.sid!r}, datetime={self.datetime!r}, cost_basis={self.cost_basis!r}, \
            size={self.size!r}, available={self.available!r}, pnl={self.pnl!r})"


class vtAccount(Base):

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # id: Mapped[int] = mapped_column(Integer, Sequence('account_id_seq'), nullable=False)
    datetime: Mapped[BigInteger] = mapped_column(BigInteger, nullable=False)
    portfolio_value: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True)
    cash: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, use_existing_column=True)
    leverage: Mapped[float] = mapped_column(Float, default=1.0, nullable=False, use_existing_column=True)
    margin: Mapped[float] = mapped_column(Float, default=0, nullable=False, use_existing_column=True)

    experiment_id: Mapped[UUID] = mapped_column(ForeignKey("experiment.experiment_id", ondelete="CASCADE"))
    
    __table_args__ = (
        UniqueConstraint("datetime", "experiment_id", name="uq_acct_datetime_experiment_id"),
        )

    experiment: Mapped["Experiment"] = relationship(
        back_populates="account"
    )

    def serialize(self, include_id=False) -> dict:
        body = AccountBody(datetime=self.datetime, portfolio_value=self.portfolio_value,
                           cash=self.cash, pnl=self.pnl, leverage=self.leverage,
                           margin=self.margin, experiment_id=self.experiment_id.bytes)
        return Resp(body=body)
    
    def __repr__(self) -> str:
        return f"vtAccount(id={self.id!r}, datetime={self.datetime!r}, portfolio_value={self.portfolio_value!r}, cash={self.cash!r}, pnl={self.pnl!r}, leverage={self.leverage!r}, margin={self.margin!r})"
    

__all__ = ["User", "Experiment", "vtOrder", "OrderBit", "vtPosition", "vtAccount"]

