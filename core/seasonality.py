"""
Analisis musiman (seasonality) — menjawab "kapan secara historis saham ini
paling sering naik": hari dalam minggu, bagian bulan, dan bulan dalam tahun.

PENTING — batas kejujuran statistik:
- Ini BUKAN prediksi pasti tanggal kenaikan di masa depan. Ini adalah pola
  rata-rata historis (calendar effect) yang TIDAK DIJAMIN berulang.
- Jumlah observasi (n_obs) WAJIB ditampilkan — pola dengan n_obs kecil
  (terutama musiman bulanan) secara statistik tidak dapat diandalkan dan
  mudah overfit pada kebetulan historis.
- Tanggal spesifik (misal "tanggal 5") TIDAK dihitung karena jumlah sampel
  per tanggal pasti dalam histori (~5-10x dalam 5 tahun) terlalu kecil untuk
  bermakna secara statistik — sebagai gantinya dipakai bucket "bagian bulan"
  (awal/tengah/akhir) yang punya jumlah observasi jauh lebih besar.
"""
import numpy as np
import pandas as pd

WEEKDAY_NAMES_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]
MONTH_NAMES_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

MIN_OBS_WEEKDAY = 60     # ~setahun data harian per weekday sudah lewat ambang ini
MIN_OBS_BUCKET = 40
MIN_OBS_MONTH = 15       # tetap diberi peringatan rendah meski lolos ambang ini


def weekday_seasonality(close: pd.Series) -> pd.DataFrame:
    ret = close.pct_change().dropna().to_frame("return")
    ret = ret[ret.index.dayofweek < 5]  # buang sabtu/minggu (jaga2 data anomali)
    ret["weekday"] = ret.index.dayofweek
    g = ret.groupby("weekday")["return"].agg(
        avg_return="mean", n_obs="count", win_rate=lambda x: (x > 0).mean()
    )
    g.index = [WEEKDAY_NAMES_ID[i] for i in g.index]
    return g.sort_values("avg_return", ascending=False)


def day_of_month_bucket_seasonality(close: pd.Series) -> pd.DataFrame:
    ret = close.pct_change().dropna().to_frame("return")
    day = ret.index.day
    bucket = np.select(
        [day <= 10, day <= 20],
        ["Awal Bulan (tgl 1-10)", "Tengah Bulan (tgl 11-20)"],
        default="Akhir Bulan (tgl 21-31)",
    )
    ret["bucket"] = bucket
    g = ret.groupby("bucket")["return"].agg(
        avg_return="mean", n_obs="count", win_rate=lambda x: (x > 0).mean()
    )
    return g.sort_values("avg_return", ascending=False)


def monthly_seasonality(close: pd.Series) -> pd.DataFrame:
    monthly_close = close.resample("ME").last()
    monthly_ret = monthly_close.pct_change().dropna().to_frame("return")
    monthly_ret["month"] = monthly_ret.index.month
    g = monthly_ret.groupby("month")["return"].agg(
        avg_return="mean", n_obs="count", win_rate=lambda x: (x > 0).mean()
    )
    g.index = [MONTH_NAMES_ID[i - 1] for i in g.index]
    return g.sort_values("avg_return", ascending=False)


def best_timing_summary(close: pd.Series) -> dict:
    wd = weekday_seasonality(close)
    bk = day_of_month_bucket_seasonality(close)
    mo = monthly_seasonality(close)

    def top(df, min_obs):
        row = df.iloc[0]
        return {
            "name": df.index[0],
            "avg_return_pct": round(row["avg_return"] * 100, 2),
            "win_rate_pct": round(row["win_rate"] * 100, 1),
            "n_obs": int(row["n_obs"]),
            "reliable": int(row["n_obs"]) >= min_obs,
        }

    return {
        "best_weekday": top(wd, MIN_OBS_WEEKDAY),
        "best_bucket": top(bk, MIN_OBS_BUCKET),
        "best_month": top(mo, MIN_OBS_MONTH),
        "weekday_table": wd,
        "bucket_table": bk,
        "monthly_table": mo,
    }
