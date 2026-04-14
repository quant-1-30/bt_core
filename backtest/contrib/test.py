# def prepare_universe(start_date: int, end_date: int, market:str, frac=0.1):
#     md_api = initialize_mdapi()
#     table = md_api.get_instrument() 
#     mask = pc.and_(
#         pc.less(table["first_trading"], end_date * 10000),
#         # pc.greater(table["delist"], start_date * 10000)
#         pc.starts_with(table["sid"], market)
#     )
#     filter_table = table.filter(mask)
#     num_rows = filter_table.num_rows
#     num_samples = int(num_rows * frac)
#     sample_table = filter_table.take(np.random.choice(num_rows, size=num_samples, replace=False))
#     samples = sample_table.column("sid").cast(pa.binary()).to_pylist() # view(pa.uint8()) 
#     universe = filter_table.column("sid").cast(pa.binary()).to_pylist() # view(pa.uint8())
#     return md_api, universe, samples