import os
import contextlib

from bt_sdk.core.client import GetMdApi
from bt_core.execution.actor.runner_actor import AsyncRunner


def get_md_api(timeout=30):
    addr_str = os.getenv("MD_ADDR", "127.0.0.1:50051")
    ip, port = addr_str.split(":")
    addr_tuple = (ip, int(port))

    return GetMdApi(addr_tuple, timeout=timeout)


@contextlib.contextmanager
def external_mdapi_context(timeout=30):
    mdapi = get_md_api(timeout)
    
    runner = AsyncRunner() # EventLoop
    runner.start()

    # attach 
    _loop = runner.get_loop()
    mdapi.start(_loop)

    try:
        yield mdapi
        
    finally:
        if hasattr(runner, 'stop'):
            runner.stop()
