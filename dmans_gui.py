"""
Dmans Desktop Application
High-speed multi-threaded download manager with dynamic connection visualizer.
"""

import os
import sys
import json
import time
import subprocess
import threading
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict, Optional

import version
import updater
from dmans_engine import DownloadTask

# Safe stdout/stderr for windowed mode
if sys.stdout is None:
    class DummyStream:
        def write(self, s): pass
        def flush(self): pass
    sys.stdout = DummyStream()
if sys.stderr is None:
    class DummyStream:
        def write(self, s): pass
        def flush(self): pass
    sys.stderr = DummyStream()

try:
    import winsound
except ImportError:
    winsound = None

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def force_bring_to_front(win):
    try:
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()
        import ctypes
        hwnd = win.winfo_id()
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.BringWindowToTop(hwnd)
        win.after(500, lambda: win.attributes("-topmost", False))
    except Exception:
        pass

APP_DIR = get_app_dir()
DB_FILE = os.path.join(APP_DIR, "dmans_db.json")

class DmansApiHandler(BaseHTTPRequestHandler):
    app_ref = None

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            resp = b'{"status": "ok", "app": "Dmans"}'
            self.send_response(200)
            self._send_cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        elif self.path == "/show":
            if DmansApiHandler.app_ref:
                DmansApiHandler.app_ref.after(0, DmansApiHandler.app_ref.show_window)
            resp = b'{"status": "shown"}'
            self.send_response(200)
            self._send_cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/add":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                if DmansApiHandler.app_ref:
                    DmansApiHandler.app_ref.after(0, DmansApiHandler.app_ref.handle_browser_add, data)
                resp = b'{"status": "received"}'
                self.send_response(200)
                self._send_cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class DmansApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Dmans v{version.VERSION} - Fast Download Accelerator")
        self.geometry("980x620")
        self.minsize(800, 500)

        # Apply icon if available
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for icon_candidate in [os.path.join(base_dir, "assets", "app.ico"), os.path.join(base_dir, "app.ico")]:
            if os.path.exists(icon_candidate):
                try:
                    self.iconbitmap(icon_candidate)
                    break
                except Exception:
                    pass

        self.style = ttk.Style(self)
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")

        self.configure(bg="#F0F2F5")
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=4)
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=26)
        self.style.configure("TButton", font=("Segoe UI", 9), padding=4)
        self.style.configure("Toolbar.TButton", font=("Segoe UI", 8), padding=3)

        self.downloads: Dict[str, DownloadTask] = {}
        self.db_records = self._load_db()
        self.selected_category = "All Downloads"
        self.clipboard_monitor_active = tk.BooleanVar(value=True)
        self.last_clipboard_url = ""
        self.detail_windows = {}

        self.queue_active = tk.BooleanVar(value=True)
        self.max_concurrent_var = tk.IntVar(value=2)

        self._build_menu()
        self._build_toolbar()
        self._build_main_split()
        self._build_statusbar()

        self._refresh_table()
        self._start_background_monitors()
        self._start_api_server()

        # Handle CLI argument or protocol URL (dmans://)
        if len(sys.argv) > 1:
            arg_url = sys.argv[1].strip()
            if arg_url.startswith("dmans://"):
                arg_url = arg_url[len("dmans://"):]
            if arg_url.startswith("http://") or arg_url.startswith("https://"):
                self.after(500, lambda u=arg_url: self.show_add_download_dialog(initial_url=u))

    def _start_api_server(self):
        def run_server():
            try:
                DmansApiHandler.app_ref = self
                server = ThreadingHTTPServer(("127.0.0.1", 18888), DmansApiHandler)
                server.serve_forever()
            except Exception as e:
                print(f"[!] Dmans API server error: {e}")

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

    def handle_browser_add(self, data: dict):
        url = data.get("url", "").strip()
        if not url:
            return
        filename = data.get("filename", "").strip()
        cookies = data.get("cookies", "")
        referer = data.get("referer", "")
        user_agent = data.get("user_agent", "")
        start_now = data.get("start_now", False)
        quality = data.get("quality", "best")
        if winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        force_bring_to_front(self)
        self.show_add_download_dialog(
            initial_url=url,
            filename=filename,
            cookies=cookies,
            referer=referer,
            user_agent=user_agent,
            start_now=start_now,
            quality=quality
        )

    def show_window(self):
        self.deiconify()
        self.lift()
        force_bring_to_front(self)

    def _load_db(self) -> list:
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_db(self):
        records = []
        for r in self.db_records:
            task = self.downloads.get(r["url"])
            if task:
                p = task.get_progress()
                r["status"] = p["status"]
                r["total_size"] = p["total_size"]
                r["downloaded"] = p["downloaded"]
                r["percent"] = p["percent"]
            records.append(r)
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
        except Exception:
            pass

    def _build_menu(self):
        menubar = tk.Menu(self)

        tasks_menu = tk.Menu(menubar, tearoff=0)
        tasks_menu.add_command(label="➕ Add new download...", command=self.show_add_download_dialog)
        tasks_menu.add_command(label="📋 Add batch downloads...", command=self.show_batch_download_dialog)
        tasks_menu.add_separator()
        tasks_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="Tasks", menu=tasks_menu)

        dl_menu = tk.Menu(menubar, tearoff=0)
        dl_menu.add_command(label="▶️ Resume Selected", command=self.resume_selected)
        dl_menu.add_command(label="⏸️ Pause Selected", command=self.pause_selected)
        dl_menu.add_command(label="▶️ Start Queue", command=self.start_queue)
        dl_menu.add_command(label="⏹️ Stop All", command=self.stop_all)
        dl_menu.add_separator()
        dl_menu.add_command(label="🗑️ Delete Selected", command=self.delete_selected)
        menubar.add_cascade(label="Downloads", menu=dl_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Monitor Clipboard", variable=self.clipboard_monitor_active)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Check for Updates...", command=self.check_updates_dialog)
        help_menu.add_command(label="GitHub Repository Settings...", command=self.show_settings_dialog)
        help_menu.add_separator()
        help_menu.add_command(label="About Dmans", command=lambda: messagebox.showinfo(
            "About Dmans",
            f"Dmans v{version.VERSION} - Fast Download Accelerator\n"
            "High-performance multi-connection segmented downloader.\n"
            "Bilingual, open-source, and free forever."
        ))
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _build_toolbar(self):
        toolbar = ttk.Frame(self, padding=4)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_defs = [
            ("➕ Add URL", self.show_add_download_dialog),
            ("📋 Batch", self.show_batch_download_dialog),
            ("▶️ Resume", self.resume_selected),
            ("⏸️ Pause", self.pause_selected),
            ("▶️ Start Queue", self.start_queue),
            ("⏹️ Stop All", self.stop_all),
            ("🗑️ Delete", self.delete_selected),
        ]

        for text, cmd in btn_defs:
            b = ttk.Button(toolbar, text=text, command=cmd, style="Toolbar.TButton")
            b.pack(side=tk.LEFT, padx=2, pady=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=2)

        cb_check = ttk.Checkbutton(
            toolbar, text="📋 Clipboard", variable=self.clipboard_monitor_active
        )
        cb_check.pack(side=tk.LEFT, padx=4)

        q_check = ttk.Checkbutton(
            toolbar, text="⚡ Auto-Queue", variable=self.queue_active
        )
        q_check.pack(side=tk.LEFT, padx=4)

        ttk.Label(toolbar, text="Max Active:").pack(side=tk.LEFT, padx=(6, 2))
        q_spin = ttk.Spinbox(toolbar, from_=1, to=10, width=3, textvariable=self.max_concurrent_var)
        q_spin.pack(side=tk.LEFT)

    def _build_main_split(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        left_frame = ttk.Frame(paned, width=190)
        paned.add(left_frame, weight=1)

        cat_lbl = ttk.Label(left_frame, text=" Categories", font=("Segoe UI", 9, "bold"), anchor="w")
        cat_lbl.pack(fill=tk.X, padx=4, pady=4)

        self.cat_tree = ttk.Treeview(left_frame, selectmode="browse", show="tree")
        self.cat_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        root_node = self.cat_tree.insert("", "end", text="📁 All Downloads", open=True, values=("All Downloads",))
        self.cat_tree.insert(root_node, "end", text="  ⏳ Unfinished", values=("Unfinished",))
        self.cat_tree.insert(root_node, "end", text="  ✅ Finished", values=("Finished",))
        
        types_node = self.cat_tree.insert("", "end", text="📂 File Types", open=True, values=("All Downloads",))
        self.cat_tree.insert(types_node, "end", text="  📦 Compressed", values=("Compressed",))
        self.cat_tree.insert(types_node, "end", text="  📄 Documents", values=("Documents",))
        self.cat_tree.insert(types_node, "end", text="  🎬 Video", values=("Video",))
        self.cat_tree.insert(types_node, "end", text="  🎵 Music", values=("Music",))
        self.cat_tree.insert(types_node, "end", text="  🖼️ Images", values=("Images",))
        self.cat_tree.insert(types_node, "end", text="  💾 Programs", values=("Programs",))
        self.cat_tree.insert(types_node, "end", text="  🗂️ General", values=("General",))

        self.cat_tree.bind("<<TreeviewSelect>>", self._on_category_select)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=5)

        columns = ("filename", "size", "status", "percent", "speed", "eta", "category", "added")
        self.tree = ttk.Treeview(right_frame, columns=columns, show="headings", selectmode="extended")
        
        self.tree.heading("filename", text="File Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("status", text="Status")
        self.tree.heading("percent", text="Progress")
        self.tree.heading("speed", text="Transfer Rate")
        self.tree.heading("eta", text="Time Left")
        self.tree.heading("category", text="Category")
        self.tree.heading("added", text="Date Added")

        self.tree.column("filename", width=220, anchor="w")
        self.tree.column("size", width=85, anchor="e")
        self.tree.column("status", width=95, anchor="center")
        self.tree.column("percent", width=75, anchor="center")
        self.tree.column("speed", width=95, anchor="e")
        self.tree.column("eta", width=75, anchor="center")
        self.tree.column("category", width=85, anchor="center")
        self.tree.column("added", width=120, anchor="center")

        tree_scroll_y = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(right_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree.bind("<Double-1>", self._on_item_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="🔍 View Details / Segments", command=self._open_selected_details)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="▶️ Resume", command=self.resume_selected)
        self.context_menu.add_command(label="⏸️ Pause", command=self.pause_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📂 Open File", command=self.open_selected_file)
        self.context_menu.add_command(label="📁 Open Folder", command=self.open_selected_folder)
        self.context_menu.add_command(label="📋 Copy Download Link", command=self.copy_selected_url)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="🗑️ Remove from List", command=self.delete_selected)

    def _build_statusbar(self):
        self.statusbar = ttk.Frame(self, relief=tk.SUNKEN, padding=(6, 3))
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_total_lbl = ttk.Label(self.statusbar, text="Total: 0 files | Active: 0")
        self.status_total_lbl.pack(side=tk.LEFT)

        self.status_speed_lbl = ttk.Label(self.statusbar, text="Global Speed: 0.00 MB/s", font=("Segoe UI", 9, "bold"))
        self.status_speed_lbl.pack(side=tk.RIGHT, padx=8)

    def _on_category_select(self, event):
        sel = self.cat_tree.selection()
        if sel:
            item = self.cat_tree.item(sel[0])
            self.selected_category = item.get("values", ["All Downloads"])[0]
            self._refresh_table()

    def _refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        for rec in self.db_records:
            cat = rec.get("category", "General")
            status = rec.get("status", "Queued")

            if self.selected_category == "Unfinished" and status == "Completed":
                continue
            elif self.selected_category == "Finished" and status != "Completed":
                continue
            elif self.selected_category not in ["All Downloads", "Unfinished", "Finished"] and cat != self.selected_category:
                continue

            size_str = self._format_size(rec.get("total_size", 0))
            pct_str = f"{rec.get('percent', 0.0):.1f}%"
            speed_str = f"{rec.get('speed', 0.0) / (1024*1024):.2f} MB/s" if status == "Downloading" else "-"
            eta_str = rec.get("eta", "-") if status == "Downloading" else "-"

            self.tree.insert("", "end", iid=rec["url"], values=(
                rec.get("filename", "unknown"),
                size_str,
                status,
                pct_str,
                speed_str,
                eta_str,
                cat,
                rec.get("added_time", "-")
            ))

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes <= 0:
            return "Unknown"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def show_add_download_dialog(self, initial_url: str = "", filename: str = "", cookies: str = "", referer: str = "", user_agent: str = "", start_now: bool = False, quality: str = "best"):
        if not initial_url:
            try:
                clip = self.clipboard_get().strip()
                if clip.startswith("http://") or clip.startswith("https://"):
                    initial_url = clip
            except Exception:
                pass

        dlg = AddDownloadDialog(
            self,
            initial_url=initial_url,
            filename=filename,
            cookies=cookies,
            referer=referer,
            user_agent=user_agent,
            start_now=start_now,
            quality=quality
        )
        self.wait_window(dlg)
        if dlg.result:
            self._add_task(dlg.result)

    def show_batch_download_dialog(self):
        dlg = AddBatchDialog(self)
        self.wait_window(dlg)
        if dlg.results:
            urls = dlg.results["urls"]
            out_dir = dlg.results["output_dir"]
            conns = dlg.results["connections"]
            added_cnt = 0
            for u in urls:
                if not any(r["url"] == u for r in self.db_records):
                    self._add_task({
                        "url": u,
                        "filename": None,
                        "output_dir": out_dir,
                        "connections": conns,
                        "max_speed_kb": None,
                        "start_now": False
                    })
                    added_cnt += 1
            messagebox.showinfo("Batch Add", f"Added {added_cnt} download(s) to the queue.")

    def _add_task(self, cfg: dict):
        url = cfg["url"]
        for rec in self.db_records:
            if rec["url"] == url:
                messagebox.showwarning("Duplicate", "This URL is already in your download list!")
                return

        rec = {
            "url": url,
            "filename": cfg["filename"],
            "output_dir": cfg["output_dir"],
            "connections": cfg["connections"],
            "max_speed_kb": cfg["max_speed_kb"],
            "cookies": cfg.get("cookies", ""),
            "referer": cfg.get("referer", ""),
            "user_agent": cfg.get("user_agent", ""),
            "quality": cfg.get("quality", "best"),
            "status": "Queued",
            "total_size": 0,
            "downloaded": 0,
            "percent": 0.0,
            "speed": 0.0,
            "eta": "-",
            "category": "General",
            "added_time": time.strftime("%Y-%m-%d %H:%M")
        }
        self.db_records.insert(0, rec)
        self._save_db()
        self._refresh_table()

        if cfg["start_now"]:
            self._start_task(rec)

    def _start_task(self, rec: dict):
        url = rec["url"]
        task = DownloadTask(
            url=url,
            output_dir=rec["output_dir"],
            custom_filename=rec["filename"],
            num_connections=rec["connections"],
            max_speed_kb=rec["max_speed_kb"],
            progress_callback=lambda p: self._on_task_progress(url, p),
            cookies=rec.get("cookies", ""),
            referer=rec.get("referer", ""),
            user_agent=rec.get("user_agent", None),
            quality=rec.get("quality", "best")
        )
        self.downloads[url] = task
        self._open_detail_window(task)

        t = threading.Thread(target=task.start, daemon=True)
        t.start()

    def _on_task_progress(self, url: str, prog: dict):
        self.after(0, self._apply_task_progress, url, prog)

    def _apply_task_progress(self, url: str, prog: dict):
        for rec in self.db_records:
            if rec["url"] == url:
                rec["status"] = prog["status"]
                rec["filename"] = prog["filename"]
                rec["total_size"] = prog["total_size"]
                rec["downloaded"] = prog["downloaded"]
                rec["percent"] = prog["percent"]
                rec["speed"] = prog["speed"]
                rec["category"] = prog["category"]

                if prog["speed"] > 0 and prog["total_size"] > prog["downloaded"]:
                    rem = (prog["total_size"] - prog["downloaded"]) / prog["speed"]
                    rec["eta"] = f"{rem:.1f}s"
                else:
                    rec["eta"] = "-"
                break

        if self.tree.exists(url):
            rec = next(r for r in self.db_records if r["url"] == url)
            self.tree.item(url, values=(
                rec["filename"],
                self._format_size(rec["total_size"]),
                rec["status"],
                f"{rec['percent']:.1f}%",
                f"{rec['speed'] / (1024*1024):.2f} MB/s" if rec["status"] == "Downloading" else "-",
                rec["eta"],
                rec["category"],
                rec["added_time"]
            ))

        if url in self.detail_windows and self.detail_windows[url].winfo_exists():
            self.detail_windows[url].update_progress(prog)

        if prog["is_finished"]:
            self._save_db()
            rec = next((r for r in self.db_records if r["url"] == url), None)
            if rec and not rec.get("_notified"):
                rec["_notified"] = True
                if winsound:
                    try:
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    except Exception:
                        pass
                file_path = os.path.join(rec["output_dir"], rec["filename"])
                DownloadCompleteDialog(self, rec["filename"], file_path, rec["total_size"])

    def resume_selected(self):
        selected = self.tree.selection()
        for url in selected:
            rec = next((r for r in self.db_records if r["url"] == url), None)
            if rec and rec["status"] in ["Paused", "Queued", "Cancelled", "Connecting"]:
                self._start_task(rec)

    def pause_selected(self):
        selected = self.tree.selection()
        for url in selected:
            task = self.downloads.get(url)
            if task:
                task.pause()

    def start_queue(self):
        self.queue_active.set(True)
        active_now = sum(1 for t in self.downloads.values() if t.status in ["Downloading", "Connecting"])
        max_c = max(1, self.max_concurrent_var.get())
        for rec in self.db_records:
            if active_now >= max_c:
                break
            if rec.get("status") in ["Queued", "Paused"]:
                self._start_task(rec)
                active_now += 1

    def stop_all(self):
        for task in self.downloads.values():
            task.pause()

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        if messagebox.askyesno("Confirm Delete", f"Delete {len(selected)} item(s) from the download list?"):
            for url in selected:
                task = self.downloads.get(url)
                if task:
                    task.cancel()
                    del self.downloads[url]
                self.db_records = [r for r in self.db_records if r["url"] != url]
            self._save_db()
            self._refresh_table()

    def _show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def _on_item_double_click(self, event):
        self._open_selected_details()

    def _open_selected_details(self):
        selected = self.tree.selection()
        if not selected:
            return
        url = selected[0]
        task = self.downloads.get(url)
        if task:
            self._open_detail_window(task)
        else:
            rec = next((r for r in self.db_records if r["url"] == url), None)
            if rec:
                messagebox.showinfo("Details", f"File: {rec['filename']}\nURL: {rec['url']}\nStatus: {rec['status']}\nSize: {self._format_size(rec['total_size'])}")

    def _open_detail_window(self, task: DownloadTask):
        url = task.url
        if url in self.detail_windows and self.detail_windows[url].winfo_exists():
            self.detail_windows[url].lift()
            return
        win = DownloadDetailDialog(self, task)
        self.detail_windows[url] = win

    def open_selected_file(self):
        selected = self.tree.selection()
        if not selected:
            return
        rec = next((r for r in self.db_records if r["url"] == selected[0]), None)
        if rec:
            path = os.path.join(rec["output_dir"], rec["filename"])
            if os.path.exists(path):
                os.startfile(path)
            else:
                messagebox.showwarning("Not Found", f"File not found:\n{path}")

    def open_selected_folder(self):
        selected = self.tree.selection()
        if not selected:
            return
        rec = next((r for r in self.db_records if r["url"] == selected[0]), None)
        if rec and os.path.exists(rec["output_dir"]):
            os.startfile(rec["output_dir"])

    def copy_selected_url(self):
        selected = self.tree.selection()
        if selected:
            self.clipboard_clear()
            self.clipboard_append(selected[0])

    def _start_background_monitors(self):
        def monitor_loop():
            while True:
                time.sleep(1.2)
                total_speed = sum(
                    t.current_speed for t in self.downloads.values() if t.status == "Downloading"
                )
                active_count = sum(
                    1 for t in self.downloads.values() if t.status == "Downloading"
                )
                speed_str = f"{total_speed / (1024 * 1024):.2f} MB/s"
                self.after(0, lambda: self._update_global_status(active_count, speed_str))

                if self.clipboard_monitor_active.get():
                    try:
                        clip = self.clipboard_get().strip()
                        if clip != self.last_clipboard_url and (clip.startswith("http://") or clip.startswith("https://")):
                            exts = [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".exe", ".msi", ".pdf", ".mp4", ".mkv", ".mp3", ".apk"]
                            is_media = any(clip.lower().endswith(e) for e in exts) or "/download" in clip.lower()
                            if is_media and not any(r["url"] == clip for r in self.db_records):
                                self.last_clipboard_url = clip
                                self.after(0, lambda u=clip: self._prompt_clipboard_download(u))
                    except Exception:
                        pass

                if self.queue_active.get():
                    active_now = sum(
                        1 for t in self.downloads.values() if t.status in ["Downloading", "Connecting"]
                    )
                    max_concurrent = max(1, self.max_concurrent_var.get())
                    if active_now < max_concurrent:
                        for rec in self.db_records:
                            if rec.get("status") == "Queued" and rec["url"] not in self.downloads:
                                self.after(0, lambda r=rec: self._start_task(r))
                                break

        t = threading.Thread(target=monitor_loop, daemon=True)
        t.start()

    def _update_global_status(self, active_count: int, speed_str: str):
        total_files = len(self.db_records)
        self.status_total_lbl.config(text=f"Total: {total_files} downloads | Active: {active_count}")
        self.status_speed_lbl.config(text=f"Global Speed: {speed_str}")

    def _prompt_clipboard_download(self, url: str):
        if messagebox.askyesno("Dmans - New Download Detected", f"Download link detected in clipboard:\n\n{url}\n\nStart download with Dmans?"):
            self.show_add_download_dialog(initial_url=url)

    def check_updates_dialog(self):
        res = updater.check_for_updates()
        if res.get("has_update"):
            msg = f"New version available: v{res['latest_version']}\n\nNotes:\n{res.get('release_notes')}\n\nOpen GitHub release page?"
            if messagebox.askyesno("Update Available", msg):
                webbrowser.open(res.get("html_url"))
        elif res.get("status") == "no_update":
            messagebox.showinfo("Up to Date", f"You are running the latest version of Dmans (v{version.VERSION}).")
        else:
            messagebox.showinfo("Updates", res.get("error_message") or "Could not check updates.")

    def show_settings_dialog(self):
        cfg = updater.load_config()
        dlg = tk.Toplevel(self)
        dlg.title("Dmans Settings")
        dlg.geometry("400x200")
        dlg.transient(self)
        dlg.grab_set()

        f = ttk.Frame(dlg, padding=12)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="GitHub Repository (username/repo):").pack(anchor=tk.W, pady=4)
        repo_var = tk.StringVar(value=cfg.get("github_repo", "user/dmans"))
        ttk.Entry(f, textvariable=repo_var, width=35).pack(fill=tk.X, pady=4)

        def save():
            cfg["github_repo"] = repo_var.get().strip()
            updater.save_config(cfg)
            dlg.destroy()
            messagebox.showinfo("Settings", "Settings saved successfully!")

        ttk.Button(f, text="Save Settings", command=save).pack(side=tk.RIGHT, pady=10)


class AddBatchDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Batch Add URLs - Dmans")
        self.geometry("560x380")
        self.transient(parent)
        self.grab_set()

        self.results = None
        self.dir_var = tk.StringVar(value=os.path.abspath("."))
        self.conn_var = tk.IntVar(value=8)

        self._build_ui()

    def _build_ui(self):
        f = ttk.Frame(self, padding=12)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="Paste URLs (one per line):", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=2)
        self.text_area = tk.Text(f, height=10, width=50, font=("Consolas", 9))
        self.text_area.pack(fill=tk.BOTH, expand=True, pady=4)

        opt_frame = ttk.Frame(f)
        opt_frame.pack(fill=tk.X, pady=6)

        ttk.Label(opt_frame, text="Save To:").grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Entry(opt_frame, textvariable=self.dir_var).grid(row=0, column=1, sticky=tk.EW, padx=4)
        ttk.Button(opt_frame, text="Browse...", command=self._browse).grid(row=0, column=2, padx=4)

        ttk.Label(opt_frame, text="Connections per file:").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(opt_frame, textvariable=self.conn_var, values=[1, 2, 4, 8, 16], width=6, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)

        opt_frame.columnconfigure(1, weight=1)

        btn_box = ttk.Frame(f)
        btn_box.pack(fill=tk.X, pady=6)

        ttk.Button(btn_box, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_box, text="Add All to Queue", command=self._done).pack(side=tk.RIGHT, padx=4)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _done(self):
        raw = self.text_area.get("1.0", tk.END).strip()
        lines = [line.strip() for line in raw.splitlines() if line.strip().startswith("http://") or line.strip().startswith("https://")]
        if not lines:
            messagebox.showerror("Error", "No valid URLs found in the text box.")
            return

        self.results = {
            "urls": lines,
            "output_dir": self.dir_var.get(),
            "connections": self.conn_var.get()
        }
        self.destroy()


class AddDownloadDialog(tk.Toplevel):
    def __init__(self, parent, initial_url: str = "", filename: str = "", cookies: str = "", referer: str = "", user_agent: str = "", start_now: bool = False, quality: str = "best"):
        super().__init__(parent)
        self.title("Enter URL to Download - Dmans")
        self.geometry("560x340")
        self.resizable(False, False)
        self.transient(parent)
        force_bring_to_front(self)
        self.grab_set()

        self.result = None
        self.cookies = cookies or ""
        self.referer = referer or ""
        self.user_agent = user_agent or ""
        self.url_var = tk.StringVar(value=initial_url)
        self.dir_var = tk.StringVar(value=os.path.abspath("."))
        self.file_var = tk.StringVar(value=filename)
        self.conn_var = tk.IntVar(value=8)
        self.speed_var = tk.StringVar(value="Unlimited")

        qual_label_map = {
            "1080p": "1080p (Full HD)",
            "720p": "720p (HD)",
            "480p": "480p (Standard)",
            "360p": "360p (Fast)",
            "audio": "Audio Only (MP3/M4A)",
            "best": "Best Available (Auto)"
        }
        init_qual_label = qual_label_map.get(quality, "Best Available (Auto)")
        self.quality_var = tk.StringVar(value=init_qual_label)

        if initial_url and not filename:
            self.file_var.set(self._guess_filename(initial_url))
            if any(k in initial_url.lower() for k in ["youtube.com", "youtu.be", "tiktok.com"]):
                def _fetch_title():
                    try:
                        import yt_dlp
                        ydl = yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True, 'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'web']}}})
                        info = ydl.extract_info(initial_url, download=False)
                        if info and info.get('title'):
                            clean = "".join(c for c in info['title'] if c.isalnum() or c in " ._- ()")
                            ext = info.get('ext', 'mp4')
                            self.after(0, lambda: self.file_var.set(f"{clean}.{ext}"))
                    except Exception:
                        pass
                threading.Thread(target=_fetch_title, daemon=True).start()

        if not filename:
            self.url_var.trace_add("write", lambda *_: self.file_var.set(self._guess_filename(self.url_var.get())))
        self._build_ui()

    def _guess_filename(self, url: str) -> str:
        try:
            parsed = urllib.parse.urlparse(url)
            name = os.path.basename(parsed.path)
            return urllib.parse.unquote(name) if name else ""
        except Exception:
            return ""

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}
        f = ttk.Frame(self, padding=12)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="Address (URL):").grid(row=0, column=0, sticky=tk.W, **pad)
        url_ent = ttk.Entry(f, textvariable=self.url_var, width=45)
        url_ent.grid(row=0, column=1, columnspan=2, sticky=tk.EW, **pad)
        url_ent.focus_set()

        ttk.Label(f, text="File Name:").grid(row=1, column=0, sticky=tk.W, **pad)
        ttk.Entry(f, textvariable=self.file_var).grid(row=1, column=1, columnspan=2, sticky=tk.EW, **pad)

        ttk.Label(f, text="Save To:").grid(row=2, column=0, sticky=tk.W, **pad)
        ttk.Entry(f, textvariable=self.dir_var).grid(row=2, column=1, sticky=tk.EW, **pad)
        ttk.Button(f, text="Browse...", command=self._browse).grid(row=2, column=2, **pad)

        ttk.Label(f, text="Connections:").grid(row=3, column=0, sticky=tk.W, **pad)
        conn_cb = ttk.Combobox(f, textvariable=self.conn_var, values=[1, 2, 4, 8, 16, 24, 32], width=8, state="readonly")
        conn_cb.grid(row=3, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text="Speed Limiter:").grid(row=4, column=0, sticky=tk.W, **pad)
        speed_cb = ttk.Combobox(f, textvariable=self.speed_var, values=["Unlimited", "500 KB/s", "1 MB/s", "2 MB/s", "5 MB/s"], width=12, state="readonly")
        speed_cb.grid(row=4, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text="Quality / Format:").grid(row=5, column=0, sticky=tk.W, **pad)
        qual_cb = ttk.Combobox(
            f,
            textvariable=self.quality_var,
            values=[
                "Best Available (Auto)",
                "1080p (Full HD)",
                "720p (HD)",
                "480p (Standard)",
                "360p (Fast)",
                "Audio Only (MP3/M4A)"
            ],
            width=22,
            state="readonly"
        )
        qual_cb.grid(row=5, column=1, sticky=tk.W, **pad)

        f.columnconfigure(1, weight=1)

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="Download Later", command=lambda: self._done(False)).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_box, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=6)
        ttk.Button(btn_box, text="OK / Download Now", command=lambda: self._done(True)).pack(side=tk.RIGHT, padx=6)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _done(self, start_now: bool):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please provide a valid URL!")
            return

        speed_map = {"Unlimited": None, "500 KB/s": 500, "1 MB/s": 1024, "2 MB/s": 2048, "5 MB/s": 5120}

        qual_rev_map = {
            "1080p (Full HD)": "1080p",
            "720p (HD)": "720p",
            "480p (Standard)": "480p",
            "360p (Fast)": "360p",
            "Audio Only (MP3/M4A)": "audio",
            "Best Available (Auto)": "best"
        }
        chosen_quality = qual_rev_map.get(self.quality_var.get(), "best")

        self.result = {
            "url": url,
            "filename": self.file_var.get().strip() or None,
            "output_dir": self.dir_var.get(),
            "connections": self.conn_var.get(),
            "max_speed_kb": speed_map.get(self.speed_var.get()),
            "start_now": start_now,
            "cookies": self.cookies,
            "referer": self.referer,
            "user_agent": self.user_agent,
            "quality": chosen_quality
        }
        self.destroy()


class DownloadDetailDialog(tk.Toplevel):
    def __init__(self, parent, task: DownloadTask):
        super().__init__(parent)
        self.task = task
        self.title(f"{task.filename} - Dmans")
        self.geometry("640x480")
        self.minsize(580, 420)

        self._build_ui()

    def _build_ui(self):
        top_f = ttk.Frame(self, padding=10)
        top_f.pack(fill=tk.X)

        self.lbl_status = ttk.Label(top_f, text=f"Status: {self.task.status}", font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(anchor=tk.W)

        self.lbl_file = ttk.Label(top_f, text=f"File: {self.task.filename}", font=("Segoe UI", 9))
        self.lbl_file.pack(anchor=tk.W, pady=2)

        self.lbl_stats = ttk.Label(top_f, text="Size: Calculating... | Speed: 0.00 MB/s | Time Left: Calculating...", font=("Segoe UI", 9))
        self.lbl_stats.pack(anchor=tk.W, pady=2)

        self.lbl_resume = ttk.Label(top_f, text="Resume capability: Yes", font=("Segoe UI", 8), foreground="#007700")
        self.lbl_resume.pack(anchor=tk.W, pady=2)

        self.overall_bar = ttk.Progressbar(self, orient=tk.HORIZONTAL, mode="determinate")
        self.overall_bar.pack(fill=tk.X, padx=12, pady=6)

        seg_frame = ttk.LabelFrame(self, text=" Dmans Dynamic Connection Segments (Real-Time Threads) ", padding=6)
        seg_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        self.canvas = tk.Canvas(seg_frame, bg="#FFFFFF", highlightthickness=1, highlightbackground="#CCCCCC")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)

        self.btn_pause = ttk.Button(btn_box, text="Pause", command=self._toggle_pause)
        self.btn_pause.pack(side=tk.LEFT, padx=6)

        self.btn_cancel = ttk.Button(btn_box, text="Cancel", command=self._cancel)
        self.btn_cancel.pack(side=tk.LEFT, padx=6)

        ttk.Button(btn_box, text="Close Window", command=self.destroy).pack(side=tk.RIGHT, padx=6)

    def _toggle_pause(self):
        if self.task.is_paused:
            self.task.is_paused = False
            self.btn_pause.config(text="Pause")
            t = threading.Thread(target=self.task.start, daemon=True)
            t.start()
        else:
            self.task.pause()
            self.btn_pause.config(text="Resume")

    def _cancel(self):
        self.task.cancel()
        self.destroy()

    def update_progress(self, prog: dict):
        pct = prog["percent"]
        tot_mb = prog["total_size"] / (1024 * 1024)
        dl_mb = prog["downloaded"] / (1024 * 1024)
        spd_mb = prog["speed"] / (1024 * 1024)

        eta = "N/A"
        if prog["speed"] > 0 and prog["total_size"] > prog["downloaded"]:
            eta = f"{(prog['total_size'] - prog['downloaded']) / prog['speed']:.1f}s"

        self.overall_bar["value"] = pct
        self.lbl_status.config(text=f"Status: {prog['status']} ({pct:.1f}%)")
        self.lbl_stats.config(text=f"Downloaded: {dl_mb:.2f} / {tot_mb:.2f} MB | Speed: {spd_mb:.2f} MB/s | Time Left: {eta}")

        if prog["is_finished"]:
            self.lbl_status.config(text="Status: Download Complete!", foreground="#008800")
            self.btn_pause.config(state=tk.DISABLED)

        self._render_canvas_segments(prog["segments"], prog["total_size"])

    def _render_canvas_segments(self, segments: list, total_size: int):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 10 or h <= 10 or not segments:
            return

        row_h = min(28, max(18, (h - 20) // len(segments)))
        y_offset = 10

        for i, seg in enumerate(segments):
            y1 = y_offset + (i * row_h)
            y2 = y1 + row_h - 4

            self.canvas.create_rectangle(10, y1, w - 80, y2, fill="#E8ECEF", outline="#B0B8C0")

            seg_tot = seg["end"] - seg["start"] + 1
            seg_dl = seg["current"] - seg["start"]
            pct = (seg_dl / seg_tot) if seg_tot > 0 else 0.0
            fill_w = 10 + int((w - 90) * pct)

            color = "#0284C7" if seg["status"] == "DOWNLOADING" else ("#16A34A" if seg["status"] == "COMPLETED" else "#EAB308")
            if fill_w > 10:
                self.canvas.create_rectangle(10, y1, fill_w, y2, fill=color, outline="")

            lbl_text = f"Thread #{seg['seg_id']+1}: {pct*100:.0f}%"
            self.canvas.create_text(w - 70, (y1 + y2) // 2, text=lbl_text, font=("Segoe UI", 8), anchor="w")


class DownloadCompleteDialog(tk.Toplevel):
    def __init__(self, parent, filename: str, filepath: str, filesize: int):
        super().__init__(parent)
        self.title("Download Complete - Dmans")
        self.geometry("460x170")
        self.resizable(False, False)
        self.filepath = filepath
        self.transient(parent)

        f = ttk.Frame(self, padding=14)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="Download Finished Successfully!", font=("Segoe UI", 10, "bold"), foreground="#16A34A").pack(anchor=tk.W, pady=2)
        ttk.Label(f, text=f"File: {filename}", font=("Segoe UI", 9)).pack(anchor=tk.W, pady=2)
        ttk.Label(f, text=f"Saved To: {filepath}", font=("Segoe UI", 8), foreground="#555555").pack(anchor=tk.W, pady=2)

        btn_box = ttk.Frame(f, padding=(0, 10, 0, 0))
        btn_box.pack(fill=tk.X, pady=6)

        ttk.Button(btn_box, text="Open File", command=self._open_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_box, text="Open Folder", command=self._open_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_box, text="Close", command=self.destroy).pack(side=tk.RIGHT, padx=4)

    def _open_file(self):
        if os.path.exists(self.filepath):
            os.startfile(self.filepath)
        self.destroy()

    def _open_folder(self):
        folder = os.path.dirname(self.filepath)
        if os.path.exists(folder):
            os.startfile(folder)
        self.destroy()


if __name__ == "__main__":
    try:
        app = DmansApp()
        app.mainloop()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            log_dir = get_app_dir()
            with open(os.path.join(log_dir, "dmans_crash.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Error starting Dmans:\n{tb}", "Dmans Startup Error", 0x10)
        except Exception:
            pass

