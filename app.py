import asyncio
import threading
import queue
import time
import re
import io
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

import requests
from PIL import Image, ImageTk

from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)
from winsdk.windows.storage.streams import DataReader, Buffer, InputStreamOptions

SPOTIFY_GREEN = "#1DB954"
SPOTIFY_BLACK = "#191414"
TEXT_WHITE = "#FFFFFF"
TEXT_GRAY = "#B3B3B3"
LYRIC_ACTIVE = "#1DB954"
LYRIC_INACTIVE = "#666666"

state_queue = queue.Queue(maxsize=1)
lirik_queue = queue.Queue(maxsize=1)
stop_event = threading.Event()

async def ambil_thumbnail_bytes(info):
    if info.thumbnail is None:
        return None
    try:
        stream = await info.thumbnail.open_read_async()
        buffer = Buffer(stream.size)
        await stream.read_async(buffer, stream.size, InputStreamOptions.READ_AHEAD)
        reader = DataReader.from_buffer(buffer)
        raw = bytearray(buffer.length)
        reader.read_bytes(raw)
        return bytes(raw)
    except Exception:
        return None


async def ambil_media_info(id_lagu_sebelumnya):
    sessions = await MediaManager.request_async()
    session = sessions.get_current_session()
    if session is None:
        return None

    info = await session.try_get_media_properties_async()
    timeline = session.get_timeline_properties()
    playback = session.get_playback_info()

    id_lagu = f"{info.title or ''}|{info.artist or ''}"
    lagu_berubah = id_lagu != id_lagu_sebelumnya

    thumbnail_bytes = None
    if lagu_berubah:
        thumbnail_bytes = await ambil_thumbnail_bytes(info)

    posisi_detik = timeline.position.total_seconds()
    waktu_acuan = time.time()
    try:
        if timeline.last_updated_time is not None:
            ts = timeline.last_updated_time.timestamp()
            selisih = time.time() - ts
            if -2 <= selisih <= 30:
                waktu_acuan = ts
    except Exception:
        pass

    return {
        "judul": info.title or "",
        "artis": info.artist or "",
        "album": info.album_title or "",
        "thumbnail": thumbnail_bytes,
        "lagu_berubah": lagu_berubah,
        "posisi_detik": posisi_detik,
        "waktu_update_terakhir": waktu_acuan,
        "sedang_main": playback.playback_status == PlaybackStatus.PLAYING,
    }


def loop_polling_media():
    async def runner():
        id_lagu_terakhir = None
        while not stop_event.is_set():
            try:
                data = await ambil_media_info(id_lagu_terakhir)
            except Exception as e:
                data = None
                print(f"[media] error: {e}")

            if data:
                id_lagu_terakhir = f"{data['judul']}|{data['artis']}"
            else:
                id_lagu_terakhir = None

            if not state_queue.empty():
                try:
                    state_queue.get_nowait()
                except queue.Empty:
                    pass
            state_queue.put(data)

            await asyncio.sleep(0.5)

    asyncio.run(runner())

LRCLIB_HEADERS = {"User-Agent": "NowPlayingLirikApp/1.0 (personal project)"}

def _cari_lrclib(params, percobaan_ulang=1):
    for percobaan in range(percobaan_ulang + 1):
        try:
            resp = requests.get(
                "https://lrclib.net/api/search",
                params=params,
                headers=LRCLIB_HEADERS,
                timeout=8,
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if percobaan < percobaan_ulang:
                print(f"[lirik] Timeout/koneksi gagal, coba lagi... ({percobaan + 1})")
                continue
            raise


def ambil_lirik_sinkron(artis, judul):
    """Cari lirik sinkron (format LRC) dari lrclib.net. Return list (detik, teks)."""
    try:
        hasil = _cari_lrclib({"track_name": judul, "artist_name": artis})
        if not hasil:
            hasil = _cari_lrclib({"q": f"{judul} {artis}"})

        if not hasil:
            hasil = _cari_lrclib({"track_name": judul})

        if not hasil:
            print(f"[lirik] Tidak ada hasil sama sekali untuk '{judul}' - '{artis}'")
            return [(0, "Lirik tidak ditemukan di database lrclib")]

        for item in hasil:
            synced = item.get("syncedLyrics")
            if synced:
                return parse_lrc(synced)

        for item in hasil:
            plain = item.get("plainLyrics")
            if plain:
                return [(0, baris) for baris in plain.split("\n") if baris.strip()]

        print(f"[lirik] Ada {len(hasil)} hasil tapi semua instrumental/tanpa lirik")
        return [(0, "Ditemukan lagu tapi tidak ada teks lirik (instrumental?)")]
    except requests.exceptions.RequestException as e:
        print(f"[lirik] Error koneksi ke lrclib: {e}")
        return [(0, f"Gagal konek ke server lirik: {e}")]
    except Exception as e:
        print(f"[lirik] Error tak terduga: {e}")
        return [(0, f"Gagal ambil lirik: {e}")]


def parse_lrc(teks_lrc):
    baris_list = []
    pola = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")
    for baris in teks_lrc.split("\n"):
        m = pola.match(baris)
        if m:
            menit, detik, teks = m.groups()
            total_detik = int(menit) * 60 + float(detik)
            if teks.strip():
                baris_list.append((total_detik, teks.strip()))
    return baris_list if baris_list else [(0, "Lirik kosong")]


def mulai_ambil_lirik_background(artis, judul):
    def worker():
        hasil = ambil_lirik_sinkron(artis, judul)
        if not lirik_queue.empty():
            try:
                lirik_queue.get_nowait()
            except queue.Empty:
                pass
        lirik_queue.put((artis, judul, hasil))

    threading.Thread(target=worker, daemon=True).start()

class AppLirik:
    def __init__(self, root):
        self.root = root
        self.root.title("Now Playing + Lirik Sinkron")
        self.root.geometry("420x650")
        self.root.configure(bg=SPOTIFY_BLACK)

        self.lirik_sinkron = [(0, "Menunggu lagu diputar...")]
        self.posisi_estimasi = 0.0
        self.waktu_update_terakhir = time.time()
        self.sedang_main = False
        self.baris_aktif_terakhir = -1

        self._bangun_ui()
        self.root.after(200, self._tick)

    def _bangun_ui(self):
        frame_top = tk.Frame(self.root, bg=SPOTIFY_BLACK)
        frame_top.pack(pady=10)

        self.label_cover = tk.Label(frame_top, bg=SPOTIFY_BLACK)
        self.label_cover.pack(pady=(0, 10))

        self.label_judul = tk.Label(frame_top, font=("Poppins", 12, "bold"), bg=SPOTIFY_BLACK, fg=TEXT_WHITE)
        self.label_judul.pack()

        self.label_artis = tk.Label(frame_top, font=("Poppins", 10), bg=SPOTIFY_BLACK, fg=TEXT_GRAY)
        self.label_artis.pack()

        frame_card = tk.Frame(self.root, bg="#222", bd=1, relief="flat")
        frame_card.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)

        self.text_lirik = tk.Text(
            frame_card,
            wrap=tk.WORD,
            font=("Poppins", 11),
            fg=LYRIC_INACTIVE,
            bg="#222",
            padx=10,
            pady=10,
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        self.text_lirik.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.text_lirik.tag_configure("aktif", foreground=LYRIC_ACTIVE, font=("Poppins", 12, "bold"))
        self.text_lirik.tag_configure("nonaktif", foreground=LYRIC_INACTIVE)

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Vertical.TScrollbar",
            troughcolor=SPOTIFY_BLACK,
            background=SPOTIFY_GREEN,
            bordercolor=SPOTIFY_BLACK,
            arrowcolor=TEXT_WHITE,
        )
        scrollbar = ttk.Scrollbar(frame_card, command=self.text_lirik.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_lirik.config(yscrollcommand=scrollbar.set)

        self.label_status = tk.Label(
            self.root, font=("Poppins", 9), bg=SPOTIFY_BLACK, fg=TEXT_GRAY, text="Menunggu media..."
        )
        self.label_status.pack(pady=(0, 10))

    def _render_lirik(self):
        self.text_lirik.config(state=tk.NORMAL)
        self.text_lirik.delete("1.0", tk.END)
        for _, teks in self.lirik_sinkron:
            self.text_lirik.insert(tk.END, teks + "\n", "nonaktif")
        self.text_lirik.config(state=tk.DISABLED)
        self.baris_aktif_terakhir = -1

    def _highlight_baris_aktif(self, posisi):
        baris_aktif = 0
        for i, (waktu, _) in enumerate(self.lirik_sinkron):
            if waktu <= posisi:
                baris_aktif = i
            else:
                break

        if baris_aktif == self.baris_aktif_terakhir:
            return

        self.text_lirik.config(state=tk.NORMAL)
        if self.baris_aktif_terakhir >= 0:
            self.text_lirik.tag_remove(
                "aktif", f"{self.baris_aktif_terakhir + 1}.0", f"{self.baris_aktif_terakhir + 2}.0"
            )
            self.text_lirik.tag_add(
                "nonaktif", f"{self.baris_aktif_terakhir + 1}.0", f"{self.baris_aktif_terakhir + 2}.0"
            )

        self.text_lirik.tag_remove("nonaktif", f"{baris_aktif + 1}.0", f"{baris_aktif + 2}.0")
        self.text_lirik.tag_add("aktif", f"{baris_aktif + 1}.0", f"{baris_aktif + 2}.0")
        self._scroll_ke_tengah(baris_aktif)
        self.text_lirik.config(state=tk.DISABLED)

        self.baris_aktif_terakhir = baris_aktif

    def _scroll_ke_tengah(self, baris_index):
        self.text_lirik.update_idletasks()
        tinggi_widget = self.text_lirik.winfo_height()
        font_lirik = tkfont.Font(font=self.text_lirik.cget("font"))
        tinggi_baris = max(1, font_lirik.metrics("linespace"))
        baris_terlihat = max(1, tinggi_widget // tinggi_baris)
        baris_tujuan = max(0, baris_index - baris_terlihat // 2)
        self.text_lirik.yview(f"{baris_tujuan + 1}.0")

    def _update_cover(self, thumbnail_bytes):
        try:
            if thumbnail_bytes:
                img = Image.open(io.BytesIO(thumbnail_bytes)).resize((180, 180))
            else:
                raise ValueError("no thumbnail")
        except Exception:
            img = Image.new("RGB", (180, 180), SPOTIFY_BLACK)

        photo = ImageTk.PhotoImage(img)
        self.label_cover.config(image=photo)
        self.label_cover.image = photo

    def _tick(self):
        try:
            data = state_queue.get_nowait()
            self._proses_state_baru(data)
        except queue.Empty:
            pass

        try:
            artis, judul, lirik = lirik_queue.get_nowait()
            if artis == self.label_artis.cget("text") and judul == self.label_judul.cget("text"):
                self.lirik_sinkron = lirik
                self._render_lirik()
        except queue.Empty:
            pass

        if self.sedang_main:
            sekarang = time.time()
            posisi = self.posisi_estimasi + (sekarang - self.waktu_update_terakhir)
            self._highlight_baris_aktif(posisi)

        self.root.after(200, self._tick)

    def _proses_state_baru(self, data):
        if data is None:
            self.label_status.config(text="Tidak ada media yang diputar")
            self.sedang_main = False
            return

        self.sedang_main = data["sedang_main"]
        self.posisi_estimasi = data["posisi_detik"]
        self.waktu_update_terakhir = data["waktu_update_terakhir"]
        self.label_status.config(text="▶ Playing" if self.sedang_main else "⏸ Paused")

        self.label_judul.config(text=data["judul"])
        self.label_artis.config(text=data["artis"])

        if data["lagu_berubah"]:
            self._update_cover(data["thumbnail"])
            self.lirik_sinkron = [(0, "Memuat lirik...")]
            self._render_lirik()
            mulai_ambil_lirik_background(data["artis"], data["judul"])


def main():
    thread = threading.Thread(target=loop_polling_media, daemon=True)
    thread.start()

    root = tk.Tk()
    AppLirik(root)

    def on_close():
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()