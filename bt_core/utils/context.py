import threading
from contextlib import contextmanager
from warnings import (
    catch_warnings,
    filterwarnings,
)

@contextmanager
def ignore_pandas_nan_categorical_warning():
    with warnings.catch_warnings():
        # Pandas >= 0.18 doesn't like null-ish values in categories, but
        # avoiding that requires a broader change to how missing values are
        # handled in pipe, so for now just silence the warning.
        warnings.filterwarnings(
            'ignore',
            category=FutureWarning,
        )
        yield


@contextlib.contextmanager
def make_context():
    print("enter make_context")
    try:
        yield {}
    except RuntimeError as err:
        print(f"{err=}")
       

class Context(contextlib.ContextDecorator):
    """ @Context
        def func(message):
            print(message)        
    """
    def __init__(self, how_used):
        self.how_used = how_used
        print(f'__init__({how_used})')

    def __enter__(self):
        print(f'__enter__({self.how_used})')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f'__exit__({self.how_used})')


class _ManagedCallbackContext(object):
    def __init__(self, pre, post, args, kwargs):
        self._pre = pre
        self._post = post
        self._args = args
        self._kwargs = kwargs

    def __enter__(self):
        return self._pre(*self._args, **self._kwargs)

    def __exit__(self, *excinfo):
        self._post(*self._args, **self._kwargs)


class WarningContext(object):
    """
    Re-usable contextmanager for contextually managing warnings.
    """
    def __init__(self, *warning_specs):
        self._warning_specs = warning_specs
        self._catchers = []

    def __enter__(self):
        catcher = catch_warnings()
        catcher.__enter__()
        self._catchers.append(catcher)
        for args, kwargs in self._warning_specs:
            filterwarnings(*args, **kwargs)
        return self

    def __exit__(self, *exc_info):
        catcher = self._catchers.pop()
        return catcher.__exit__(*exc_info)


context = threading.local()


def get_algo_instance():
    return getattr(context, 'algorithm', None)


def set_algo_instance(algo):
    context.algorithm = algo


class AlgoAPI(object):
    """
    TLS: ThreadLocalStorage to avoid var confliction / withdraw: tls cannot be gc until thread exit
    """
    def __init__(self, algo_instance):
        self.algo_instance = algo_instance

    def __enter__(self):
        """
        Set the given algo instance, storing any previously-existing instance.
        """
        self.old_algo_instance = get_algo_instance()
        set_algo_instance(self.algo_instance)

    def __exit__(self, _type, _value, _tb):
        """
        Restore the algo instance stored in __enter__.
        """
        set_algo_instance(self.old_algo_instance)


# with ExitStack() as stack: # used for nested with | pop_all() to transfer stack | core api enter_context
#     """
#     register callback is reverse to regiter method similar to multi with
#     expand to try / catch or supress 
#     enter_context  and __exit__() to stack / return value from __enter__()
#     callback(回调, * args, ** kwds)
#     with open('file1.txt', 'w') as f1:
#          with open('file2.txt', 'w') as f2:
#              with tempfile.NamedTemporaryFile() as tmp:
#                   f1.write('Hello')
#                   f2.write('World')
#                   tmp.write(b'Data')
#     """
#     f1 = stack.enter_context(open('file1.txt', 'w'))
#     f2 = stack.enter_context(open('file2.txt', 'w'))
#     tmp = stack.enter_context(tempfile.NamedTemporaryFile())
    
#     f1.write('Hello')
#     f2.write('World')
#     tmp.write(b'Data')
