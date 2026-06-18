"""
IDX Stock Analyzer Pro — Streamlit App (Enhanced)
Tambahan:
  - Tab 4: 🌟 Rekomendasi Bullish Harian (semua IDX, AI-powered)
  - Tab 5: 🎯 Decision Engine Beli/Jual/Hold

Jalankan dengan: streamlit run app.py
"""
import io
import datetime
import time
import requests

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

# ================================================================
# FULL IDX UNIVERSE (representatif, bisa diperluas)
# ================================================================
IDX_FULL_UNIVERSE = [
    # Blue chips & LQ45
    "BBCA.JK","BBRI.JK","BMRI.JK","BBNI.JK","BRIS.JK","BTPS.JK","BJTM.JK",
    "TLKM.JK","ASII.JK","UNVR.JK","HMSP.JK","GGRM.JK","ICBP.JK","INDF.JK",
    "KLBF.JK","SIDO.JK","MYOR.JK","ULTJ.JK",
    # Tambang & Energi
    "ANTM.JK","TINS.JK","INCO.JK","PTBA.JK","ADRO.JK","BUMI.JK","ITMG.JK",
    "HRUM.JK","MBMA.JK","NCKL.JK","MDKA.JK","PSAB.JK","SMMT.JK","ELSA.JK",
    "MEDC.JK","PGAS.JK","AKRA.JK","ESSA.JK",
    # Properti & Konstruksi
    "BSDE.JK","SMRA.JK","CTRA.JK","PWON.JK","LPKR.JK","JRPT.JK","WSKT.JK",
    "WIKA.JK","PTPP.JK","ADHI.JK","TOTL.JK",
    # Consumer & Retail
    "ACES.JK","MAPA.JK","RALS.JK","LPPF.JK","HERO.JK","SRTG.JK","CLEO.JK",
    "FOOD.JK","HOKI.JK","CAMP.JK","AISA.JK","GOOD.JK","DMND.JK","SKLT.JK",
    # Telekomunikasi & Teknologi
    "EXCL.JK","ISAT.JK","LINK.JK","MLPT.JK","TOWR.JK","SUPR.JK","TBIG.JK",
    "BUKA.JK","GOTO.JK","EMTK.JK","KIOS.JK","INET.JK",
    # Transportasi & Logistik
    "GIAA.JK","BIRD.JK","ASSA.JK","SMDR.JK","TMAS.JK","WINS.JK","NELY.JK",
    # Kesehatan & Farmasi
    "KAEF.JK","KLBF.JK","MIKA.JK","SAME.JK","HEAL.JK","PRIM.JK","PRDA.JK",
    "SOHO.JK","PYFA.JK","INAF.JK",
    # Perkebunan & Agribisnis
    "AALI.JK","LSIP.JK","SSMS.JK","BWPT.JK","DSNG.JK","PALM.JK","ANJT.JK",
    # Semen & Material
    "SMGR.JK","INTP.JK","SEMEN.JK","TPIA.JK","BRPT.JK","INKP.JK","TKIM.JK",
    # Otomotif & Manufaktur
    "ASII.JK","AUTO.JK","SMSM.JK","IMAS.JK","HEXA.JK","MPMX.JK","MASA.JK",
    # Keuangan Non-Bank
    "ADMF.JK","BFIN.JK","CFIN.JK","VRNA.JK","MFIN.JK","WOMF.JK","PNLF.JK",
    # Small-Mid Cap Potensial
    "AVIA.JK","DCII.JK","GTSI.JK","CUAN.JK","MIDI.JK","FAST.JK","KINO.JK",
    "WOOD.JK","TOBA.JK","DSSA.JK","HAIS.JK","CMNT.JK","TRGU.JK","BOBA.JK",
]
# Deduplikasi
IDX_FULL_UNIVERSE = list(dict.fromkeys(IDX_FULL_UNIVERSE))


# ================================================================
# HELPER FUNCTIONS
# ================================================================

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
        "macd": latest.get("macd", None),
        "macd_signal": latest.get("macd_signal", None),
        "ema20": latest.get("ema_20", None),
        "ema50": latest.get("ema_50", None),
        "bb_upper": latest.get("bb_upper", None),
        "bb_lower": latest.get("bb_lower", None),
        "volume": latest.get("Volume", None),
        "vol_avg20": df["Volume"].rolling(20).mean().iloc[-1] if "Volume" in df.columns else None,
        "beta": beta,
        "df": df,
        "fund": fund,
        "ihsg_trend_up": ihsg_trend_up,
        "latest": latest,
    }


# ================================================================
# BULLISH SIGNAL DETECTOR
# ================================================================

def detect_bullish_signals(r: dict) -> list[str]:
    """Identifikasi sinyal bullish secara eksplisit."""
    signals = []
    lat = r.get("latest", {})
    rsi = r.get("rsi")
    macd = r.get("macd")
    macd_sig = r.get("macd_signal")
    ema20 = r.get("ema20")
    ema50 = r.get("ema50")
    price = r.get("current_price", 0)
    bb_lower = r.get("bb_lower")
    vol = r.get("volume")
    vol_avg = r.get("vol_avg20")

    if rsi and 30 < rsi < 60:
        signals.append(f"RSI {rsi:.1f} — zona recovery (30–60), momentum beli mulai terbentuk")
    if rsi and rsi < 35:
        signals.append(f"RSI {rsi:.1f} — oversold, potensi reversal/rebound kuat")
    if macd and macd_sig and macd > macd_sig:
        signals.append("MACD golden cross — momentum beli lebih kuat dari sinyal jual")
    if ema20 and ema50 and ema20 > ema50:
        signals.append("EMA 20 > EMA 50 — tren jangka pendek lebih kuat, uptrend aktif")
    if price and ema20 and price > ema20:
        signals.append("Harga di atas EMA 20 — konfirmasi tren naik jangka pendek")
    if bb_lower and price and price <= bb_lower * 1.02:
        signals.append("Harga menyentuh/mendekati Bollinger Band bawah — zona support kuat")
    if vol and vol_avg and vol > vol_avg * 1.3:
        signals.append(f"Volume hari ini {vol/vol_avg:.1f}x rata-rata 20 hari — akumulasi institusi")
    if r.get("ihsg_trend_up"):
        signals.append("IHSG di atas MA-50 — sentimen pasar keseluruhan positif (makro mendukung)")

    comp = r.get("components", {})
    if comp.get("technical", 0) >= 70:
        signals.append(f"Skor teknikal tinggi ({comp['technical']}) — mayoritas indikator bullish")
    if comp.get("fundamental", 0) >= 60:
        signals.append(f"Fundamental kuat (skor {comp['fundamental']}) — nilai intrinsik mendukung")

    timing = r.get("timing", {})
    if timing:
        today_name = datetime.datetime.today().strftime("%A")
        wd = timing.get("best_weekday", {})
        if wd.get("name", "") in today_name or today_name in wd.get("name", ""):
            signals.append(
                f"Hari ini ({today_name}) secara historis hari terkuat untuk saham ini "
                f"(win rate {wd.get('win_rate_pct',0)}%)"
            )

    return signals if signals else ["Tidak ada sinyal bullish dominan yang terdeteksi hari ini"]


# ================================================================
# DECISION ENGINE
# ================================================================

def make_decision(r: dict, user_avg_price: float | None = None) -> dict:
    """
    Menghasilkan rekomendasi BELI / JUAL / HOLD beserta reasoning.
    """
    score = r.get("composite_score", 50)
    signals = detect_bullish_signals(r)
    comp = r.get("components", {})
    price = r.get("current_price", 0)
    rsi = r.get("rsi")
    penalty = comp.get("red_flag_penalty", 0)
    liq_flag = r.get("liquidity_flag", "")
    fc = r.get("forecast", {})
    q = fc.get("quantiles", {}) if fc else {}

    # Kalkulasi upside/downside
    q50 = q.get("q50") if q else None
    upside_pct = ((q50 - price) / price * 100) if q50 and price else None

    # Kalkulasi P&L jika ada harga rata-rata user
    unrealized_pnl_pct = None
    if user_avg_price and price:
        unrealized_pnl_pct = (price - user_avg_price) / user_avg_price * 100

    # Decision logic
    if penalty > 0:
        decision = "JUAL"
        confidence = "TINGGI"
        reasoning = [
            "🚩 Red flag terdeteksi (likuiditas sangat tipis, ROE negatif, atau potensi saham gorengan)",
            "Risiko asimetris: kemungkinan turun lebih besar dari potensi naik",
            "Disarankan keluar dari posisi untuk lindungi modal",
        ]
    elif score >= 75 and (rsi is None or rsi < 70):
        decision = "BELI"
        confidence = "TINGGI"
        reasoning = [
            f"Skor komposit sangat kuat ({score}/100) — multi-faktor bullish",
            "RSI belum overbought, masih ada ruang naik",
            f"Upside estimasi {upside_pct:.1f}%" if upside_pct else "Estimasi return positif",
        ] + signals[:2]
    elif score >= 65 and (rsi is None or rsi < 65):
        decision = "BELI"
        confidence = "SEDANG"
        reasoning = [
            f"Skor komposit baik ({score}/100)",
            "Indikator teknikal mayoritas bullish",
            f"Upside estimasi {upside_pct:.1f}%" if upside_pct else "Return positif moderat",
        ]
    elif score <= 35 or (rsi and rsi > 75):
        decision = "JUAL"
        confidence = "SEDANG"
        reasoning = [
            f"Skor komposit rendah ({score}/100) — tekanan jual dominan",
        ]
        if rsi and rsi > 75:
            reasoning.append(f"RSI {rsi:.1f} — kondisi overbought, risiko koreksi tinggi")
        if unrealized_pnl_pct and unrealized_pnl_pct > 0:
            reasoning.append(f"Profit taking disarankan — unrealized gain {unrealized_pnl_pct:.1f}%")
    else:
        decision = "HOLD"
        confidence = "SEDANG"
        reasoning = [
            f"Skor komposit moderat ({score}/100) — tidak ada sinyal kuat ke arah mana pun",
            "Pantau break level kunci sebelum tambah/kurangi posisi",
        ]
        if unrealized_pnl_pct and unrealized_pnl_pct < -8:
            reasoning.append(f"⚠️ Floating loss {unrealized_pnl_pct:.1f}% — pertimbangkan cut loss jika melampaui batas toleransi risiko")

    # Stop loss & target price
    q10 = q.get("q10") if q else None
    q90 = q.get("q90") if q else None
    stop_loss = q10 if q10 else (price * 0.93 if price else None)
    target_price = q90 if q90 else (price * 1.10 if price else None)

    return {
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasoning,
        "bullish_signals": signals,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "upside_pct": upside_pct,
        "unrealized_pnl_pct": unrealized_pnl_pct,
    }


# ================================================================
# AI NARASI (Anthropic API)
# ================================================================

def get_anthropic_api_key() -> str | None:
    """
    Ambil Anthropic API key dengan urutan prioritas:
    1. st.secrets["ANTHROPIC_API_KEY"]  ← Streamlit Cloud Secrets (direkomendasikan)
    2. os.environ["ANTHROPIC_API_KEY"]  ← environment variable lokal
    3. st.session_state["_anthropic_key_override"]  ← input manual dari UI (fallback dev)
    """
    import os
    # 1. Streamlit Secrets (Streamlit Cloud)
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY") or st.secrets.get("anthropic_api_key")
        if key:
            return str(key).strip()
    except Exception:
        pass
    # 2. Environment variable
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    # 3. Session state override (diisi dari UI sidecar)
    return st.session_state.get("_anthropic_key_override", "").strip() or None


def call_claude_api(prompt: str, system: str = "") -> str:
    """
    Panggil Anthropic API.
    API key dibaca otomatis dari Streamlit Secrets → env var → input manual.
    """
    api_key = get_anthropic_api_key()
    if not api_key:
        return (
            "⚙️ **API key belum dikonfigurasi.**\n"
            "Tambahkan `ANTHROPIC_API_KEY` ke **Streamlit Cloud Secrets** "
            "(Settings → Secrets) dengan format:\n"
            "```\nANTHROPIC_API_KEY = \"sk-ant-...\"\n```\n"
            "Atau isi field kunci di bawah checkbox AI."
        )
    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 1000,
            "system": system or (
                "Kamu adalah analis saham Indonesia berpengalaman. "
                "Berikan analisis singkat, tajam, dan berbasis data. "
                "Gunakan bahasa Indonesia. Hindari bahasa generik. "
                "Sertakan tanda-tanda bullish/bearish spesifik."
            ),
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
            return "\n".join(texts)
        elif resp.status_code == 401:
            return "❌ API key tidak valid atau kadaluarsa. Periksa kembali key di Streamlit Secrets."
        elif resp.status_code == 429:
            return "⏳ Rate limit tercapai. Tunggu beberapa detik lalu coba lagi."
        else:
            return f"❌ API error HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.Timeout:
        return "⏳ Request timeout. Server AI sedang sibuk, coba lagi."
    except Exception as e:
        return f"❌ Koneksi gagal: {e}"


def ai_bullish_narrative(r: dict, signals: list[str], horizon: str) -> str:
    ticker = r["ticker"]
    price = r["current_price"]
    score = r["composite_score"]
    fc = r.get("forecast", {})
    q = fc.get("quantiles", {}) if fc else {}
    q10 = q.get("q10", "n/a")
    q50 = q.get("q50", "n/a")
    q90 = q.get("q90", "n/a")
    rsi = r.get("rsi", "n/a")
    prompt = f"""
Analisis singkat saham {ticker} untuk horizon {horizon}:
- Harga saat ini: Rp {price:,.0f}
- Skor komposit: {score}/100
- RSI: {rsi}
- Estimasi harga (q10/q50/q90): {q10} / {q50} / {q90}
- Sinyal bullish terdeteksi: {'; '.join(signals[:4])}

Tulis narasi analis 3–4 kalimat: kondisi teknikal saat ini, alasan bullish, dan estimasi harga target realistis.
Akhiri dengan 1 kalimat risiko utama yang harus diwaspadai.
"""
    return call_claude_api(prompt)


def ai_decision_narrative(r: dict, decision: dict) -> str:
    ticker = r["ticker"]
    price = r["current_price"]
    dec = decision["decision"]
    reasoning = "; ".join(decision["reasoning"][:3])
    prompt = f"""
Saham: {ticker} | Harga: Rp {price:,.0f} | Keputusan sistem: {dec}
Alasan utama: {reasoning}
Stop loss: {decision['stop_loss']} | Target: {decision['target_price']}

Beri justifikasi singkat (2–3 kalimat) mengapa keputusan {dec} ini tepat secara analisis teknikal dan fundamental,
serta satu skenario yang bisa membatalkan rekomendasi ini.
"""
    return call_claude_api(prompt)


# ================================================================
# UI
# ================================================================
st.title("📊 IDX Stock Analyzer Pro")
st.caption(
    "Analisis transparan & explainable untuk saham Bursa Efek Indonesia — "
    "skor multi-faktor, rekomendasi bullish harian, dan decision engine beli/jual/hold."
)
show_disclaimer()

# ── Sidebar: API Key Setup ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Konfigurasi AI")
    _key_status = get_anthropic_api_key()
    if _key_status:
        st.success("✅ API key terkonfigurasi — fitur AI aktif", icon="🤖")
    else:
        st.warning("Fitur narasi AI memerlukan Anthropic API key.", icon="🔑")
        st.markdown(
            "**Cara terbaik (Streamlit Cloud):**\n\n"
            "1. Buka **Settings > Secrets** di Streamlit Cloud\n"
            "2. Tambahkan lalu klik **Save** dan **Reboot app**:\n"
            "`ANTHROPIC_API_KEY = \"sk-ant-...\"` "
        )
        st.divider()
        st.markdown("**Atau masukkan sementara di sini** *(hanya sesi ini)*:")
        _manual_key = st.text_input(
            "API Key (sk-ant-...)",
            type="password",
            key="_sidebar_api_key_input",
            placeholder="sk-ant-api03-...",
        )
        if _manual_key and _manual_key.startswith("sk-ant-"):
            st.session_state["_anthropic_key_override"] = _manual_key
            st.success("Key disimpan untuk sesi ini")
        elif _manual_key:
            st.error("Format tidak valid, harus diawali sk-ant-")
    st.divider()
    st.markdown(
        "**IDX Stock Analyzer Pro**\n\n"
        "Fitur baru:\n"
        "- 🌟 Rekomendasi Bullish Harian\n"
        "- 🎯 Decision Engine Beli/Jual/Hold\n"
        "- 🤖 Narasi AI (opsional)\n\n"
        "⚠️ Bukan saran investasi."
    )

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 Screening Multi-Saham",
    "📈 Analisis Satu Saham",
    "📉 Backtest Strategi",
    "🌟 Rekomendasi Bullish Harian",
    "🎯 Decision Engine",
])


# ================================================================
# TAB 1: SCREENING
# ================================================================
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
            st.error("Tidak ada data berhasil diambil.")
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
                    "Rentang Harga (q10–q90)": f"{q['q10']:,.0f} – {q['q90']:,.0f}" if q['q10'] else "n/a",
                    "Likuiditas": r["liquidity_flag"],
                    "Hari Paling Bullish": f"{wd['name']} ({wd['win_rate_pct']}% win)",
                    "Bulan Paling Bullish": f"{mo['name']} ({mo['win_rate_pct']}% win)",
                })
            df_out = pd.DataFrame(rows)

            st.markdown("#### 🎯 Top Kandidat")
            for r in results[:3]:
                tw = r["timing"]
                wd, mo = tw["best_weekday"], tw["best_month"]
                st.markdown(
                    f"**{r['ticker']}** (skor {r['composite_score']}) — "
                    f"historis paling sering naik di **{wd['name']}** "
                    f"(win rate {wd['win_rate_pct']}%) dan bulan **{mo['name']}**."
                )
            st.caption(
                "Pola musiman = rata-rata historis (calendar effect), BUKAN prediksi pasti. "
                "Tanda ⚠️tipis = observasi historis sedikit."
            )
            st.dataframe(df_out, use_container_width=True, hide_index=True)

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
                st.caption(f"🚩 Red-flag: {', '.join(top_red_flag)} — detail di tab Analisis Satu Saham.")

            st.markdown("#### Rincian faktor per saham (top 3)")
            for r in results[:3]:
                with st.expander(f"{r['ticker']} — skor {r['composite_score']}"):
                    st.json(r["components"])
                    for f in r["top_factors"]:
                        st.write("•", f)


# ================================================================
# TAB 2: ANALISIS SATU SAHAM
# ================================================================
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

            st.markdown("##### Komponen Skor")
            st.json(r["components"])

            st.markdown("##### Top Faktor Pendorong")
            for f in r["top_factors"]:
                st.write("•", f)

            st.markdown("##### Grafik Candlestick + Indikator")
            st.plotly_chart(candlestick_with_indicators(r["df"].tail(250), ticker), use_container_width=True)

            st.markdown("##### Estimasi Rentang Harga")
            fc = r["forecast"]
            q = fc["quantiles"]
            if q["q50"]:
                qdf = pd.DataFrame([
                    {"Persentil": k.upper(), "Estimasi Harga": f"Rp {v:,.0f}"} for k, v in q.items()
                ])
                st.dataframe(qdf, hide_index=True, use_container_width=True)
                st.caption(
                    f"Batas ARA: Rp {fc['ara_arb_bound']['ara']:,.0f} | "
                    f"Batas ARB: Rp {fc['ara_arb_bound']['arb']:,.0f}"
                )
            else:
                st.info("Histori data belum cukup untuk estimasi interval.")

            st.markdown("##### 📅 Pola Musiman Historis")
            tw = r["timing"]
            wcol, bcol, mcol = st.columns(3)
            for col, key, label in [(wcol, "best_weekday", "Hari"), (bcol, "best_bucket", "Bagian Bulan"), (mcol, "best_month", "Bulan")]:
                d = tw[key]
                col.metric(label, d["name"], f"win rate {d['win_rate_pct']}% (n={d['n_obs']})")
                if not d["reliable"]:
                    col.caption("⚠️ sampel tipis")
            with st.expander("Lihat tabel lengkap pola musiman"):
                st.write("**Per hari dalam minggu:**")
                st.dataframe(tw["weekday_table"].style.format({"avg_return": "{:.2%}", "win_rate": "{:.1%}"}), use_container_width=True)
                st.write("**Per bagian bulan:**")
                st.dataframe(tw["bucket_table"].style.format({"avg_return": "{:.2%}", "win_rate": "{:.1%}"}), use_container_width=True)
                st.write("**Per bulan dalam tahun:**")
                st.dataframe(tw["monthly_table"].style.format({"avg_return": "{:.2%}", "win_rate": "{:.1%}"}), use_container_width=True)


# ================================================================
# TAB 3: BACKTEST
# ================================================================
with tab3:
    st.subheader("Backtest Strategi (SMA Crossover, net of cost)")
    bcol1, bcol2, bcol3 = st.columns(3)
    bt_ticker = bcol1.text_input("Ticker", value="BBCA.JK", key="bt_ticker")
    bt_period = bcol2.selectbox("Panjang histori", ["1y", "2y", "3y", "5y"], index=2)
    bt_fast_slow = bcol3.selectbox("SMA Fast/Slow", ["10/30", "20/50", "50/200"], index=1)

    adv = st.expander("Pengaturan lanjutan")
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
            st.error("Data tidak ditemukan. Cek ticker (akhiran .JK) atau perpanjang histori.")
        else:
            result = run_backtest(df_bt, fast=fast, slow=slow, atr_mult_stop=atr_stop,
                                   atr_mult_tp=atr_tp, buy_cost_pct=buy_cost, sell_cost_pct=sell_cost)
            if result["metrics"] is None:
                st.warning("Tidak ada trade pada periode ini.")
            else:
                m = result["metrics"]
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("CAGR Strategi", f"{m['cagr']}%")
                k2.metric("CAGR Buy & Hold", f"{m['buy_and_hold_cagr']}%")
                k3.metric("Sharpe Ratio", m["sharpe"])
                k4.metric("Max Drawdown", f"{m['max_drawdown']}%")
                k5.metric("Win Rate", f"{m['win_rate']}%")
                st.plotly_chart(equity_curve_chart(result["equity_curve"], df_bt["Close"]), use_container_width=True)
                st.markdown("##### Log Transaksi")
                st.dataframe(result["trades"], use_container_width=True, hide_index=True)
                excel_buf_bt = to_excel_bytes({"Metrics": pd.DataFrame([m]), "Trades": result["trades"]})
                st.download_button("⬇️ Download Hasil Backtest", data=excel_buf_bt,
                                    file_name=f"backtest_{bt_ticker.replace('.','_')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                st.caption("⚠️ Backtest historis TIDAK menjamin performa masa depan.")


# ================================================================
# TAB 4: REKOMENDASI BULLISH HARIAN ← FITUR BARU
# ================================================================
with tab4:
    st.subheader("🌟 Rekomendasi Saham Bullish Harian")
    st.markdown(
        f"**Tanggal analisis:** {datetime.datetime.today().strftime('%A, %d %B %Y')}  \n"
        "Screening seluruh universe IDX — menampilkan saham dengan sinyal bullish terkuat hari ini "
        "hingga proyeksi beberapa hari ke depan dan bulanan."
    )

    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        daily_universe = st.selectbox(
            "Universe Saham",
            ["IDX Full (~120 saham)", "LQ45 Saja", "Custom"],
            key="daily_universe",
        )
    with rc2:
        daily_horizon = st.selectbox(
            "Horizon Proyeksi",
            list(HORIZON_DAYS.keys()),
            key="daily_horizon",
        )
    with rc3:
        top_n = st.slider("Tampilkan Top-N Saham", min_value=5, max_value=30, value=10)

    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        min_score = st.slider("Skor minimum komposit", 0, 100, 55, key="min_score_daily")
    with col_filter2:
        exclude_illiquid = st.checkbox("Sembunyikan saham illikuid/gorengan", value=True)

    if daily_universe == "Custom":
        custom_daily = st.text_input(
            "Ticker kustom (pisah koma)", value="BBCA.JK,BBRI.JK,TLKM.JK,ANTM.JK,ADRO.JK"
        )
        daily_tickers = [t.strip().upper() for t in custom_daily.split(",") if t.strip()]
    elif daily_universe == "LQ45 Saja":
        daily_tickers = LQ45_APPROX
    else:
        daily_tickers = IDX_FULL_UNIVERSE

    use_ai = st.checkbox("✨ Aktifkan narasi AI per saham (memerlukan API key Anthropic)", value=False)

    run_daily = st.button("🔍 Cari Saham Bullish Hari Ini", type="primary", use_container_width=True)

    if run_daily:
        bullish_results = []
        prog = st.progress(0.0, text="Memulai screening...")
        failed = []
        for i, tk in enumerate(daily_tickers):
            prog.progress((i + 1) / len(daily_tickers), text=f"Screening {tk} ({i+1}/{len(daily_tickers)})...")
            try:
                r = analyze_ticker(tk, daily_horizon)
                if r is None:
                    continue
                if exclude_illiquid and r.get("liquidity_flag") in ["SANGAT RENDAH", "TIPIS"]:
                    continue
                if r["composite_score"] < min_score:
                    continue
                signals = detect_bullish_signals(r)
                bullish_count = len([s for s in signals if "Tidak ada" not in s])
                if bullish_count >= 2:  # minimal 2 sinyal bullish
                    bullish_results.append((r, signals, bullish_count))
            except Exception as e:
                failed.append(tk)
        prog.empty()

        if failed:
            st.caption(f"⚠️ Gagal: {', '.join(failed[:10])}{'...' if len(failed)>10 else ''}")

        bullish_results.sort(key=lambda x: (x[2], x[0]["composite_score"]), reverse=True)
        bullish_results = bullish_results[:top_n]

        if not bullish_results:
            st.warning(
                "Tidak ada saham yang memenuhi kriteria bullish dengan filter saat ini. "
                "Coba turunkan skor minimum atau ubah universe."
            )
        else:
            st.success(f"✅ Ditemukan **{len(bullish_results)} saham bullish** dari {len(daily_tickers)} yang discreening.")

            # Ringkasan tabel
            summary_rows = []
            for r, signals, sig_count in bullish_results:
                fc = r["forecast"]
                q = fc.get("quantiles", {}) if fc else {}
                q10 = q.get("q10")
                q50 = q.get("q50")
                q90 = q.get("q90")
                price = r["current_price"]
                upside = f"{(q50 - price) / price * 100:.1f}%" if q50 and price else "n/a"
                summary_rows.append({
                    "Ticker": r["ticker"],
                    "Harga Sekarang (Rp)": f"{price:,.0f}",
                    "Skor": r["composite_score"],
                    "RSI": f"{r['rsi']:.1f}" if r.get("rsi") else "n/a",
                    "Sinyal Bullish": sig_count,
                    "Target Konservatif (Rp)": f"{q50:,.0f}" if q50 else "n/a",
                    "Target Optimis (Rp)": f"{q90:,.0f}" if q90 else "n/a",
                    "Stop Loss (Rp)": f"{q10:,.0f}" if q10 else "n/a",
                    "Potensi Upside": upside,
                    "Likuiditas": r["liquidity_flag"],
                })
            df_bullish = pd.DataFrame(summary_rows)
            st.dataframe(df_bullish, use_container_width=True, hide_index=True)

            # Download
            excel_bull = to_excel_bytes({"Bullish Harian": df_bullish})
            st.download_button(
                "⬇️ Download Rekomendasi (Excel)", data=excel_bull,
                file_name=f"bullish_harian_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            st.divider()
            st.markdown("### 📋 Detail Per Saham")

            for idx, (r, signals, sig_count) in enumerate(bullish_results):
                ticker_name = r["ticker"]
                score = r["composite_score"]
                price = r["current_price"]
                fc = r["forecast"]
                q = fc.get("quantiles", {}) if fc else {}

                color = "🟢" if score >= 70 else "🟡"
                with st.expander(f"{color} **{ticker_name}** — Skor {score} | Rp {price:,.0f} | {sig_count} sinyal bullish"):
                    d1, d2, d3, d4 = st.columns(4)
                    d1.metric("Harga", f"Rp {price:,.0f}")
                    d2.metric("Skor Komposit", score)
                    d3.metric("RSI", f"{r['rsi']:.1f}" if r.get("rsi") else "n/a")
                    d4.metric("Likuiditas", r["liquidity_flag"])

                    st.markdown("**🔥 Tanda-tanda Bullish:**")
                    for sig in signals:
                        if "Tidak ada" not in sig:
                            st.markdown(f"✅ {sig}")

                    # Estimasi harga
                    st.markdown("**💰 Estimasi Kisaran Harga:**")
                    h1, h2, h3 = st.columns(3)
                    q10 = q.get("q10")
                    q50 = q.get("q50")
                    q90 = q.get("q90")
                    h1.metric("Konservatif (Q10)", f"Rp {q10:,.0f}" if q10 else "n/a",
                              delta=f"{(q10-price)/price*100:.1f}%" if q10 and price else None)
                    h2.metric("Moderat (Q50)", f"Rp {q50:,.0f}" if q50 else "n/a",
                              delta=f"{(q50-price)/price*100:.1f}%" if q50 and price else None)
                    h3.metric("Optimis (Q90)", f"Rp {q90:,.0f}" if q90 else "n/a",
                              delta=f"{(q90-price)/price*100:.1f}%" if q90 and price else None)
                    st.caption(
                        f"Horizon: **{daily_horizon}** | "
                        f"Batas ARA: Rp {fc['ara_arb_bound']['ara']:,.0f} | "
                        f"Batas ARB: Rp {fc['ara_arb_bound']['arb']:,.0f}"
                        if fc and fc.get("ara_arb_bound") else ""
                    )

                    # Komponen skor
                    comp = r["components"]
                    st.markdown("**📊 Komponen Skor:**")
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Teknikal", comp["technical"])
                    s2.metric("Fundamental", comp["fundamental"])
                    s3.metric("Makro", comp["macro"])
                    s4.metric("Penalti", comp["red_flag_penalty"])

                    # Timing musiman
                    tw = r["timing"]
                    wd = tw.get("best_weekday", {})
                    mo = tw.get("best_month", {})
                    st.caption(
                        f"📅 Historis paling sering naik: hari **{wd.get('name','?')}** "
                        f"(win rate {wd.get('win_rate_pct','?')}%) | "
                        f"bulan **{mo.get('name','?')}** (win rate {mo.get('win_rate_pct','?')}%)"
                    )

                    # AI Narasi
                    if use_ai:
                        with st.spinner("Menghasilkan narasi AI..."):
                            narasi = ai_bullish_narrative(r, signals, daily_horizon)
                        st.markdown("**🤖 Analisis AI:**")
                        st.info(narasi)

            st.caption(
                "⚠️ Rekomendasi di atas berdasarkan data historis & indikator teknikal/fundamental. "
                "BUKAN saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi."
            )


# ================================================================
# TAB 5: DECISION ENGINE BELI/JUAL/HOLD ← FITUR BARU
# ================================================================
with tab5:
    st.subheader("🎯 Decision Engine — Beli / Jual / Hold")
    st.markdown(
        "Masukkan ticker saham yang ingin dianalisis. Sistem akan menghasilkan rekomendasi "
        "**BELI / JUAL / HOLD** berdasarkan analisis multi-faktor: teknikal, fundamental, makro, "
        "dan data real-time (via Yahoo Finance). Opsional: masukkan harga rata-rata beli Anda "
        "untuk kalkulasi P&L dan rekomendasi yang lebih personal."
    )

    de_col1, de_col2, de_col3 = st.columns(3)
    de_ticker = de_col1.text_input("Ticker Saham", value="BBCA.JK", key="de_ticker")
    de_horizon = de_col2.selectbox("Horizon Analisis", list(HORIZON_DAYS.keys()), key="de_horizon")
    user_avg_price = de_col3.number_input(
        "Harga rata-rata beli Anda (Rp) — opsional",
        min_value=0, value=0, step=100, key="de_avg_price",
        help="Kosongkan (isi 0) jika belum punya posisi atau tidak ingin masukkan"
    )
    use_ai_de = st.checkbox("✨ Aktifkan justifikasi AI", value=False, key="de_use_ai")

    if st.button("⚡ Analisis & Buat Keputusan", type="primary", use_container_width=True):
        with st.spinner(f"Menganalisis {de_ticker}..."):
            r_de = analyze_ticker(de_ticker, de_horizon)

        if r_de is None:
            st.error("Data tidak ditemukan. Cek format ticker (akhiran .JK).")
        else:
            avg_price_input = float(user_avg_price) if user_avg_price and user_avg_price > 0 else None
            signals_de = detect_bullish_signals(r_de)
            dec = make_decision(r_de, user_avg_price=avg_price_input)

            # Hero: keputusan utama
            decision_color = {
                "BELI": ("🟢", "success"),
                "JUAL": ("🔴", "error"),
                "HOLD": ("🟡", "warning"),
            }
            icon, alert_type = decision_color.get(dec["decision"], ("⚪", "info"))

            st.markdown("---")
            de_hero_col1, de_hero_col2 = st.columns([1, 2])
            with de_hero_col1:
                st.markdown(
                    f"<div style='text-align:center; padding:30px; border-radius:16px; "
                    f"background:{'#1a472a' if dec['decision']=='BELI' else '#4a1c1c' if dec['decision']=='JUAL' else '#3d3000'};"
                    f"border:2px solid {'#2ecc71' if dec['decision']=='BELI' else '#e74c3c' if dec['decision']=='JUAL' else '#f39c12'}'>"
                    f"<div style='font-size:3rem'>{icon}</div>"
                    f"<div style='font-size:2rem; font-weight:900; color:{'#2ecc71' if dec['decision']=='BELI' else '#e74c3c' if dec['decision']=='JUAL' else '#f1c40f'}'>"
                    f"{dec['decision']}</div>"
                    f"<div style='color:#aaa; font-size:0.9rem'>Keyakinan: {dec['confidence']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with de_hero_col2:
                price_de = r_de["current_price"]
                de_m1, de_m2, de_m3 = st.columns(3)
                de_m1.metric("Harga Sekarang", f"Rp {price_de:,.0f}")
                de_m2.metric("Skor Komposit", r_de["composite_score"])
                de_m3.metric("RSI", f"{r_de['rsi']:.1f}" if r_de.get("rsi") else "n/a")

                if avg_price_input:
                    pnl = dec.get("unrealized_pnl_pct")
                    pnl_color = "normal" if not pnl else ("inverse" if pnl < 0 else "normal")
                    st.metric(
                        "P&L (vs Harga Beli Anda)",
                        f"Rp {price_de:,.0f}",
                        delta=f"{pnl:.2f}%" if pnl else "n/a",
                        delta_color=pnl_color,
                    )

                if dec.get("target_price"):
                    st.metric("Target Harga (Q90)", f"Rp {dec['target_price']:,.0f}",
                              delta=f"Upside {dec['upside_pct']:.1f}%" if dec.get("upside_pct") else None)
                if dec.get("stop_loss"):
                    st.metric("Stop Loss (Q10)", f"Rp {dec['stop_loss']:,.0f}")

            st.markdown("---")

            # Reasoning
            st.markdown("#### 📝 Alasan Keputusan")
            for reason in dec["reasoning"]:
                st.markdown(f"• {reason}")

            # Sinyal bullish
            st.markdown("#### 🔍 Sinyal Bullish Terdeteksi")
            for sig in signals_de:
                if "Tidak ada" not in sig:
                    st.markdown(f"✅ {sig}")
                else:
                    st.markdown(f"⚪ {sig}")

            # Komponen skor detail
            st.markdown("#### 📊 Breakdown Skor Multi-Faktor")
            comp_de = r_de["components"]
            sc1, sc2, sc3, sc4, sc5 = st.columns(5)
            sc1.metric("Teknikal", comp_de["technical"], help="0–100, bobot tertinggi untuk trading")
            sc2.metric("Fundamental", comp_de["fundamental"], help="0–100, PER/PBV/ROE")
            sc3.metric("Likuiditas", comp_de["liquidity"], help="0–100, ADTV")
            sc4.metric("Makro", comp_de["macro"], help="0–100, beta & trend IHSG")
            sc5.metric("Penalti Red-Flag", -comp_de["red_flag_penalty"], help="Negatif = dikurangi dari skor")

            # Estimasi harga detail
            fc_de = r_de["forecast"]
            q_de = fc_de.get("quantiles", {}) if fc_de else {}
            if q_de.get("q50"):
                st.markdown("#### 💰 Proyeksi Kisaran Harga")
                proj_cols = st.columns(5)
                labels = ["Q10 (Pesimis)", "Q25", "Q50 (Moderat)", "Q75", "Q90 (Optimis)"]
                keys = ["q10", "q25", "q50", "q75", "q90"]
                for i, (col, lbl, key) in enumerate(zip(proj_cols, labels, keys)):
                    val = q_de.get(key)
                    delta_str = f"{(val - price_de)/price_de*100:.1f}%" if val and price_de else None
                    col.metric(lbl, f"Rp {val:,.0f}" if val else "n/a", delta=delta_str)
                st.caption(
                    f"Berdasarkan distribusi return historis {fc_de.get('n_obs',0)} observasi | "
                    f"Horizon: {de_horizon}"
                )

            # Candlestick
            st.markdown("#### 📈 Grafik Teknikal")
            st.plotly_chart(
                candlestick_with_indicators(r_de["df"].tail(180), de_ticker),
                use_container_width=True,
            )

            # Seasonality
            tw_de = r_de["timing"]
            wd_de = tw_de.get("best_weekday", {})
            mo_de = tw_de.get("best_month", {})
            bk_de = tw_de.get("best_bucket", {})
            st.markdown("#### 📅 Pola Waktu Historis")
            t1, t2, t3 = st.columns(3)
            t1.metric("Hari Terkuat", wd_de.get("name", "?"), f"win rate {wd_de.get('win_rate_pct','?')}%")
            t2.metric("Bagian Bulan Terkuat", bk_de.get("name", "?"), f"win rate {bk_de.get('win_rate_pct','?')}%")
            t3.metric("Bulan Terkuat", mo_de.get("name", "?"), f"win rate {mo_de.get('win_rate_pct','?')}%")

            # AI Justifikasi
            if use_ai_de:
                with st.spinner("Menghasilkan justifikasi AI..."):
                    ai_just = ai_decision_narrative(r_de, dec)
                st.markdown("#### 🤖 Justifikasi AI")
                st.info(ai_just)

            # Disclaimer & export
            st.divider()
            st.caption(
                "⚠️ Rekomendasi ini dihasilkan oleh algoritma berbasis data historis & indikator. "
                "BUKAN saran investasi. Kondisi pasar bisa berubah drastis akibat berita/sentimen "
                "yang tidak tertangkap oleh model kuantitatif. Selalu konsultasikan dengan analis "
                "berlisensi sebelum mengambil keputusan investasi."
            )

            # Export keputusan
            export_data = {
                "Ticker": [de_ticker],
                "Tanggal": [datetime.date.today()],
                "Harga": [price_de],
                "Keputusan": [dec["decision"]],
                "Keyakinan": [dec["confidence"]],
                "Skor Komposit": [r_de["composite_score"]],
                "Target (Q90)": [dec["target_price"]],
                "Stop Loss (Q10)": [dec["stop_loss"]],
                "Teknikal": [comp_de["technical"]],
                "Fundamental": [comp_de["fundamental"]],
                "Likuiditas": [comp_de["liquidity"]],
                "Makro": [comp_de["macro"]],
            }
            export_buf = to_excel_bytes({"Keputusan": pd.DataFrame(export_data)})
            st.download_button(
                "⬇️ Download Keputusan (Excel)", data=export_buf,
                file_name=f"decision_{de_ticker.replace('.','_')}_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
