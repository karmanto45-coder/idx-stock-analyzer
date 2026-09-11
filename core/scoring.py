"""
Composite scoring — SETIAP komponen dihitung & ditampilkan terpisah (sesuai
mandat skill: jangan pernah keluarkan "score > 60" tanpa rincian).
Skala tiap komponen: 0-100. Bobot berbeda per horizon (lihat HORIZON_WEIGHTS).
"""
from core.constants import MIN_ADTV_IDR

HORIZON_WEIGHTS = {
    "Harian (1-5 hari)": {"technical": 0.65, "liquidity": 0.20, "macro": 0.15, "fundamental": 0.0},
    "Bulanan (~20 hari)": {"technical": 0.40, "liquidity": 0.15, "macro": 0.15, "fundamental": 0.30},
    "Tahunan (~252 hari)": {"technical": 0.15, "liquidity": 0.05, "macro": 0.30, "fundamental": 0.50},
}


def _clip(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def technical_score(latest: dict) -> tuple[float, list[str]]:
    """latest = dict berisi nilai indikator terbaru untuk satu saham."""
    score = 50.0
    factors = []

    close, sma50, sma200 = latest["Close"], latest.get("sma_50"), latest.get("sma_200")
    if sma50 and sma200:
        if close > sma50 > sma200:
            score += 20
            factors.append("Uptrend: harga > SMA50 > SMA200")
        elif close < sma50 < sma200:
            score -= 20
            factors.append("Downtrend: harga < SMA50 < SMA200")

    rsi_v = latest.get("rsi_14")
    if rsi_v is not None:
        if rsi_v < 30:
            score += 8
            factors.append(f"RSI {rsi_v:.0f} oversold — potensi rebound teknikal")
        elif rsi_v > 70:
            score -= 8
            factors.append(f"RSI {rsi_v:.0f} overbought — risiko koreksi")

    macd_h = latest.get("macd_hist")
    if macd_h is not None:
        if macd_h > 0:
            score += 10
            factors.append("MACD histogram positif (momentum naik)")
        else:
            score -= 10
            factors.append("MACD histogram negatif (momentum turun)")

    adx_v = latest.get("adx_14")
    if adx_v is not None and adx_v > 25:
        # ADX menguatkan arah trend yang sudah terdeteksi
        if close > (sma50 or close):
            score += 7
            factors.append(f"ADX {adx_v:.0f} — trend naik kuat")
        else:
            score -= 7
            factors.append(f"ADX {adx_v:.0f} — trend turun kuat")

    vol_ratio = latest.get("Volume", 0) / (latest.get("vol_sma_20") or 1)
    if vol_ratio > 1.5:
        score += 5
        factors.append(f"Volume {vol_ratio:.1f}x rata-rata 20 hari — minat meningkat")

    return _clip(score), factors


def liquidity_score(adtv_idr: float) -> tuple[float, list[str], str]:
    factors = []
    if adtv_idr < MIN_ADTV_IDR:
        flag = "thin"
        score = _clip(30 * (adtv_idr / MIN_ADTV_IDR))
        factors.append(f"ADTV Rp{adtv_idr:,.0f} < ambang minimum — likuiditas tipis, sinyal kurang andal")
    else:
        flag = "ok"
        score = _clip(50 + 10 * min(5, adtv_idr / MIN_ADTV_IDR))
        factors.append(f"ADTV Rp{adtv_idr:,.0f}/hari — likuiditas memadai")
    return score, factors, flag


def fundamental_score(fund: dict) -> tuple[float, list[str]]:
    score, factors, n = 50.0, [], 0
    pe, pbv, roe = fund.get("pe"), fund.get("pbv"), fund.get("roe")
    if pe is not None and pe > 0:
        n += 1
        if pe < 15:
            score += 10; factors.append(f"PER {pe:.1f}x relatif murah")
        elif pe > 30:
            score -= 10; factors.append(f"PER {pe:.1f}x relatif mahal")
    if pbv is not None and pbv > 0:
        n += 1
        if pbv < 1.5:
            score += 8; factors.append(f"PBV {pbv:.2f}x relatif murah")
        elif pbv > 4:
            score -= 8; factors.append(f"PBV {pbv:.2f}x relatif mahal")
    if roe is not None:
        n += 1
        if roe > 0.15:
            score += 12; factors.append(f"ROE {roe*100:.1f}% solid")
        elif roe < 0:
            score -= 15; factors.append(f"ROE negatif ({roe*100:.1f}%) — perhatian")
    if n == 0:
        factors.append("Data fundamental tidak tersedia dari sumber — skor dinetralkan ke 50")
    return _clip(score), factors


def fundamental_verdict(fund: dict) -> dict:
    """
    Simpulan kualitatif "sehat & undervalue" berbasis kriteria value-investing
    klasik ala Graham (PER, PBV, ROE, DER, pertumbuhan laba). Ini HEURISTIK
    SEDERHANA berbasis ambang batas umum — BUKAN riset ekuitas menyeluruh,
    bukan valuasi DCF, dan tidak membandingkan terhadap rata-rata sektor
    (data itu tidak tersedia gratis dari Yahoo Finance). Selalu tampilkan
    bersama disclaimer & sarankan cross-check ke laporan keuangan resmi.

    Catatan skala data dari Yahoo Finance (core/data.py -> fetch_fundamentals):
    - roe, eps_growth ("earningsQuarterlyGrowth"): FRAKSI, contoh 0.15 = 15%.
    - debt_to_equity ("debtToEquity"): PERSEN, contoh 195.868 berarti 195.9%
      (bukan rasio 1.96x) — ini konvensi bawaan Yahoo Finance, bukan pilihan
      di kode ini. Referensi: field ini utk Apple bernilai ~195 (bukan ~2).
    - Field mana pun yang None (banyak terjadi utk emiten IDX non blue-chip di
      Yahoo Finance) TIDAK dihitung sebagai buruk maupun baik, hanya diabaikan
      dari perhitungan rasio ("data tidak cukup").
    """
    pe, pbv, roe = fund.get("pe"), fund.get("pbv"), fund.get("roe")
    eps_growth, der = fund.get("eps_growth"), fund.get("debt_to_equity")

    reasons = []
    health_points = health_checks = 0.0
    value_points = value_checks = 0.0

    if roe is not None:
        health_checks += 1
        if roe > 0.15:
            health_points += 1
            reasons.append(f"ROE {roe*100:.1f}% (>15%) — profitabilitas solid")
        elif roe < 0:
            reasons.append(f"ROE negatif ({roe*100:.1f}%) — perusahaan sedang merugi")
        else:
            health_points += 0.5
            reasons.append(f"ROE {roe*100:.1f}% — profitabilitas moderat")

    if der is not None:
        health_checks += 1
        if der < 100:
            health_points += 1
            reasons.append(f"DER {der:.0f}% — beban utang terhadap ekuitas rendah/wajar")
        elif der > 200:
            reasons.append(f"DER {der:.0f}% — beban utang tinggi, perhatikan risiko leverage")
        else:
            health_points += 0.5
            reasons.append(f"DER {der:.0f}% — beban utang moderat")

    if eps_growth is not None:
        health_checks += 1
        if eps_growth > 0:
            health_points += 1
            reasons.append(f"Pertumbuhan laba kuartalan +{eps_growth*100:.1f}% YoY — mesin laba masih tumbuh")
        else:
            reasons.append(f"Pertumbuhan laba kuartalan {eps_growth*100:.1f}% YoY — laba menyusut")

    if pe is not None and pe > 0:
        value_checks += 1
        if pe < 15:
            value_points += 1
            reasons.append(f"PER {pe:.1f}x (<15x) — tergolong murah secara historis")
        elif pe > 25:
            reasons.append(f"PER {pe:.1f}x (>25x) — tergolong mahal secara historis")
        else:
            value_points += 0.5
            reasons.append(f"PER {pe:.1f}x — tergolong wajar")

    if pbv is not None and pbv > 0:
        value_checks += 1
        if pbv < 1.5:
            value_points += 1
            reasons.append(f"PBV {pbv:.2f}x (<1.5x) — harga mendekati/di bawah nilai buku")
        elif pbv > 3:
            reasons.append(f"PBV {pbv:.2f}x (>3x) — premium tinggi terhadap nilai buku")
        else:
            value_points += 0.5
            reasons.append(f"PBV {pbv:.2f}x — tergolong wajar")

    if health_checks == 0 and value_checks == 0:
        return {
            "health_label": "Data Tidak Cukup", "valuation_label": "Data Tidak Cukup",
            "verdict": "❔ Data Fundamental Tidak Tersedia", "verdict_key": "unknown",
            "reasons": ["Yahoo Finance tidak menyediakan data fundamental untuk emiten ini."],
            "n_health_checks": 0, "n_value_checks": 0,
        }

    def _label(points, checks, good, bad, mid):
        if checks == 0:
            return "Data Tidak Cukup"
        ratio = points / checks
        prefix = "Kemungkinan " if checks < 2 else ""
        if ratio >= 0.75:
            return prefix + good
        if ratio <= 0.25:
            return prefix + bad
        return prefix + mid

    health_label = _label(health_points, health_checks, "Sehat", "Kurang Sehat", "Cukup Sehat")
    valuation_label = _label(value_points, value_checks, "Undervalue", "Overvalue", "Fair Value")

    is_healthy = health_checks > 0 and "Sehat" in health_label and "Kurang" not in health_label
    is_unhealthy = health_checks > 0 and "Kurang Sehat" in health_label
    is_cheap = value_checks > 0 and "Undervalue" in valuation_label
    is_expensive = value_checks > 0 and "Overvalue" in valuation_label

    if health_checks == 0:
        verdict, verdict_key = f"❔ Kesehatan tidak terukur — valuasi tampak {valuation_label}", "unknown"
    elif value_checks == 0:
        verdict, verdict_key = f"❔ Valuasi tidak terukur — kesehatan tampak {health_label}", "unknown"
    elif is_healthy and is_cheap:
        verdict, verdict_key = "✅ Sehat & Undervalue — Kandidat Value Layak Dipertimbangkan", "good"
    elif is_unhealthy and is_cheap:
        verdict, verdict_key = "⚠️ Murah tapi Kurang Sehat — Waspada Potensi Value Trap", "warning"
    elif is_healthy and is_expensive:
        verdict, verdict_key = "⚠️ Sehat tapi Sudah Mahal — Pertimbangkan Tunggu Koreksi", "warning"
    elif is_unhealthy and is_expensive:
        verdict, verdict_key = "🚫 Kurang Sehat & Mahal — Kurang Menarik", "bad"
    else:
        verdict, verdict_key = f"ℹ️ Kesehatan: {health_label} | Valuasi: {valuation_label}", "neutral"

    return {
        "health_label": health_label, "valuation_label": valuation_label,
        "verdict": verdict, "verdict_key": verdict_key, "reasons": reasons,
        "n_health_checks": int(health_checks), "n_value_checks": int(value_checks),
    }


def macro_score(beta_vs_ihsg: float, ihsg_trend_up: bool) -> tuple[float, list[str]]:
    score, factors = 50.0, []
    if ihsg_trend_up:
        score += 10 if beta_vs_ihsg > 0 else -5
        factors.append("IHSG dalam trend naik" + (" — saham beta positif diuntungkan" if beta_vs_ihsg > 0 else ""))
    else:
        score -= 10 if beta_vs_ihsg > 0 else 0
        factors.append("IHSG dalam trend turun/sideways")
    factors.append(f"Beta vs IHSG ≈ {beta_vs_ihsg:.2f}")
    return _clip(score), factors


def red_flag_penalty(adtv_idr: float, roe, ara_arb_streak: int) -> tuple[float, list[str]]:
    penalty, factors = 0.0, []
    if adtv_idr < MIN_ADTV_IDR / 5:
        penalty += 15
        factors.append("Likuiditas sangat tipis — indikasi rawan 'saham gorengan'")
    if roe is not None and roe < -0.10:
        penalty += 10
        factors.append("ROE sangat negatif")
    if ara_arb_streak >= 3:
        penalty += 15
        factors.append(f"Pernah ARA/ARB berturut-turut {ara_arb_streak}x tanpa katalis fundamental jelas")
    return penalty, factors


def composite_score(horizon: str, tech, liq, fund, macro, penalty) -> float:
    w = HORIZON_WEIGHTS[horizon]
    base = tech * w["technical"] + liq * w["liquidity"] + fund * w["fundamental"] + macro * w["macro"]
    return round(_clip(base - penalty), 1)
