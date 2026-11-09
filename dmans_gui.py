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
from dmans_engine import (
    DownloadTask,
    extract_stream_breakdown,
    detect_file_category,
    resolve_category_path
)

CAT_ICON_MAP = {
    "All Downloads": "📁 All Downloads",
    "Unfinished": "⏳ Unfinished",
    "Finished": "✅ Finished",
    "Compressed": "📦 Compressed",
    "Documents": "📄 Documents",
    "Video": "🎬 Video",
    "Music": "🎵 Music",
    "Images": "🖼️ Images",
    "Programs": "💾 Programs",
    "General": "🗂️ General",
}

# Bulletproof stdout/stderr wrapper for PyInstaller windowed mode (prevents [WinError 6] The handle is invalid)
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
        user32 = ctypes.windll.user32
        child_hwnd = win.winfo_id()
        hwnd = user32.GetParent(child_hwnd)
        if not hwnd:
            try:
                hwnd = int(win.wm_frame(), 16)
            except Exception:
                hwnd = child_hwnd

        fore_hwnd = user32.GetForegroundWindow()
        if fore_hwnd:
            fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
            curr_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            if fore_thread != curr_thread:
                user32.AttachThreadInput(curr_thread, fore_thread, True)
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                user32.AttachThreadInput(curr_thread, fore_thread, False)
            else:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
        else:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

        win.after(1500, lambda: win.attributes("-topmost", False))
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

        self.configure(bg="#F1F5F9")
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=(6, 6))
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=28)
        self.style.configure("TButton", font=("Segoe UI", 9), padding=(6, 3))
        self.style.configure("Toolbar.TButton", font=("Segoe UI", 9), padding=(6, 3))
        self.style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"), padding=(8, 4))

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
        start_now = data.get("start_now", True)
        quality = data.get("quality", "best")

        if winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        self.deiconify()
        self.lift()
        force_bring_to_front(self)

        app_cfg = updater.load_config()
        base_dir = app_cfg.get("download_dir") or updater.get_default_download_dir()
        auto_cat = app_cfg.get("auto_categorize", True)

        cat = detect_file_category(filename=filename, url=url)
        if quality == "audio":
            cat = "Music"
        target_dir = resolve_category_path(base_dir, cat, auto_cat)

        if not filename:
            try:
                parsed = urllib.parse.urlparse(url)
                name = os.path.basename(parsed.path)
                filename = urllib.parse.unquote(name) if name else ""
            except Exception:
                filename = ""
            if not filename:
                filename = "download"

        show_dialog = app_cfg.get("show_download_dialog", True)

        # Check if this exact URL is already actively downloading
        existing_task = self.downloads.get(url)
        if existing_task and existing_task.status in ["Downloading", "Finalizing"]:
            self._open_detail_window(existing_task)
            return

        if show_dialog:
            self.show_add_download_dialog(
                initial_url=url,
                filename=filename,
                cookies=cookies,
                referer=referer,
                user_agent=user_agent,
                start_now=True,
                quality=quality
            )
        else:
            cfg = {
                "url": url,
                "filename": filename,
                "output_dir": target_dir,
                "category": cat,
                "connections": app_cfg.get("default_connections", 8),
                "max_speed_kb": None,
                "cookies": cookies,
                "referer": referer,
                "user_agent": user_agent,
                "quality": quality,
                "start_now": True
            }
            # Remove any stale record of this URL so it cleanly starts
            self.db_records = [r for r in self.db_records if r["url"] != url]
            self._add_task(cfg)

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
        dl_menu.add_command(label="📁 Open Downloads Folder", command=self.open_downloads_folder)
        dl_menu.add_command(label="⚙️ Settings & Options...", command=self.show_settings_dialog)
        dl_menu.add_separator()
        dl_menu.add_command(label="🗑️ Delete Selected", command=self.delete_selected)
        menubar.add_cascade(label="Downloads", menu=dl_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Monitor Clipboard", variable=self.clipboard_monitor_active)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Check for Updates...", command=self.check_updates_dialog)
        help_menu.add_command(label="⚙️ Settings / Preferences...", command=self.show_settings_dialog)
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
        toolbar = ttk.Frame(self, padding=(6, 4))
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

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        b_folder = ttk.Button(toolbar, text="📁 Open Folder", command=self.open_downloads_folder, style="Toolbar.TButton")
        b_folder.pack(side=tk.LEFT, padx=2, pady=2)

        b_settings = ttk.Button(toolbar, text="⚙️ Settings", command=self.show_settings_dialog, style="Toolbar.TButton")
        b_settings.pack(side=tk.LEFT, padx=2, pady=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

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

        left_frame = ttk.Frame(paned, width=200)
        paned.add(left_frame, weight=1)

        cat_lbl = ttk.Label(left_frame, text=" Categories", font=("Segoe UI", 9, "bold"), anchor="w")
        cat_lbl.pack(fill=tk.X, padx=4, pady=4)

        self.cat_tree = ttk.Treeview(left_frame, selectmode="browse", show="tree")
        self.cat_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        root_node = self.cat_tree.insert("", "end", text="📁 All Downloads", open=True, values=("All Downloads",))
        unfin_node = self.cat_tree.insert(root_node, "end", text="  ⏳ Unfinished", values=("Unfinished",))
        fin_node = self.cat_tree.insert(root_node, "end", text="  ✅ Finished", values=("Finished",))
        
        types_node = self.cat_tree.insert("", "end", text="📂 File Types", open=True, values=("All Downloads",))
        comp_node = self.cat_tree.insert(types_node, "end", text="  📦 Compressed", values=("Compressed",))
        doc_node = self.cat_tree.insert(types_node, "end", text="  📄 Documents", values=("Documents",))
        video_node = self.cat_tree.insert(types_node, "end", text="  🎬 Video", values=("Video",))
        music_node = self.cat_tree.insert(types_node, "end", text="  🎵 Music", values=("Music",))
        img_node = self.cat_tree.insert(types_node, "end", text="  🖼️ Images", values=("Images",))
        prog_node = self.cat_tree.insert(types_node, "end", text="  💾 Programs", values=("Programs",))
        gen_node = self.cat_tree.insert(types_node, "end", text="  🗂️ General", values=("General",))

        self.cat_nodes = {
            "All Downloads": root_node,
            "Unfinished": unfin_node,
            "Finished": fin_node,
            "Compressed": comp_node,
            "Documents": doc_node,
            "Video": video_node,
            "Music": music_node,
            "Images": img_node,
            "Programs": prog_node,
            "General": gen_node,
        }

        self.cat_tree.bind("<<TreeviewSelect>>", self._on_category_select)

        self.cat_menu = tk.Menu(self, tearoff=0)
        self.cat_menu.add_command(label="📁 Open Category Folder in Explorer", command=self.open_downloads_folder)
        self.cat_tree.bind("<Button-3>", self._show_cat_context_menu)

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
        self.tree.column("category", width=105, anchor="center")
        self.tree.column("added", width=120, anchor="center")

        # Treeview row & status tags
        self.tree.tag_configure("even", background="#FFFFFF")
        self.tree.tag_configure("odd", background="#F8FAFC")
        self.tree.tag_configure("status_completed", foreground="#16A34A")
        self.tree.tag_configure("status_downloading", foreground="#0284C7")
        self.tree.tag_configure("status_paused", foreground="#D97706")
        self.tree.tag_configure("status_error", foreground="#DC2626")
        self.tree.tag_configure("status_queued", foreground="#64748B")

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

    def _show_cat_context_menu(self, event):
        item = self.cat_tree.identify_row(event.y)
        if item:
            self.cat_tree.selection_set(item)
            item_data = self.cat_tree.item(item)
            self.selected_category = item_data.get("values", ["All Downloads"])[0]
            self._refresh_table()
            self.cat_menu.tk_popup(event.x_root, event.y_root)

    def _build_statusbar(self):
        self.statusbar = ttk.Frame(self, relief=tk.FLAT, padding=(8, 4))
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_total_lbl = ttk.Label(self.statusbar, text="Total: 0 files | Active: 0", font=("Segoe UI", 9))
        self.status_total_lbl.pack(side=tk.LEFT)

        ttk.Separator(self.statusbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.status_folder_lbl = ttk.Label(
            self.statusbar,
            text="📁 Downloads Folder",
            font=("Segoe UI", 9, "underline"),
            cursor="hand2",
            foreground="#0369a1"
        )
        self.status_folder_lbl.pack(side=tk.LEFT)
        self.status_folder_lbl.bind("<Button-1>", lambda _: self.open_downloads_folder())

        self.status_speed_lbl = ttk.Label(self.statusbar, text="⚡ Global Speed: 0.00 MB/s", font=("Segoe UI", 9, "bold"), foreground="#0284c7")
        self.status_speed_lbl.pack(side=tk.RIGHT, padx=8)

        self._update_statusbar_folder_label()

    def _update_statusbar_folder_label(self):
        cfg = updater.load_config()
        base_dir = cfg.get("download_dir") or updater.get_default_download_dir()
        short_dir = base_dir if len(base_dir) <= 35 else f"...{base_dir[-32:]}"
        auto_str = " (Auto-Sort ON)" if cfg.get("auto_categorize", True) else ""
        if hasattr(self, "status_folder_lbl"):
            self.status_folder_lbl.config(text=f"📁 Save: {short_dir}{auto_str}")

    def open_downloads_folder(self):
        cfg = updater.load_config()
        base_dir = cfg.get("download_dir") or updater.get_default_download_dir()
        if self.selected_category in ["Video", "Music", "Compressed", "Documents", "Programs", "Images"]:
            cat_dir = os.path.join(base_dir, self.selected_category)
            if os.path.exists(cat_dir):
                os.startfile(cat_dir)
                return
        if os.path.exists(base_dir):
            os.startfile(base_dir)
        else:
            try:
                os.makedirs(base_dir, exist_ok=True)
                os.startfile(base_dir)
            except Exception:
                pass

    def _on_category_select(self, event):
        sel = self.cat_tree.selection()
        if sel:
            item = self.cat_tree.item(sel[0])
            self.selected_category = item.get("values", ["All Downloads"])[0]
            self._refresh_table()

    def _refresh_category_counts(self):
        if not hasattr(self, "cat_nodes"):
            return
        counts = {
            "All Downloads": len(self.db_records),
            "Unfinished": sum(1 for r in self.db_records if r.get("status") != "Completed"),
            "Finished": sum(1 for r in self.db_records if r.get("status") == "Completed"),
            "Compressed": sum(1 for r in self.db_records if r.get("category") == "Compressed"),
            "Documents": sum(1 for r in self.db_records if r.get("category") == "Documents"),
            "Video": sum(1 for r in self.db_records if r.get("category") == "Video"),
            "Music": sum(1 for r in self.db_records if r.get("category") == "Music"),
            "Images": sum(1 for r in self.db_records if r.get("category") == "Images"),
            "Programs": sum(1 for r in self.db_records if r.get("category") == "Programs"),
            "General": sum(1 for r in self.db_records if r.get("category") == "General"),
        }
        
        node_labels = {
            "All Downloads": f"📁 All Downloads ({counts['All Downloads']})",
            "Unfinished": f"  ⏳ Unfinished ({counts['Unfinished']})",
            "Finished": f"  ✅ Finished ({counts['Finished']})",
            "Compressed": f"  📦 Compressed ({counts['Compressed']})",
            "Documents": f"  📄 Documents ({counts['Documents']})",
            "Video": f"  🎬 Video ({counts['Video']})",
            "Music": f"  🎵 Music ({counts['Music']})",
            "Images": f"  🖼️ Images ({counts['Images']})",
            "Programs": f"  💾 Programs ({counts['Programs']})",
            "General": f"  🗂️ General ({counts['General']})",
        }
        
        for cat_key, node_id in self.cat_nodes.items():
            if self.cat_tree.exists(node_id):
                self.cat_tree.item(node_id, text=node_labels[cat_key])

    def _refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        idx = 0
        for rec in self.db_records:
            cat = rec.get("category", "General")
            status = rec.get("status", "Queued")

            if self.selected_category == "Unfinished" and status == "Completed":
                continue
            elif self.selected_category == "Finished" and status != "Completed":
                continue
            elif self.selected_category not in ["All Downloads", "Unfinished", "Finished"] and cat != self.selected_category:
                continue

            idx += 1
            stripe_tag = "even" if idx % 2 == 0 else "odd"
            status_tag = f"status_{status.lower()}"

            size_str = self._format_size(rec.get("total_size", 0))
            pct_str = f"{rec.get('percent', 0.0):.1f}%"
            speed_str = f"{rec.get('speed', 0.0) / (1024*1024):.2f} MB/s" if status == "Downloading" else "-"
            eta_str = rec.get("eta", "-") if status == "Downloading" else "-"
            cat_display = CAT_ICON_MAP.get(cat, cat)

            self.tree.insert("", "end", iid=rec["url"], values=(
                rec.get("filename", "unknown"),
                size_str,
                status,
                pct_str,
                speed_str,
                eta_str,
                cat_display,
                rec.get("added_time", "-")
            ), tags=(stripe_tag, status_tag))

        self._refresh_category_counts()

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
            app_cfg = updater.load_config()
            auto_cat = app_cfg.get("auto_categorize", True)
            added_cnt = 0
            for u in urls:
                if not any(r["url"] == u for r in self.db_records):
                    cat = detect_file_category(url=u)
                    target_dir = resolve_category_path(out_dir, cat, auto_cat)
                    self._add_task({
                        "url": u,
                        "filename": None,
                        "output_dir": target_dir,
                        "category": cat,
                        "connections": conns,
                        "max_speed_kb": None,
                        "start_now": False
                    })
                    added_cnt += 1
            messagebox.showinfo("Batch Add", f"Added {added_cnt} download(s) to the queue.")

    def _add_task(self, cfg: dict):
        url = cfg["url"]
        for rec in list(self.db_records):
            if rec["url"] == url:
                if rec.get("status") in ["Downloading", "Finalizing"]:
                    task = self.downloads.get(url)
                    if task:
                        self._open_detail_window(task)
                    return
                self.db_records.remove(rec)
                break

        cat = cfg.get("category") or detect_file_category(filename=cfg.get("filename", ""), url=url)
        if cfg.get("quality") == "audio":
            cat = "Music"

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
            "category": cat,
            "added_time": time.strftime("%Y-%m-%d %H:%M")
        }
        # Ensure sidebar resets to All Downloads so newly added downloads are never hidden
        self.selected_category = "All Downloads"
        if hasattr(self, "cat_nodes") and "All Downloads" in self.cat_nodes:
            try:
                self.cat_tree.selection_set(self.cat_nodes["All Downloads"])
            except Exception:
                pass

        self.db_records.insert(0, rec)
        self._save_db()
        self._refresh_table()

        if self.tree.exists(url):
            try:
                self.tree.selection_set(url)
                self.tree.see(url)
            except Exception:
                pass

        if cfg["start_now"]:
            self._start_task(rec)

    def _start_task(self, rec: dict):
        url = rec["url"]
        app_cfg = updater.load_config()
        base_dir = app_cfg.get("download_dir") or updater.get_default_download_dir()
        auto_cat = app_cfg.get("auto_categorize", True)

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
            quality=rec.get("quality", "best"),
            auto_categorize=auto_cat,
            base_download_dir=base_dir
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
                if prog.get("output_dir"):
                    rec["output_dir"] = prog["output_dir"]
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
            rec = next((r for r in self.db_records if r["url"] == url), None)
            if rec:
                cat_display = CAT_ICON_MAP.get(rec["category"], rec["category"])
                current_tags = self.tree.item(url, "tags") or ("even",)
                stripe = current_tags[0] if current_tags else "even"
                status_tag = f"status_{rec['status'].lower()}"
                self.tree.item(url, values=(
                    rec["filename"],
                    self._format_size(rec["total_size"]),
                    rec["status"],
                    f"{rec['percent']:.1f}%",
                    f"{rec['speed'] / (1024*1024):.2f} MB/s" if rec["status"] == "Downloading" else "-",
                    rec["eta"],
                    cat_display,
                    rec["added_time"]
                ), tags=(stripe, status_tag))
        else:
            self._refresh_table()

        if url in self.detail_windows and self.detail_windows[url].winfo_exists():
            self.detail_windows[url].update_progress(prog)

        if prog["is_finished"]:
            self._save_db()
            self._refresh_category_counts()
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
            force_bring_to_front(self.detail_windows[url])
            return
        win = DownloadDetailDialog(self, task)
        self.detail_windows[url] = win
        force_bring_to_front(win)

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
        dlg.title("Dmans Options & Settings")
        dlg.geometry("560x430")
        dlg.minsize(520, 390)
        dlg.transient(self)
        dlg.grab_set()

        dlg.update_idletasks()
        pw = self.winfo_width()
        ph = self.winfo_height()
        px = self.winfo_rootx()
        py = self.winfo_rooty()
        w, h = 560, 430
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        main_frame = ttk.Frame(dlg, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # TAB 1: General & Save Path
        tab_general = ttk.Frame(notebook, padding=12)
        notebook.add(tab_general, text="📁 Save Path & Sorting")

        folder_group = ttk.LabelFrame(tab_general, text=" Default Download Directory ", padding=10)
        folder_group.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(folder_group, text="Main folder where files will be stored:").pack(anchor=tk.W, pady=(0, 4))
        
        path_box = ttk.Frame(folder_group)
        path_box.pack(fill=tk.X, pady=2)
        
        dir_var = tk.StringVar(value=cfg.get("download_dir") or updater.get_default_download_dir())
        dir_entry = ttk.Entry(path_box, textvariable=dir_var)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        def _browse_dir():
            d = filedialog.askdirectory(initialdir=dir_var.get(), parent=dlg)
            if d:
                dir_var.set(os.path.normpath(d))

        def _open_current_dir():
            d = dir_var.get().strip()
            if os.path.exists(d):
                os.startfile(d)
            else:
                try:
                    os.makedirs(d, exist_ok=True)
                    os.startfile(d)
                except Exception as err:
                    messagebox.showerror("Error", f"Could not open directory: {err}", parent=dlg)

        ttk.Button(path_box, text="Browse...", command=_browse_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(path_box, text="Open Folder", command=_open_current_dir).pack(side=tk.LEFT, padx=2)

        cat_group = ttk.LabelFrame(tab_general, text=" Auto-Categorize & Subfolders (IDM-Style) ", padding=10)
        cat_group.pack(fill=tk.X, pady=(0, 10))

        auto_cat_var = tk.BooleanVar(value=cfg.get("auto_categorize", True))
        ttk.Checkbutton(
            cat_group,
            text="Automatically sort files into category subfolders (Video, Music, Documents, etc.)",
            variable=auto_cat_var
        ).pack(anchor=tk.W, pady=2)

        sub_info = ttk.Label(
            cat_group,
            text="• Video files & YouTube: \\Video\n• Audio & Music: \\Music\n• Compressed (.zip, .rar): \\Compressed\n• Documents (.pdf, .docx): \\Documents\n• Programs & Installers: \\Programs\n• Images & Photos: \\Images",
            font=("Segoe UI", 8),
            foreground="#475569"
        )
        sub_info.pack(anchor=tk.W, padx=20, pady=(4, 0))

        prompt_group = ttk.LabelFrame(tab_general, text=" Download Destination & Confirmation ", padding=10)
        prompt_group.pack(fill=tk.X, pady=(0, 10))

        show_dialog_var = tk.BooleanVar(value=cfg.get("show_download_dialog", True))
        ttk.Checkbutton(
            prompt_group,
            text="Show download confirmation dialog before starting (Choose save folder & filename)",
            variable=show_dialog_var
        ).pack(anchor=tk.W, pady=2)

        prompt_desc = ttk.Label(
            prompt_group,
            text="• Enabled: Dmans will pop up a dialog so you can choose where to save each file or change its name.\n• Disabled: Dmans will start downloading immediately using the default/category folder.",
            font=("Segoe UI", 8),
            foreground="#475569"
        )
        prompt_desc.pack(anchor=tk.W, padx=20, pady=(2, 0))

        # TAB 2: Performance
        tab_network = ttk.Frame(notebook, padding=12)
        notebook.add(tab_network, text="⚡ Performance")

        perf_group = ttk.LabelFrame(tab_network, text=" Download Accelerator Engine ", padding=10)
        perf_group.pack(fill=tk.X, pady=(0, 10))

        perf_grid = ttk.Frame(perf_group)
        perf_grid.pack(fill=tk.X, pady=4)

        ttk.Label(perf_grid, text="Default Connections per File:").grid(row=0, column=0, sticky=tk.W, pady=6)
        conn_var = tk.IntVar(value=cfg.get("default_connections", 8))
        conn_combo = ttk.Combobox(perf_grid, textvariable=conn_var, values=[1, 2, 4, 8, 16, 24, 32], width=6, state="readonly")
        conn_combo.grid(row=0, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Label(perf_grid, text="Max Concurrent Active Downloads:").grid(row=1, column=0, sticky=tk.W, pady=6)
        max_active_var = tk.IntVar(value=cfg.get("max_concurrent_downloads", 2))
        active_spin = ttk.Spinbox(perf_grid, from_=1, to=10, width=5, textvariable=max_active_var)
        active_spin.grid(row=1, column=1, sticky=tk.W, padx=10, pady=6)

        # TAB 3: Updates & About
        tab_updates = ttk.Frame(notebook, padding=12)
        notebook.add(tab_updates, text="ℹ️ Updates & About")

        repo_group = ttk.LabelFrame(tab_updates, text=" GitHub Repository Updates ", padding=10)
        repo_group.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(repo_group, text="Repository (owner/repo):").pack(anchor=tk.W, pady=(0, 4))
        repo_var = tk.StringVar(value=cfg.get("github_repo", version.DEFAULT_GITHUB_REPO))
        ttk.Entry(repo_group, textvariable=repo_var).pack(fill=tk.X, pady=2)

        auto_up_var = tk.BooleanVar(value=cfg.get("auto_check_updates", True))
        ttk.Checkbutton(repo_group, text="Automatically check for updates on startup", variable=auto_up_var).pack(anchor=tk.W, pady=6)

        btn_check = ttk.Button(repo_group, text="🔍 Check for Updates Now", command=lambda: (dlg.destroy(), self.check_updates_dialog()))
        btn_check.pack(anchor=tk.W, pady=4)

        about_lbl = ttk.Label(
            tab_updates,
            text=f"Dmans v{version.VERSION} - Fast Download Accelerator\nEngine: Multi-connection Segmented Downloader with yt-dlp & FFmpeg integration.",
            font=("Segoe UI", 9),
            foreground="#64748B"
        )
        about_lbl.pack(anchor=tk.W, pady=10)

        # Bottom buttons
        btn_bar = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        def _save_all():
            new_dir = dir_var.get().strip()
            if not new_dir:
                new_dir = updater.get_default_download_dir()
            try:
                os.makedirs(new_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Invalid Path", f"Could not create folder: {e}", parent=dlg)
                return

            cfg["download_dir"] = os.path.normpath(new_dir)
            cfg["auto_categorize"] = auto_cat_var.get()
            cfg["show_download_dialog"] = show_dialog_var.get()
            cfg["default_connections"] = conn_var.get()
            cfg["max_concurrent_downloads"] = max_active_var.get()
            cfg["github_repo"] = repo_var.get().strip()
            cfg["auto_check_updates"] = auto_up_var.get()

            updater.save_config(cfg)
            self.max_concurrent_var.set(cfg["max_concurrent_downloads"])
            self._update_statusbar_folder_label()
            dlg.destroy()
            messagebox.showinfo("Settings Saved", "Preferences and download paths saved successfully!")

        ttk.Button(btn_bar, text="Save Settings", style="Accent.TButton", command=_save_all).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)


class AddBatchDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Batch Add URLs - Dmans")
        self.geometry("560x400")
        self.transient(parent)
        self.grab_set()

        self.results = None
        app_cfg = updater.load_config()
        default_dir = app_cfg.get("download_dir") or updater.get_default_download_dir()
        self.dir_var = tk.StringVar(value=default_dir)
        self.conn_var = tk.IntVar(value=app_cfg.get("default_connections", 8))

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
        ttk.Combobox(opt_frame, textvariable=self.conn_var, values=[1, 2, 4, 8, 16, 24, 32], width=6, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)

        opt_frame.columnconfigure(1, weight=1)

        note_lbl = ttk.Label(
            f,
            text="* If auto-categorization is enabled, files will be sorted into subfolders automatically.",
            font=("Segoe UI", 8),
            foreground="#64748B"
        )
        note_lbl.pack(anchor=tk.W, pady=(0, 6))

        btn_box = ttk.Frame(f)
        btn_box.pack(fill=tk.X, pady=6)

        ttk.Button(btn_box, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_box, text="Add All to Queue", style="Accent.TButton", command=self._done).pack(side=tk.RIGHT, padx=4)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get(), parent=self)
        if d:
            self.dir_var.set(os.path.normpath(d))

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


class VideoStreamBreakdownDialog(tk.Toplevel):
    def __init__(self, parent, url: str, on_select_format):
        super().__init__(parent)
        self.title("Video Stream Breakdown - Dmans")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 660, 420
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.transient(parent)
        force_bring_to_front(self)
        self.grab_set()

        self.url = url
        self.on_select = on_select_format
        self.streams_data = []

        self._build_ui()
        threading.Thread(target=self._fetch_breakdown, daemon=True).start()

    def _build_ui(self):
        f = ttk.Frame(self, padding=12)
        f.pack(fill=tk.BOTH, expand=True)

        self.lbl_title = ttk.Label(f, text="🔍 Analyzing available video & audio streams with yt-dlp...", font=("Segoe UI", 10, "bold"), wraplength=620)
        self.lbl_title.pack(anchor=tk.W, pady=(0, 8))

        cols = ("Quality", "Type", "Resolution", "Ext", "Size", "Codec")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=8, selectmode="browse")
        self.tree.heading("Quality", text="Quality")
        self.tree.heading("Type", text="Stream Type")
        self.tree.heading("Resolution", text="Resolution")
        self.tree.heading("Ext", text="Format")
        self.tree.heading("Size", text="Est. Size")
        self.tree.heading("Codec", text="Codec")

        self.tree.column("Quality", width=140)
        self.tree.column("Type", width=100)
        self.tree.column("Resolution", width=90)
        self.tree.column("Ext", width=60)
        self.tree.column("Size", width=80)
        self.tree.column("Codec", width=70)

        self.tree.pack(fill=tk.BOTH, expand=True, pady=6)
        self.tree.bind("<Double-1>", lambda _: self._confirm())

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)

        self.btn_dl = ttk.Button(btn_box, text="⬇️ Select This Stream", command=self._confirm, state=tk.DISABLED)
        self.btn_dl.pack(side=tk.RIGHT, padx=6)
        ttk.Button(btn_box, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=6)

    def _fetch_breakdown(self):
        res = extract_stream_breakdown(self.url)
        self.after(0, self._apply_breakdown, res)

    def _apply_breakdown(self, data: dict):
        if "error" in data:
            self.lbl_title.config(text=f"⚠️ {data['error']}", foreground="#cc0000")
            return

        title = data.get("title", "Video Stream")
        duration = data.get("duration", 0)
        dur_str = f" ({duration//60}:{duration%60:02d})" if duration else ""
        self.lbl_title.config(text=f"🎬 {title}{dur_str}", foreground="#000000")

        self.streams_data = data.get("streams", [])
        for s in self.streams_data:
            self.tree.insert("", tk.END, iid=s["quality"], values=(
                s["label"],
                s["type"],
                s["resolution"],
                s["ext"].upper(),
                s["size"],
                s["codec"]
            ))

        if self.streams_data:
            self.tree.selection_set(self.streams_data[0]["quality"])
            self.btn_dl.config(state=tk.NORMAL)

    def _confirm(self):
        sel = self.tree.selection()
        if not sel:
            return
        chosen_q = sel[0]
        chosen_stream = next((s for s in self.streams_data if s["quality"] == chosen_q), None)
        if chosen_stream and self.on_select:
            self.on_select(chosen_stream)
        self.destroy()


class AddDownloadDialog(tk.Toplevel):
    def __init__(self, parent, initial_url: str = "", filename: str = "", cookies: str = "", referer: str = "", user_agent: str = "", start_now: bool = False, quality: str = "best"):
        super().__init__(parent)
        self.title("Enter URL to Download - Dmans")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 580, 400
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.resizable(False, False)
        self.transient(parent)
        force_bring_to_front(self)
        self.grab_set()

        self.result = None
        self.cookies = cookies or ""
        self.referer = referer or ""
        self.user_agent = user_agent or ""
        self.url_var = tk.StringVar(value=initial_url)
        self.file_var = tk.StringVar(value=filename)

        app_cfg = updater.load_config()
        self.base_dir = app_cfg.get("download_dir") or updater.get_default_download_dir()
        self.auto_cat = app_cfg.get("auto_categorize", True)

        init_cat = detect_file_category(filename=filename, url=initial_url)
        if quality == "audio":
            init_cat = "Music"
        self.category_var = tk.StringVar(value=init_cat)
        self.category_desc_var = tk.StringVar(value=self._get_cat_desc(init_cat))

        target_dir = resolve_category_path(self.base_dir, init_cat, self.auto_cat)
        self.dir_var = tk.StringVar(value=target_dir)
        self.user_custom_dir = False

        self.conn_var = tk.IntVar(value=app_cfg.get("default_connections", 8))
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
                            self.after(0, lambda: self._apply_fetched_title(clean, ext))
                    except Exception:
                        pass
                threading.Thread(target=_fetch_title, daemon=True).start()

        if not filename:
            self.url_var.trace_add("write", lambda *_: self.file_var.set(self._guess_filename(self.url_var.get())))

        self.url_var.trace_add("write", self._on_input_changed)
        self.file_var.trace_add("write", self._on_input_changed)
        self.quality_var.trace_add("write", self._on_input_changed)

        self._build_ui()

    def _get_cat_desc(self, cat: str) -> str:
        icon_text = CAT_ICON_MAP.get(cat, f"🗂️ {cat}")
        if self.auto_cat and cat not in ["General", "All Downloads"]:
            return f"{icon_text}  (Auto-sorted into \\{cat} folder)"
        return f"{icon_text}  (Main downloads folder)"

    def _apply_fetched_title(self, clean: str, ext: str):
        self.file_var.set(f"{clean}.{ext}")
        self._on_input_changed()

    def _on_input_changed(self, *_):
        if self.user_custom_dir:
            return
        u = self.url_var.get().strip()
        fn = self.file_var.get().strip()
        q = self.quality_var.get()
        cat = detect_file_category(filename=fn, url=u)
        if "Audio Only" in q:
            cat = "Music"
        self.category_var.set(cat)
        self.category_desc_var.set(self._get_cat_desc(cat))
        new_target = resolve_category_path(self.base_dir, cat, self.auto_cat)
        self.dir_var.set(new_target)

    def _guess_filename(self, url: str) -> str:
        try:
            parsed = urllib.parse.urlparse(url)
            name = os.path.basename(parsed.path)
            return urllib.parse.unquote(name) if name else ""
        except Exception:
            return ""

    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}
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
        
        save_btn_box = ttk.Frame(f)
        save_btn_box.grid(row=2, column=2, sticky=tk.W, padx=4, pady=4)
        ttk.Button(save_btn_box, text="Browse...", command=self._browse).pack(side=tk.LEFT, padx=2)
        ttk.Button(save_btn_box, text="Default", command=self._reset_default).pack(side=tk.LEFT, padx=2)

        ttk.Label(f, text="Category:").grid(row=3, column=0, sticky=tk.W, **pad)
        ttk.Label(f, textvariable=self.category_desc_var, font=("Segoe UI", 9, "bold"), foreground="#0369a1").grid(row=3, column=1, columnspan=2, sticky=tk.W, **pad)

        ttk.Label(f, text="Connections:").grid(row=4, column=0, sticky=tk.W, **pad)
        conn_cb = ttk.Combobox(f, textvariable=self.conn_var, values=[1, 2, 4, 8, 16, 24, 32], width=8, state="readonly")
        conn_cb.grid(row=4, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text="Speed Limiter:").grid(row=5, column=0, sticky=tk.W, **pad)
        speed_cb = ttk.Combobox(f, textvariable=self.speed_var, values=["Unlimited", "500 KB/s", "1 MB/s", "2 MB/s", "5 MB/s"], width=12, state="readonly")
        speed_cb.grid(row=5, column=1, sticky=tk.W, **pad)

        ttk.Label(f, text="Quality / Format:").grid(row=6, column=0, sticky=tk.W, **pad)
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
        qual_cb.grid(row=6, column=1, sticky=tk.W, **pad)
        ttk.Button(f, text="🔍 Breakdown...", command=self._open_breakdown).grid(row=6, column=2, **pad)

        f.columnconfigure(1, weight=1)

        chk_frame = ttk.Frame(self, padding=(14, 0, 14, 4))
        chk_frame.pack(fill=tk.X)
        self.dont_ask_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            chk_frame,
            text="Don't show this dialog again (Auto-start downloads using default/category folder)",
            variable=self.dont_ask_var
        ).pack(anchor=tk.W)

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="Download Later", command=lambda: self._done(False)).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_box, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=6)
        ttk.Button(btn_box, text="OK / Download Now", style="Accent.TButton", command=lambda: self._done(True)).pack(side=tk.RIGHT, padx=6)

        self.bind("<Return>", lambda e: self._done(True))
        self.bind("<Escape>", lambda e: self.destroy())

    def _reset_default(self):
        self.user_custom_dir = False
        self._on_input_changed()

    def _open_breakdown(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("URL Missing", "Please enter a valid video URL first!")
            return
        def _on_format_selected(stream_info):
            self.quality_var.set(stream_info["label"])
            if stream_info.get("ext"):
                base = os.path.splitext(self.file_var.get())[0] or "video"
                self.file_var.set(f"{base}.{stream_info['ext']}")
        VideoStreamBreakdownDialog(self, url, _on_format_selected)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get(), parent=self)
        if d:
            self.dir_var.set(os.path.normpath(d))
            self.user_custom_dir = True

    def _done(self, start_now: bool):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please provide a valid URL!")
            return

        if hasattr(self, "dont_ask_var") and self.dont_ask_var.get():
            app_cfg = updater.load_config()
            app_cfg["show_download_dialog"] = False
            updater.save_config(app_cfg)

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
            "category": self.category_var.get(),
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
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 640, 480
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(580, 420)
        force_bring_to_front(self)

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

        if prog.get("filename"):
            self.lbl_file.config(text=f"File: {prog['filename']}")

        eta = "N/A"
        if prog["speed"] > 0 and prog["total_size"] > prog["downloaded"]:
            eta = f"{(prog['total_size'] - prog['downloaded']) / prog['speed']:.1f}s"

        self.overall_bar["value"] = pct
        self.lbl_status.config(text=f"Status: {prog['status']} ({pct:.1f}%)")
        self.lbl_stats.config(text=f"Downloaded: {dl_mb:.2f} / {tot_mb:.2f} MB | Speed: {spd_mb:.2f} MB/s | Time Left: {eta}")

        if prog["is_finished"]:
            self.lbl_status.config(text="Status: Download Complete!", foreground="#008800")
            self.btn_pause.config(state=tk.DISABLED)
        elif prog.get("status") == "Error":
            self.lbl_status.config(text="Status: Download Error / Connection Failed", foreground="#DC2626")
            self.btn_pause.config(text="Retry", state=tk.NORMAL)

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


def check_single_instance() -> bool:
    """Ensures only one instance of Dmans is running.
    If another instance is active on port 18888 and has a visible window,
    forwards CLI URL and brings existing window to front.
    If the existing instance is windowless/zombie, frees port 18888 and lets this GUI launch."""
    try:
        import ctypes
        import urllib.request
        
        user32 = ctypes.windll.user32
        title_prefix = "Dmans v"
        found_hwnd = 0

        def enum_cb(h, _):
            nonlocal found_hwnd
            if user32.IsWindowVisible(h):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(h, buf, 256)
                if buf.value.startswith(title_prefix):
                    found_hwnd = h
                    return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        is_port_active = False
        try:
            req = urllib.request.Request("http://127.0.0.1:18888/ping", headers={"User-Agent": "DmansInstanceCheck"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("app") == "Dmans":
                    is_port_active = True
        except Exception:
            is_port_active = False

        if is_port_active:
            # If CLI arguments were passed, forward them via /add
            if len(sys.argv) > 1:
                raw_arg = sys.argv[1].strip()
                if raw_arg.startswith("dmans://"):
                    raw_arg = raw_arg[len("dmans://"):]
                if raw_arg.startswith("http://") or raw_arg.startswith("https://"):
                    try:
                        add_req = urllib.request.Request(
                            "http://127.0.0.1:18888/add",
                            data=json.dumps({"url": raw_arg, "start_now": True}).encode("utf-8"),
                            headers={"Content-Type": "application/json"}
                        )
                        urllib.request.urlopen(add_req, timeout=2.0)
                    except Exception:
                        pass
                return False

            # If user launched Dmans directly (no CLI arguments)
            if found_hwnd != 0:
                user32.ShowWindow(found_hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(found_hwnd)
                try:
                    show_req = urllib.request.Request("http://127.0.0.1:18888/show")
                    urllib.request.urlopen(show_req, timeout=1.0)
                except Exception:
                    pass
                return False
            else:
                # Port is active but NO visible window exists (headless/zombie process)
                # Terminate the zombie process on port 18888 so this GUI can start cleanly!
                try:
                    import subprocess
                    out = subprocess.check_output("netstat -ano -p tcp", shell=True).decode()
                    my_pid = os.getpid()
                    for line in out.splitlines():
                        if ":18888" in line and "LISTENING" in line:
                            parts = line.strip().split()
                            pid = int(parts[-1])
                            if pid != my_pid and pid > 0:
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                except Exception:
                    pass
                return True
    except Exception:
        pass
    return True


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if not check_single_instance():
        sys.exit(0)
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

