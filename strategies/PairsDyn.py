from freqtrade.strategy import IStrategy
from pandas import DataFrame
import pandas as pd
import numpy as np
import json
import os
from pathlib import Path

DATA_DIR = os.environ.get(
    "FT_DATA_DIR", str(Path(os.environ.get("FREQTRADE_USERDATA", "user_data")) / "data" / "binance" / "futures")
)

_SWEEP = {}
_sweep_file = Path(os.environ.get("PA_SWEEP", "/tmp/ft_sweep.json"))
if _sweep_file.exists():
    _SWEEP = json.loads(_sweep_file.read_text())

PAIRS_FILE = _SWEEP.get("PAIRS_FILE", str(Path(os.environ.get("FT_PAIRS", str(Path(__file__).resolve().parent.parent / "pairs_dyn.json")))))

ENTRY_Z = _SWEEP.get("ENTRY_Z", 2.0)
EXIT_Z = _SWEEP.get("EXIT_Z", 0.05)
SPAN = _SWEEP.get("SPAN", 48)

MAX_HOLD = _SWEEP.get("MAX_HOLD", 336)
STOP_Z = _SWEEP.get("STOP_Z", 4.0)
CORR_GATE = _SWEEP.get("CORR_GATE", 1)
CORR_MIN = _SWEEP.get("CORR_MIN", 0.70)
CORR_WINDOW = _SWEEP.get("CORR_WINDOW", 480)
ADF_GATE = _SWEEP.get("ADF_GATE", 1)
ADF_WINDOW = _SWEEP.get("ADF_WINDOW", 720)
ADF_CRIT = _SWEEP.get("ADF_CRIT", -2.86)
LEVERAGE = _SWEEP.get("LEVERAGE", 3.0)
TP_PCT = _SWEEP.get("TP_PCT", 0.0)   # exit at +profit_ratio (0=off)


class PairsDyn(IStrategy):
    """Pairs trading voi bo cap ROLLING: moi tuan chon lai cac cap cointegrated
    tu cua so formation moi nhat (pairs_dyn.json). Long A + short B cung von,
    z-score > entry: short a / long b. Exit khi z ve 0. TP_PCT de khoa loi som."""

    INTERFACE_VERSION = 3

    can_short = True

    timeframe = "1h"

    minimal_roi = {"0": 100}

    stoploss = -0.10

    process_only_new_candles = True

    def __init__(self, config):
        super().__init__(config)
        windows = json.loads(Path(PAIRS_FILE).read_text())
        self._starts = np.array([pd.Timestamp(w["start"]).value for w in windows])
        self._pairs = [w["pairs"] for w in windows]
        self._cache = {}

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side):
        return LEVERAGE

    def _load_close(self, coin: str) -> pd.Series:
        if coin in self._cache:
            return self._cache[coin]
        df = pd.read_feather(f"{DATA_DIR}/{coin}_USDT_USDT-1h-futures.feather")
        s = pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["date"], utc=True)).sort_index()
        self._cache[coin] = s
        return s

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        coin = metadata["pair"].split("/")[0]
        idx = dataframe["date"]
        t_vals = idx.to_numpy().astype("datetime64[ns]").astype("int64")
        wi = np.searchsorted(self._starts, t_vals, side="right") - 1
        n = len(dataframe)
        p_self = dataframe["close"].to_numpy()
        log_s = np.log(p_self)

        role = np.full(n, "none", dtype=object)
        z = np.full(n, np.nan)

        # per-window pair membership + EWM z (reset at window boundary, warmup gate)
        for i in np.unique(wi):
            if i < 0:
                continue
            m = {}
            for p in self._pairs[i]:
                m[p["a"]] = {"partner": p["b"], "beta": p["beta"], "role": "a"}
                m[p["b"]] = {"partner": p["a"], "beta": p["beta"], "role": "b"}
            if coin not in m:
                continue
            mask = wi == i
            inv = m[coin]
            role[mask] = inv["role"]
            p_partner = self._load_close(inv["partner"]).reindex(idx[mask]).ffill().to_numpy()
            if inv["role"] == "a":
                spread = log_s[mask] - inv["beta"] * np.log(p_partner)
            else:
                spread = np.log(p_partner) - inv["beta"] * log_s[mask]
            s = pd.Series(spread, index=idx[mask])
            ema = s.ewm(span=SPAN, adjust=False).mean()
            std = s.ewm(span=SPAN, adjust=False).std()
            zr = ((s - ema) / std).shift(1).to_numpy()
            z[mask] = zr

        dataframe["z"] = z
        dataframe["role"] = role
        dataframe["corr"] = np.full(n, np.nan)
        dataframe["adf_t"] = np.full(n, np.nan)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        z = dataframe["z"]
        role = dataframe["role"]
        ok = None
        if CORR_GATE:
            ok = dataframe["corr"] > CORR_MIN
        if ADF_GATE:
            adf = dataframe["adf_t"] <= ADF_CRIT
            ok = adf if ok is None else (ok & adf)
        a = role == "a"
        b = role == "b"
        zhi = (z > ENTRY_Z) & z.notna()
        zlo = (z < -ENTRY_Z) & z.notna()
        if ok is not None:
            zhi &= ok
            zlo &= ok
        dataframe.loc[a & zhi, "enter_short"] = 1
        dataframe.loc[a & zlo, "enter_long"] = 1
        dataframe.loc[b & zhi, "enter_long"] = 1
        dataframe.loc[b & zlo, "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        z = dataframe["z"]
        role = dataframe["role"]
        a = role == "a"
        b = role == "b"
        if STOP_Z > 0:
            hi = (z < EXIT_Z) | (z > STOP_Z)
            lo = (z > -EXIT_Z) | (z < -STOP_Z)
        else:
            hi = z < EXIT_Z
            lo = z > -EXIT_Z
        dataframe.loc[a & hi, "exit_short"] = 1
        dataframe.loc[a & lo, "exit_long"] = 1
        dataframe.loc[b & hi, "exit_long"] = 1
        dataframe.loc[b & lo, "exit_short"] = 1
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if MAX_HOLD > 0 and (current_time - trade.open_date_utc).total_seconds() / 3600 >= MAX_HOLD:
            return "max_hold"
        if TP_PCT > 0 and current_profit >= TP_PCT:
            return "take_profit"
        coin = pair.split("/")[0]
        ct = pd.Timestamp(current_time)
        if ct.tzinfo is not None:
            tv = ct.tz_convert("UTC").value
        else:
            tv = ct.value
        wi = int(np.searchsorted(self._starts, tv, side="right") - 1)
        if wi >= 0 and wi < len(self._pairs):
            active = any(p["a"] == coin or p["b"] == coin for p in self._pairs[wi])
            if not active:
                return "pair_changed"
        return None
