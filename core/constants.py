"""
Konstanta pasar IDX: aturan Auto Rejection (ARA/ARB), daftar universe default,
dan threshold likuiditas. SUMBER: SK Direksi BEI — aturan ini berubah dari
waktu ke waktu (terakhir besar: April 2025). SELALU verifikasi ulang sebelum
dipakai untuk keputusan nyata.
"""

# ARB flat 15% untuk semua tier harga (sejak penyesuaian simetris->asimetris
# April 2025). Sebelumnya ARB mengikuti tier seperti ARA.
ARB_PCT = 0.15


def get_ara_pct(prev_close: float) -> float:
    """ARA (Auto Reject Atas) tier berdasarkan harga penutupan hari sebelumnya."""
    if prev_close <= 200:
        return 0.35
    elif prev_close <= 5000:
        return 0.25
    else:
        return 0.20


def get_arb_pct(prev_close: float) -> float:
    return ARB_PCT


# Daftar approx. anggota LQ45 (per pengetahuan terakhir model — KOMPOSISI LQ45
# DIEVALUASI ULANG BEI SETIAP ~6 BULAN, jadi list ini BISA SUDAH USANG).
# Selalu lebih baik memasukkan ticker custom Anda sendiri di UI.
LQ45_APPROX = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BBTN.JK", "BRIS.JK",
    "TLKM.JK", "EXCL.JK", "ISAT.JK", "TOWR.JK", "TBIG.JK",
    "ASII.JK", "UNTR.JK", "UNVR.JK", "ICBP.JK", "INDF.JK", "MYOR.JK",
    "KLBF.JK", "SIDO.JK", "CMRY.JK", "AMRT.JK",
    "ADRO.JK", "PTBA.JK", "ITMG.JK", "ANTM.JK", "INCO.JK", "MDKA.JK",
    "PGAS.JK", "MEDC.JK", "AKRA.JK", "BRPT.JK", "TPIA.JK", "ESSA.JK",
    "SMGR.JK", "INTP.JK", "CPIN.JK", "JPFA.JK",
    "GGRM.JK", "HMSP.JK", "AMMN.JK",
    "PWON.JK", "CTRA.JK", "SMRA.JK", "JSMR.JK",
    "ACES.JK", "ERAA.JK", "MAPI.JK",
]

# Threshold likuiditas minimum (rata-rata nilai transaksi harian, dalam Rupiah)
# di bawah ini saham ditandai "thin" — sinyal kuantitatif jadi kurang andal.
MIN_ADTV_IDR = 1_000_000_000  # Rp 1 miliar/hari

DISCLAIMER = (
    "Analisis ini dihasilkan oleh model statistik untuk tujuan edukasi dan "
    "pendukung keputusan. Ini BUKAN rekomendasi atau nasihat investasi resmi. "
    "Pasar modal mengandung risiko, termasuk risiko kehilangan modal. "
    "Keputusan investasi sepenuhnya menjadi tanggung jawab pengguna. "
    "Verifikasi data dengan sumber resmi (IDX, laporan keuangan emiten) "
    "sebelum bertransaksi."
)

HORIZON_DAYS = {
    "Harian (1-5 hari)": 5,
    "Bulanan (~20 hari)": 20,
    "Tahunan (~252 hari)": 252,
}
