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
