"""Visualisasi candlestick + indikator (Plotly)."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def candlestick_with_indicators(df, ticker: str):
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.20, 0.25], vertical_spacing=0.04,
        subplot_titles=(f"{ticker} — Harga & MA", "Volume", "RSI(14)"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="Harga", increasing_line_color="#16a34a", decreasing_line_color="#dc2626",
    ), row=1, col=1)

    for col, name, dash in [("sma_20", "SMA20", "solid"), ("sma_50", "SMA50", "solid")]:
        if col in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=name,
                                      line=dict(width=1.3, dash=dash)), row=1, col=1)
    if "bb_upper" in df.columns and "bb_lower" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper",
                                  line=dict(width=1, dash="dot", color="gray")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower",
                                  line=dict(width=1, dash="dot", color="gray")), row=1, col=1)

    vol_colors = ["#16a34a" if c >= o else "#dc2626" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=vol_colors), row=2, col=1)

    if "rsi_14" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["rsi_14"], name="RSI(14)",
                                  line=dict(color="#7c3aed")), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#dc2626", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#16a34a", row=3, col=1)

    fig.update_layout(
        height=720, xaxis_rangeslider_visible=False, showlegend=True,
        margin=dict(t=40, b=10, l=10, r=10), legend=dict(orientation="h", y=1.02),
    )
    return fig


def equity_curve_chart(equity_df, buy_hold_series=None):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_df.index, y=equity_df["equity"], name="Strategi (equity)",
                              line=dict(color="#2563eb", width=2)))
    if buy_hold_series is not None:
        norm = buy_hold_series / buy_hold_series.iloc[0]
        fig.add_trace(go.Scatter(x=norm.index, y=norm, name="Buy & Hold",
                                  line=dict(color="#9ca3af", width=1.5, dash="dash")))
    fig.update_layout(height=380, margin=dict(t=20, b=10, l=10, r=10),
                       yaxis_title="Pertumbuhan modal (relatif)", showlegend=True)
    return fig
