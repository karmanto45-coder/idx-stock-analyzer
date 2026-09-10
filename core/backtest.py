"""
Backtest historis — sesuai mandat skill Section 5:
- Stop loss/take profit berbasis ATR (bukan persentase arbitrer)
- Biaya transaksi realistis (brokerage + levy + VAT, net of cost)
- Metrik: CAGR, Sharpe, Max Drawdown, Win Rate, Profit Factor
- Pembanding: buy & hold

Strategi yang dipakai: SMA crossover (golden/death cross) — dipilih karena
sederhana, transparan, dan mudah dipahami pemula (bukan model fitted/ML,
jadi tidak ada train/test split yang diperlukan — ini rule eksplisit).
"""
import numpy as np
import pandas as pd

from core.indicators import atr as calc_atr
from core.indicators import sma


def run_backtest(
    df_ohlcv: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    atr_mult_stop: float = 2.0,
    atr_mult_tp: float = 4.0,
    buy_cost_pct: float = 0.0020,   # brokerage + levy, estimasi sisi beli
    sell_cost_pct: float = 0.0030,  # brokerage + levy + VAT, estimasi sisi jual
) -> dict:
    df = df_ohlcv.copy()
    df["sma_fast"] = sma(df["Close"], fast)
    df["sma_slow"] = sma(df["Close"], slow)
    df["atr"] = calc_atr(df, 14)
    df = df.dropna(subset=["sma_fast", "sma_slow", "atr"]).copy()

    if len(df) < 30:
        return {"trades": pd.DataFrame(), "metrics": None, "equity_curve": pd.DataFrame()}

    trades = []
    in_position = False
    entry_price = stop_price = tp_price = entry_date = None
    equity = 1.0
    equity_curve = [{"date": df.index[0], "equity": equity}]

    rows = df.to_dict("records")
    idx = df.index
    for i in range(1, len(df)):
        row, prev = rows[i], rows[i - 1]
        golden = prev["sma_fast"] <= prev["sma_slow"] and row["sma_fast"] > row["sma_slow"]
        death = prev["sma_fast"] >= prev["sma_slow"] and row["sma_fast"] < row["sma_slow"]

        if not in_position and golden:
            entry_price = row["Close"] * (1 + buy_cost_pct)
            stop_price = row["Close"] - atr_mult_stop * row["atr"]
            tp_price = row["Close"] + atr_mult_tp * row["atr"]
            entry_date = idx[i]
            in_position = True
        elif in_position:
            exit_reason, exit_price = None, None
            if row["Low"] <= stop_price:
                exit_price, exit_reason = stop_price * (1 - sell_cost_pct), "stop_loss"
            elif row["High"] >= tp_price:
                exit_price, exit_reason = tp_price * (1 - sell_cost_pct), "take_profit"
            elif death:
                exit_price, exit_reason = row["Close"] * (1 - sell_cost_pct), "signal_exit"

            if exit_reason:
                ret = exit_price / entry_price - 1
                trades.append({
                    "entry_date": entry_date, "exit_date": idx[i],
                    "entry_price": entry_price, "exit_price": exit_price,
                    "return_pct": round(ret * 100, 2), "exit_reason": exit_reason,
                })
                equity *= (1 + ret)
                in_position = False

        equity_curve.append({"date": idx[i], "equity": equity})

    equity_df = pd.DataFrame(equity_curve).set_index("date")
    trades_df = pd.DataFrame(trades)

    if trades_df.empty:
        return {"trades": trades_df, "metrics": None, "equity_curve": equity_df}

    n_days = (df.index[-1] - df.index[0]).days or 1
    cagr = equity ** (365 / n_days) - 1
    daily_ret = equity_df["equity"].pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0.0
    running_max = equity_df["equity"].cummax()
    max_dd = (equity_df["equity"] / running_max - 1).min()
    win_rate = (trades_df["return_pct"] > 0).mean()
    gains = trades_df.loc[trades_df["return_pct"] > 0, "return_pct"].sum()
    losses = -trades_df.loc[trades_df["return_pct"] < 0, "return_pct"].sum()
    profit_factor = (gains / losses) if losses > 0 else float("inf")

    buy_hold_ret = df["Close"].iloc[-1] / df["Close"].iloc[0] - 1
    buy_hold_cagr = (1 + buy_hold_ret) ** (365 / n_days) - 1

    metrics = {
        "cagr": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "win_rate": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
        "n_trades": len(trades_df),
        "buy_and_hold_cagr": round(buy_hold_cagr * 100, 2),
        "net_of_costs": True,
        "period": {"start": str(df.index[0].date()), "end": str(df.index[-1].date())},
    }
    return {"trades": trades_df, "metrics": metrics, "equity_curve": equity_df}
