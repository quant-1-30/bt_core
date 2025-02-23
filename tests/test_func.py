from collections import deque
from bisect import bisect_left, bisect_right


mask = [5, 10, 12, 15, 20]  # Allowed days in the month
dday = 12
dc = bisect_left(mask, dday) 
print("dc", dc)
curday = bisect_right(mask, dday, lo=dc) # check dday
print("curday", curday)
