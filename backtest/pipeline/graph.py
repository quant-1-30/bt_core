"""
Dependency-Graph representation of Pipeline API terms.
"""
import uuid
import copy
import queue
import networkx as nx
import matplotlib.pyplot as plt
from toolz import valfilter
from functools import reduce, partial
from typing import Mapping
from .visualize import display_graph
from .term import Term
from utils.wrapper import LazyFunc
from utils.search import bfs_by_level
from utils.input_validation import expect_element


class CyclicDependency(Exception):
    pass


# This sentinel value is uniquely-generated at import time so that we can
# guarantee that it never conflicts with a user-provided column name.
#
# (Yes, technically, a user can import this file and pass this as the name of a
# column. If you do that you deserve whatever bizarre failure you cause.)


class TermGraph(object):
    """
    An abstract representation of Pipeline Term dependencies.

    This class does not keep any additional metadata about any term relations
    other than dependency ordering.  As such it is only useful in contexts
    where you care exclusively about order properties (for example, when
    drawing visualizations of execution order).

    Parameters
    ----------
    terms : dict
        A dict mapping names to final output terms.

    Attributes
    ----------
    outputs

    Methods
    -------
    ordered()
        Return a topologically-sorted iterator over the terms in self.
    execution_order(workspace, refcounts)
        Return a topologically-sorted iterator over the terms in self, skipping
        entries in ``workspace`` and entries with refcounts of zero.

    See Also
    --------
    ExecutionPlan
    """
    def __init__(self, terms):
        self.graph = nx.DiGraph()

        self._frozen = False
        parents = set()
        for term in terms.values():
            self._add_to_graph(term, parents)
            assert not parents, "ensure CyclicDependency Error"

        self._outputs = terms

        # Mark that no more terms should be added to the graph.
        self._frozen = True

    def _add_to_graph(self, term, parents):
        """
        Add a term and all its children to ``graph``.

        ``parents`` is the set of all the parents of ``term` that we've added
        so far. It is only used to detect dependency cycles.
        """
        if self._frozen:
            raise ValueError(
                "Can't mutate %s after construction." % type(self).__name__
            )

        # If we've seen this node already as a parent of the current traversal,
        # it means we have an unsatisifiable dependency.  This should only be
        # possible if the term's inputs are mutated after construction.
        if term in parents:
            raise CyclicDependency(term)

        parents.add(term)

        self.graph.add_node(term)

        for dependency in term.dependencies:
            self._add_to_graph(dependency, parents)
            self.graph.add_edge(dependency, term)

        parents.remove(term)

    def __len__(self):
        return len(self._outputs)

    def __contains__(self, term):
        return term in self._outputs

    @LazyFunc
    def screen(self):
        """
        The screen of this pipeline. class:`~zipline.pipeline.Filter` 
        representing criteria for including an asset in the results of a Pipeline.

        Returns
        -------
        screen : zipline.pipeline.Filter or None
            Term defining the screen for this pipeline. If ``screen`` is a
            filter, rows that do not pass the filter (i.e., rows for which the
            filter computed ``False``) will be dropped from the output of this
            pipeline before returning results.

        Notes
        -----
        Setting a screen on a Graph does not change the values produced for
        any rows: it only affects whether a given row is returned. Computing a
        pipeline with a screen is logically equivalent to computing the
        pipeline without the screen and then, as a post-processing-step,
        filtering out any rows for which the screen computed ``False``.
        """
        return 'screen_' + uuid.uuid4().hex

    @LazyFunc
    def initial_refcounts(self):
        """
        Calculate initial refcounts for execution of this graph.

        Parameters
        ----------
        initial_terms : iterable[Term]
            An iterable of terms that were pre-computed before graph execution.

        Each node starts with a refcount equal to its outdegree, and output
        nodes get one extra reference to ensure that they're still in the graph
        at the end of execution.
        """
        refcounts = dict(self.graph.in_degree())
        return refcounts
    
    def ordered(self):
        return iter(nx.topological_sort(self.graph))
    
    def relabel(self, specializations: Mapping={}, copy=False):
        if not specializations:
            specializations = {
                t: t.alias()
                for t in self.graph if isinstance(t, Term)
            }
        self.graph = nx.relabel_nodes(self.graph, specializations, copy=copy)

    def execution_order(self, exclude=[]):
        """
        Return a topologically-sorted list of the terms in ``self`` which
        need to be computed.

        Filters out any terms that are already present in ``workspace``, as
        well as any terms with refcounts of 0.

        Parameters
        ----------
        exclude : list[Term]
            Terms that should be excluded from the execution order.
        refcounts : dict[Term, int]
            Reference counts for terms to be computed. Terms with reference
            counts of 0 do not need to be computed.
        """
        refcounts = self.initial_refcounts()
        return list(nx.topological_sort(
            self.graph.subgraph(
                {
                    term for term, refcount in refcounts.items()
                    if refcount > 0 and term not in exclude
                },
            ),
        ))
    
    def decref_dependencies(self, term):
        """
        Decrement in-edges for ``term`` after computation.

        Parameters
        ----------
        term : zipline.pipeline.Term
            The term whose parents should be decref'ed.
        refcounts : dict[Term -> int]
            Dictionary of refcounts.

        Return
        ------
        garbage : set[Term]
            Terms whose refcounts hit zero after decrefing.
        """
        garbage = set()
        new_graph = copy.copy(self.graph)
        refcounts = dict(self.graph.out_degree())
        # Edges are tuple of (from, to).
        for parent, _ in self.graph.in_edges([term]):
            # No one else depends on this term. Remove it from the
            # workspace to conserve memory.
            if refcounts[parent] == 1:
                new_graph.remove_node(parent)
        return garbage
    
    def to_execution_plan(self, initial_include=True):
        """
        Compile into an ExecutionPlan.

        Returns
        -------
        graph : zipline.pipeline.graph.ExecutionPlan
            Graph encoding term dependencies, including metadata about extra
            row requirements.
        """
        plan = ExecutionPlan(self.graph)
        return plan

    @expect_element(format=('svg', 'png', 'jpeg'))
    def show_graph(self, format='svg'):
        """
        Render this Pipeline as a DAG.

        Parameters
        ----------
        format : {'svg', 'png', 'jpeg'}
            Image format to render with.  Default is 'svg'.
        """
        return display_graph(self, format)
    
    def draw(self):
        # plt.subplot(121)
        # nx.draw(self.graph)
        # plt.subplot(122)
        # nx.draw(self.graph, pos=nx.circular_layout(self.graph),
        #         node_color='r', edge_color='b')
        nx.draw_networkx(self.graph, pos=nx.circular_layout(self.graph),
                         node_color='r', edge_color='b')
        plt.show()


class ExecutionPlan(object):
    """
    Graph represention of Pipeline Term dependencies that includes metadata
    about extra rows required to perform computations.

    Each node in the graph has an `extra_rows` attribute, indicating how many,
    if any, extra rows we should compute for the node.  Extra rows are most
    often needed when a term is an input to a rolling window computation.  For
    example, if we compute a 30 day moving average of price from day X to day
    Y, we need to load price data for the range from day (X - 29) to day Y.

    Parameters
    ----------
    domain : zipline.pipeline.domain.Domain
        The domain of execution for which we need to build a plan.
    terms : dict
        A dict mapping names to final output terms.
    start_date : pd.Timestamp
        The first date for which output is requested for ``terms``.
    end_date : pd.Timestamp
        The last date for which output is requested for ``terms``.

    Attributes
    ----------
    domain
    extra_rows
    outputs
    offset
    """
    def __init__(self, graph, minperiod=0):
        # super(ExecutionPlan, self).__init__(graph)

        # Specialize all the LoadableTerms in the graph to our domain, so that
        # when the engine requests an execution order, we emit the specialized
        # versions of loadable terms.
        #
        # NOTE: We're explicitly avoiding using self.loadable_terms here.
        #
        # At this point the graph still contains un-specialized loadable terms,
        # and this is where we're actually going through and specializing all
        # of them. We don't want use self.loadable_terms because it's a
        # lazyval, and we don't want its result to be cached until after we've
        # specialized.
        specializations = {
                t: t.alias()
                for t in self.graph if isinstance(t, Term)
        }
        
        self.graph = nx.relabel_nodes(graph, specializations)
    
    def compile(self, next=True, oco=False):
        # for term in execution_order:
        #     # `term` may have been supplied in `initial_workspace`, or we may
        #     # have loaded `term` as part of a batch with another term coming
        #     # from the same loader (see note on loader_group_key above). In
        #     # either case, we already have the term computed, so don't
        #     # recompute.
        #     if term in workspace:
        #         continue

        #     # Asset labels are always the same, but date labels vary by how
        #     # many extra rows are needed.
        #     mask, mask_dates = graph.mask_and_dates_for_term(
        #         term,
        #         self._root_mask_term,
        #         workspace,
        #         dates,
        #     )

        #     with hooks.computing_term(term):
        #             workspace[term] = term._compute(
        #                 self._inputs_for_term(
        #                     term,
        #                     workspace,
        #                     graph,
        #                     domain,
        #                     refcounts,
        #                 ),
        #                 mask_dates,
        #                 sids,
        #                 mask,
        #             )

        #         # Decref dependencies of ``term``, and clear any terms
        #         # whose refcounts hit 0.
        #     for garbage in graph.decref_dependencies(term, refcounts):
        #             del workspace[garbage]

        # # At this point, all the output terms are in the workspace.
        # out = {}
        # graph_extra_rows = graph.extra_rows
        # for name, term in iteritems(graph.outputs):
        #     # Truncate off extra rows from outputs.
        #     out[name] = workspace[term][graph_extra_rows[term]:]
        # return out
        self._ensure_minperiod()
        pipelines = self.to_execution_plan()
        compute = partial(self._compute, next=next) if not oco else partial(self._compute_open, next=next)
        for level in range(len(pipelines)):
            passthrough = compute(pipelines[level])
            if not passthrough:
                return False
        return True
    
    def to_execution_plan(self, initial_include=True):
        """
        Compile into an ExecutionPlan.

        Returns
        -------
        graph : zipline.pipeline.graph.ExecutionPlan
            Graph encoding term dependencies, including metadata about extra
            row requirements.
        """
        refcounts = self.graph.initial_refcounts()
        start_nodes = valfilter(lambda x: x == 0, refcounts)
        start_nodes = list(start_nodes.keys())
        pipelines = bfs_by_level(self.graph, start_nodes)
        if initial_include:
            pipelines[0].extend(start_nodes)
        return pipelines

    def _compute(self, terms, next=True):
        if next:
            _outputs = [term._compute_next() for term in terms]
        else:
            _outputs = [term._compute_once() for term in terms]
        passthrough = reduce(lambda x, y: set(x) & set(y), _outputs)
        return passthrough
    
    def _compute_open(self, terms, next=True):
        if next:
            _outputs = [term._compute_next_open() for term in terms]
        else:
            _outputs = [term._compute_once_open() for term in terms]
        passthrough = reduce(lambda x, y: set(x) & set(y), _outputs)
        return passthrough

    def _ensure_minperiod(self):
        """
        Ensure all terms have the same _minperiods to ensure next method
        """
        graph_minperiod = max([term._minperiods for term in self.graph])
        if graph_minperiod < 0:
            raise ValueError(
                "graph_minperiod is greater than the minperiod of the domain"
            )
        # force update domain minperiod
        for term in self.graph._outputs:
            term._ensure_minperiod(graph_minperiod)

