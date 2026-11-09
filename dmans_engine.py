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

# Bulletproof stdout/stderr wrapper for windowed mode
class SafeStream:
    def __init__(self, target=None):
        self.target = target
    def write(self, s):
        try:
            if self.target and hasattr(self.target, "write"):
                self.target.write(s)
        except Exception:
            pass
    def flush(self):
        try:
            if self.target and hasattr(self.target, "flush"):
                self.target.flush()
        except Exception:
            pass

sys.stdout = SafeStream(sys.stdout)
sys.stderr = SafeStream(sys.stderr)

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Set global socket options for high-throughput networking
socket.setdefaulttimeout(30)
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
OPTIMAL_CHUNK_SIZE = 262144  # 256 KB chunks for high throughput and reduced lock contention

def detect_file_category(filename: str = "", content_type: str = "", url: str = "") -> str:
    """Smartly classifies a file or stream into an IDM category based on extension, MIME, or URL."""
    url_lower = url.lower() if url else ""
    if any(k in url_lower for k in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com/reel", "twitter.com", "x.com"]):
        return "Video"

    ext = os.path.splitext(filename.lower())[1] if filename else ""
    ct = content_type.lower() if content_type else ""

    if ext in [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".cab", ".tgz", ".7zip"] or any(x in ct for x in ["zip", "compressed", "tar"]):
        return "Compressed"
    elif ext in [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts", ".m4v", ".3gp", ".wmv"] or "video" in ct:
        return "Video"
    elif ext in [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".wma", ".alac"] or "audio" in ct:
        return "Music"
    elif ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff", ".raw", ".heic"] or "image" in ct:
        return "Images"
    elif ext in [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".epub", ".csv", ".odt", ".ods"] or "pdf" in ct or "msword" in ct:
        return "Documents"
    elif ext in [".exe", ".msi", ".apk", ".dmg", ".bat", ".cmd", ".sh", ".bin"]:
        return "Programs"
    return "General"

def resolve_category_path(base_dir: str, category: str, auto_categorize: bool = True) -> str:
    """Returns the target download folder path, respecting auto-categorization into subfolders."""
    if not base_dir:
        base_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    if auto_categorize and category and category not in ["General", "All Downloads", "Unfinished", "Finished"]:
        target = os.path.join(base_dir, category)
    else:
        target = base_dir
    try:
        os.makedirs(target, exist_ok=True)
    except Exception:
        pass
    return target

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
        progress_callback: Optional[Callable] = None,
        cookies: str = "",
        referer: str = "",
        user_agent: Optional[str] = None,
        quality: str = "best",
        format_spec: str = "",
        auto_categorize: bool = False,
        base_download_dir: Optional[str] = None
    ):
        self.original_url = url
        self.url = url
        self.output_dir = os.path.abspath(output_dir)
        self.auto_categorize = auto_categorize
        self.base_download_dir = os.path.abspath(base_download_dir) if base_download_dir else self.output_dir
        self.num_connections = max(1, min(num_connections, 32))
        self.chunk_size = chunk_size
        self.max_speed_kb = max_speed_kb
        self.progress_callback = progress_callback
        self.cookies = cookies or ""
        self.referer = referer or ""
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.quality = quality or "best"
        self.format_spec = format_spec or ""

        self.total_size = 0
        self.supports_range = False
        self.filename = custom_filename or self._extract_filename(url)
        self.final_path = os.path.join(self.output_dir, self.filename)
        self.part_path = self.final_path + ".dmpart"
        self.meta_path = self.final_path + ".dmmeta"
        self.is_stream_task = False

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

    def _set_filename(self, name: str):
        if not name:
            return
        import re
        clean_name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
        if not clean_name:
            clean_name = "download"
        self.filename = clean_name
        self.final_path = os.path.join(self.output_dir, self.filename)
        self.part_path = self.final_path + ".dmpart"
        self.meta_path = self.final_path + ".dmmeta"

    def _detect_category(self, filename: str, content_type: str = "") -> str:
        if getattr(self, "quality", "") == "audio":
            return "Music"
        if getattr(self, "is_stream_task", False):
            return "Video"
        return detect_file_category(filename, content_type, url=self.url)

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
        url_lower = self.original_url.lower()
        if any(domain in url_lower for domain in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com/reel", "twitter.com", "x.com"]):
            self.is_stream_task = True
            self.category = "Video"
            if not yt_dlp:
                return
            try:
                target_url = self.original_url
                if "youtube.com" in url_lower:
                    try:
                        parsed = urllib.parse.urlparse(self.original_url)
                        qs = urllib.parse.parse_qs(parsed.query)
                        v = qs.get("v", [""])[0]
                        if v:
                            target_url = f"https://www.youtube.com/watch?v={v}"
                    except Exception:
                        pass

                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'skip_download': True,
                    'noplaylist': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'ios', 'web']
                        }
                    }
                }
                node_path = r'C:\Program Files\node-v26.13.0-win-x64\node.exe'
                if os.path.exists(node_path):
                    ydl_opts['js_runtimes'] = {'node': {'path': node_path}}
                http_headers = {'User-Agent': self.user_agent}
                if self.cookies:
                    http_headers['Cookie'] = self.cookies
                if self.referer:
                    http_headers['Referer'] = self.referer
                ydl_opts['http_headers'] = http_headers

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(target_url, download=False)
                    if info:
                        title = info.get('title')
                        ext = info.get('ext', 'mp4')
                        clean = "".join(c for c in title if c.isalnum() or c in " ._- ()") if title else "video"
                        self._set_filename(f"{clean}.{ext}")
                        if info.get('filesize'):
                            self.total_size = info.get('filesize')
                        elif info.get('filesize_approx'):
                            self.total_size = info.get('filesize_approx')
            except Exception:
                pass

    def _parse_headers_for_metadata(self, headers: dict):
        """Extracts file size, Range support, RFC 6266 Content-Disposition filename, and Content-Type extension"""
        if "content-length" in headers and headers["content-length"].isdigit():
            self.total_size = int(headers["content-length"])
        if headers.get("accept-ranges", "").lower() == "bytes":
            self.supports_range = True

        cd = headers.get("content-disposition", "")
        cur_ext = os.path.splitext(self.filename)[1].lower()
        is_generic_name = (
            not self.filename
            or not cur_ext
            or self.filename.lower() in ["download", "watch", "file", "index.html", "uc", "get"]
            or cur_ext in [".bin", ".htm", ".html"]
            or self.filename.startswith("download_")
        )
        if cd and (is_generic_name or "attachment" in cd.lower() or "filename" in cd.lower()):
            import re
            m_utf = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)", cd, re.IGNORECASE)
            if m_utf:
                fname = urllib.parse.unquote(m_utf.group(1).strip('"\''))
                self._set_filename(fname)
            else:
                m = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\s]+))', cd, re.IGNORECASE)
                if m:
                    fname = urllib.parse.unquote((m.group(1) or m.group(2)).strip('"\''))
                    self._set_filename(fname)

        ct = headers.get("content-type", "").lower()
        # If filename has no extension or is generic .bin/.htm, infer accurate extension from Content-Type
        cur_ext = os.path.splitext(self.filename)[1].lower()
        if not cur_ext or cur_ext in [".bin", ".htm", ".html"]:
            base = os.path.splitext(self.filename)[0] or "download"
            if "image/jpeg" in ct:
                self._set_filename(f"{base}.jpg")
            elif "image/png" in ct:
                self._set_filename(f"{base}.png")
            elif "image/webp" in ct:
                self._set_filename(f"{base}.webp")
            elif "image/gif" in ct:
                self._set_filename(f"{base}.gif")
            elif "image/" in ct:
                sub = ct.split("image/")[1].split(";")[0].strip()
                self._set_filename(f"{base}.{sub}")
            elif "video/mp4" in ct:
                self._set_filename(f"{base}.mp4")
            elif "video/webm" in ct:
                self._set_filename(f"{base}.webm")
            elif "video/x-matroska" in ct:
                self._set_filename(f"{base}.mkv")
            elif "video/" in ct:
                sub = ct.split("video/")[1].split(";")[0].strip()
                self._set_filename(f"{base}.{sub}")
            elif "audio/mpeg" in ct or "audio/mp3" in ct:
                self._set_filename(f"{base}.mp3")
            elif "audio/mp4" in ct or "audio/m4a" in ct:
                self._set_filename(f"{base}.m4a")
            elif "audio/" in ct:
                sub = ct.split("audio/")[1].split(";")[0].strip()
                self._set_filename(f"{base}.{sub}")
            elif "application/pdf" in ct:
                self._set_filename(f"{base}.pdf")
            elif "application/zip" in ct:
                self._set_filename(f"{base}.zip")
            elif "application/x-rar" in ct or "application/vnd.rar" in ct:
                self._set_filename(f"{base}.rar")
            elif "application/x-7z-compressed" in ct:
                self._set_filename(f"{base}.7z")
            elif "compressed" in ct:
                self._set_filename(f"{base}.zip")

        old_cat = self.category
        self.category = self._detect_category(self.filename, ct)
        if getattr(self, "auto_categorize", False) and self.category != old_cat:
            new_target_dir = resolve_category_path(getattr(self, "base_download_dir", self.output_dir), self.category, True)
            if new_target_dir != self.output_dir:
                self.output_dir = new_target_dir
                self._set_filename(self.filename)

    def probe(self):
        """Detect file length and Range support via HTTP HEAD or GET"""
        self._resolve_streaming_url()
        if self.is_stream_task:
            return

        req = urllib.request.Request(self.url, method="HEAD")
        req.add_header("User-Agent", self.user_agent)
        req.add_header("Connection", "keep-alive")
        if self.cookies:
            req.add_header("Cookie", self.cookies)
        if self.referer:
            req.add_header("Referer", self.referer)

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                self._parse_headers_for_metadata(headers)
        except Exception:
            pass

        if not self.supports_range:
            try:
                headers = {
                    "User-Agent": self.user_agent,
                    "Range": "bytes=0-0",
                    "Connection": "keep-alive"
                }
                if self.cookies:
                    headers["Cookie"] = self.cookies
                if self.referer:
                    headers["Referer"] = self.referer
                probe_req = urllib.request.Request(self.url, headers=headers)
                with urllib.request.urlopen(probe_req, timeout=12) as resp:
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    self._parse_headers_for_metadata(headers)
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
            except Exception:
                pass

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

        # Smart dynamic connection count (IDM adaptive multi-threading)
        actual_conns = self.num_connections
        if self.total_size > 0:
            if self.total_size < 1024 * 1024:  # Under 1 MB (e.g. images, icons, small docs)
                actual_conns = 1
            elif self.total_size < 5 * 1024 * 1024:  # Under 5 MB
                actual_conns = min(actual_conns, 4)

        # Fast NTFS pre-allocation
        with open(self.part_path, "wb") as f:
            f.truncate(self.total_size)

        part_size = self.total_size // actual_conns
        self.segments = []
        for i in range(actual_conns):
            start = i * part_size
            end = (start + part_size - 1) if (i < actual_conns - 1) else (self.total_size - 1)
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
        headers = {
            "User-Agent": self.user_agent,
            "Range": f"bytes={segment.current}-{segment.end}",
            "Connection": "keep-alive"
        }
        if self.cookies:
            headers["Cookie"] = self.cookies
        if self.referer:
            headers["Referer"] = self.referer
        req = urllib.request.Request(self.url, headers=headers)

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
        headers = {
            "User-Agent": self.user_agent,
            "Connection": "keep-alive"
        }
        if self.cookies:
            headers["Cookie"] = self.cookies
        if self.referer:
            headers["Referer"] = self.referer
        req = urllib.request.Request(self.url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                headers_dict = {k.lower(): v for k, v in resp.headers.items()}
                self._parse_headers_for_metadata(headers_dict)
                while not self.is_paused and not self.is_cancelled:
                    t0 = time.time()
                    chunk = resp.read(self.chunk_size)
                    if not chunk:
                        break
                    with self.file_lock:
                        file_handle.write(chunk)
                        if self.segments:
                            self.segments[0].current += len(chunk)
                            if self.total_size <= 0:
                                self.segments[0].end = self.segments[0].current

                    if self.max_speed_kb and self.max_speed_kb > 0:
                        target_bps = self.max_speed_kb * 1024
                        expected_time = len(chunk) / target_bps
                        elapsed = time.time() - t0
                        if elapsed < expected_time:
                            time.sleep(expected_time - elapsed)

                if self.segments and not self.is_paused and not self.is_cancelled:
                    self.segments[0].status = "COMPLETED"
                    if self.total_size <= 0:
                        self.total_size = self.segments[0].current
                        self.segments[0].end = max(0, self.segments[0].current - 1)
        except Exception as e:
            print(f"[!] Single stream worker error: {e}")
            if self.segments:
                self.segments[0].status = "FAILED"

    def get_progress(self) -> dict:
        total_downloaded = sum(seg.downloaded_bytes for seg in self.segments)
        pct = (total_downloaded / self.total_size * 100) if self.total_size > 0 else 0.0
        
        return {
            "filename": self.filename,
            "url": self.url,
            "category": self.category,
            "output_dir": self.output_dir,
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

    def _download_stream(self):
        self.status = "Downloading"
        target_url = self.original_url
        if "youtube.com" in target_url.lower():
            try:
                parsed = urllib.parse.urlparse(target_url)
                qs = urllib.parse.parse_qs(parsed.query)
                v = qs.get("v", [""])[0]
                if v:
                    target_url = f"https://www.youtube.com/watch?v={v}"
            except Exception:
                pass

        def _yt_hook(d):
            if self.is_cancelled:
                raise Exception("Download cancelled by user")
            status = d.get("status")
            if status == "downloading":
                self.status = "Downloading"
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or self.total_size or 0
                if total > 0:
                    self.total_size = total
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0.0
                self.current_speed = speed

                num_segs = self.num_connections or 8
                if not self.segments or len(self.segments) != num_segs:
                    total_est = self.total_size or (downloaded * 2) or 1000000
                    seg_size = max(1, total_est // num_segs)
                    self.segments = []
                    for i in range(num_segs):
                        s_start = i * seg_size
                        s_end = (i + 1) * seg_size if i < num_segs - 1 else total_est
                        self.segments.append(Segment(i, s_start, s_end, s_start))

                remaining = downloaded
                for seg in self.segments:
                    seg_cap = max(1, seg.end - seg.start)
                    if remaining >= seg_cap:
                        seg.current = seg.end
                        seg.status = "COMPLETED"
                        remaining -= seg_cap
                    elif remaining > 0:
                        seg.current = seg.start + remaining
                        seg.status = "DOWNLOADING"
                        remaining = 0
                    else:
                        seg.current = seg.start
                        seg.status = "PENDING"

                if self.progress_callback:
                    self.progress_callback(self.get_progress())
            elif status == "finished":
                self.status = "Finalizing"
                if self.segments:
                    for seg in self.segments:
                        seg.current = seg.end
                        seg.status = "COMPLETED"
                if self.progress_callback:
                    self.progress_callback(self.get_progress())

        out_base = os.path.splitext(self.final_path)[0]
        outtmpl = f"{out_base}.%(ext)s"

        if self.format_spec:
            ydl_format = self.format_spec
        elif self.quality == "1080p":
            ydl_format = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
        elif self.quality == "720p":
            ydl_format = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
        elif self.quality == "480p":
            ydl_format = 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
        elif self.quality == "360p":
            ydl_format = 'bestvideo[height<=360]+bestaudio/best[height<=360]/best'
        elif self.quality == "audio":
            ydl_format = 'bestaudio/best'
            self.category = "Music"
        else:
            ydl_format = 'bestvideo+bestaudio/best'

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'format': ydl_format,
            'outtmpl': outtmpl,
            'merge_output_format': 'mp4',
            'progress_hooks': [_yt_hook],
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web']
                }
            }
        }
        node_path = r'C:\Program Files\node-v26.13.0-win-x64\node.exe'
        if os.path.exists(node_path):
            ydl_opts['js_runtimes'] = {'node': {'path': node_path}}

        http_headers = {'User-Agent': self.user_agent}
        if self.cookies:
            http_headers['Cookie'] = self.cookies
        if self.referer:
            http_headers['Referer'] = self.referer
        ydl_opts['http_headers'] = http_headers

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=True)
                if info:
                    title = info.get('title')
                    if title:
                        clean = "".join(c for c in title if c.isalnum() or c in " ._- ()")
                        for ext in ["mp4", "webm", "mkv", "m4a"]:
                            cand_base = f"{out_base}.{ext}"
                            if os.path.exists(cand_base):
                                target_path = os.path.join(self.output_dir, f"{clean}.{ext}")
                                try:
                                    if cand_base != target_path:
                                        if os.path.exists(target_path):
                                            os.remove(target_path)
                                        os.rename(cand_base, target_path)
                                except Exception:
                                    target_path = cand_base
                                self._set_filename(os.path.basename(target_path))
                                break

            self.is_finished = True
            self.status = "Completed"
            self.current_speed = 0.0
            if os.path.exists(self.final_path):
                self.total_size = os.path.getsize(self.final_path)
            if self.segments:
                for seg in self.segments:
                    seg.status = "COMPLETED"
                    seg.current = seg.end
            if self.progress_callback:
                self.progress_callback(self.get_progress())
        except Exception as e:
            if not self.is_cancelled:
                self.status = "Error"
                self.current_speed = 0.0
                if self.progress_callback:
                    self.progress_callback(self.get_progress())

    def start(self):
        self.is_paused = False
        self.is_cancelled = False
        self.status = "Connecting"
        if self.progress_callback:
            self.progress_callback(self.get_progress())

        self.probe()

        if self.is_stream_task:
            if yt_dlp:
                self._download_stream()
            else:
                self.status = "Error"
                if self.progress_callback:
                    self.progress_callback(self.get_progress())
            return

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

            # IDM-style fault tolerance: If any segment failed, retry sequentially before finalizing
            if not self.is_paused and not self.is_cancelled:
                incomplete = [s for s in self.segments if not s.is_finished and s.status != "COMPLETED"]
                for seg in incomplete:
                    self._download_segment(seg, f)

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
                try:
                    os.remove(self.part_path)
                except Exception:
                    pass
            if os.path.exists(self.meta_path):
                try:
                    os.remove(self.meta_path)
                except Exception:
                    pass
            if self.progress_callback:
                self.progress_callback(self.get_progress())
        else:
            self.status = "Error"
            self.current_speed = 0.0
            if self.progress_callback:
                self.progress_callback(self.get_progress())

    def pause(self):
        self.is_paused = True
        self.status = "Paused"

    def cancel(self):
        self.is_cancelled = True
        self.status = "Cancelled"


def extract_stream_breakdown(url: str) -> dict:
    """Extracts all available video and audio format streams for interactive breakdown in GUI"""
    if not yt_dlp:
        return {"error": "yt-dlp is not installed"}

    target_url = url
    if "youtube.com" in url.lower():
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            v = qs.get("v", [""])[0]
            if v:
                target_url = f"https://www.youtube.com/watch?v={v}"
        except Exception:
            pass

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        }
    }
    node_path = r'C:\Program Files\node-v26.13.0-win-x64\node.exe'
    if os.path.exists(node_path):
        ydl_opts['js_runtimes'] = {'node': {'path': node_path}}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            if not info:
                return {"error": "Failed to extract video information"}

            title = info.get("title", "Video")
            duration = info.get("duration", 0)
            thumbnail = info.get("thumbnail", "")
            raw_formats = info.get("formats", [])

            stream_options = []
            seen_resolutions = set()

            for target_h in [1080, 720, 480, 360, 240]:
                for f in raw_formats:
                    h = f.get("height")
                    if h == target_h and h not in seen_resolutions:
                        seen_resolutions.add(h)
                        size_mb = ""
                        size_bytes = f.get("filesize") or f.get("filesize_approx")
                        if size_bytes:
                            size_mb = f"{size_bytes / (1024*1024):.1f} MB"
                        else:
                            tbr = f.get("tbr") or (h * 3.2)
                            est = (tbr * 1024 / 8) * duration
                            size_mb = f"~{est / (1024*1024):.1f} MB" if duration else "-"

                        stream_options.append({
                            "quality": f"{h}p",
                            "label": f"{h}p ({'Full HD' if h==1080 else 'HD' if h==720 else 'Standard' if h==480 else 'Fast'})",
                            "format_spec": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best",
                            "resolution": f"{f.get('width', '-')}x{h}",
                            "ext": "mp4",
                            "size": size_mb,
                            "codec": str(f.get("vcodec", "avc1")).split(".")[0],
                            "type": "Video + Audio"
                        })
                        break

            audio_f = next((f for f in raw_formats if f.get("vcodec") == "none" and f.get("acodec") != "none"), None)
            if audio_f:
                a_size = ""
                a_bytes = audio_f.get("filesize") or audio_f.get("filesize_approx")
                if a_bytes:
                    a_size = f"{a_bytes / (1024*1024):.1f} MB"
                elif duration:
                    a_size = f"~{(128 * 1024 / 8 * duration) / (1024*1024):.1f} MB"

                stream_options.append({
                    "quality": "audio",
                    "label": "Audio Only (M4A/MP3)",
                    "format_spec": "bestaudio/best",
                    "resolution": "Audio",
                    "ext": "m4a",
                    "size": a_size or "-",
                    "codec": str(audio_f.get("acodec", "m4a")).split(".")[0],
                    "type": "Audio Only"
                })

            return {
                "title": title,
                "duration": duration,
                "thumbnail": thumbnail,
                "streams": stream_options
            }
    except Exception as e:
        return {"error": str(e)}

