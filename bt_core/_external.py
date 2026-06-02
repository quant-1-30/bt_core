import os
import atexit
import contextlib

from bt_sdk.core.client import GetMdApi
from bt_core.execution.actor.runner_actor import AsyncRunner

_global_runner = None

def get_global_runner():
    global _global_runner
    if _global_runner is None:
        _global_runner = AsyncRunner()
        _global_runner.start()
        print(f"[MdProvider] Global AsyncRunner started. Loop: {id(_global_runner.get_loop())}")
    return _global_runner


@atexit.register
def _cleanup_runner():
    global _global_runner
    if _global_runner is not None:
        if hasattr(_global_runner, 'stop'):
            _global_runner.stop()
        print("[MdProvider] Global AsyncRunner stopped.")


def get_md_api(timeout=30):
    addr_str = os.getenv("MD_ADDR", "127.0.0.1:50051")
    ip, port = addr_str.split(":")
    addr_tuple = (ip, int(port))
    return GetMdApi(addr_tuple, timeout=timeout)


@contextlib.contextmanager
def external_mdapi_context(timeout=30):
    mdapi = get_md_api(timeout)
    # runner = AsyncRunner() # EventLoop
    # runner.start()
    # _loop = runner.get_loop()
    runner = get_global_runner()
    _loop = runner.get_loop()
    # attach 
    mdapi.start(_loop)

    try:
        yield mdapi
        
    finally:
        # reuse global runner for next dag task
        # if hasattr(runner, 'stop'):
        #     runner.stop()
        pass
