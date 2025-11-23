import pandas as pd

def resample(ns, df, data, freq="D"):
    # resmaple 生成连续日期
    df = df.astype("float")
    if "datetime" in df.columns:
        data.index = df.index = df.loc[:, "datetime"].apply(lambda x: pd.to_datetime(float(x), unit="s"))
    else:
        df.index = data.index

    if ns == "MetaBtData":
        sample = df.resample(freq, closed="left", label="left").agg({
                'open': 'first',     
                'high': 'max',       
                'low': 'min',         
                'close': 'last',      
                'volume': 'mean',
                'datetime': 'max'
            })
    else:
        sample = df.resample(freq, closed="left", label="left").first()

    sample.dropna(axis=0, how="any", inplace=True) # 剔除非交易日
    # import pdb; pdb.set_trace()

    if "datetime" in sample.columns: 
        sample.drop(columns=["datetime"], inplace=True)
    sample["datetime"] = sample.index
    return sample

