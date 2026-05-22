from bt_core.execution.core.finance.common cimport AdjustmentData, RightData


cdef struct cRatio:
    double sizer_ratio
    double bonus_ratio


cdef inline cRatio calc_ratio(AdjustmentData dividend) nogil:
    """
        股权登记日 ex_date
        股权除息日(为股权登记日下一个交易日)
        但是红股的到账时间不一致(制度是固定的)
        根据上海证券交易规则,对投资者享受的红股和股息实行自动划拨到账。股权(息)登记日为R日,除权(息)基准日为R+1日
        投资者的红股在R+1日自动到账, 并可进行交易,股息在R+2日自动到帐
        其中对于分红的时间存在差异
        根据深圳证券交易所交易规则,投资者的红股在R+3日自动到账,并可进行交易,股息在R+5日自动到账
        持股超过1年 税负5%; 持股1个月至1年 税负10%; 持股1个月以内 税负20%新政实施后,上市公司会先按照5%的最低税率代缴红利税
    """
    cdef cRatio cr

    sizer_ratio = (dividend.bonus_share + dividend.transfer) / 10 + 1.0
    bonus_ratio = dividend.bonus / 10
    cr.sizer_ratio = sizer_ratio
    cr.bonus_ratio = bonus_ratio
    return cr


cdef inline double calc_right(RightData rights) nogil:
    """
        配股机制如果不缴纳款,自动放弃到期除权相当于亏损,在股权登记日卖出 一般的配股缴款起止日为5个交易日
    """
    return 0.0
