import math
from typing import List


def check_gt_zero(sig_list: List, nosig: List):
    for x in sig_list or nosig:
        v = x[0]
        if math.isnan(v) or v <= 0.0: return False
    return True

def check_lt_zero(sig_list: List, nosig: List):
    for x in sig_list or nosig:
        v = x[0]
        if math.isnan(v) or v >= 0.0: return False
    return True

def check_nanzero(sig_list: List, nosig: List):
    for x in sig_list or nosig:
        v = x[0]
        if not math.isnan(v) and v != 0.0: return True
    return False
