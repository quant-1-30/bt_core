#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from functools import partial

from numpy import array, arange
from pandas import DataFrame, MultiIndex
from toolz import groupby
from collections import defaultdict

from utils.input_validation import expect_types

from .graph import TermGraph, ExecutionPlan
from .hooks import DelegatingHooks
from .assets import AssetFinder


def compute_range_chunks(masks, chunksize):
    """
    Compute a list of ranges from a list of masks.
    """
    from toolz import partition_all

    return (
        (r[0], r[-1]) for r in partition_all(
            chunksize, masks
        )
    )


class GraphEngine(ABC):
    """
    Computation engines for executing Pipelines.

    This module defines the core computation algorithms for executing Pipelines.

    The primary entrypoint of this file is SimplePipelineEngine.run_pipeline, which
    implements the following algorithm for executing pipelines:

    1. Determine the domain of the pipeline. The domain determines the
       top-level set of dates and assets that serve as row- and
       column-labels for the computations performed by this
       pipeline. This logic lives in
       zipline.pipeline.domain.infer_domain.

    2. Build a dependency graph of all terms in `pipeline`, with
       information about how many extra rows each term needs from its
       inputs. At this point we also **specialize** any generic
       LoadableTerms to the domain determined in (1). This logic lives in
       zipline.pipeline.graph.TermGraph and
       zipline.pipeline.graph.ExecutionPlan.

    3. Combine the domain computed in (2) with our AssetFinder to produce
       a "lifetimes matrix". The lifetimes matrix is a DataFrame of
       booleans whose labels are dates x assets. Each entry corresponds
       to a (date, asset) pair and indicates whether the asset in
       question was tradable on the date in question. This logic
       primarily lives in AssetFinder.lifetimes.

    4. Call self._populate_initial_workspace, which produces a
       "workspace" dictionary containing cached or otherwise pre-computed
       terms. By default, the initial workspace contains the lifetimes
       matrix and its date labels.

    5. Topologically sort the graph constructed in (1) to produce an
       execution order for any terms that were not pre-populated.  This
       logic lives in TermGraph.

    6. Iterate over the terms in the order computed in (5). For each term:

       a. Fetch the term's inputs from the workspace, possibly removing
          unneeded leading rows from the input (see ExecutionPlan.offset
          for details on why we might have extra leading rows).

       b. Call ``term._compute`` with the inputs. Store the results into
          the workspace.

       c. Decrement "reference counts" on the term's inputs, and remove
          their results from the workspace if the refcount hits 0. This
          significantly reduces the maximum amount of memory that we
          consume during execution

       This logic lives in SimplePipelineEngine.compute_chunk.

    7. Extract the pipeline's outputs from the workspace and convert them
       into "narrow" format, with output labels dictated by the Pipeline's
       screen. This logic lives in SimplePipelineEngine._to_narrow.
    """

    _finder = AssetFinder()

    @abstractmethod
    def run_pipeline(self, graph: TermGraph, start_date, end_date, hooks=None):
        """
        Compute values for ``pipeline`` from ``start_date`` to ``end_date``.

        Parameters
        ----------
        graph : zipline.pipeline.graph.TermGraph
            The graph to run.
        start_date : pd.Timestamp
            Start date of the computed matrix.
        end_date : pd.Timestamp
            End date of the computed matrix.
        hooks : list[implements(PipelineHooks)], optional
            Hooks for instrumenting Pipeline execution.

        Returns
        -------
        result : pd.DataFrame
            A frame of computed results.

            The ``result`` columns correspond to the entries of
            `pipeline.columns`, which should be a dictionary mapping strings to
            instances of :class:`zipline.pipeline.Term`.

            For each date between ``start_date`` and ``end_date``, ``result``
            will contain a row for each asset that passed `pipeline.screen`.
            A screen of ``None`` indicates that a row should be returned for
            each asset that existed each day.
        """
        raise NotImplementedError("run_pipeline")

    @abstractmethod
    def run_chunked_pipeline(self,
                             graph: TermGraph,
                             session_ix,
                             mask,
                             chunksize,
                             hooks=None):
        """
        Compute values for ``pipeline`` from ``start_date`` to ``end_date``, in
        date chunks of size ``chunksize``.

        Chunked execution reduces memory consumption, and may reduce
        computation time depending on the contents of your pipeline.

        Parameters
        ----------
        graph : zipline.pipeline.graph.TermGraph
            The graph to run.
        start_date : pd.Timestamp
            The start date to run the pipeline for.
        end_date : pd.Timestamp
            The end date to run the pipeline for.
        chunksize : int
            The number of days to execute at a time.
        hooks : list[implements(PipelineHooks)], optional
            Hooks for instrumenting Pipeline execution.

        Returns
        -------
        result : pd.DataFrame
            A frame of computed results.

            The ``result`` columns correspond to the entries of
            `pipeline.columns`, which should be a dictionary mapping strings to
            instances of :class:`zipline.pipeline.Term`.

            For each date between ``start_date`` and ``end_date``, ``result``
            will contain a row for each asset that passed `pipeline.screen`.
            A screen of ``None`` indicates that a row should be returned for
            each asset that existed each day.

        See Also
        --------
        :meth:`zipline.pipeline.engine.PipelineEngine.run_pipeline`
        """
        raise NotImplementedError("run_chunked_pipeline")
    

class NoEngineRegistered(Exception):
    """
    Raised if a user tries to call pipeline_output in an algorithm that hasn't
    set up a pipeline engine.
    """


class SimpleEngine(GraphEngine):
    """
    PipelineEngine class that computes each term independently.

    Parameters
    ----------
    asset_finder : zipline.assets.AssetFinder
        An AssetFinder instance.  We depend on the AssetFinder to determine
        which assets are in the top-level universe at any point in time.
    
    default_hooks : list, optional
        List of hooks that should be used to instrument all pipelines executed
        by this engine.

    See Also
    --------
    :func:`zipline.pipeline.engine.default_populate_initial_workspace`
    """
    __slots__ = ("_root_mask", "default_hooks")

    # @expect_types(
    #     __funcname='SimplePipelineEngine',
    # )
    def __init__(self, _root_mask=None, default_hooks=None):

        if default_hooks is None:
            self._default_hooks = []
        else:
            self._default_hooks = list(default_hooks)

        self._root_mask = _root_mask if _root_mask else defaultdict(set)
        
        # resolved_assets = array(self._finder.retrieve_all(assets))
        # index = _pipeline_output_index(dates, resolved_assets, mask)

    def run_chunked_pipeline(self,
                             graph,
                             session_ix,
                             mask,
                             chunksize,
                             hooks=None):
        """
        Compute values for ``pipeline`` on ``session_ix``, in
        assets chunks of size ``chunksize``.

        Chunked execution reduces memory consumption, and may reduce
        computation time depending on the contents of your pipeline.

        Parameters
        ----------
        pipeline : Pipeline
            The pipeline to run.
        session_ix : pd.Int64Index
            The session index to run the pipeline for.
        mask : set
            The assets to be excluded from the pipeline.
        chunksize : int
            The number of assets to execute at a time.
        hooks : list[implements(PipelineHooks)], optional
            Hooks for instrumenting Pipeline execution.

        Returns
        -------
        result : pd.DataFrame
            A frame of computed results.

            The ``result`` columns correspond to the entries of
            `pipeline.columns`, which should be a dictionary mapping strings to
            instances of :class:`zipline.pipeline.Term`.

            For each date between ``start_date`` and ``end_date``, ``result``
            will contain a row for each asset that passed `pipeline.screen`.
            A screen of ``None`` indicates that a row should be returned for
            each asset that existed each day.

        See Also
        --------
        :meth:`zipline.pipeline.engine.PipelineEngine.run_pipeline`
        """
        compute_mask = self._compute_root_mask(session_ix, mask)
        chunks_mask = compute_range_chunks(
            compute_mask,
            chunksize,
        )
        hooks = self._resolve_hooks(hooks)

        run_pipeline = partial(self._run_pipeline_impl, graph, hooks=hooks)
        with hooks.running_pipeline(graph, mask):
            chunks = [run_pipeline(m) for m in chunks_mask]

        if len(chunks) == 1:
            # OPTIMIZATION: Don't make an extra copy in `categorical_df_concat`
            # if we don't have to.
            return chunks[0]

        # Filter out empty chunks. Empty dataframes lose dtype information,
        # which makes concatenation fail.
        # nonempty_chunks = [c for c in chunks if len(c)]
        # return categorical_df_concat(nonempty_chunks, inplace=True)
        return chunks

    def run_pipeline(self, graph, session_ix, mask, hooks=None):
        """
        Compute values for ``pipeline`` on ``session_ix``.

        Parameters
        ----------
        pipeline : zipline.pipeline.Pipeline
            The pipeline to run.
        start_date : pd.Timestamp
            Start date of the computed matrix.
        end_date : pd.Timestamp
            End date of the computed matrix.
        hooks : list[implements(PipelineHooks)], optional
            Hooks for instrumenting Pipeline execution.

        Returns
        -------
        result : pd.DataFrame
            A frame of computed results.

            The ``result`` columns correspond to the entries of
            `pipeline.columns`, which should be a dictionary mapping strings to
            instances of :class:`zipline.pipeline.Term`.

            For each date between ``start_date`` and ``end_date``, ``result``
            will contain a row for each asset that passed `pipeline.screen`.
            A screen of ``None`` indicates that a row should be returned for
            each asset that existed each day.
        """
        hooks = self._resolve_hooks(hooks)
        compute_mask = self._compute_root_mask(session_ix, mask)
        with hooks.running_pipeline(graph, compute_mask):
            return self._run_pipeline_impl(
                graph,
                session_ix,
                compute_mask,
                hooks,
            )

    def _run_pipeline_impl(self, graph, mask, hooks):
        """Shared core for ``run_pipeline`` and ``run_chunked_pipeline``.
        """
        # See notes at the top of this module for a description of the
        # algorithm implemented here.

        plan = graph.to_execution_plan(mask)

        execution_order = graph.execution_order()

        results = self._compute(
            plan=plan,
            mask=mask,
            execution_order=execution_order,
            hooks=hooks,
        )

        return results

    def _compute_root_mask(self, session_ix, mask):
        """
        Compute a lifetimes matrix from our AssetFinder, then drop columns that
        didn't exist at all during the query dates.

        Parameters
        ----------
        domain : zipline.pipeline.domain.Domain
            Domain for which we're computing a pipeline.
        start_date : pd.Timestamp
            Base start date for the matrix.
        end_date : pd.Timestamp
            End date for the matrix.
        extra_rows : int
            Number of extra rows to compute before `start_date`.
            Extra rows are needed by terms like moving averages that require a
            trailing window of data.

        Returns
        -------
        lifetimes : pd.DataFrame
            Frame of dtype `bool` containing dates from `extra_rows` days
            before `start_date`, continuing through to `end_date`.  The
            returned frame contains as columns all assets in our AssetFinder
            that existed for at least one day between `start_date` and
            `end_date`.
        """

        finder = self._finder
        lifetimes = finder.lifetimes(
            session_ix,
            exclude=mask,
        )

        if not lifetimes.columns.unique:
            columns = lifetimes.columns
            duplicated = columns[columns.duplicated()].unique()
            raise AssertionError("Duplicated sids: %d" % duplicated)

        # Filter out columns that didn't exist from the farthest look back
        # window through the end of the requested dates.
        existed = lifetimes.any()
        ret = lifetimes.loc[:, existed]
        num_assets = ret.shape[1]

        if num_assets == 0:
            raise ValueError(
                f"Failed to find any assets with {session_ix} that traded "
                "\n"
                "This probably means that your asset db is old or that it has "
                "incorrect country/exchange metadata.")

        return ret

    def _compute(self, plan: ExecutionPlan, mask, hooks, kwargs):
        """
        Compute the Pipeline terms in the graph for the requested start and end
        dates.

        This is where we do the actual work of running a pipeline.

        Parameters
        ----------
        plan : zipline.pipeline.graph.ExecutionPlan
            Dependency graph of the terms to be executed.
        sids : pd.Int64Index
            Column labels for our root mask.
        workspace : dict
            Map from term -> output.
            Must contain at least entry for `self._root_mask_term` whose shape
            is `(len(dates), len(assets))`, but may contain additional
            pre-computed terms for testing or optimization purposes.
        refcounts : dict[Term, int]
            Dictionary mapping terms to number of dependent terms. When a
            term's refcount hits 0, it can be safely discarded from
            ``workspace``. See TermGraph.decref_dependencies for more info.
        hooks : implements(PipelineHooks)
            Hooks to instrument pipeline execution.

        Returns
        -------
        results : dict
            Dictionary mapping requested results to outputs.
        """
        # Copy the supplied initial workspace so we don't mutate it in place.
        # Many loaders can fetch data more efficiently if we ask them to
        # retrieve all their inputs at once. For example, a loader backed by a
        # SQL database can fetch multiple columns from the database in a single
        # query.
        #
        # To enable these loaders to fetch their data efficiently, we group
        # together requests for LoadableTerms if they are provided by the same
        # loader and they require the same number of extra rows.
        #
        # The extra rows condition is a simplification: we don't currently have
        # a mechanism for asking a loader to fetch different windows of data
        # for different terms, so we only batch requests together when they're
        # going to produce data for the same set of dates. That may change in
        # the future if we find a loader that can still benefit significantly
        # from batching unequal-length requests.

        # Only produce loader groups for the terms we expect to load.  This
        # ensures that we can run pipelines for graphs where we don't have a
        # loader registered for an atomic term if all the dependencies of that
        # term were supplied in the initial workspace.

        next = kwargs.get('next', True)
        oco = kwargs.get('oco', False)
        # self._inputs_for_term
        with hooks.computing_term(plan):
            output = plan.compile(next=next, oco=oco)
            fmts = self._to_narrow(output, mask, kwargs)
  
        return fmts
       
    def _to_narrow(self, data, mask, kwargs):
        """
        Convert raw computed pipeline results into a DataFrame for public APIs.

        Parameters
        ----------
        data : dict[str -> bool]
            Dict mapping column names to terms.
        mask : ndarray[bool, ndim=2]
            Mask array of values to keep.
        kwargs : dict
            Keyword arguments.

        Returns
        -------
        results : pd.DataFrame
            The indices of `results` are as follows:

            index : two-tiered MultiIndex of (date, asset).
                Contains an entry for each (date, asset) pair corresponding to
                a `True` value in `mask`.
            columns : Index of str
                One column per entry in `data`.

        If mask[date, asset] is True, then result.loc[(date, asset), colname]
        will contain the value of data[colname][date, asset].
        """
        # return MultiIndex(
        #     levels=[dates, assets],
        #     labels=[date_labels, asset_labels],
        #     # TODO: We should probably add names for these.
        #     names=[None, None],
        #     verify_integrity=False,
        # )
        return data

    def _resolve_hooks(self, hooks):
        if hooks is None:
            hooks = []
        return DelegatingHooks(self._default_hooks + hooks)
