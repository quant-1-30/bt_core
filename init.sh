#! /bin/bash

# set +e # warning continue

# initialize database
poetry run python init.py

# activte web
cd backtest && poetry run python cerebro.py

