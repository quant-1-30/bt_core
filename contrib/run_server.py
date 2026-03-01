#! /usr/bin/env python3 
# -*- coding: utf-8 -*-

import os

# force numpy run on one core
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"


import asyncio
import signal
import atexit
import gc
import sys
import uvloop
import tracemalloc
import warnings
from dotenv import load_dotenv

from bt_trade.core.gateway.operator import async_ops
from bt_trade.core.server import AsyncTCPServer

uvloop.install()


@atexit.register
def cleanup_before_exit(): # sys.exit(0)# SystemExit ---> atexit
    sys.stdout.flush()
    sys.stderr.flush()

    print("gc atexit") 
    gc.collect()


def main():
    async def async_main():
        try:
            loop = asyncio.get_running_loop()
            
            # intialize pg 
            async with async_ops as ctx:
                pass

            server = AsyncTCPServer()
            await server.start_server()
        except asyncio.CancelledError:
            raise

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
            
    try:
        loop.run_until_complete(async_main())
    except asyncio.CancelledError:
        print("CancelledError caught in main loop, exiting cleanly.")
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
    finally:
        loop.close()


if __name__ == '__main__':

    load_dotenv()
    main()
