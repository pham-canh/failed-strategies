from freqtrade.strategy import IStrategy
from pandas import DataFrame
import numpy as np
import pandas as pd
import json
import os
import pandas as pd
from pathlib import Path

DATA_DIR = os.environ.get(
    "FT_DATA_DIR", str(Path(os.environ.get("FREQTRADE_USERDATA", "user_data")) / "data" / "binance" / "futures")
)
FUNDING_DIR = DATA_DIR

_SWEEP = {}
_sweep_file = Path("/tmp/ft_sweep.json")
if _sweep_file.exists():
    _SWEEP = json.loads(_sweep_file.read_text())

FUND_WINDOW = _SWEEP.get("FUND_WINDOW", 168)
FUND_HOLD = _SWEEP.get("FUND_HOLD", 0.00002)


class Carry(IStrategy):
    """
    Carry (Koijen, Moskowitz, Pedersen & Vrugt 2018, JFE 'Carry').
    Trong futures crypto, carry = funding rate (tra truoc moi 8h).
    Funding duong trung binh -> nguoi short nhan funding -> short.
    Funding am trung binh -> nguoi long nhan funding -> long.
    Don gian nhat cua funding capture, khong can threshold noi bat.
    """

    INTERFACE_VERSION = 3

    can_short = True

    timeframe = "1h"

    minimal_roi = {"0": 100}

    stoploss = -0.10

    process_only_new_candles = True

    def __init__(self, config):
        super().__init__(config)
        self._fund_cache = {}

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side):
        return 1.0

    def _load_funding(self, pair: str) -> pd.Series:
        if pair in self._fund_cache:
            return self._fund_cache[pair]
        coin = pair.split("/")[0]
        df = pd.read_feather(f"{FUNDING_DIR}/{coin}_USDT_USDT-1h-funding_rate.feather")
        s = pd.Series(df["open"].to_numpy(), index=pd.to_datetime(df["date"], utc=True)).sort_index()
        self._fund_cache[pair] = s
        return s

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fund = self._load_funding(metadata["pair"])
        fund_rate = fund.reindex(dataframe["date"].dt.tz_convert("UTC")).ffill()
        dataframe["funding_rate"] = fund_rate.shift(1).to_numpy()
        dataframe["fund_avg"] = dataframe["funding_rate"].rolling(FUND_WINDOW).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fa = dataframe["fund_avg"]
        dataframe.loc[(fa > FUND_HOLD) & (fa.notna()), "enter_short"] = 1
        dataframe.loc[(fa < -FUND_HOLD) & (fa.notna()), "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fa = dataframe["fund_avg"]
        dataframe.loc[(fa < FUND_HOLD) & (fa > -FUND_HOLD) & (fa.notna()), "exit_short"] = 1
        dataframe.loc[(fa < FUND_HOLD) & (fa > -FUND_HOLD) & (fa.notna()), "exit_long"] = 1
        return dataframe
