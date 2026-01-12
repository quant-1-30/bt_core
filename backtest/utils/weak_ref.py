# -*- coding : utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
from itertools import compress
from weakref import WeakKeyDictionary, ref
from threading import Lock
from functools import wraps
from toolz.sandbox import unzip
from collections import OrderedDict, Sequence


class Lazyproperty:
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, cls):
        if instance is None:
            return self
        else:
            value = self.func(instance)
            setattr(instance, self.func.__name__, value)
            return value
        
    def __set__(self, instance, cls):
        return getattr(instance, self.func.__name__)


class LazyFunc(object): # __getattribute__ > __getattr__ (AttributeError)
    
    def __init__(self, func):
        self.func = func
        self.cache = weakref.WeakKeyDictionary()

    def __get__(self, instance, owner):
        if instance is None:
            return self
        try:
            return self.cache[instance]
        except KeyError:
            ret = self.func(instance)
            self.cache[instance] = ret
            return ret

    def __set__(self, instance, value):
        raise AttributeError("LazyFunc set value!!!")

    def __delete__(self, instance):
        del self.cache[instance]


class LazyClsFunc(LazyFunc):

    def __get__(self, instance, owner):
        return super(LazyClsFunc, self).__get__(owner, owner)


class _WeakArgs(Sequence):
    """
    Works with _WeakArgsDict to provide a weak cache for function args.
    When any of those args are gc'd, the pair is removed from the cache.
    """
    def __init__(self, items, dict_remove=None):
        def remove(selfref=ref(self), dict_remove=dict_remove):
            self = selfref()
            if self is not None and dict_remove is not None:
                dict_remove(self)

        self._items, self._selectors = unzip(self._try_ref(item, remove)
                                             for item in items)
        self._items = tuple(self._items)
        self._selectors = tuple(self._selectors)

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return len(self._items)

    @staticmethod
    def _try_ref(item, callback):
        try:
            """ 
                Return a weak reference to object.
                If callback is provided and not None, and the returned weakref object is still alive, 
                the callback will be called when the object is about to be finalized; 
                the weak reference object will be passed as the only parameter to the callback; 
                the referent will no longer be available.
            """
            return ref(item, callback), True
        except TypeError:
            return item, False

    @property
    def alive(self):
        """
        itertools.compress(data, selectors)¶
        Make an iterator that filters elements from data returning only those
        that have a corresponding element in selectors that evaluates to True.
        """
        return all(item() is not None
                   for item in compress(self._items, self._selectors))

    def __eq__(self, other):
        return self._items == other._items

    def __hash__(self):
        try:
            return self.__hash
        except AttributeError:
            h = self.__hash = hash(self._items)
            return h


class _WeakArgsDict(WeakKeyDictionary, object):
    def __delitem__(self, key):
        del self.data[_WeakArgs(key)]

    def __getitem__(self, key):
        return self.data[_WeakArgs(key)]

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.data)

    def __setitem__(self, key, value):
        self.data[_WeakArgs(key, self._remove)] = value

    def __contains__(self, key):
        try:
            wr = _WeakArgs(key)
        except TypeError:
            return False
        return wr in self.data

    def pop(self, key, *args):
        return self.data.pop(_WeakArgs(key), *args)


class _WeakArgsOrderedDict(_WeakArgsDict, object):
    def __init__(self):
        super(_WeakArgsOrderedDict, self).__init__()
        self.data = OrderedDict()

    def popitem(self, last=True):
        while True:
            key, value = self.data.popitem(last)
            if key.alive:
                return tuple(key), value

    def move_to_end(self, key):
        """Move an existing element to the end.

        Raises KeyError if the element does not exist.
        """
        self[key] = self.pop(key)


def _weak_lru_cache(maxsize=100):
    """
    Users should only access the lru_cache through its public API:
    cache_info, cache_clear
    The internals of the lru_cache are encapsulated for thread safety and
    to allow the implementation to change.
    """
    def decorating_function(
            user_function, tuple=tuple, sorted=sorted, len=len,
            KeyError=KeyError):

        hits, misses = [0], [0]
        kwd_mark = (object(),)    # separates positional and keyword args
        lock = Lock()             # needed because OrderedDict isn't threadsafe

        if maxsize is None:
            cache = _WeakArgsDict()  # cache without ordering or size limit

            @wraps(user_function)
            def wrapper(*args, **kwds):
                key = args
                if kwds:
                    key += kwd_mark + tuple(sorted(kwds.items()))
                try:
                    result = cache[key]
                    hits[0] += 1
                    return result
                except KeyError:
                    pass
                result = user_function(*args, **kwds)
                cache[key] = result
                misses[0] += 1
                return result
        else:
            # ordered least recent to most recent
            cache = _WeakArgsOrderedDict()
            cache_popitem = cache.popitem
            cache_renew = cache.move_to_end

            @wraps(user_function)
            def wrapper(*args, **kwds):
                key = args
                if kwds:
                    key += kwd_mark + tuple(sorted(kwds.items()))
                with lock:
                    try:
                        result = cache[key]
                        cache_renew(key)    # record recent use of this key
                        hits[0] += 1
                        return result
                    except KeyError:
                        pass
                result = user_function(*args, **kwds)
                with lock:
                    cache[key] = result     # record recent use of this key
                    misses[0] += 1
                    if len(cache) > maxsize:
                        # purge least recently used cache entry
                        cache_popitem(False)
                return result

        def cache_info():
            """Report cache statistics"""
            with lock:
                return hits[0], misses[0], maxsize, len(cache)

        def cache_clear():
            """Clear the cache and cache statistics"""
            with lock:
                cache.clear()
                hits[0] = misses[0] = 0

        wrapper.cache_info = cache_info
        wrapper.cache_clear = cache_clear
        return wrapper

    return decorating_function


def weak_lru_cache(maxsize=100):
    """Weak least-recently-used cache decorator.

    If *maxsize* is set to None, the LRU features are disabled and the cache
    can grow without bound.

    Arguments to the cached function must be hashable. Any that are weak-
    referenceable will be stored by weak reference.  Once any of the args have
    been garbage collected, the entry will be removed from the cache.

    View the cache statistics named tuple (hits, misses, maxsize, currsize)
    with f.cache_info().  Clear the cache and statistics with f.cache_clear().

    See:  http://en.wikipedia.org/wiki/Cache_algorithms#Least_Recently_Used

    """
    class desc(lazyval):
        def __get__(self, instance, owner):
            if instance is None:
                return self
            try:
                return self._cache[instance]
            except KeyError:
                inst = ref(instance)

                @_weak_lru_cache(maxsize)
                @wraps(self._get)
                def wrapper(*args, **kwargs):
                    return self._get(inst(), *args, **kwargs)

                self._cache[instance] = wrapper
                return wrapper

        @_weak_lru_cache(maxsize)
        def __call__(self, *args, **kwargs):
            return self._get(*args, **kwargs)

    return desc


class CachedObject(object):
    """
    A simple struct for maintaining a cached object with an expiration date.

    Parameters
    ----------
    value : object
        The object to cache.
    expires : datetime-like []
        Expiration date of `value`. The cache is considered invalid for dates
        **strictly greater** than `expires`.
    """
    def __init__(self, value, expires):
        self._value = value
        self._expires = expires

    def unwrap(self, dts):
        """
        Get the cached value.
        dts: sessions
        dts : [start_date, end_date]

        Returns
        -------
        value : object
            The cached value.

        Raises
        ------
        Expired
            Raised when `dt` is greater than self.expires.
        """
        expires = self._expires
        if dts[0] < expires[0] or dts[-1] > expires[-1]:
            raise Expired(expires)
        return self._value

    def _unsafe_get_value(self):
        """You almost certainly shouldn't use this."""
        return self._value

class ExpiredCache(object):
    """
    A cache of multiple CachedObjects, which returns the wrapped the value
    or raises and deletes the CachedObject if the value has expired.

    Parameters
    ----------
    cache : dict-like, optional
        An instance of a dict-like object which needs to support at least:
        `__del__`, `__getitem__`, `__setitem__`
        If `None`, than a dict is used as a default.

    cleanup : callable, optional
        A method that takes a single argument, a cached object, and is called
        upon expiry of the cached object, prior to deleting the object. If not
        provided, defaults to a no-op.

    """
    def __init__(self):
        self._cache = {}
        # cleanup = lambda value_to_clean: None

    def get(self, key, dts):
        """Get the value of a cached object.

        Parameters
        ----------
        key : any
            The key to lookup.
        dts : datetime list e.g.[start, end]
            The time of the lookup.

        Returns
        -------
        result : any
            The value for ``key``.

        Raises
        ------
        KeyError
            Raised if the key is not in the cache or the value for the key
            has expired.
        """
        value = self._cache[key].unwrap(dts)
        return value

    def set(self, key, value, expiration_dt):
        """Adds a new key value pair to the cache.

        Parameters
        ----------
        key : sid
            Asset object sid attribute
        value : any
            The value to store under the name ``key``.
        expiration_dt : datetime
            When should this mapping expire? The cache is considered invalid
            for dates **strictly greater** than ``expiration_dt``.
        """
        self._cache[key] = CachedObject(value, expiration_dt)

    def remove(self, key):
        del self._cache[key]


class DummyMapping(object):
    """
    Dummy object used to provide a mapping interface for singular values.
    """
    def __init__(self, value):
        self._value = value

    def __getitem__(self, key):
        return self._value
