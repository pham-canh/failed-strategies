from freqtrade.strategy import IStrategy
from pandas import DataFrame
import numpy as np
import json
import os
import pandas as pd
from pathlib import Path

DATA_DIR = os.environ.get(
    "FT_DATA_DIR", str(Path(os.environ.get("FREQTRADE_USERDATA", "user_data")) / "data" / "binance" / "futures")
)
UNIVERSE = json.loads(
    Path(os.environ.get("FT_UNIVERSE", str(Path(__file__).resolve().parent.parent / "universe.json"))).read_text()
)

_SWEEP = {}
# Overridable so no strategy is pinned to one machine's /tmp. The file is
# optional: without it the defaults below are used.
_sweep_file = Path(os.environ.get("FT_SWEEP", "/tmp/ft_sweep.json"))
if _sweep_file.exists():
    _SWEEP = json.loads(_sweep_file.read_text())

VOL_WIN = _SWEEP.get("VOL_WIN", 168)
TOP = _SWEEP.get("TOP", 0.80)
BOT = _SWEEP.get("BOT", 0.20)
EXIT_LONG = _SWEEP.get("EXIT_LONG", 0.40)
EXIT_SHORT = _SWEEP.get("EXIT_SHORT", 0.60)
LONG_ONLY = _SWEEP.get("LONG_ONLY", 0)   # 1=disable shorts
SHORT_ONLY = _SWEEP.get("SHORT_ONLY", 1)  # 1=disable longs (research: long low-vol side la drag; edge la short high-vol)
VOL_WIN = _SWEEP.get("VOL_WIN", 168)

# Regime filter (research: low-vol long side chet trong bear market)
BTC_LOOKBACK = _SWEEP.get("BTC_LOOKBACK", 168)
REGIME = _SWEEP.get("REGIME", 1)   # 0=off, 1=long only uptrend, short only downtrend

# Risk management (research: SL/ATR + time-stop, khong stop -10% cung)
ATR_WINDOW = _SWEEP.get("ATR_WINDOW", 14)
SL_ATR_MULT = _SWEEP.get("SL_ATR_MULT", 0.0)   # hard stop = mult * ATR; 0=off
SL_PCT = _SWEEP.get("SL_PCT", -0.15)            # entry-anchored hard stop; 0=use stoploss attr
MAX_HOLD = _SWEEP.get("MAX_HOLD", 0)          # hours; 0=off


class LowVol(IStrategy):
    """
    Low volatility anomaly (Ang, Hodrick, Xing & Zhang 2006, JF).
    Coin co volatility cao -> loi nhuan thap (overvalued boi nha dau tu thich loto).
    Edge chinh la SHORT coin vol cao nhat (rank > TOP) trong downtrend; long side
    low-vol la drag (backtest: SHORT_ONLY) -> mac dinh short-only.
    """

    INTERFACE_VERSION = 3

    can_short = True

    timeframe = "1h"

    minimal_roi = {"0": 100}

    stoploss = -abs(SL_PCT) if SL_PCT else -0.10

    process_only_new_candles = True

    use_custom_stoploss = bool(SL_ATR_MULT)

    def __init__(self, config):
        super().__init__(config)
        self._closes = self._load_all()
        self._btc = self._load_btc()
        self._rank = None
        self._regime = None
        self._atr = {}

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side):
        return 1.0

    def _load_all(self) -> pd.DataFrame:
        closes = {}
        for c in UNIVERSE:
            df = pd.read_feather(f"{DATA_DIR}/{c}_USDT_USDT-1h-futures.feather")
            closes[c] = pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["date"], utc=True))
        return pd.DataFrame(closes).sort_index()

    def _load_btc(self) -> pd.Series:
        df = pd.read_feather(f"{DATA_DIR}/BTC_USDT_USDT-1h-futures.feather")
        return pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["date"], utc=True))

    def _regime_series(self) -> pd.Series:
        if self._regime is None:
            btc = self._btc
            sma = btc.rolling(BTC_LOOKBACK).mean().shift(1)
            self._regime = (btc > sma).astype(float)
        return self._regime

    def _vol_rank(self) -> pd.DataFrame:
        if self._rank is None:
            rets = self._closes.pct_change()
            vol = rets.rolling(VOL_WIN).std()
            self._rank = vol.shift(1).rank(axis=1, pct=True)
        return self._rank

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        coin = metadata["pair"].split("/")[0]
        rank = self._vol_rank()
        idx = dataframe["date"].dt.tz_convert("UTC")
        dataframe["vol_rank"] = rank[coin].reindex(idx).to_numpy()
        if REGIME:
            dataframe["btc_regime"] = self._regime_series().reindex(idx).to_numpy()
        if SL_ATR_MULT:
            h, l, c = dataframe["high"], dataframe["low"], dataframe["close"]
            tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
            atr = tr.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean()
            self._atr[coin] = pd.Series(atr.to_numpy(), index=dataframe["date"]).reindex(self._closes.index).ffill()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        r = dataframe["vol_rank"]
        long_cond = (r < BOT) & r.notna()
        short_cond = (r > TOP) & r.notna()
        if REGIME:
            up = dataframe["btc_regime"] == 1
            long_cond &= up
            short_cond &= ~up
        if LONG_ONLY:
            short_cond = pd.Series(False, index=dataframe.index)
        if SHORT_ONLY:
            long_cond = pd.Series(False, index=dataframe.index)
        dataframe.loc[long_cond, "enter_long"] = 1
        dataframe.loc[short_cond, "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        r = dataframe["vol_rank"]
        dataframe.loc[(r > EXIT_LONG) & (r.notna()), "exit_long"] = 1
        dataframe.loc[(r < EXIT_SHORT) & (r.notna()), "exit_short"] = 1
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if MAX_HOLD and (current_time - trade.open_date_utc).total_seconds() / 3600 >= MAX_HOLD:
            return "max_hold"
        return None

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if not SL_ATR_MULT:
            return self.stoploss
        coin = pair.split("/")[0]
        val = self._atr[coin].asof(current_time)
        if np.isfinite(val) and val > 0:
            return -SL_ATR_MULT * val / current_rate * trade.leverage
        return self.stoploss
