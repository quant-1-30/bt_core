#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-

from .localstore import LocalStore

_stores = {
    "local": LocalStore,
}

__all__ = ["LocalStore", "_stores"]
