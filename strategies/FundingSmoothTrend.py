from freqtrade.strategy import IStrategy, IntParameter
from pandas import DataFrame
import talib.abstract as ta


class FundingSmoothTrend(IStrategy):
    """
    Công thức: EMA trend-following CÓ VOLATILITY FILTER + trend-direction filter.
    Khác với trend-following "YouTube classic" (EMA 13/80, win 21%, lỗ -0.87%/lệnh):
    - Lọc trend mạnh (ADX) trước khi vào - chỉ trend thật mới theo
    - Chặn timeframes dài (1D/4H chết vì fee khuếch đại)
    - Chỉ top liquid pairs
    """

    INTERFACE_VERSION = 3

    can_short = False

    timeframe = "1h"

    minimal_roi = {
        "0": 0.35,
        "60": 0.20,
        "240": 0.10,
        "480": 0,
    }

    stoploss = -0.06

    use_custom_stoploss = False

    process_only_new_candles = True

    ema_fast = IntParameter(10, 30, default=20, space="buy")
    ema_slow = IntParameter(40, 100, default=60, space="buy")
    adx_threshold = IntParameter(20, 35, default=25, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["adx"] > self.adx_threshold.value)
                & (dataframe["adx"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] < dataframe["ema_slow"]),
            "exit_long",
        ] = 1
        return dataframe
