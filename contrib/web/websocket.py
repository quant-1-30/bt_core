#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 16 13:56:19 2019

@author: python
"""
import json, socket, ssl, sys, traceback
from datetime import datetime
from threading import Lock, Thread
from time import sleep
import websocket

"""
    Werkzeug 用于实现 WSGI ,应用和服务之间的标准 Python 接口
    Jinja 用于渲染页面的模板语言
    MarkupSafe 与 Jinja 共用,在渲染页面时用于避免不可信的输入,防止注入攻击
    ItsDangerous 保证数据完整性的安全标志数据,用于保护 Flask 的 session cookie
    Click 是一个命令行应用的框架。用于提供 flask 命令,并允许添加自定义 管理命令
    string （缺省值） 接受任何不包含斜杠的文本
    int 接受正整数
    float  接受正浮点数
    path 类似 string ,但可以包含斜杠
    uuid  接受 UUID 字符串
    
    http:
    1GET将数据以未加密的形式发送到服务器,这最常用的方法。
    2HEAD与GET相同,但没有响应主体
    3POST用于将HTML表单数据发送到服务器。通过POST方法接收的数据不会被服务器缓存。
    4PUT用上传的内容替换目标资源的所有当前表示。
    5DELETE删除由URL给出的所有目标资源的所有表示
    默认情况下,Flask路由响应GET请求。 但是,可以通过为route()装饰器提供方法参数来更改此首选项。
    为了演示在URL路由中使用POST方法,首先创建一个HTML表单并使用POST方法将表单数据发送到URL。
    
"""

class WebsocketClient(object):
    """
    Websocket API

    After creating the client object, use start() to run worker and ping threads.
    The worker thread connects websocket automatically.

    Use stop to stop threads and disconnect websocket before destroying the client
    object (especially when exiting the programme).

    Default serialization format is json.

    Callbacks to overrides:
    * unpack_data
    * on_connected
    * on_disconnected
    * on_packet
    * on_error

    After start() is called, the ping thread will ping server every 60 seconds.

    If you want to send anything other than JSON, override send_packet.
    """

    def __init__(self):
        """Constructor"""
        self.host = None

        self._ws_lock = Lock()
        self._ws = None

        self._worker_thread = None
        self._ping_thread = None
        self._active = False

        self.proxy_host = None
        self.proxy_port = None
        self.ping_interval = 60     # seconds
        self.header = {}

        # For debugging
        self._last_sent_text = None
        self._last_received_text = None

    def init(self, host: str, proxy_host: str = "", proxy_port: int = 0, ping_interval: int = 60, header: dict = None):
        """
        :param ping_interval: unit: seconds, type: int
        """
        self.host = host
        self.ping_interval = ping_interval  # seconds

        if header:
            self.header = header

        if proxy_host and proxy_port:
            self.proxy_host = proxy_host
            self.proxy_port = proxy_port

    def start(self):
        """
        Start the client and on_connected function is called after webscoket
        is connected succesfully.

        Please don't send packet untill on_connected fucntion is called.
        """

        self._active = True
        self._worker_thread = Thread(target=self._run)
        self._worker_thread.start()

        self._ping_thread = Thread(target=self._run_ping)
        self._ping_thread.start()

    def stop(self):
        """
        Stop the client.
        """
        self._active = False
        self._disconnect()

    def join(self):
        """
        Wait till all threads finish.

        This function cannot be called from worker thread or callback function.
        """
        self._ping_thread.join()
        self._worker_thread.join()

    def send_packet(self, packet: dict):
        """
        Send a packet (dict data) to server

        override this if you want to send non-json packet
        """
        text = json.dumps(packet)
        self._record_last_sent_text(text)
        return self._send_text(text)

    def _send_text(self, text: str):
        """
        Send a text string to server.
        """
        ws = self._ws
        if ws:
            ws.send(text, opcode=websocket.ABNF.OPCODE_TEXT)

    def _send_binary(self, data: bytes):
        """
        Send bytes data to server.
        """
        ws = self._ws
        if ws:
            ws._send_binary(data)

    def _reconnect(self):
        """"""
        if self._active:
            self._disconnect()
            self._connect()

    def _create_connection(self, *args, **kwargs):
        """"""
        return websocket.create_connection(*args, **kwargs)

    def _connect(self):
        """"""
        self._ws = self._create_connection(
            self.host,
            sslopt={"cert_reqs": ssl.CERT_NONE},
            http_proxy_host=self.proxy_host,
            http_proxy_port=self.proxy_port,
            header=self.header
        )
        self.on_connected()

    def _disconnect(self):
        """
        """
        with self._ws_lock:
            if self._ws:
                self._ws.close()
                self._ws = None

    def _run(self):
        """
        Keep running till stop is called.
        """
        try:
            self._connect()

            # todo: onDisconnect
            while self._active:
                try:
                    ws = self._ws
                    if ws:
                        text = ws.recv()

                        # ws object is closed when recv function is blocking
                        if not text:
                            self._reconnect()
                            continue

                        self._record_last_received_text(text)

                        try:
                            data = self.unpack_data(text)
                        except ValueError as e:
                            print("websocket unable to parse data: " + text)
                            raise e

                        self.on_packet(data)
                # ws is closed before recv function is called
                # For socket.error, see Issue #1608
                except (websocket.WebSocketConnectionClosedException, socket.error):
                    self._reconnect()

                # other internal exception raised in on_packet
                except:  # noqa
                    #sys.exc_info ,返回系统执行信息
                    et, ev, tb = sys.exc_info()
                    self.on_error(et, ev, tb)
                    self._reconnect()
        except:  # noqa
            et, ev, tb = sys.exc_info()
            self.on_error(et, ev, tb)
            self._reconnect()

    @staticmethod
    def unpack_data(data: str):
        """
        Default serialization format is json.

        override this method if you want to use other serialization format.
        """
        return json.loads(data)

    def _run_ping(self):
        """"""
        while self._active:
            try:
                self._ping()
            except:  # noqa
                et, ev, tb = sys.exc_info()
                self.on_error(et, ev, tb)
                self._reconnect()
            for i in range(self.ping_interval):
                if not self._active:
                    break
                sleep(1)

    def _ping(self):
        """"""
        ws = self._ws
        if ws:
            ws.send("ping", websocket.ABNF.OPCODE_PING)

    @staticmethod
    def on_connected():
        """
        Callback when websocket is connected successfully.
        """
        pass

    @staticmethod
    def on_disconnected():
        """
        Callback when websocket connection is lost.
        """
        pass

    @staticmethod
    def on_packet(packet: dict):
        """
        Callback when receiving data from server.
        """
        pass

    def on_error(self, exception_type: type, exception_value: Exception, tb):
        """
        Callback when exception raised.
        """
        sys.stderr.write(
            self.exception_detail(exception_type, exception_value, tb)
        )
        return sys.excepthook(exception_type, exception_value, tb)

    def exception_detail(
        self, exception_type: type, exception_value: Exception, tb
    ):
        """
        Print detailed exception information;traceback
        """
        text = "[{}]: Unhandled WebSocket Error:{}\n".format(
            datetime.now().isoformat(), exception_type
        )
        text += "LastSentText:\n{}\n".format(self._last_sent_text)
        text += "LastReceivedText:\n{}\n".format(self._last_received_text)
        text += "Exception trace: \n"
        text += "".join(
            traceback.format_exception(exception_type, exception_value, tb)
        )
        return text

    def _record_last_sent_text(self, text: str):
        """
        Record last sent text for debug purpose.
        """
        self._last_sent_text = text[:1000]

    def _record_last_received_text(self, text: str):
        """
        Record last received text for debug purpose.
        """
        self._last_received_text = text[:1000]


# asyncio websocket from fastapi

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Union

from fastapi import WebSocket, WebSocketDisconnect
# from fastapi import APIRouter, StreamingResponse 
# # sse

from utils import logger


class WSConnectionManager:
    def __init__(self, timeout: int = 300):
        self.active_connections = {}
        self.timeout = timeout

    async def connect(self, websocket: WebSocket, session_id: Optional[str] = None):
        await websocket.accept()
        if session_id:
            self.active_connections[session_id] = websocket
        else:
            self.active_connections[id(websocket)] = websocket

    def disconnect(self, websocket: WebSocket, session_id: Optional[str] = None):
        if session_id:
            self.active_connections.pop(session_id)
        else:
            self.active_connections.pop(id(websocket))

    @staticmethod
    async def send_personal_message(message: Union[str, dict], websocket: WebSocket):
        if isinstance(message, dict):
            await websocket.send_json(message)
        else:
            await websocket.send_text(message)

    async def broadcast(self, message: Union[str, dict]):
        for connection in self.active_connections.values():
            if isinstance(message, dict):
                await connection.send_json(message)
            else:
                await connection.send_text(message)

    async def handle(self, handler, websocket: WebSocket, *args):
        try:
            await self.connect(websocket)
            loop = asyncio.get_running_loop()
            while True:
                try:
                    data_json = await asyncio.wait_for(websocket.receive_json(), timeout=self.timeout)
                    if data_json.get("prompt").upper() == "PING":
                        await self.send_personal_message("PONG", websocket)
                        continue
                    await self.send_personal_message("__START__", websocket)
                    logger.info(f"receive data: {data_json}")
                    with ThreadPoolExecutor() as pool:
                        out = await loop.run_in_executor(pool, handler, data_json, *args)
                        logger.info(f"send data: {out}")
                        await self.send_personal_message(out, websocket)

                except asyncio.TimeoutError:
                    await self.send_personal_message("__ERROR__", websocket)
                    await self.send_personal_message("客户端长时间未响应，服务器将关闭连接，如需使用请刷新", websocket)
                    break
                except WebSocketDisconnect as e:
                    await self.send_personal_message("__ERROR__", websocket)
                    logger.error(f"websocket disconnect: {e}")
                    await self.send_personal_message(str(e), websocket)
                    break
                except Exception as e:
                    await self.send_personal_message("__ERROR__", websocket)
                    logger.error(f"websocket error: {e}")
                    await self.send_personal_message(str(e), websocket)
                    break
                finally:
                    await self.send_personal_message("__END__", websocket)

        except Exception as e:
            logger.error(f"websocket error: {e}")
            self.disconnect(websocket)

