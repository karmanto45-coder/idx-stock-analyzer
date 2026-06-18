"""
Interval forecasting: pendekatan EMPIRICAL QUANTILE dari distribusi return
historis pada horizon H (bukan single-point prediction — sesuai mandat
skill bahwa forecast harga harus berbentuk interval, bukan angka tunggal).

Untuk horizon harian (H=1), interval WAJIB dipotong ke batas ARA/ARB —
tidak ada angka hasil model yang boleh melebihi batas fisik bursa.
"""
import numpy as np
import pandas as pd

from core.constants import get_ara_pct, get_arb_pct

QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]


def historical_return_quantiles(close: pd.Series, horizon_days: int) -> dict:
    rets = close.pct_change(horizon_days).dropna()
    if len(rets) < 30:
        return {q: np.nan for q in QUANTILES}
    return {q: float(rets.quantile(q)) for q in QUANTILES}


def price_range_forecast(current_price: float, close_history: pd.Series, horizon_days: int) -> dict:
    q_rets = historical_return_quantiles(close_history, horizon_days)
    prices = {f"q{int(q*100)}": current_price * (1 + r) if not np.isnan(r) else None
              for q, r in q_rets.items()}

    ara_pct = get_ara_pct(current_price)
    arb_pct = get_arb_pct(current_price)
    ara_price = round(current_price * (1 + ara_pct), 2)
    arb_price = round(current_price * (1 - arb_pct), 2)

    clipped_note = None
    if horizon_days == 1:
        # WAJIB clip ke batas ARA/ARB harian — batas fisik bursa
        for k, v in prices.items():
            if v is not None and v > ara_price:
                prices[k] = ara_price
                clipped_note = "Beberapa estimasi dipotong ke batas ARA harian"
            elif v is not None and v < arb_price:
                prices[k] = arb_price
                clipped_note = "Beberapa estimasi dipotong ke batas ARB harian"

    return {
        "quantiles": prices,
        "ara_arb_bound": {"ara": ara_price, "arb": arb_price},
        "clipping_note": clipped_note,
        "expected_return_q50": q_rets.get(0.50),
        "n_obs": int(close_history.pct_change(horizon_days).dropna().shape[0]),
    }
