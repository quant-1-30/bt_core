#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-

import ray

# ray start --head --port=6379

# 出现session问题, stop gcs redis server
# ray stop
# rm -rf /tmp/ray/session_latest ---> /private/tmp
# find / -name "" -type d -exec rm -rf {} \;
# pkill -f ray
# restart ray

