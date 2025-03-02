
#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 27 15:37:47 2025

@author: python
"""
from .iface import PipelineHooks, contextmanager


class NoHooks(PipelineHooks):
    """A PipelineHooks that defines no-op methods for all available hooks.
    """
    @contextmanager
    def running_pipeline(self, pipeline, start_date, end_date):
        yield

    @contextmanager
    def computing_chunk(self, terms, start_date, end_date):
        yield

    @contextmanager
    def loading_terms(self, terms):
        yield

    @contextmanager
    def computing_term(self, term):
        yield
