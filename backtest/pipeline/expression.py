# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 15:37:47 2019

@author: python
"""
import re
import numpy as np
import numexpr
from itertools import chain
from numbers import Number
from numpy import (
    full,
    inf,
)
from numexpr.necompiler import getExprNames

bool_dtype = np.dtype(bool)

_VARIABLE_NAME_RE = re.compile("^(x_)([0-9]+)$")

# Map from op symbol to equivalent Python magic method name.
ops_to_methods = {
    '+': '__add__',
    '-': '__sub__',
    '*': '__mul__',
    '/': '__div__',
    '%': '__mod__',
    '**': '__pow__',
    '&': '__and__',
    '|': '__or__',
    '^': '__xor__',
    '<': '__lt__',
    '<=': '__le__',
    '==': '__eq__',
    '!=': '__ne__',
    '>=': '__ge__',
    '>': '__gt__',
}
# Map from method name to op symbol.
methods_to_ops = {v: k for k, v in ops_to_methods.items()}

# Map from op symbol to equivalent Python magic method name after flipping
# arguments.
ops_to_commuted_methods = {
    '+': '__radd__',
    '-': '__rsub__',
    '*': '__rmul__',
    '/': '__rdiv__',
    '%': '__rmod__',
    '**': '__rpow__',
    '&': '__rand__',
    '|': '__ror__',
    '^': '__rxor__',
    '<': '__gt__',
    '<=': '__ge__',
    '==': '__eq__',
    '!=': '__ne__',
    '>=': '__le__',
    '>': '__lt__',
}
unary_ops_to_methods = {
    '-': '__neg__',
    '~': '__invert__',
}

UNARY_OPS = {'-'}
MATH_BINOPS = {'+', '-', '*', '/', '**', '%'}
FILTER_BINOPS = {'&', '|'}  # NumExpr doesn't support xor.
COMPARISONS = {'<', '<=', '!=', '>=', '>', '=='}

NUMEXPR_MATH_FUNCS = {
    'sin',
    'cos',
    'tan',
    'arcsin',
    'arccos',
    'arctan',
    'sinh',
    'cosh',
    'tanh',
    'arcsinh',
    'arccosh',
    'arctanh',
    'log',
    'log10',
    'log1p',
    'exp',
    'expm1',
    'sqrt',
    'abs',
}


def _ensure_element(tup, elem):
    """
    Create a tuple containing all elements of tup, plus elem.

    Returns the new tuple and the index of elem in the new tuple.
    """
    try:
        return tup, tup.index(elem)
    except ValueError:
        return tuple(chain(tup, (elem,))), len(tup)


class BadBinaryOperator(TypeError):
    """
    Called when a bad binary operation is encountered.

    Parameters
    ----------
    op : str
        The attempted operation
    left : zipline.computable.Term
        The left hand side of the operation.
    right : zipline.computable.Term
        The right hand side of the operation.
    """
    def __init__(self, op, left, right):
        super(BadBinaryOperator, self).__init__(
            "Can't compute {left} {op} {right}".format(
                op=op,
                left=type(left).__name__,
                right=type(right).__name__,
            )
        )


def method_name_for_op(op, commute=False):
    """
    Get the name of the Python magic method corresponding to `op`.

    Parameters
    ----------
    op : str {'+','-','*', '/','**','&','|','^','<','<=','==','!=','>=','>'}
        The requested operation.
    commute : bool
        Whether to return the name of an equivalent method after flipping args.

    Returns
    -------
    method_name : str
        The name of the Python magic method corresponding to `op`.
        If `commute` is True, returns the name of a method equivalent to `op`
        with inputs flipped.

    Examples
    --------
    >>> method_name_for_op('+')
    '__add__'
    >>> method_name_for_op('+', commute=True)
    '__radd__'
    >>> method_name_for_op('>')
    '__gt__'
    >>> method_name_for_op('>', commute=True)
    '__lt__'
    """
    if commute:
        return ops_to_commuted_methods[op]
    return ops_to_methods[op]


def unary_op_name(op):
    return unary_ops_to_methods[op]


def is_comparison(op):
    return op in COMPARISONS


class NumericalExpression(object):
    """
    Term binding to a numexpr expression.

    Parameters
    ----------
    expr : string
        A string suitable for passing to numexpr.  All variables in 'expr'
        should be of the form "x_i", where i is the index of the corresponding
        factor input in 'binds'.
    binds : tuple
        A tuple of factors to use as inputs.
    dtype : np.dtype
        The dtype for the expression.
    """
    window_length = 0

    def __new__(cls, expr, binds, dtype):
        # We always allow filters to be used in windowed computations.
        # Otherwise, an expression is window_safe if all its constituents are
        # window_safe.
        window_safe = (
            (dtype == bool_dtype) or all(t.window_safe for t in binds)
        )

        return super(NumericalExpression, cls).__new__(
            cls,
            inputs=binds,
            expr=expr,
            dtype=dtype,
            window_safe=window_safe,
        )

    def _init(self, expr, *args, **kwargs):
        self._expr = expr
        return super(NumericalExpression, self)._init(*args, **kwargs)

    @classmethod
    def _static_identity(cls, expr, *args, **kwargs):
        return (
            super(NumericalExpression, cls)._static_identity(*args, **kwargs),
            expr,
        )

    def _validate(self):
        """
        Ensure that our expression string has variables of the form x_0, x_1,
        ... x_(N - 1), where N is the length of our inputs.
        """
        variable_names, _unused = getExprNames(self._expr, {})
        expr_indices = []
        for name in variable_names:
            if name == 'inf':
                continue
            match = _VARIABLE_NAME_RE.match(name)
            if not match:
                raise ValueError("%r is not a valid variable name" % name)
            expr_indices.append(int(match.group(2)))

        expr_indices.sort()
        expected_indices = list(range(len(self.inputs)))
        if expr_indices != expected_indices:
            raise ValueError(
                "Expected %s for variable indices, but got %s" % (
                    expected_indices, expr_indices,
                )
            )
        super(NumericalExpression, self)._validate()

    def _compute(self, arrays, dates, assets, mask):
        """
        Compute our stored expression string with numexpr.
        """
        out = full(mask.shape, self.missing_value, dtype=self.dtype)
        # This writes directly into our output buffer.
        numexpr.evaluate(
            self._expr,
            local_dict={
                "x_%d" % idx: array
                for idx, array in enumerate(arrays)
            },
            global_dict={'inf': inf},
            out=out,
        )
        return out

    def _rebind_variables(self, new_inputs):
        """
        Return self._expr with all variables rebound to the indices implied by
        new_inputs.
        """
        expr = self._expr

        # If we have 11+ variables, some of our variable names may be
        # substrings of other variable names. For example, we might have x_1,
        # x_10, and x_100. By enumerating in reverse order, we ensure that
        # every variable name which is a substring of another variable name is
        # processed after the variable of which it is a substring. This
        # guarantees that the substitution of any given variable index only
        # ever affects exactly its own index. For example, if we have variables
        # with indices going up to 100, we will process all of the x_1xx names
        # before x_1x, which will be before x_1, so the substitution of x_1
        # will not affect x_1x, which will not affect x_1xx.
        for idx, input_ in reversed(list(enumerate(self.inputs))):
            old_varname = "x_%d" % idx
            # Temporarily rebind to x_temp_N so that we don't overwrite the
            # same value multiple times.
            temp_new_varname = "x_temp_%d" % new_inputs.index(input_)
            expr = expr.replace(old_varname, temp_new_varname)
        # Clear out the temp variables now that we've finished iteration.
        return expr.replace("_temp_", "_")

    def _merge_expressions(self, other):
        """
        Merge the inputs of two NumericalExpressions into a single input tuple,
        rewriting their respective string expressions to make input names
        resolve correctly.

        Returns a tuple of (new_self_expr, new_other_expr, new_inputs)
        """
        new_inputs = tuple(set(self.inputs).union(other.inputs))
        new_self_expr = self._rebind_variables(new_inputs)
        new_other_expr = other._rebind_variables(new_inputs)
        return new_self_expr, new_other_expr, new_inputs

    def build_binary_op(self, op, other):
        """
        Compute new expression strings and a new inputs tuple for combining
        self and other with a binary operator.
        """
        if isinstance(other, NumericalExpression):
            self_expr, other_expr, new_inputs = self._merge_expressions(other)
        # elif isinstance(other, Term):
        #     self_expr = self._expr
        #     new_inputs, other_idx = _ensure_element(self.inputs, other)
        #     other_expr = "x_%d" % other_idx
        elif isinstance(other, Number):
            self_expr = self._expr
            other_expr = str(other)
            new_inputs = self.inputs
        else:
            raise BadBinaryOperator(op, other)
        return self_expr, other_expr, new_inputs

    @property
    def bindings(self):
        return {
            "x_%d" % i: input_
            for i, input_ in enumerate(self.inputs)
        }

    def __repr__(self):
        return "{typename}(expr='{expr}', bindings={bindings})".format(
            typename=type(self).__name__,
            expr=self._expr,
            bindings=self.bindings,
        )

    def graph_repr(self):
        """Short repr to use when rendering Pipeline graphs."""

        # Replace any floating point numbers in the expression
        # with their scientific notation
        final = re.sub(r"[-+]?\d*\.\d+",
                       lambda x: format(float(x.group(0)), '.2E'),
                       self._expr)
        # Graphviz interprets `\l` as "divide label into lines, left-justified"
        return "Expression:\\l  {}\\l".format(
            final,
        )



# def coerce_numbers_to_my_dtype(f):
#     """
#     A decorator for methods whose signature is f(self, other) that coerces
#     ``other`` to ``self.dtype``.

#     This is used to make comparison operations between numbers and `Factor`
#     instances work independently of whether the user supplies a float or
#     integer literal.

#     For example, if I write::

#         my_filter = my_factor > 3

#     my_factor probably has dtype float64, but 3 is an int, so we want to coerce
#     to float64 before doing the comparison.
#     """
#     @wraps(f)
#     def method(self, other):
#         if isinstance(other, Number):
#             other = coerce_to_dtype(self.dtype, other)
#         return f(self, other)
#     return method


# def binop_return_dtype(op, left, right):
#     """
#     Compute the expected return dtype for the given binary operator.

#     Parameters
#     ----------
#     op : str
#         Operator symbol, (e.g. '+', '-', ...).
#     left : numpy.dtype
#         Dtype of left hand side.
#     right : numpy.dtype
#         Dtype of right hand side.

#     Returns
#     -------
#     outdtype : numpy.dtype
#         The dtype of the result of `left <op> right`.
#     """
#     if is_comparison(op):
#         if left != right:
#             raise TypeError(
#                 "Don't know how to compute {left} {op} {right}.\n"
#                 "Comparisons are only supported between Factors of equal "
#                 "dtypes.".format(left=left, op=op, right=right)
#             )
#         return bool_dtype

#     elif left != float64_dtype or right != float64_dtype:
#         raise TypeError(
#             "Don't know how to compute {left} {op} {right}.\n"
#             "Arithmetic operators are only supported between Factors of "
#             "dtype 'float64'.".format(
#                 left=left.name,
#                 op=op,
#                 right=right.name,
#             )
#         )
#     return float64_dtype


# BINOP_DOCSTRING_TEMPLATE = """
# Construct a :class:`~zipline.pipeline.{rtype}` computing ``self {op} other``.

# Parameters
# ----------
# other : zipline.pipeline.Factor, float
#     Right-hand side of the expression.

# Returns
# -------
# {ret}
# """

# BINOP_RETURN_FILTER = """\
# filter : zipline.pipeline.Filter
#     Filter computing ``self {op} other`` with the outputs of ``self`` and
#     ``other``.
# """

# BINOP_RETURN_FACTOR = """\
# factor : zipline.pipeline.Factor
#     Factor computing ``self {op} other`` with outputs of ``self`` and
#     ``other``.
# """


# def binary_operator(op):
#     """
#     Factory function for making binary operator methods on a Factor subclass.

#     Returns a function, "binary_operator" suitable for implementing functions
#     like __add__.
#     """
#     # When combining a Factor with a NumericalExpression, we use this
#     # attrgetter instance to defer to the commuted implementation of the
#     # NumericalExpression operator.
#     commuted_method_getter = attrgetter(method_name_for_op(op, commute=True))

#     is_compare = is_comparison(op)

#     if is_compare:
#         ret_doc = BINOP_RETURN_FILTER.format(op=op)
#         rtype = 'Filter'
#     else:
#         ret_doc = BINOP_RETURN_FACTOR.format(op=op)
#         rtype = 'Factor'

#     docstring = BINOP_DOCSTRING_TEMPLATE.format(
#         op=op,
#         ret=ret_doc,
#         rtype=rtype,
#     )

#     @with_doc(docstring)
#     @with_name(method_name_for_op(op))
#     @coerce_numbers_to_my_dtype
#     def binary_operator(self, other):
#         # This can't be hoisted up a scope because the types returned by
#         # binop_return_type aren't defined when the top-level function is
#         # invoked in the class body of Factor.
#         return_type = NumExprFilter if is_compare else NumExprFactor

#         if isinstance(self, NumExprFactor):
#             self_expr, other_expr, new_inputs = self.build_binary_op(
#                 op, other,
#             )
#             return return_type(
#                 "({left}) {op} ({right})".format(
#                     left=self_expr,
#                     op=op,
#                     right=other_expr,
#                 ),
#                 new_inputs,
#                 dtype=binop_return_dtype(op, self.dtype, other.dtype),
#             )
#         elif isinstance(other, NumExprFactor):
#             # NumericalExpression overrides ops to correctly handle merging of
#             # inputs.  Look up and call the appropriate reflected operator with
#             # ourself as the input.
#             return commuted_method_getter(other)(self)
#         elif isinstance(other, Term):
#             if self is other:
#                 return return_type(
#                     "x_0 {op} x_0".format(op=op),
#                     (self,),
#                     dtype=binop_return_dtype(op, self.dtype, other.dtype),
#                 )
#             return return_type(
#                 "x_0 {op} x_1".format(op=op),
#                 (self, other),
#                 dtype=binop_return_dtype(op, self.dtype, other.dtype),
#             )
#         elif isinstance(other, Number):
#             return return_type(
#                 "x_0 {op} ({constant})".format(op=op, constant=other),
#                 binds=(self,),
#                 # .dtype access is safe here because coerce_numbers_to_my_dtype
#                 # will convert any input numbers to numpy equivalents.
#                 dtype=binop_return_dtype(op, self.dtype, other.dtype)
#             )
#         raise BadBinaryOperator(op, self, other)

#     return binary_operator

# def unary_operator(op):
#     """
#     Factory function for making unary operator methods for Factors.
#     """
#     # Only negate is currently supported.
#     valid_ops = {'-'}
#     if op not in valid_ops:
#         raise ValueError("Invalid unary operator %s." % op)

#     @with_doc("Unary Operator: '%s'" % op)
#     @with_name(unary_op_name(op))
#     def unary_operator(self):
#         if self.dtype != float64_dtype:
#             raise TypeError(
#                 "Can't apply unary operator {op!r} to instance of "
#                 "{typename!r} with dtype {dtypename!r}.\n"
#                 "{op!r} is only supported for Factors of dtype "
#                 "'float64'.".format(
#                     op=op,
#                     typename=type(self).__name__,
#                     dtypename=self.dtype.name,
#                 )
#             )

#         # This can't be hoisted up a scope because the types returned by
#         # unary_op_return_type aren't defined when the top-level function is
#         # invoked.
#         if isinstance(self, NumericalExpression):
#             return NumExprFactor(
#                 "{op}({expr})".format(op=op, expr=self._expr),
#                 self.inputs,
#                 dtype=float64_dtype,
#             )
#         else:
#             return NumExprFactor(
#                 "{op}x_0".format(op=op),
#                 (self,),
#                 dtype=float64_dtype,
#             )
#     return unary_operator

# def demean(row):
#     return row - np.nanmean(row)


# def zscore(row):
#     return (row - np.nanmean(row)) / np.nanstd(row)


# def winsorize(row, min_percentile, max_percentile):
#     """
#     This implementation is based on scipy.stats.mstats.winsorize
#     """
#     a = row.copy()
#     nan_count = np.isnan(row).sum()
#     nonnan_count = a.size - nan_count

#     # NOTE: argsort() sorts nans to the end of the array.
#     idx = a.argsort()

#     # Set values at indices below the min percentile to the value of the entry
#     # at the cutoff.
#     if min_percentile > 0:
#         lower_cutoff = int(min_percentile * nonnan_count)
#         a[idx[:lower_cutoff]] = a[idx[lower_cutoff]]

#     # Set values at indices above the max percentile to the value of the entry
#     # at the cutoff.
#     if max_percentile < 1:
#         upper_cutoff = int(np.ceil(nonnan_count * max_percentile))
#         # if max_percentile is close to 1, then upper_cutoff might not
#         # remove any values.
#         if upper_cutoff < nonnan_count:
#             start_of_nans = (-nan_count) if nan_count else None
#             a[idx[upper_cutoff:start_of_nans]] = a[idx[upper_cutoff - 1]]

#     return a
