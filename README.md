# IDX Stock Analyzer Pro

Aplikasi screening & analisis saham IDX (Bursa Efek Indonesia) berbasis
indikator teknikal, fundamental ringkas, dan makro — dengan skor komposit
yang **transparan** (semua komponen bisa dirinci, bukan kotak hitam) dan
estimasi rentang harga (bukan angka tunggal) yang **dibatasi aturan ARA/ARB**
bursa.

> ⚠️ Ini alat bantu edukasi/analisis, BUKAN nasihat investasi. Lihat
> disclaimer di dalam aplikasi.

---

## 1. Instalasi (sekali saja)

Aplikasi ini jalan di **komputer Anda sendiri** (bukan di server Claude),
karena butuh akses internet langsung ke Yahoo Finance untuk data saham —
jadi lebih privat dan tidak ada batasan rate limit dari pihak ketiga.

**Langkah:**

1. Install Python 3.10+ jika belum ada: https://www.python.org/downloads/
   (saat install di Windows, centang "Add Python to PATH").
2. Extract folder `idx_analyzer` ini ke lokasi mana saja, misalnya Desktop.
3. Buka Terminal (Mac/Linux) atau Command Prompt/PowerShell (Windows), lalu:

```bash
cd path/ke/idx_analyzer
pip install -r requirements.txt
```

## 2. Menjalankan aplikasi

```bash
streamlit run app.py
```

Browser akan otomatis terbuka ke `http://localhost:8501`. Jika tidak,
buka link itu manual.

## 3. Cara pakai (singkat)

- **Tab "Screening Multi-Saham"**: pilih universe (LQ45 default, atau ketik
  ticker sendiri pisah koma), pilih horizon (Harian/Bulanan/Tahunan), klik
  "Jalankan Screening". Hasil diurutkan dari skor komposit tertinggi, plus
  ringkasan nama saham + **estimasi waktu paling sering bullish secara
  historis** (hari/bagian bulan/bulan), dan tombol download Excel.
- **Tab "Analisis Satu Saham"**: ketik 1 ticker (format `KODE.JK`, contoh
  `BBCA.JK`), lihat grafik candlestick + indikator, rincian skor, estimasi
  rentang harga, dan panel musiman (hari/bagian bulan/bulan paling bullish).
- **Tab "Backtest Strategi"**: uji strategi SMA crossover (golden/death
  cross) dengan stop-loss/take-profit berbasis ATR, net biaya transaksi —
  bandingkan CAGR, Sharpe, Max Drawdown, Win Rate vs buy & hold. Hasil bisa
  diunduh ke Excel.
- Saham bertanda **liquidity = "thin"** artinya transaksi hariannya kecil —
  perlakukan sinyalnya dengan kehati-hatian ekstra (rawan "saham gorengan").
- Tanda **⚠️tipis** pada estimasi waktu = jumlah sampel historisnya kecil,
  jangan dijadikan dasar utama keputusan.

### Soal "prediksi waktu bullish"

Aplikasi ini TIDAK memprediksi tanggal pasti di masa depan (itu secara
statistik tidak mungkin diklaim jujur dari data harga historis). Yang
ditampilkan adalah **pola musiman historis** (calendar effect): hari dalam
minggu, bagian bulan (awal/tengah/akhir), dan bulan dalam tahun yang
**rata-rata historisnya** paling sering naik untuk saham tersebut — lengkap
dengan jumlah sampel (n_obs) supaya Anda bisa menilai sendiri seberapa
andal pola itu. Pola harian jauh lebih banyak datanya (andal) dibanding
pola bulanan (biasanya hanya beberapa observasi per bulan dalam 5 tahun).


## 4. Keterbatasan yang perlu Anda sadari

- Data dari Yahoo Finance delay 15-20 menit dan kadang ada selisih kecil di
  sekitar aksi korporasi (stock split, dividen) — untuk transaksi nyata,
  cross-check ke RTI/Stockbit/IDX resmi.
- Prediksi **harian** sangat dipengaruhi noise pasar — interval yang
  dihasilkan lebar dan sengaja dipotong ke batas ARA/ARB supaya tidak
  memberi angka yang mustahil secara fisik di bursa.
- Skor fundamental hanya seakurat data `.info` Yahoo Finance untuk emiten
  Indonesia, yang kadang tidak lengkap — kalau kosong, skor dinetralkan
  (tidak dianggap baik/buruk).
- List LQ45 di `core/constants.py` adalah perkiraan dan **bisa usang**
  (BEI mengevaluasi ulang ~tiap 6 bulan) — gunakan mode "Custom" kalau ragu.
- Aplikasi ini TIDAK menyertakan data broker summary/foreign flow
  ("bandarmology") — sesuai catatan skill asli, ini sinyal heuristik
  komunitas yang belum tervalidasi secara statistik, sengaja tidak dijadikan
  komponen utama.

## 5. Struktur kode (kalau Anda ingin kustomisasi)

```
idx_analyzer/
├── app.py                 # UI Streamlit (3 tab: screening, analisis, backtest)
├── core/
│   ├── constants.py        # aturan ARA/ARB, list saham, disclaimer
│   ├── data.py              # fetch data Yahoo Finance
│   ├── indicators.py        # SMA, RSI, MACD, Bollinger, ATR, ADX, dst
│   ├── scoring.py            # skor komposit per komponen & horizon
│   ├── forecast.py           # estimasi rentang harga (quantile + ARA/ARB clip)
│   ├── seasonality.py        # pola musiman: hari/bagian-bulan/bulan paling bullish
│   ├── backtest.py           # backtest SMA crossover, net of cost
│   └── charts.py             # grafik candlestick & equity curve (Plotly)
└── requirements.txt
```

Mau ubah bobot skor? Edit `HORIZON_WEIGHTS` di `core/scoring.py`.
Mau ubah ambang likuiditas? Edit `MIN_ADTV_IDR` di `core/constants.py`.
