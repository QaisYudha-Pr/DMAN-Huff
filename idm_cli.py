"""
IDM CLI - Command Line Multi-Threaded Download Manager
Usage:
  python idm_cli.py <URL> [-c CONNECTIONS] [-o OUTPUT_DIR] [-f FILENAME]
"""

import sys
import argparse
from idm_engine import DownloadTask

def render_progress(prog: dict):
    pct = prog["percent"]
    total = prog["total_size"] / (1024 * 1024)
    dl = prog["downloaded"] / (1024 * 1024)
    speed = prog["speed"] / (1024 * 1024)
    
    eta = "N/A"
    if prog["speed"] > 0 and prog["total_size"] > prog["downloaded"]:
        rem_sec = (prog["total_size"] - prog["downloaded"]) / prog["speed"]
        eta = f"{rem_sec:.1f}s"
        
    bar_width = 30
    filled = int(bar_width * (pct / 100)) if total > 0 else 0
    bar = "=" * filled + "-" * (bar_width - filled)
    
    # Segment breakdown summary (e.g. [8/8 active])
    active_segs = sum(1 for s in prog["segments"] if s["status"] == "DOWNLOADING")
    total_segs = len(prog["segments"])
    
    line = f"\r[{bar}] {pct:5.1f}% | {dl:.2f}/{total:.2f} MB | {speed:.2f} MB/s | ETA: {eta:6s} | Threads: {active_segs}/{total_segs}"
    sys.stdout.write(line)
    sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Multi-threaded Segmented Download Manager (IDM-style)")
    parser.add_argument("url", help="Direct URL of the file to download")
    parser.add_argument("-c", "--connections", type=int, default=8, help="Number of parallel connections (1-32, default 8)")
    parser.add_argument("-o", "--output-dir", default=".", help="Directory to save the downloaded file")
    parser.add_argument("-f", "--filename", default=None, help="Custom filename to save as")
    
    args = parser.parse_args()
    
    task = DownloadTask(
        url=args.url,
        output_dir=args.output_dir,
        custom_filename=args.filename,
        num_connections=args.connections,
        progress_callback=render_progress
    )
    
    try:
        task.start()
    except KeyboardInterrupt:
        print("\n[!] User paused download. Preserving state for resume...")
        task.pause()

if __name__ == "__main__":
    main()

