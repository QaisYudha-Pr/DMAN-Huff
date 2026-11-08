"""
Core Download Manager Engine
Implements multi-connection segmented downloads with HTTP Range requests,
pre-allocated sparse file writing, and real-time speed monitoring.
"""

import sys
import os
import time
import threading
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

class DownloadManager:
    def __init__(self, url: str, output_path: str = None, num_connections: int = 8, chunk_size: int = 65536):
        self.url = url
        self.output_path = output_path or self._get_filename_from_url(url)
        self.num_connections = num_connections
        self.chunk_size = chunk_size
        self.total_size = 0
        self.supports_range = False
        self.downloaded_bytes = 0
        self.lock = threading.Lock()
        self.is_done = False
        self.start_time = None
        self.segment_progress = {}

    def _get_filename_from_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        filename = os.path.basename(parsed.path)
        if not filename:
            filename = "downloaded_file.bin"
        return filename

    def probe(self):
        """Inspect headers to determine file size and Range support (like IDM probe)"""
        req = urllib.request.Request(self.url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DownloadManager/1.0")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                content_length = headers.get("content-length")
                accept_ranges = headers.get("accept-ranges", "")
                
                self.supports_range = (accept_ranges.lower() == "bytes")
                if content_length:
                    self.total_size = int(content_length)
        except Exception:
            # Fallback to GET with Range: bytes=0-0 if HEAD is disallowed
            req = urllib.request.Request(self.url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DownloadManager/1.0",
                "Range": "bytes=0-0"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 206:
                    self.supports_range = True
                    cr = resp.headers.get("Content-Range", "")
                    if "/" in cr:
                        self.total_size = int(cr.split("/")[-1])
                else:
                    cl = resp.headers.get("Content-Length")
                    if cl:
                        self.total_size = int(cl)

    def _download_segment(self, seg_id: int, start: int, end: int, file_handle):
        """Worker thread to download a specific byte range"""
        req = urllib.request.Request(self.url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DownloadManager/1.0")
        req.add_header("Range", f"bytes={start}-{end}")
        
        current_offset = start
        expected_bytes = (end - start + 1)
        seg_downloaded = 0
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            while current_offset <= end:
                read_amount = min(self.chunk_size, end - current_offset + 1)
                chunk = resp.read(read_amount)
                if not chunk:
                    break
                
                with self.lock:
                    file_handle.seek(current_offset)
                    file_handle.write(chunk)
                    self.downloaded_bytes += len(chunk)
                    seg_downloaded += len(chunk)
                    self.segment_progress[seg_id] = (seg_downloaded, expected_bytes)
                
                current_offset += len(chunk)

    def _download_single_stream(self, file_handle):
        """Fallback when server does not support Range requests"""
        req = urllib.request.Request(self.url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DownloadManager/1.0"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            while True:
                chunk = resp.read(self.chunk_size)
                if not chunk:
                    break
                file_handle.write(chunk)
                with self.lock:
                    self.downloaded_bytes += len(chunk)

    def _progress_reporter(self):
        """Live progress display in the console showing overall & per-connection stats"""
        last_bytes = 0
        last_time = time.time()
        
        while not self.is_done:
            time.sleep(0.5)
            now = time.time()
            dt = now - last_time
            if dt <= 0:
                continue
            
            with self.lock:
                current_bytes = self.downloaded_bytes
                total = self.total_size
                segments = dict(self.segment_progress)
            
            speed = (current_bytes - last_bytes) / dt # bytes/sec
            last_bytes = current_bytes
            last_time = now
            
            speed_mb = speed / (1024 * 1024)
            cur_mb = current_bytes / (1024 * 1024)
            total_mb = total / (1024 * 1024) if total > 0 else 0
            
            pct = (current_bytes / total * 100) if total > 0 else 0
            eta_str = f"{(total - current_bytes) / speed:.1f}s" if speed > 0 and total > 0 else "N/A"
            
            bar_len = 30
            filled = int(bar_len * (pct / 100)) if total > 0 else 0
            bar = "=" * filled + "-" * (bar_len - filled)
            
            status = f"\r[{bar}] {pct:5.1f}% | {cur_mb:.2f}/{total_mb:.2f} MB | {speed_mb:.2f} MB/s | ETA: {eta_str}"
            sys.stdout.write(status)
            sys.stdout.flush()

    def start(self):
        print(f"[*] Probing URL: {self.url}")
        self.probe()
        print(f"[*] File Size: {self.total_size / (1024 * 1024):.2f} MB ({self.total_size} bytes)")
        print(f"[*] Resuming/Range support: {'YES' if self.supports_range else 'NO'}")
        
        self.start_time = time.time()
        
        # Pre-allocate file to eliminate end-of-download stitching bottleneck
        with open(self.output_path, "wb") as f:
            if self.total_size > 0:
                f.seek(self.total_size - 1)
                f.write(b"\0")
        
        # Start reporter thread
        reporter = threading.Thread(target=self._progress_reporter, daemon=True)
        reporter.start()
        
        with open(self.output_path, "r+b") as f:
            if self.supports_range and self.total_size > 0 and self.num_connections > 1:
                # Calculate segments
                part_size = self.total_size // self.num_connections
                ranges = []
                for i in range(self.num_connections):
                    start = i * part_size
                    end = (start + part_size - 1) if (i < self.num_connections - 1) else (self.total_size - 1)
                    ranges.append((i, start, end))
                    self.segment_progress[i] = (0, end - start + 1)
                
                print(f"[*] Splitting into {len(ranges)} parallel segments...")
                with ThreadPoolExecutor(max_workers=self.num_connections) as executor:
                    futures = [
                        executor.submit(self._download_segment, seg_id, start, end, f)
                        for seg_id, start, end in ranges
                    ]
                    for future in futures:
                        future.result()
            else:
                print("[*] Downloading via single connection stream...")
                self._download_single_stream(f)
        
        self.is_done = True
        elapsed = time.time() - self.start_time
        avg_speed = (self.total_size / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        print(f"\n[+] Download complete! Saved to '{self.output_path}'")
        print(f"[+] Total time: {elapsed:.2f}s | Average speed: {avg_speed:.2f} MB/s")

if __name__ == "__main__":
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://speed.cloudflare.com/__down?bytes=10485760" # 10MB test
    conns = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    dm = DownloadManager(test_url, num_connections=conns)
    dm.start()

