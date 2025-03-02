#! /usr/bin/env python3 
# -*- coding: utf-8 -*-

import operator
from collections import defaultdict
from typing import Any
from weakref import WeakValueDictionary
from utils.input_validation import expect_types, optional
from utils.loader import get_module_by_module_path
from utils.sentinel import NotSpecified
from .dtypes import bool_dtype


class Domain:
    """
    Descriptor for the strategy of a term which wraps the strategy module.
    """

    def __init__(self):
        self.proxy = ""

    def __set__(self, instance, value):
        # load module via value
        if not isinstance(value, str):
            raise ValueError("strategy must be a string")
        # load module via value
        module = get_module_by_module_path(value)
        self.strategy = getattr(module, value)()

    def __get__(self, instance, owner):
        return self.strategy

    def __delete__(self, instance):
        del self._obj


class Term(object):

    """
    Wrapper of term as node in graph
    """
    _term_cache = WeakValueDictionary()
    domain = Domain()
    dtype = bool_dtype
    mask = set()
    
    def __new__(cls,
                domain,
                dtype=NotSpecified,
                mask=NotSpecified,
                *args, **kwargs):

        if dtype is NotSpecified:
            dtype = cls.dtype
        if mask is NotSpecified:
            mask = cls.mask

        identity = cls._static_identity(
                    domain=domain,
                    dtype=dtype,
                    mask=mask,
                    *args, **kwargs
        )

        try:
            return cls._term_cache[identity]
        except KeyError:
            new_instance = cls._term_cache[identity] = \
                super(Term, cls).__new__(cls)._init(
                    domain=domain,
                    dtype=dtype,
                    *args, **kwargs
                )
        return new_instance

    def _init(self, domain, dtype, mask, *args, **kwargs):
        self.domain = domain
        self.dtype = dtype
        self.mask = mask
        self.dependencies = set()
        # self.dependencies = [dependencies] if isinstance(dependencies, Term) or dependencies == NotSpecific \
        #     else dependencies
        # return super(ComputableTerm, self)._init(*args, **kwargs)
    
    def __init__(self, *args, **kwargs):
        """
        Noop constructor to play nicely with our caching __new__.  Subclasses
        should implement _init instead of this method.

        When a class' __new__ returns an instance of that class, Python will
        automatically call __init__ on the object, even if a new object wasn't
        actually constructed.  Because we memoize instances, we often return an
        object that was already initialized from __new__, in which case we
        don't want to call __init__ again.

        Subclasses that need to initialize new instances should override _init,
        which is guaranteed to be called only once.
        """
        pass

    def alias(self):
        """
        Make a term from ``self`` that names the expression.

        Parameters
        ----------
        {name}

        Returns
        -------
        aliased : Aliased
            ``self`` with a name.

        Notes
        -----
        This is useful for giving a name to a numerical or boolean expression.
        """
        return self.domain.alias() 
    
    def dependence(self, term):
        """
        The number of extra rows needed for each of our inputs to compute this
        term.
        """
        if not isinstance(term, self):
            raise ValueError("term must be a Term")
        
        self.dependencies.add(term)

    def _ensure_minperiod(self, minperiod):
        self.domain._force(minperiod)

    def _next(self):
        return self.domain._next()
    
    def _next_open(self):
        return self.domain._next_open()
    
    def _once(self):
        return self.domain._oncepost() 
    
    def _once_open(self):
        return self.domain._oncepost_open()
    
    def __eq__(self, other):
        if isinstance(other, self):
            return self.domain == other.domain
        return False

    def __or__(self, other):
        return Pseudo(self, other, operator.__or__)
        
    def __and__(self, other):
        return Pseudo(self, other, operator.__and__)
        
    def __xor__(self):
        # __xor__ is used to customize the behavior of the ^ operator
        return Pseudo(self, self, operator.__xor__)

    def __repr__(self):
        return f"Term(domain={self.domain})"
    
    # @classlazyval
    # def _constant_type(cls):
    # #    from .mixins import ConstantMixin
    #     from .mixins import IfElseMixin
    #     return cls._with_mixin(ConstantMixin)

    # @classmethod
    # def _with_mixin(cls, mixin_type):
    #     return mixin_type.universal_mixin_specialization(
    #         cls._principal_computable_term_type(),
    #     )

    # If a class overrides the __eq__ method , Python automatically sets __hash__ to None
    # By setting __hash__ = object.__hash__, you can override this behavior and ensure that instances remain hashable.

    __hash__ = object.__hash__

 
class Pseudo(Term):
    
    def __init__(self, term_obj1, term_obj2, operator):
        self.term_obj1 = term_obj1
        self.term_obj2 = term_obj2
        self.operator = operator
        
    def next(self):
        return self.operator(self.term_obj1.next(), self.term_obj2.next())
    
    def once(self):
        return self.operator(self.term_obj1.once(), self.term_obj2.once()) 
    
