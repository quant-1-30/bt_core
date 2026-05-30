import os
from bt_sdk.core.client import GetMdApi
from bt_sdk.core.protocol import *


def get_md_api(timeout=30):
    addr_str = os.getenv("MD_API_ADDR", "127.0.0.1:5555")
    ip, port = addr_str.split(":")
    addr_tuple = (ip, int(port))

    return GetMdApi(addr_tuple, timeout=timeout)
