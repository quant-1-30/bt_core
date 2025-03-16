Fake it until you make it

# https://pypi.tuna.tsinghua.edu.cn/simple

Six is a Python 2 and 3 compatibility library. It provides utility functions
for smoothing over the differences between the Python versions with the goal
of writing Python code that is compatible on both Python versions. See the
documentation for more information on what is provided.

mysql tool:
    # select host,user,authentication_string from mysql.user;
    # set password for user@localhost = newpassword;
    # flush privileges;
    # create user c_test@locahost identified by password;
    # drop user c_test@localhost;
    # grant select,update | all privileges on orm.* to guest@localhost;
    # 当忘记密码:  mysqld --skip-grant-tables,use mysql,set password
    # primary key
    # constraint
    # foreign key references
    # alter add constraint
    # alter  drop foreign key

mysql --- between and (include edge)

# apply --- function axis = 0 or axis = 1
# applymap ---- function value of dataframe
# map ---- function on series

#python 随机数生产需要指定种子seed , 相同的种子产生相同的随机数
import random
random.seed(-------)

response = requests.get(new_url, **self.requests_kwargs)

content_length = 0

for chunk in response.iter_content(self.CONTENT_CHUNK_SIZE,
                                   decode_unicode=True):
    if content_length > self.MAX_DOCUMENT_SIZE:
        raise Exception('Document size too big.')
    if chunk:
        content_length += len(chunk)
        yield chunk

memory : joblib.Memory interface used to cache the fitted transformers of
    the Pipeline. By default,no caching is performed. If a string is given,
    it is the path to the caching directory. Enabling caching triggers a clone
    of the transformers before fitting.Caching the transformers is advantageous
    when fitting is time consuming.

3. from multiprocessing import Pool
     pool = Pool(4)
     res = [pool.apply_async(func,(i,)) for i in range(10)]
     for r in res:
         print(r.get())
func --- main()  --- 单独的函数以def, 类里面的函数不可以apply_async, get()
super().method ; super().__init__()
生成器 基于yield方法将函数转化为迭代器, next方法, 每次执行到yield停止;而iter(迭代器将非可迭代对象强制转化为对象)
from interface import Interface,implements
sparse.hstack(Xs).tocsr() # Compressed Sparse Row format
关于精度 ---- float(2进制), decimal ---- (10进制)
from decimal import Decimal , getcontext
decimal.getcontext().prec = 3
decimal.Decimal
# 堆队列(数值小，优先权高)
from heapq import heappush
# from collections import deque, defaultdict
# dqueue 双向队列

# from collections import ChainMap
# 有多个字典或者映射，想把它们合并成为一个单独的映射
c=ChainMap()
d=c.new_child()
e=c.new_child()
e.parents
# os.path.expandvars(path)
# 根据环境变量的值替换path中包含的
# "$name"

# Mapping MutableMapping
# hash __hash__ __eq__ or __cmp__
# Functions are applied from right to left so that compose(f, g, h)(x, y) is the same as f(g(h(x, y)))
# Identity function. Return x
# NamedTemporaryFile has a visble name in file system can be retrieved from the name attribute , delete ---
  True means delete as file closed

default_extension : bool, optional
    Should the default zipline extension be loaded. This is found at
    ``$ZIPLINE_ROOT/extension.py``
extensions : iterable[str], optional
    The names of any other extensions to load. Each element may either be
    a dotted module path like ``a.b.c`` or a path to a python file ending
    in ``.py`` like ``a/b/c.py``.
strict_extensions : bool, optional
    Should the run fail if any extensions fail to load. If this is false,
    a warning will be raised instead.
environ : mapping[str -> str], optional
    The os environment to use. Many extensions use this to get parameters.
    This defaults to ``os.environ``.

descriptor:
    __get__(self, instance, owner):调用一个属性时,触发
    __set__(self, instance, value):为一个属性赋值时,触发
    __delete__(self, instance):采用del删除属性时,触发

backtrader:

addbindings
indicators linesiterator lineseries

indicator next logic / line + line / line + ind
minperiod
update minperiod 
 __getitem__ --> next 方法 / prenext
feed / ind 分开
linealias 
dataflow cerebro runnext ---> data[0] 变化 ---> strategy ---> indicator 
addbings to sync datas minperiod
_owner lines ---> Indicator / Indicator ---> Strategy / DataFeed ---> Cerebro
coupler align dt
lineaction ---> makeoperation / coupler
feed load ---> _load (while)
__getitem__ keys starting from 0 , also can be used in for loop

lines _derive / lineseries __new__ update cls.lines
AutoInfoParam similar to lines _derive aims to update

metaclass __new__ ---> __call__ 
__new__ dct meaning class attributes(property, method) / __call__ **kwargs meaning instance 

add feed ---> based on lineseries preload ---> while load ---> _load

indicator ---> datas (lineseries) to update self.lines / next method

python class protect property via property func method() instead __init__

preload may cause performance problem

indicator ---> datas / IndType / self.lines

_clock ---> _clock._clock (high level clock)

slave is used for unchanged action

owner is used to connnect with strategy or cerebro obj

exactbars control the memory usage of strategy

_runonce_old ---> strategy._once() ---> strategy._oncepost()

_runonce ---> strategy._once() ---> strategy._oncepost()

_runnext_old ---> strategy._next()

_runnext ---> strategy._next()

strategy different mode depends on the data type ( islive / runonce )

_once ---> strategy._once() origin from lineiterator _once method 

every indicator has its own _once method (preonce > once > oncestart > oncebinding) inherit from linebuffer

line operation ---> LineOperation ---> inherit from linebuffer

_owner / addindicator is key to implement indicator _once / _next method (from base to compound)

plot also based on line object

data _check /_last method

LineCoupler (align different line length)

resample logic cerebro resampledata ---> resample ---> addfilter

feed + resample ---> while True ---> load ---> self._load ---> filter ---> stash popleft

componly --- means not intraday (compression only)

timer ---> checkmonth / checkweek (via bisect left / right) 
compare with nexteos / compare with checkmonth / checkweek / update dtwen

strategy ---> signal ---> size ---> control --> execution ---> next

trategy lineroot / linebuffer / op

filter ---> bsplitter / day splitter

# 策略 以bayies 为主

workflow --- based on ray and big model sam to analyse ( indicator + pymc)

Dag --- based on zipline (MIfeature)

sequential_feature_factory --> penetrate layer by layer
concurrent_feature_factory --> intersect between same node

Ind --> Strategy --> Term --> Pipeline

setup property of Term to define strategy (Generic, Computable, Filter, Classifier)

conflict resolution:
    1. position need to be sold but the strategy signal tiggers the same asset
    2. risk control 

broker policy:
    1. coo / coc

to solve 1 : 
    a. to exclude the position asset which to need to be sold
    b. trading_control ---> quantity / avaiable according to existing position
    c. before execute the strategy , setup universe_mask

adjustment apply on feed load process ---> to add adjustment line and right line 
line multiple coef if adjustment is True

ABC.register(type) ---> ABCMeta.__call__

zipline filter ---> nanpercentile / ~ / & / isin /frozenset / ().view(uint8)

vnpy rpc --- select / poll / epoll (fd_set / pollfd / avl + ready_link) rpc which client has not method
vnpy event_driven ---> event_engine (thread / queue / register) 
vnpy gateway mainengine (include omsengine / logengine / emsengine which register handler to event_engine) 

plugin ---> importlib.metadata ( setuptools.entrypoints ) / pluggy


strategy  ---> [-1] / execution_plan next broker

