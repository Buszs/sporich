# Now Playing + Lirik Sinkron

Aplikasi desktop untuk Windows yang menampilkan lagu yang sedang diputar dari aplikasi apa pun (Spotify, browser, dan lainnya) beserta lirik yang tersinkronisasi secara real-time, mengikuti posisi playback baris demi baris.

Berbeda dari kebanyakan implementasi serupa, proyek ini tidak bergantung pada Spotify Web API — sehingga tidak memerlukan akun Premium, API key, maupun proses autentikasi OAuth.

## Fitur

- Deteksi lagu yang sedang diputar secara lokal melalui Windows Media Session (SMTC), sehingga kompatibel dengan berbagai aplikasi pemutar musik, bukan hanya Spotify.
- Lirik tersinkronisasi per baris, dengan highlight otomatis pada baris yang sedang dinyanyikan.
- Baris lirik aktif selalu diposisikan di tengah tampilan, menyerupai gaya karaoke.
- Cover art diambil langsung dari metadata media, tanpa permintaan tambahan ke API eksternal.
- Proses jaringan (pengambilan lirik) berjalan di background thread terpisah, sehingga antarmuka tetap responsif.

## Cara Kerja

1. **Deteksi media** — Aplikasi membaca informasi sesi media aktif dari Windows melalui `winsdk`, mencakup judul lagu, artis, cover art, status pemutaran, dan posisi playback.
2. **Pengambilan lirik** — Ketika lagu berganti, judul dan nama artis dikirim ke [lrclib.net](https://lrclib.net), basis data lirik gratis dan terbuka yang menyediakan lirik tersinkron dalam format LRC.
3. **Sinkronisasi tampilan** — Posisi playback diestimasi secara halus di antara siklus polling, menggunakan `last_updated_time` dari Windows sebagai titik acuan waktu, sehingga highlight baris lirik mengikuti audio secara akurat.

## Requirements

- Windows 10/11
- Python 3.9 atau lebih baru
- Dependensi pada `requirements.txt`:
  - `winsdk`
  - `requests`
  - `Pillow`

## Instalasi

```bash
git clone https://github.com/username/nama-repo.git
cd nama-repo
pip install -r requirements.txt
```

## Menjalankan Aplikasi

```bash
python lirik_v2.py
```

Putar lagu apa pun melalui aplikasi favorit kamu (Spotify, browser, dan sebagainya), lalu jendela aplikasi akan otomatis menampilkan informasi lagu beserta liriknya.

## Struktur Proyek

```
.
├── lirik_v2.py         # Berkas utama aplikasi
├── requirements.txt    # Daftar dependensi Python
└── README.md
```

## Keterbatasan

- Hanya berjalan di Windows, karena bergantung pada Windows Media Session API.
- Ketersediaan lirik bergantung pada basis data lrclib.net, yang bersifat kolaboratif dan tidak selalu lengkap untuk setiap lagu — terutama rilisan baru, indie, atau instrumental.
- Akurasi sinkronisasi lirik mengikuti kualitas metadata timeline yang dilaporkan oleh aplikasi pemutar musik masing-masing.

## Kredit

- [lrclib.net](https://lrclib.net) — basis data lirik tersinkron, gratis dan tanpa API key.
- [winsdk](https://pypi.org/project/winsdk/) — binding Python untuk Windows Runtime API.

## Lisensi

Proyek ini dibuat untuk keperluan pengembangan pribadi/pembelajaran. Silakan sesuaikan lisensi (MIT, dsb.) sesuai kebutuhan sebelum dipublikasikan.
