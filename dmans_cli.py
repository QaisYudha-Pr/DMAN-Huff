"""
Dmans CLI - Fast Multi-Threaded Command-Line Downloader
Usage:
  dmans <URL> [-c CONNECTIONS] [-o OUTPUT_DIR] [-f FILENAME] [-l SPEED_LIMIT_KB]
"""

import sys
import argparse
from dmans_engine import DownloadTask
import version

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
    
    active_segs = sum(1 for s in prog["segments"] if s["status"] == "DOWNLOADING")
    total_segs = len(prog["segments"])
    
    line = f"\r[{bar}] {pct:5.1f}% | {dl:.2f}/{total:.2f} MB | {speed:.2f} MB/s | ETA: {eta:6s} | Threads: {active_segs}/{total_segs}"
    sys.stdout.write(line)
    sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(
        prog="dmans",
        description=f"Dmans v{version.VERSION} - Fast Multi-Connection Download Accelerator"
    )
    parser.add_argument("url", nargs="?", default="", help="Direct URL of the file to download")
    parser.add_argument("-c", "--connections", type=int, default=8, help="Number of parallel connections (1-32, default 8)")
    parser.add_argument("-o", "--output-dir", default=".", help="Directory to save the downloaded file")
    parser.add_argument("-f", "--filename", default=None, help="Custom filename to save as")
    parser.add_argument("-l", "--limit", type=int, default=None, help="Speed limit in KB/s (e.g. 1024 for 1 MB/s)")
    parser.add_argument("-v", "--version", action="version", version=f"Dmans v{version.VERSION}")
    
    args = parser.parse_args()
    
    if not args.url:
        parser.print_help()
        sys.exit(0)

    task = DownloadTask(
        url=args.url,
        output_dir=args.output_dir,
        custom_filename=args.filename,
        num_connections=args.connections,
        max_speed_kb=args.limit,
        progress_callback=render_progress
    )
    
    try:
        task.start()
    except KeyboardInterrupt:
        print("\n[!] Paused download. State preserved for resume.")
        task.pause()

if __name__ == "__main__":
    main()

