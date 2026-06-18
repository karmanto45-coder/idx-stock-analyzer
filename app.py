"""
IDX Stock Analyzer Pro — Streamlit App
Jalankan dengan: streamlit run app.py
"""
import io

import numpy as np
import pandas as pd
import streamlit as st

from core.backtest import run_backtest
from core.charts import candlestick_with_indicators, equity_curve_chart
from core.constants import DISCLAIMER, HORIZON_DAYS, LQ45_APPROX, MIN_ADTV_IDR
from core.data import compute_adtv_idr, fetch_fundamentals, fetch_ihsg, fetch_ohlcv
from core.forecast import price_range_forecast
from core.indicators import add_all_indicators
from core.scoring import (
    composite_score,
    fundamental_score,
    liquidity_score,
    macro_score,
    red_flag_penalty,
    technical_score,
)
from core.seasonality import best_timing_summary

st.set_page_config(page_title="IDX Stock Analyzer Pro", layout="wide")


def show_disclaimer():
    st.warning(DISCLAIMER, icon="⚠️")


def to_excel_bytes(sheets: dict) -> io.BytesIO:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    buf.seek(0)
    return buf


def compute_beta(stock_close: pd.Series, ihsg_close: pd.Series) -> float:
    df = pd.DataFrame({"s": stock_close, "i": ihsg_close}).dropna()
    if len(df) < 30:
        return 1.0
    r_s = df["s"].pct_change().dropna()
    r_i = df["i"].pct_change().dropna()
    df2 = pd.DataFrame({"s": r_s, "i": r_i}).dropna()
    if df2["i"].var() == 0 or len(df2) < 30:
        return 1.0
    cov = df2.cov().iloc[0, 1]
    return float(cov / df2["i"].var())


@st.cache_data(ttl=3600, show_spinner=False)
def analyze_ticker(ticker: str, horizon_label: str):
    horizon_days = HORIZON_DAYS[horizon_label]
    # 5 tahun: cukup untuk seasonality bulanan & quantile forecast yang lebih stabil
    df = fetch_ohlcv(ticker, period="5y")
    if df.empty or len(df) < 60:
        return None
    df = add_all_indicators(df)
    latest = df.iloc[-1].to_dict()
    current_price = float(latest["Close"])

    ihsg = fetch_ihsg(period="5y")
    beta = compute_beta(df["Close"], ihsg["Close"]) if not ihsg.empty else 1.0
    ihsg_trend_up = bool(ihsg["Close"].iloc[-1] > ihsg["Close"].rolling(50).mean().iloc[-1]) if not ihsg.empty else True

    adtv = compute_adtv_idr(df)
    fund = fetch_fundamentals(ticker)

    t_score, t_factors = technical_score(latest)
    l_score, l_factors, liq_flag = liquidity_score(adtv)
    f_score, f_factors = fundamental_score(fund)
    m_score, m_factors = macro_score(beta, ihsg_trend_up)
    penalty, pen_factors = red_flag_penalty(adtv, fund.get("roe"), ara_arb_streak=0)

    score = composite_score(horizon_label, t_score, l_score, f_score, m_score, penalty)
    fc = price_range_forecast(current_price, df["Close"], min(horizon_days, len(df) // 3))
    timing = best_timing_summary(df["Close"])

    all_factors = t_factors + l_factors + f_factors + m_factors + pen_factors
    # urutkan faktor yang paling berdampak duluan: prioritaskan technical & penalty
    top_factors = (pen_factors + t_factors + f_factors + m_factors + l_factors)[:5]

    return {
        "ticker": ticker,
        "current_price": current_price,
        "composite_score": score,
        "components": {
            "technical": t_score, "liquidity": l_score,
            "fundamental": f_score, "macro": m_score, "red_flag_penalty": penalty,
        },
        "top_factors": top_factors,
        "liquidity_flag": liq_flag,
        "adtv": adtv,
        "forecast": fc,
        "timing": timing,
        "rsi": latest.get("rsi_14"),
        "beta": beta,
        "df": df,
    }


# ---------------- UI ----------------
st.title("📊 IDX Stock Analyzer Pro")
st.caption("Analisis transparan & explainable untuk saham Bursa Efek Indonesia — bukan ML black-box, semua skor bisa dirinci.")
show_disclaimer()

tab1, tab2, tab3 = st.tabs(["🔍 Screening Multi-Saham", "📈 Analisis Satu Saham", "📉 Backtest Strategi"])

with tab1:
    st.subheader("Screening")
    col1, col2 = st.columns([2, 1])
    with col1:
        universe_choice = st.radio("Universe", ["LQ45 (approx.)", "Custom"], horizontal=True)
        if universe_choice == "Custom":
            custom_input = st.text_input(
                "Masukkan ticker, pisahkan koma (contoh: BBCA.JK, TLKM.JK)",
                value="BBCA.JK, BBRI.JK, TLKM.JK, ASII.JK, ANTM.JK",
            )
            tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
        else:
            tickers = LQ45_APPROX
            st.caption(f"{len(tickers)} saham — list LQ45 bisa berubah, verifikasi berkala.")
    with col2:
        horizon_label = st.selectbox("Horizon", list(HORIZON_DAYS.keys()))
        run = st.button("🚀 Jalankan Screening", type="primary", use_container_width=True)

    if run:
        results = []
        progress = st.progress(0.0, text="Memulai...")
        for i, tk in enumerate(tickers):
            progress.progress((i + 1) / len(tickers), text=f"Menganalisis {tk}...")
            try:
                r = analyze_ticker(tk, horizon_label)
                if r:
                    results.append(r)
            except Exception as e:
                st.caption(f"⚠️ Gagal mengambil {tk}: {e}")
        progress.empty()

        if not results:
            st.error("Tidak ada data berhasil diambil. Cek koneksi internet atau ticker yang dimasukkan.")
        else:
            results.sort(key=lambda r: r["composite_score"], reverse=True)
            rows = []
            for r in results:
                q = r["forecast"]["quantiles"]
                tw = r["timing"]
                wd, mo = tw["best_weekday"], tw["best_month"]
                rows.append({
                    "Ticker": r["ticker"],
                    "Harga": f"{r['current_price']:,.0f}",
                    "Skor Komposit": r["composite_score"],
                    "Estimasi Return (q50)": f"{(r['forecast']['expected_return_q50'] or 0)*100:.1f}%",
                    "Rentang Harga (q10-q90)": f"{q['q10']:,.0f} – {q['q90']:,.0f}" if q['q10'] else "n/a",
                    "Likuiditas": r["liquidity_flag"],
                    "Hari Paling Bullish (historis)": f"{wd['name']} ({wd['win_rate_pct']}% win, n={wd['n_obs']})" + ("" if wd["reliable"] else " ⚠️tipis"),
                    "Bulan Paling Bullish (historis)": f"{mo['name']} ({mo['win_rate_pct']}% win, n={mo['n_obs']})" + ("" if mo["reliable"] else " ⚠️tipis"),
                })
            df_out = pd.DataFrame(rows)

            st.markdown("#### 🎯 Top Kandidat & Estimasi Waktu Bullish (Historis)")
            for r in results[:3]:
                tw = r["timing"]
                wd, mo, bk = tw["best_weekday"], tw["best_month"], tw["best_bucket"]
                rel_note = "" if (wd["reliable"] and mo["reliable"]) else " (⚠️ sebagian sampel tipis, lihat catatan di bawah)"
                st.markdown(
                    f"**{r['ticker']}** (skor {r['composite_score']}) — secara historis paling sering naik di "
                    f"hari **{wd['name']}** (win rate {wd['win_rate_pct']}%, n={wd['n_obs']}) dan bulan "
                    f"**{mo['name']}** (win rate {mo['win_rate_pct']}%, n={mo['n_obs']}); pada bagian bulan "
                    f"**{bk['name']}** juga historis paling kuat.{rel_note}"
                )
            st.caption(
                "Ini pola RATA-RATA HISTORIS (calendar effect), BUKAN jaminan tanggal pasti di masa depan. "
                "Tanggal spesifik (misal 'tgl 5') tidak dihitung karena sampelnya terlalu sedikit untuk bermakna "
                "secara statistik — yang ditampilkan adalah hari-dalam-minggu, bagian-bulan, dan bulan, yang "
                "jumlah datanya jauh lebih besar. Tanda ⚠️tipis = jumlah observasi historisnya kecil, jangan "
                "dijadikan dasar utama keputusan."
            )

            st.dataframe(df_out, use_container_width=True, hide_index=True)
            st.caption(
                "Catatan stabilitas ranking: skor di atas adalah snapshot satu titik waktu. "
                "Saham 'thin' likuiditas ditandai — perlakukan sinyalnya dengan skeptis lebih tinggi "
                "(risiko 'saham gorengan')."
            )

            comp_rows = []
            for r in results:
                c = r["components"]
                comp_rows.append({
                    "Ticker": r["ticker"], "Skor Komposit": r["composite_score"],
                    "Teknikal": c["technical"], "Likuiditas": c["liquidity"],
                    "Fundamental": c["fundamental"], "Makro": c["macro"],
                    "Penalti Red-Flag": c["red_flag_penalty"],
                    "Top Faktor": " | ".join(r["top_factors"]),
                })
            df_comp = pd.DataFrame(comp_rows)

            excel_buf = to_excel_bytes({"Screening": df_out, "Komponen Skor": df_comp})
            st.download_button(
                "⬇️ Download Hasil (Excel)", data=excel_buf,
                file_name=f"idx_screening_{horizon_label.split()[0].lower()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            top_red_flag = [r["ticker"] for r in results if r["components"]["red_flag_penalty"] > 0]
            if top_red_flag:
                st.caption(f"🚩 Red-flag terdeteksi pada: {', '.join(top_red_flag)} — lihat detail per saham di tab kedua.")

            st.markdown("#### Rincian faktor per saham (top 3)")
            for r in results[:3]:
                with st.expander(f"{r['ticker']} — skor {r['composite_score']}"):
                    st.json(r["components"])
                    for f in r["top_factors"]:
                        st.write("•", f)

with tab2:
    st.subheader("Analisis Detail Satu Saham")
    ticker = st.text_input("Ticker (format Yahoo, contoh: BBCA.JK)", value="BBCA.JK", key="single_ticker")
    horizon_label2 = st.selectbox("Horizon", list(HORIZON_DAYS.keys()), key="single_horizon")
    if st.button("Analisis", type="primary"):
        with st.spinner(f"Mengambil & menganalisis {ticker}..."):
            r = analyze_ticker(ticker, horizon_label2)
        if r is None:
            st.error("Data tidak ditemukan / terlalu sedikit histori. Cek format ticker (akhiran .JK).")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Harga Terakhir", f"Rp {r['current_price']:,.0f}")
            c2.metric("Skor Komposit", r["composite_score"])
            c3.metric("Status Likuiditas", r["liquidity_flag"])

            st.markdown("##### Komponen Skor (transparan)")
            st.json(r["components"])

            st.markdown("##### Top Faktor Pendorong")
            for f in r["top_factors"]:
                st.write("•", f)

            st.markdown("##### Grafik Candlestick + Indikator")
            st.plotly_chart(candlestick_with_indicators(r["df"].tail(250), ticker), use_container_width=True)

            st.markdown("##### Estimasi Rentang Harga (interval, bukan titik tunggal)")
            fc = r["forecast"]
            q = fc["quantiles"]
            if q["q50"]:
                qdf = pd.DataFrame([
                    {"Persentil": k.upper(), "Estimasi Harga": f"Rp {v:,.0f}"} for k, v in q.items()
                ])
                st.dataframe(qdf, hide_index=True, use_container_width=True)
                st.caption(
                    f"Batas ARA hari ini: Rp {fc['ara_arb_bound']['ara']:,.0f} | "
                    f"Batas ARB hari ini: Rp {fc['ara_arb_bound']['arb']:,.0f}"
                    + (f" | {fc['clipping_note']}" if fc["clipping_note"] else "")
                )
                st.caption(f"Berdasarkan {fc['n_obs']} observasi historis return pada horizon ini.")
            else:
                st.info("Histori data belum cukup untuk estimasi interval yang andal di horizon ini.")

            st.markdown("##### 📅 Kapan Historisnya Paling Sering Bullish?")
            tw = r["timing"]
            wcol, bcol, mcol = st.columns(3)
            for col, key, label in [(wcol, "best_weekday", "Hari"), (bcol, "best_bucket", "Bagian Bulan"), (mcol, "best_month", "Bulan")]:
                d = tw[key]
                col.metric(label, d["name"], f"win rate {d['win_rate_pct']}% (n={d['n_obs']})")
                if not d["reliable"]:
                    col.caption("⚠️ sampel tipis — kurang andal")
            with st.expander("Lihat tabel lengkap pola musiman"):
                st.write("**Per hari dalam minggu:**")
                st.dataframe(tw["weekday_table"].style.format({"avg_return": "{:.2%}", "win_rate": "{:.1%}"}), use_container_width=True)
                st.write("**Per bagian bulan:**")
                st.dataframe(tw["bucket_table"].style.format({"avg_return": "{:.2%}", "win_rate": "{:.1%}"}), use_container_width=True)
                st.write("**Per bulan dalam tahun:**")
                st.dataframe(tw["monthly_table"].style.format({"avg_return": "{:.2%}", "win_rate": "{:.1%}"}), use_container_width=True)
            st.caption(
                "Pola musiman = rata-rata historis (calendar effect), BUKAN prediksi pasti. Pola bulanan "
                "biasanya punya n_obs kecil (hanya beberapa tahun data) — perlakukan sebagai info tambahan, "
                "bukan dasar utama. Pola harian (hari dalam minggu) jauh lebih banyak datanya, jadi relatif "
                "lebih bisa diandalkan secara statistik dibanding pola bulanan."
            )

with tab3:
    st.subheader("Backtest Strategi (SMA Crossover, net of cost)")
    st.caption(
        "Strategi rule-based transparan: beli saat Golden Cross (SMA cepat memotong ke atas SMA lambat), "
        "stop loss & take profit berbasis ATR, keluar saat Death Cross. Biaya transaksi disimulasikan."
    )
    bcol1, bcol2, bcol3 = st.columns(3)
    bt_ticker = bcol1.text_input("Ticker", value="BBCA.JK", key="bt_ticker")
    bt_period = bcol2.selectbox("Panjang histori", ["1y", "2y", "3y", "5y"], index=2, key="bt_period")
    bt_fast_slow = bcol3.selectbox("SMA Fast/Slow", ["10/30", "20/50", "50/200"], index=1, key="bt_fastslow")

    adv = st.expander("Pengaturan lanjutan (stop loss / take profit / biaya)")
    with adv:
        a1, a2, a3, a4 = st.columns(4)
        atr_stop = a1.number_input("ATR x Stop Loss", value=2.0, step=0.5)
        atr_tp = a2.number_input("ATR x Take Profit", value=4.0, step=0.5)
        buy_cost = a3.number_input("Biaya beli (%)", value=0.20, step=0.05) / 100
        sell_cost = a4.number_input("Biaya jual (%)", value=0.30, step=0.05) / 100

    if st.button("▶️ Jalankan Backtest", type="primary"):
        fast, slow = [int(x) for x in bt_fast_slow.split("/")]
        with st.spinner("Mengambil data & menjalankan backtest..."):
            df_bt = fetch_ohlcv(bt_ticker, period=bt_period)
        if df_bt.empty or len(df_bt) < 60:
            st.error("Data tidak ditemukan / terlalu sedikit. Cek ticker (akhiran .JK) atau perpanjang histori.")
        else:
            result = run_backtest(df_bt, fast=fast, slow=slow, atr_mult_stop=atr_stop,
                                   atr_mult_tp=atr_tp, buy_cost_pct=buy_cost, sell_cost_pct=sell_cost)
            if result["metrics"] is None:
                st.warning("Tidak ada trade yang terjadi pada periode ini dengan parameter tersebut.")
            else:
                m = result["metrics"]
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("CAGR Strategi", f"{m['cagr']}%")
                k2.metric("CAGR Buy & Hold", f"{m['buy_and_hold_cagr']}%")
                k3.metric("Sharpe Ratio", m["sharpe"])
                k4.metric("Max Drawdown", f"{m['max_drawdown']}%")
                k5.metric("Win Rate", f"{m['win_rate']}%")
                st.caption(f"Jumlah trade: {m['n_trades']} | Profit factor: {m['profit_factor']} | "
                           f"Periode: {m['period']['start']} s.d. {m['period']['end']} | Net of cost: ✅")

                st.plotly_chart(equity_curve_chart(result["equity_curve"], df_bt["Close"]), use_container_width=True)

                st.markdown("##### Log Transaksi")
                st.dataframe(result["trades"], use_container_width=True, hide_index=True)

                excel_buf_bt = to_excel_bytes({"Metrics": pd.DataFrame([m]), "Trades": result["trades"]})
                st.download_button("⬇️ Download Hasil Backtest (Excel)", data=excel_buf_bt,
                                    file_name=f"backtest_{bt_ticker.replace('.', '_')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                st.caption(
                    "⚠️ Backtest historis TIDAK menjamin performa masa depan. Strategi rule-based sederhana ini "
                    "untuk edukasi & pembanding — semakin sedikit jumlah trade, semakin tidak signifikan "
                    "statistiknya."
                )
