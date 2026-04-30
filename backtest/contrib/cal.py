    # def addcalendar(self, cal=None):
    #     '''Adds a global trading calendar to the system. Individual data feeds
    #     may have separate calendars which override the global one

    #     ``cal`` can be an instance of ``TradingCalendar`` a string or an
    #     instance of ``pandas_market_calendars``. A string will be will be
    #     instantiated as a ``PandasMarketCalendar`` (which needs the module
    #     ``pandas_market_calendar`` installed in the system.

    #     If a subclass of `TradingCalendarBase` is passed (not an instance) it
    #     will be instantiated
    #     '''
    #     if cal and issubclass(cal, TradingCalendarBase): 
    #         self._tradingcal = cal
    #     else:
    #         self._tradingcal = TradingCalendar()

    # def addsizer(self, sizer="fixed", **kwargs):
    #     '''Adds a ``Sizer`` class (and args) which is the default sizer for any
    #     strategy added to cerebro
    #     '''
    #     self.sizer = _sizers[sizer](**kwargs)

    # def addrisk(self, risk="tl", **kwargs):
    #     '''Adds a ``RiskControl`` class (and args) which is the default risk for any
    #     strategy added to cerebro
    #     '''
    #     self._r = _rctl[risk](**kwargs)

