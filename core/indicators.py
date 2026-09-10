"""
Indikator teknikal — implementasi pandas/numpy murni (tanpa dependency
ta-lib yang sering bermasalah saat instalasi).
"""
import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(series: pd.Series, window=20, num_std=2):
    mid = sma(series, window)
    std = series.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def atr(df: pd.DataFrame, window=14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["Close"].diff()).fillna(0)
    return (direction * df["Volume"]).cumsum()


def adx(df: pd.DataFrame, window=14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr_ = tr.ewm(alpha=1 / window, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / window, adjust=False).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / window, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / window, adjust=False).mean().fillna(0)


def historical_volatility(series: pd.Series, window=20) -> pd.Series:
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252)


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan semua indikator ke DataFrame OHLCV (kolom: Open,High,Low,Close,Volume)."""
    out = df.copy()
    close = out["Close"]

    for w in (5, 10, 20, 50, 200):
        out[f"sma_{w}"] = sma(close, w)
    for s in (12, 26):
        out[f"ema_{s}"] = ema(close, s)

    out["rsi_14"] = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)
    out["macd"] = macd_line
    out["macd_signal"] = signal_line
    out["macd_hist"] = hist

    bb_u, bb_m, bb_l = bollinger(close)
    out["bb_upper"], out["bb_mid"], out["bb_lower"] = bb_u, bb_m, bb_l

    out["atr_14"] = atr(out)
    out["obv"] = obv(out)
    out["adx_14"] = adx(out)
    out["hist_vol_20"] = historical_volatility(close, 20)
    out["vol_sma_20"] = sma(out["Volume"], 20)

    return out
