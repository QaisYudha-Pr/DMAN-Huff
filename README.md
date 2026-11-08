# PyIDM - Custom High-Performance Download Manager

A zero-dependency, multi-threaded download accelerator implementing the core architecture and acceleration techniques popularized by **Internet Download Manager (IDM)**.

---

## 🔬 How IDM Works (Under the Hood)

Internet Download Manager (and tools like `aria2`) does not possess "magic speed"—it leverages fundamental TCP/IP and HTTP/1.1 protocols to bypass standard browser bottlenecks:

### 1. The Single-Connection Bottleneck
When a normal web browser downloads a file:
* It establishes a single TCP connection.
* Due to TCP congestion control (Slow Start, packet loss recovery), high latency, or server-side per-connection bandwidth throttles (e.g., limiting each connection to 500 KB/s), your maximum network bandwidth is often underutilized.

### 2. HTTP Byte Range Requests (RFC 7233)
Web servers that serve files support the `Range` HTTP header:
```http
GET /large_file.zip HTTP/1.1
Host: example.com
Range: bytes=0-10485759
```
The server responds with HTTP **`206 Partial Content`**, transmitting only that requested byte slice.

### 3. Dynamic Segmentation
IDM splits the file's total byte length into $N$ segments (e.g. 8, 16, or 32 connections):
* **Connection 1:** Bytes `0` to `25,000,000`
* **Connection 2:** Bytes `25,000,001` to `50,000,000`
* **Connection 3:** Bytes `50,000,001` to `75,000,000`
* **Connection 4:** Bytes `75,000,001` to `100,000,000`

By opening multiple simultaneous TCP streams, it saturates your available bandwidth and bypasses per-connection speed caps.

### 4. Direct In-Place Sparse Writing (No 99% Freeze)
Old download managers downloaded parts into separate files (`part1.tmp`, `part2.tmp`) and then spent minutes copying and concatenating them at the end.
Modern download engines pre-allocate a sparse file of the exact target length:
```python
file.seek(offset)
file.write(chunk)
```
Each thread seeks directly to its assigned byte position and writes chunks live. When the last chunk arrives, the download is instantaneously complete.

### 5. Pause & Resume (State Persistence)
Progress is saved to a `.idmmeta` JSON record. If the network drops or you pause, only the unfinished byte ranges are re-requested on resume.

---

## 🚀 How to Run

### Option A: Desktop GUI (IDM Clone)
Double-click `run_gui.bat` or run from any terminal:
```powershell
idm-gui
```
* **IDM Layout**: Category sidebar (`All Downloads`, `Unfinished`, `Finished`, `Compressed`, `Video`, `Music`, `Documents`, `Programs`).
* **Main Downloads Table**: Lists file name, size, status, progress, speed, time left, category, and date added.
* **IDM Progress Dialog**: Double-click any download to open the iconic IDM dynamic segment visualizer showing real-time multi-threaded chunk progress.
* **Right-Click Context Menu**: Resume, Pause, Open File, Open Folder, Copy Download Link, Delete.
* **Clipboard Sniffer**: Automatically detects downloadable URLs copied to your Windows clipboard and prompts to download.
* **Persistent History**: Saves all download states across restarts in `downloads_db.json`.

### Option B: Command Line (CLI)
Run globally from any terminal:
```powershell
idm "https://example.com/file.zip" -c 16 -o "C:\Downloads"
```
* `-c / --connections`: Number of parallel threads (1-32, default: 8).
* `-o / --output-dir`: Destination folder.
* `-f / --filename`: Custom output filename.

---

## 📁 File Structure
* [idm_engine.py](file:///c:/Users/asus/Downloads/11-12-IDM/idm_engine.py): Multi-threaded download engine with Range support and state persistence.
* [idm_gui.py](file:///c:/Users/asus/Downloads/11-12-IDM/idm_gui.py): Tkinter desktop application with live per-thread visualizer.
* [idm_cli.py](file:///c:/Users/asus/Downloads/11-12-IDM/idm_cli.py): CLI interface with live ASCII progress bar and ETA.
* [run_gui.bat](file:///c:/Users/asus/Downloads/11-12-IDM/run_gui.bat): Quick double-click launcher for the desktop GUI.

