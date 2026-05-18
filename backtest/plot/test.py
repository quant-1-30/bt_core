    # def get_pf_items(self):
    #     '''Returns a tuple of 4 elements which can be used for further processing with
    #       ``pyfolio``

    #       returns, positions, transactions, gross_leverage

    #     Because the objects are meant to be used as direct input to ``pyfolio``
    #     this method makes a local import of ``pandas`` to convert the internal
    #     *backtrader* results to *pandas DataFrames* which is the expected input
    #     by, for example, ``pyfolio.create_full_tear_sheet``

    #     The method will break if ``pandas`` is not installed
    #     '''
    #     # keep import local to avoid disturbing installations with no pandas
    #     import pandas
    #     from pandas import DataFrame as DF

    #     # Returns
    #     cols = ['index', 'return']
    #     returns = DF.from_records(self.rets['returns'].items(),
    #                               index=cols[0], columns=cols)
    #     returns.index = pandas.to_datetime(returns.index)
    #     returns.index = returns.index.tz_localize('UTC')
    #     rets = returns['return']
        
    #     # Positions
    #     pss = self.rets['positions']
    #     ps = [[k] + v[-2:] for k, v in pss.items()]
    #     cols = ps.pop(0)  # headers are in the first entry
    #     positions = DF.from_records(ps, index=cols[0], columns=cols)
    #     positions.index = pandas.to_datetime(positions.index)
    #     positions.index = positions.index.tz_localize('UTC')

    #    # Gross Leverage
    #     cols = ['index', 'gross_lev']
    #     gross_lev = DF.from_records(self.rets['gross_lev'].items(),
    #                                 index=cols[0], columns=cols)

    #     gross_lev.index = pandas.to_datetime(gross_lev.index)
    #     gross_lev.index = gross_lev.index.tz_localize('UTC')
    #     glev = gross_lev['gross_lev']

    #     # Return all together
    #     return rets, positions, glev
