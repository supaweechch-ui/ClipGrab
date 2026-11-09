"""ClipGrab - เว็บแอปโหลดคลิปจากลิงก์ (Flask + yt-dlp)

รันบน Termux แล้วเปิดจากมือถือ/iPad ผ่านเบราว์เซอร์ที่ http://<IP เครื่อง>:8080
"""
import glob
import os
import re
import shutil
import socket
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, abort, jsonify, request, send_file

BASE = Path(__file__).parent.resolve()
PORT = int(os.environ.get("PORT", 8080))
MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", 2))

_termux_dl = Path.home() / "storage" / "downloads"
DOWNLOAD_DIR = Path(
    os.environ.get("DOWNLOAD_DIR")
    or (_termux_dl / "ClipGrab" if _termux_dl.exists() else BASE / "downloads")
)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"

app = Flask(__name__, static_folder=None)
JOBS: dict = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=MAX_PARALLEL)
THUMB_OK: set = set()  # อนุญาตให้พร็อกซีเฉพาะภาพปกที่ได้จาก /api/info


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- helpers
def valid_url(u: str) -> bool:
    return bool(re.match(r"^https?://[^\s]+$", u or ""))


def fmt_error(e) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip()
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"^\[[^\]]+\]\s*[\w-]+:\s*", "", msg)
    if "confirm you" in msg and "bot" in msg:
        return "YouTube ขอให้ยืนยันว่าไม่ใช่บอท ลองอัปเดต yt-dlp (bash update.sh) หรือลองใหม่ภายหลัง"
    return msg[:220] or "เกิดข้อผิดพลาด"


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n]+', "_", s or "").strip()[:80] or "clip"


def first_entry(info):
    if info and info.get("_type") == "playlist":
        return next(iter(info.get("entries") or []), None) or {}
    return info or {}


def pick_thumb(info):
    for t in reversed(info.get("thumbnails") or []):
        u = t.get("url", "")
        if urlparse(u).path.lower().endswith((".jpg", ".jpeg", ".png")):
            return u
    return info.get("thumbnail")


def fetch_bytes(url: str, limit: int = 8 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(limit), r.headers.get("Content-Type", "image/jpeg")


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    i = 2
    while True:
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists():
            return q
        i += 1


def locate_output(info, workdir: Path) -> Path:
    info = first_entry(info)
    for rd in info.get("requested_downloads") or []:
        p = rd.get("filepath")
        if p and Path(p).exists():
            return Path(p)
    vid = info.get("id")
    if vid:
        cands = [
            p
            for p in workdir.glob("*" + glob.escape(f"[{vid}].") + "*")
            if p.suffix not in (".part", ".ytdl")
        ]
        if cands:
            return max(cands, key=lambda p: p.stat().st_mtime)
    raise RuntimeError("ดาวน์โหลดเสร็จแต่หาไฟล์ผลลัพธ์ไม่เจอ")


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_") and k not in ("path", "cancel")}


# ---------------------------------------------------------------- download
def build_format(fmt: str, q):
    h = f"[height<=?{q}]" if q else ""
    if HAS_FFMPEG:
        return f"bv*{h}[ext=mp4]+ba[ext=m4a]/bv*{h}+ba/b{h}[ext=mp4]/b{h}/b"
    return f"b{h}[ext=mp4]/b{h}/b"


def grab_media(job: dict) -> Path:
    # แต่ละงานโหลดในโฟลเดอร์ชั่วคราวของตัวเอง กันไฟล์ชนกันตอนโหลด MP4+MP3 ของคลิปเดียวกันพร้อมกัน
    workdir = DOWNLOAD_DIR / ".tmp" / job["id"]
    workdir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if job["cancel"]:
            raise Cancelled()
        if d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        frac = (d.get("downloaded_bytes", 0) / total) if total else 0
        fname = d.get("filename")
        if fname != job["_file"]:
            if job["_file"] is not None:
                job["_part"] += 1
            job["_file"] = fname
        parts = len((d.get("info_dict") or {}).get("requested_formats") or [1])
        pct = min(99.0, (job["_part"] + frac) / parts * 100)
        job["percent"] = round(max(job["percent"], pct), 1)
        job["speed"] = d.get("speed")
        job["eta"] = d.get("eta")

    def pp_hook(d):
        if d.get("status") == "started":
            job.update(status="processing", speed=None, eta=None)

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "playlist_items": "1",
        "outtmpl": str(workdir / "%(title).80s [%(id)s].%(ext)s"),
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
        "socket_timeout": 20,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "windowsfilenames": True,
    }
    if job["format"] == "mp3":
        if HAS_FFMPEG:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        else:  # ไม่มี ffmpeg แปลงเป็น mp3 ไม่ได้ ใช้เสียงต้นฉบับ (m4a)
            opts["format"] = "bestaudio[ext=m4a]/bestaudio"
    else:
        opts["format"] = build_format("mp4", job["quality"])
        if HAS_FFMPEG:
            opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(job["url"], download=True)
        src = locate_output(info, workdir)
        dest = unique_path(DOWNLOAD_DIR / src.name)
        shutil.move(str(src), str(dest))
        return dest
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def grab_thumb(job: dict) -> Path:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "playlist_items": "1",
        "skip_download": True,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = first_entry(ydl.extract_info(job["url"], download=False))
    url = pick_thumb(info)
    if not url:
        raise RuntimeError("ไม่พบภาพปกของคลิปนี้")
    data, ctype = fetch_bytes(url)
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(
        ctype.split(";")[0].strip(), Path(urlparse(url).path).suffix or ".jpg"
    )
    name = safe_name(info.get("title") or info.get("id") or "thumbnail")
    path = unique_path(DOWNLOAD_DIR / f"{name} [{info.get('id', 'thumb')}]{ext}")
    path.write_bytes(data)
    return path


def run_job(jid: str):
    job = JOBS.get(jid)
    if not job:
        return
    if job["cancel"]:
        job["status"] = "cancelled"
        return
    job["status"] = "downloading"
    try:
        path = grab_thumb(job) if job["format"] == "thumb" else grab_media(job)
        job.update(
            path=str(path), filename=path.name, status="done", percent=100.0, speed=None, eta=None
        )
    except Exception as e:  # noqa: BLE001
        if job["cancel"]:
            job["status"] = "cancelled"
        else:
            job.update(status="error", error=fmt_error(e), speed=None, eta=None)


# ---------------------------------------------------------------- routes
@app.get("/")
def index():
    return send_file(BASE / "static" / "index.html")


@app.post("/api/info")
def api_info():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    if not valid_url(url):
        return jsonify(error="ลิงก์ไม่ถูกต้อง"), 400
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "playlist_items": "1",
        "skip_download": True,
        "socket_timeout": 15,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = first_entry(ydl.extract_info(url, download=False))
    except Exception as e:  # noqa: BLE001
        return jsonify(error=fmt_error(e)), 422
    thumb = pick_thumb(info)
    if thumb:
        THUMB_OK.add(thumb)
    heights = sorted({f["height"] for f in info.get("formats") or [] if f.get("height")}, reverse=True)
    return jsonify(
        url=url,
        title=info.get("title") or url,
        thumbnail=thumb,
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel"),
        site=info.get("extractor_key"),
        heights=heights,
    )


@app.get("/api/thumb")
def api_thumb():
    url = request.args.get("url", "")
    if url not in THUMB_OK:
        abort(404)
    try:
        data, ctype = fetch_bytes(url)
    except Exception:  # noqa: BLE001
        abort(502)
    return data, 200, {"Content-Type": ctype, "Cache-Control": "max-age=3600"}


@app.post("/api/download")
def api_download():
    data = request.get_json(silent=True) or {}
    fmt = data.get("format", "mp4")
    if fmt not in ("mp4", "mp3", "thumb"):
        return jsonify(error="รูปแบบไม่ถูกต้อง"), 400
    q = str(data.get("quality", ""))
    q = int(q) if q.isdigit() else None
    ids = []
    for it in (data.get("items") or [])[:50]:
        url = (it.get("url") or "").strip()
        if not valid_url(url):
            continue
        jid = uuid.uuid4().hex[:10]
        job = {
            "id": jid,
            "url": url,
            "title": it.get("title") or url,
            "thumbnail": it.get("thumbnail"),
            "format": fmt,
            "quality": q,
            "status": "queued",
            "percent": 0.0,
            "speed": None,
            "eta": None,
            "error": None,
            "filename": None,
            "created": time.time(),
            "cancel": False,
            "_part": 0,
            "_file": None,
        }
        with LOCK:
            JOBS[jid] = job
        POOL.submit(run_job, jid)
        ids.append(jid)
    return jsonify(ids=ids)


@app.get("/api/jobs")
def api_jobs():
    with LOCK:
        return jsonify([public(j) for j in reversed(list(JOBS.values()))])


@app.post("/api/jobs/<jid>/cancel")
def api_cancel(jid):
    job = JOBS.get(jid)
    if not job:
        abort(404)
    job["cancel"] = True
    if job["status"] == "queued":
        job["status"] = "cancelled"
    return jsonify(ok=True)


@app.delete("/api/jobs/<jid>")
def api_delete(jid):
    with LOCK:
        job = JOBS.get(jid)
        if job and job["status"] in ("done", "error", "cancelled"):
            del JOBS[jid]
    return jsonify(ok=True)


@app.get("/api/file/<jid>")
def api_file(jid):
    job = JOBS.get(jid)
    if not job or job["status"] != "done" or not job.get("path") or not Path(job["path"]).exists():
        abort(404)
    return send_file(job["path"], as_attachment=True, download_name=job["filename"])


# ---------------------------------------------------------------- main
def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return None
    finally:
        s.close()


if __name__ == "__main__":
    ip = lan_ip()
    print("\n=== ClipGrab พร้อมใช้งาน ===")
    print(f"เปิดบนเครื่องนี้ : http://localhost:{PORT}")
    if ip:
        print(f"เปิดจาก iPad/เครื่องอื่นใน Wi-Fi เดียวกัน : http://{ip}:{PORT}")
    print(f"ไฟล์จะถูกเก็บที่  : {DOWNLOAD_DIR}")
    if not HAS_FFMPEG:
        print("คำเตือน: ไม่พบ ffmpeg จึงรวมภาพ+เสียง/แปลง MP3 ไม่ได้ (pkg install ffmpeg)")
    print("กด Ctrl+C เพื่อหยุด\n")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
