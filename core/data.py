"""
Pengambilan data. Sumber: Yahoo Finance via yfinance (gratis, delay
15-20 menit, kadang ada error harga adjusted di sekitar corporate action —
selalu cross-check angka penting dengan idx.co.id sebelum bertransaksi).
"""
import pandas as pd
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ohlcv(ticker: str, period: str = "2y") -> pd.DataFrame:
    df = yf.download(ticker, period=period, progress=False, auto_adjust=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(how="all")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ihsg(period: str = "2y") -> pd.DataFrame:
    return fetch_ohlcv("^JKSE", period)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usdidr(period: str = "2y") -> pd.DataFrame:
    return fetch_ohlcv("IDR=X", period)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamentals(ticker: str) -> dict:
    """Ambil ringkasan fundamental. Yahoo Finance .info kadang tidak lengkap
    untuk emiten IDX — field yang hilang akan bernilai None, ditangani di
    scoring sebagai data tidak tersedia (bukan dianggap buruk/baik)."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}
    return {
        "pe": info.get("trailingPE"),
        "pbv": info.get("priceToBook"),
        "roe": info.get("returnOnEquity"),
        "eps_growth": info.get("earningsQuarterlyGrowth"),
        "debt_to_equity": info.get("debtToEquity"),
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector"),
    }


def compute_adtv_idr(df: pd.DataFrame, window: int = 20) -> float:
    """Average Daily Transaction Value (Rupiah) — estimasi dari Close*Volume."""
    if df.empty or len(df) < 2:
        return 0.0
    recent = df.tail(window)
    return float((recent["Close"] * recent["Volume"]).mean())
