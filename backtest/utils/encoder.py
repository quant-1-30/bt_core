#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
import uuid
import json
import datetime
import numpy as np
import base64


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()

        if isinstance(obj, np.ndarray):
            return obj.tolist()

        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode('utf-8') # base64.b64encode 将任意bytes 转为 ascii  / base64.b64decode

        if isinstance(obj, set):
            return list(obj)

        if isinstance(obj, uuid.UUID):
            return str(obj)

        return super().default(obj)
