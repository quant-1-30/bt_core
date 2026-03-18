#! /usr/bin/env python3 
# -*- coding: utf-8 -*-

import os
import asyncio
from typing import Tuple
from concurrent.futures import ThreadPoolExecutor
from bt_trade.core.protocol import Event, Resp, _ENCODER, _DECODER 
from bt_trade.core.broker.engine import BackBroker, BrokerTopic, ErrMSg, Resp

HeaderLength = 4 # 4byte
ReqLength = 16 


class AsyncTCPServer:
    """python 3.11 asyncio 对udp支持, 之前版本对于tcp stream An asynchronous TCP server.
    Asynchronous TCP server with asyncio, optimized with zero-copy, buffer pool, and connection reuse."""

    def __init__(self) -> None:
        self.host = os.getenv("OMS_HOST")
        self.port = int(os.getenv("OMS_PORT"))
        self.max_conn = int(os.getenv("MAX_CONNECTIONS"))
        self.executor = ThreadPoolExecutor(max_workers=int(os.getenv("MAX_WORKERS")))
        # self.recv_buf = bytearray(int(os.getenv("RECV_BUF_SIZE")) * 1024) # default 64 KB 
        self.MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH")) * 1024 * 1024  # 100 MB restrict

        self.oms_engine = BackBroker()
        self.semaphore = asyncio.Semaphore(self.max_conn)

    async def on_recv(self, reader: asyncio.StreamReader) -> dict:
        """
        :param reader: asyncio.StreamReader
        :return: msgspec struct object
        :raises: asyncio.IncompleteReadError, ValueError
        """
        length_data = await reader.readexactly(HeaderLength)
        msg_len = int.from_bytes(length_data, byteorder='big')
        
        if msg_len <= 0 or msg_len > self.MAX_MESSAGE_LENGTH:
            raise ValueError(f"Invalid or too large message size: {msg_len} bytes")
    
        payload = await reader.readexactly(msg_len) # allocate memory
        return memoryview(payload)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr: Tuple[str, int] = writer.get_extra_info('peername')
        print(f"Connected to {addr}")

        async with self.semaphore:
            while True:
                try:
                    serialize = await self.on_recv(reader) # cdef const unsigned char[:] # const means read-only / unhashable
                    req_id = serialize[:ReqLength]
                    event = _DECODER.decode(serialize[ReqLength:]) 
                    # print(f"Received decode {event} from {addr}\n")
                    payload = await self.dispatcher(event) 
                    # tcp stream not packet / tcp mss = 1500(mtu) - 20(ip header) - 20(tcp header) / udp 1500 - 20 - 8
                    payload_len = len(req_id) + len(payload)
                    writer.writelines([ # multi writer.write
                        payload_len.to_bytes(HeaderLength, byteorder='big'),
                        req_id,
                        payload
                    ])
                    await writer.drain() # writer.transport.get_write_buffer_size()

                    writer.write((0).to_bytes(HeaderLength, 'big')) # sentinel
                    await writer.drain() 
                except asyncio.IncompleteReadError:
                    print(f"Client {addr} closed connection normally")
                    break
                except ConnectionResetError:
                    print(f"Client {addr} disconnected (connection reset)")
                    break
                except Exception as e:
                    print(f"Unexpected error handling client {addr}: {str(e)}")
                    pass
        
        if not writer.is_closing():
            writer.close() # send Fin
        try:
            await writer.wait_closed() 
        except Exception:
            pass  
        print(f"Closed connection to {addr}")

    async def dispatcher(self, event: Event):
        topic = event.topic
        try:
            if topic == BrokerTopic.Register:
                resp = await self.oms_engine.register(event)

            elif topic == BrokerTopic.SetCash:
                resp = await self.oms_engine.set_cash(event) 

            elif topic == BrokerTopic.Submit:
                resp = await self.oms_engine.submit(event)
        
            elif topic == BrokerTopic.DayOver:
                resp = await self.oms_engine.on_dt_over(event)

            elif topic == BrokerTopic.GetValue:
                resp = await self.oms_engine.getvalue(event)

            elif topic == BrokerTopic.Subscribe:
                resp = await self.oms_engine.subscribe(event)
        except Exception as e:
            resp = Resp(body=ErrMSg(error=str(e)))
        
        resp = resp if isinstance(resp, list) else [resp]
        payload = _ENCODER.encode(resp)
        return memoryview(payload)

    async def start_server(self) -> None:
        self.oms_engine.start()

        server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        addr = server.sockets[0].getsockname()
        print(f'Serving on {addr}')

        async with server:
            await server.serve_forever()
