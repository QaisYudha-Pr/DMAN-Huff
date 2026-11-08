"""
Dmans Engine - High-Performance Multi-Connection Download Accelerator
Optimized for high-speed streaming, dynamic segmentation, and low disk latency.
"""

import os
import sys
import json
import time
import socket
import urllib.request
import urllib.parse
import threading
from typing import Dict, List, Optional, Callable

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Set global socket options for high-throughput networking
socket.setdefaulttimeout(30)
DEFAULT_USER_AGENT = "Dmans/1.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OPTIMAL_CHUNK_SIZE = 262144  # 256 KB chunks for high throughput and reduced lock contention

class Segment:
    def __init__(self, seg_id: int, start: int, end: int, current: int = None):
        self.seg_id = seg_id
        self.start = start
        self.end = end
        self.current = current if current is not None else start
        self.status = "PENDING"  # PENDING, DOWNLOADING, COMPLETED, FAILED

    @property
    def total_bytes(self) -> int:
        return self.end - self.start + 1

    @property
    def downloaded_bytes(self) -> int:
        return self.current - self.start

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.end - self.current + 1)

    @property
    def is_finished(self) -> bool:
        return self.current > self.end

    def to_dict(self) -> dict:
        return {
            "seg_id": self.seg_id,
            "start": self.start,
            "end": self.end,
            "current": self.current,
            "status": self.status
        }

    @classmethod
    def from_dict(cls, data: dict):
        seg = cls(data["seg_id"], data["start"], data["end"], data["current"])
        seg.status = data.get("status", "PENDING")
        return seg


class DownloadTask:
    def __init__(
        self,
        url: str,
        output_dir: str = ".",
        custom_filename: Optional[str] = None,
        num_connections: int = 8,
        chunk_size: int = OPTIMAL_CHUNK_SIZE,
        max_speed_kb: Optional[int] = None,
        progress_callback: Optional[Callable] = None
    ):
        self.url = url
        self.output_dir = os.path.abspath(output_dir)
        self.num_connections = max(1, min(num_connections, 32))
        self.chunk_size = chunk_size
        self.max_speed_kb = max_speed_kb
        self.progress_callback = progress_callback

        self.total_size = 0
        self.supports_range = False
        self.filename = custom_filename or self._extract_filename(url)
        self.final_path = os.path.join(self.output_dir, self.filename)
        self.part_path = self.final_path + ".dmpart"
        self.meta_path = self.final_path + ".dmmeta"

        self.segments: List[Segment] = []
        self.is_paused = False
        self.is_cancelled = False
        self.is_finished = False

        self.file_lock = threading.Lock()
        self.meta_lock = threading.Lock()
        self.split_lock = threading.Lock()
        self.workers: List[threading.Thread] = []

        self.start_time = None
        self.last_checked_time = 0
        self.last_checked_bytes = 0
        self.current_speed = 0.0
        self.added_time = time.strftime("%Y-%m-%d %H:%M")
        self.status = "Queued"
        self.category = self._detect_category(self.filename)

    def _detect_category(self, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        if ext in [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"]:
            return "Compressed"
        elif ext in [".pdf", ".doc", ".docx", ".txt", ".rtf", ".epub", ".xls", ".xlsx", ".ppt", ".pptx"]:
            return "Documents"
        elif ext in [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"]:
            return "Video"
        elif ext in [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"]:
            return "Music"
        elif ext in [".exe", ".msi", ".apk", ".dmg", ".bat", ".cmd", ".sh"]:
            return "Programs"
        return "General"

    def _extract_filename(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        name = os.path.basename(parsed.path)
        if not name or "." not in name:
            qs = urllib.parse.parse_qs(parsed.query)
            if "filename" in qs:
                name = qs["filename"][0]
            else:
                name = "download_" + str(int(time.time())) + ".bin"
        return urllib.parse.unquote(name)

    def _resolve_streaming_url(self):
        """Resolves direct stream URLs for YouTube, TikTok, etc. using yt_dlp if available"""
        if not yt_dlp:
            return
        url_lower = self.url.lower()
        if any(domain in url_lower for domain in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com/reel", "twitter.com", "x.com"]):
            try:
                ydl_opts = {
                    'format': 'best[ext=mp4]/best',
                    'quiet': True,
                    'no_warnings': True,
                    'skip_download': True
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
                    if info:
                        direct = info.get('url')
                        title = info.get('title')
                        if direct:
                            self.url = direct
                        if title and (not self.filename or self.filename.endswith(".bin") or "watch" in self.filename):
                            clean = "".join(c for c in title if c.isalnum() or c in " ._- ()")
                            ext = info.get('ext', 'mp4')
                            self.filename = f"{clean}.{ext}"
                            self.filepath = os.path.join(self.output_dir, self.filename)
            except Exception:
                pass

    def probe(self):
        """Detect file length and Range support via HTTP HEAD or GET"""
        self._resolve_streaming_url()
        req = urllib.request.Request(self.url, method="HEAD")
        req.add_header("User-Agent", DEFAULT_USER_AGENT)
        req.add_header("Connection", "keep-alive")

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                if "content-length" in headers:
                    self.total_size = int(headers["content-length"])
                if headers.get("accept-ranges", "").lower() == "bytes":
                    self.supports_range = True
        except Exception:
            pass

        if not self.supports_range:
            try:
                probe_req = urllib.request.Request(self.url, headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Range": "bytes=0-0",
                    "Connection": "keep-alive"
                })
                with urllib.request.urlopen(probe_req, timeout=12) as resp:
                    if resp.status == 206:
                        self.supports_range = True
                        cr = resp.headers.get("Content-Range", "")
                        if "/" in cr:
                            total = cr.split("/")[-1]
                            if total.isdigit():
                                self.total_size = int(total)
                    elif resp.status == 200:
                        cl = resp.headers.get("Content-Length")
                        if cl and cl.isdigit():
                            self.total_size = int(cl)
            except Exception as e:
                print(f"[!] Warning: Probe encountered error: {e}")

    def _save_metadata(self):
        with self.meta_lock:
            data = {
                "url": self.url,
                "filename": self.filename,
                "total_size": self.total_size,
                "supports_range": self.supports_range,
                "num_connections": self.num_connections,
                "segments": [seg.to_dict() for seg in self.segments]
            }
            try:
                with open(self.meta_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def _load_metadata(self) -> bool:
        if not os.path.exists(self.meta_path) or not os.path.exists(self.part_path):
            return False
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.total_size = data["total_size"]
            self.supports_range = data["supports_range"]
            self.segments = [Segment.from_dict(s) for s in data["segments"]]
            return True
        except Exception:
            return False

    def _setup_segments(self):
        if self._load_metadata():
            print("[*] Found existing partial download. Resuming...")
            return

        os.makedirs(self.output_dir, exist_ok=True)

        if not self.supports_range or self.total_size <= 0:
            self.segments = [Segment(0, 0, self.total_size - 1 if self.total_size > 0 else 0)]
            with open(self.part_path, "wb") as f:
                pass
            return

        # Fast NTFS sparse file allocation via truncate
        with open(self.part_path, "wb") as f:
            f.truncate(self.total_size)

        part_size = self.total_size // self.num_connections
        self.segments = []
        for i in range(self.num_connections):
            start = i * part_size
            end = (start + part_size - 1) if (i < self.num_connections - 1) else (self.total_size - 1)
            self.segments.append(Segment(i, start, end))

        self._save_metadata()

    def _find_and_split_work(self) -> Optional[Segment]:
        """Dynamic Work Stealing: Splitting the largest remaining portion in half"""
        MIN_SPLIT_THRESHOLD = 1048576  # 1 MB threshold for high efficiency
        with self.split_lock:
            best_seg = None
            max_remaining = 0
            for seg in self.segments:
                if seg.status == "DOWNLOADING" and seg.remaining_bytes > max_remaining:
                    max_remaining = seg.remaining_bytes
                    best_seg = seg

            if best_seg and max_remaining >= MIN_SPLIT_THRESHOLD:
                split_point = best_seg.current + (max_remaining // 2)
                old_end = best_seg.end
                best_seg.end = split_point - 1

                new_seg_id = len(self.segments)
                new_seg = Segment(new_seg_id, split_point, old_end)
                self.segments.append(new_seg)
                return new_seg
        return None

    def _worker(self, initial_segment: Segment, file_handle):
        current_segment = initial_segment
        while current_segment and not self.is_paused and not self.is_cancelled:
            self._download_segment(current_segment, file_handle)
            if self.is_paused or self.is_cancelled:
                break
            current_segment = self._find_and_split_work()

    def _download_segment(self, segment: Segment, file_handle):
        if segment.is_finished:
            segment.status = "COMPLETED"
            return

        segment.status = "DOWNLOADING"
        req = urllib.request.Request(self.url, headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Range": f"bytes={segment.current}-{segment.end}",
            "Connection": "keep-alive"
        })

        retries = 3
        while retries > 0 and not self.is_paused and not self.is_cancelled:
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    while segment.current <= segment.end and not self.is_paused and not self.is_cancelled:
                        t0 = time.time()
                        to_read = min(self.chunk_size, segment.end - segment.current + 1)
                        chunk = resp.read(to_read)
                        if not chunk:
                            break

                        with self.file_lock:
                            file_handle.seek(segment.current)
                            file_handle.write(chunk)
                            segment.current += len(chunk)

                        if self.max_speed_kb and self.max_speed_kb > 0:
                            target_bps = (self.max_speed_kb * 1024) / max(1, self.num_connections)
                            expected_time = len(chunk) / target_bps
                            elapsed = time.time() - t0
                            if elapsed < expected_time:
                                time.sleep(expected_time - elapsed)

                if segment.is_finished:
                    segment.status = "COMPLETED"
                    break
            except Exception as e:
                retries -= 1
                if retries <= 0:
                    segment.status = "FAILED"
                    print(f"\n[!] Segment {segment.seg_id} failed: {e}")
                time.sleep(1)

    def _single_stream_worker(self, file_handle):
        req = urllib.request.Request(self.url, headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Connection": "keep-alive"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            while not self.is_paused and not self.is_cancelled:
                t0 = time.time()
                chunk = resp.read(self.chunk_size)
                if not chunk:
                    break
                with self.file_lock:
                    file_handle.write(chunk)
                    if self.segments:
                        self.segments[0].current += len(chunk)

                if self.max_speed_kb and self.max_speed_kb > 0:
                    target_bps = self.max_speed_kb * 1024
                    expected_time = len(chunk) / target_bps
                    elapsed = time.time() - t0
                    if elapsed < expected_time:
                        time.sleep(expected_time - elapsed)

            if self.segments:
                self.segments[0].status = "COMPLETED"

    def get_progress(self) -> dict:
        total_downloaded = sum(seg.downloaded_bytes for seg in self.segments)
        pct = (total_downloaded / self.total_size * 100) if self.total_size > 0 else 0.0
        
        return {
            "filename": self.filename,
            "url": self.url,
            "category": self.category,
            "status": self.status,
            "added_time": self.added_time,
            "total_size": self.total_size,
            "downloaded": total_downloaded,
            "percent": pct,
            "speed": self.current_speed,
            "is_finished": self.is_finished,
            "is_paused": self.is_paused,
            "is_cancelled": self.is_cancelled,
            "segments": [seg.to_dict() for seg in self.segments]
        }

    def start(self):
        self.is_paused = False
        self.is_cancelled = False
        self.status = "Connecting"
        if self.progress_callback:
            self.progress_callback(self.get_progress())

        self.probe()
        self.status = "Downloading"
        self._setup_segments()
        self.start_time = time.time()
        self.last_checked_time = self.start_time
        self.last_checked_bytes = sum(seg.downloaded_bytes for seg in self.segments)

        mode = "r+b" if os.path.exists(self.part_path) and os.path.getsize(self.part_path) > 0 else "wb"
        with open(self.part_path, mode) as f:
            if self.supports_range and len(self.segments) > 1:
                threads = []
                for seg in self.segments:
                    t = threading.Thread(target=self._worker, args=(seg, f))
                    threads.append(t)
                    t.start()
                self.workers = threads
            else:
                t = threading.Thread(target=self._single_stream_worker, args=(f,))
                threads = [t]
                t.start()
                self.workers = threads

            while any(t.is_alive() for t in threads):
                time.sleep(0.35)
                now = time.time()
                dt = now - self.last_checked_time
                if dt > 0:
                    curr_dl = sum(seg.downloaded_bytes for seg in self.segments)
                    self.current_speed = (curr_dl - self.last_checked_bytes) / dt
                    self.last_checked_bytes = curr_dl
                    self.last_checked_time = now

                self._save_metadata()
                if self.progress_callback:
                    self.progress_callback(self.get_progress())

            for t in threads:
                t.join()

        all_done = all(seg.is_finished or seg.status == "COMPLETED" for seg in self.segments)
        if all_done and not self.is_paused and not self.is_cancelled:
            if os.path.exists(self.final_path):
                os.remove(self.final_path)
            os.rename(self.part_path, self.final_path)
            if os.path.exists(self.meta_path):
                os.remove(self.meta_path)
            self.is_finished = True
            self.status = "Completed"
            self.current_speed = 0.0
            if self.progress_callback:
                self.progress_callback(self.get_progress())
        elif self.is_paused:
            self.status = "Paused"
            self.current_speed = 0.0
            if self.progress_callback:
                self.progress_callback(self.get_progress())
        elif self.is_cancelled:
            self.status = "Cancelled"
            self.current_speed = 0.0
            if os.path.exists(self.part_path):
                os.remove(self.part_path)
            if os.path.exists(self.meta_path):
                os.remove(self.meta_path)
            if self.progress_callback:
                self.progress_callback(self.get_progress())

    def pause(self):
        self.is_paused = True
        self.status = "Paused"

    def cancel(self):
        self.is_cancelled = True
        self.status = "Cancelled"

