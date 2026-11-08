# ⚡ PyIDM - Internet Download Manager Clone & Accelerator

<p align="center">
  <b>High-Speed Multi-Threaded Download Manager for Windows</b><br>
  <i>Akselerator Unduhan Cepat Berbasis Segmentasi Dinamis (RFC 7233) dengan Tampilan & Ekstensi Browser ala IDM.</i>
</p>

---

## 🌐 Bahasa Indonesia

### 📌 Ringkasan Proyek
PyIDM adalah aplikasi download manager mandiri berformat **`.exe`** (tanpa script `.bat`) yang mereplikasi cara kerja dan fitur legendaris **Internet Download Manager (IDM)**:
* **Multi-koneksi paralel (1 - 32 thread)** untuk memaksimalkan bandwidth internet.
* **Integrasi Browser (Chrome / Edge / Brave)** dengan penangkap link otomatis dan tombol melayang download video.
* **Installer native (`Installer.exe`)** lengkap dengan shortcut Desktop, Start Menu, dan Uninstaller.
* **Sistem Auto-Update** langsung dari GitHub Releases.

---

### ❓ Mengapa Opsi "Download with..." Sebelumnya Tidak Muncul?
Pada versi awal browser extension:
1. **Konteks Klik Kanan Terlalu Terbatas**: Menu klik kanan hanya dipasang untuk tag tautan HTML (`<a href>`) standar. Jika tombol unduhan di website dibungkus oleh elemen `<div>`, `<button>`, `<span>`, atau custom player (seperti YouTube, streaming player, tombol cloud storage), browser tidak mendeteksinya sebagai tautan sehingga opsi klik kanan **tidak muncul**.
2. **Tidak Ada Content Script Pendeteksi Media**: IDM asli menggunakan *content script* yang disuntikkan ke dalam halaman web untuk mendeteksi tag `<video>` dan `<audio>`.

#### 🛠️ Perbaikan di Ekstensi Versi 2.0 (Sekarang):
* **Konteks Universal (`contexts: ["all"]`)**: Menu **"⚡ Download with PyIDM"** sekarang dijamin **selalu muncul di mana saja** saat Anda klik kanan di halaman web apa pun!
* **Tombol Melayang Video (Floating Bar)**: Saat membuka video di web, tombol biru **"⚡ Download Video (PyIDM)"** akan otomatis muncul di sudut video.
* **Auto-Catch Unduhan**: Klik pada link file `.zip`, `.exe`, `.iso`, `.mp4`, `.pdf`, dsb., akan otomatis dialihkan ke PyIDM.

---

### 🚀 Cara Pasang Ekstensi Browser (Chrome / Edge / Brave)
1. Buka browser Anda:
   * **Chrome / Brave**: buka `chrome://extensions`
   * **Microsoft Edge**: buka `edge://extensions`
2. Aktifkan **"Developer mode"** (Mode Pengembang) di pojok kanan atas.
3. Klik tombol **"Load unpacked"** (Muat yang belum dibongkar) di pojok kiri atas.
4. Pilih folder:
   ```text
   C:\Users\asus\Downloads\11-12-IDM\browser_extension
   ```
5. **Selesai!** Ekstensi sekarang aktif dan langsung terhubung dengan aplikasi PyIDM desktop.

---

### 💻 Cara Install Aplikasi (Tanpa .bat)
Semua file telah dikompilasi menjadi file biner native **`.exe`**:

1. **Pasang ke Komputer**:
   * Klik dua kali **`Installer.exe`**.
   * Aplikasi akan otomatis dipasang ke direktori standar Windows (`%LOCALAPPDATA%\Programs\PyIDM`).
   * Shortcut akan otomatis dibuat di **Desktop** dan **Start Menu**.
   * Perintah `idm` otomatis aktif di PowerShell & Command Prompt.
2. **Buka Aplikasi**:
   * Klik shortcut **PyIDM** di Desktop atau cari di Start Menu.
   * Atau klik dua kali **`PyIDM.exe`**.
3. **Menggunakan CLI di Terminal**:
   ```powershell
   idm "https://example.com/file.zip" -c 16
   ```
4. **Hapus Instalasi (Uninstall)**:
   * Jalankan **`Uninstall.exe`** atau hapus dari Windows Settings -> Installed Apps.

---

### 🔬 Cara Kerja PyIDM (Under The Hood)
1. **RFC 7233 HTTP Byte Ranges**: Saat file mulai diunduh, PyIDM mengirim permintaan `Range: bytes=0-0` untuk mengecek apakah server mendukung pemotongan file.
2. **Dynamic Work Slicing**: File dibagi menjadi $N$ segmen byte (misalnya 16 koneksi). Masing-masing segmen berjalan di thread terpisah.
3. **Sparse File Writing (Bebas Macet di 99%)**: File tujuan dialokasikan langsung sesuai ukuran aslinya. Tiap thread menulis datanya secara langsung menggunakan penunjuk offset (`seek`). Tidak ada proses penggabungan lambat di akhir unduhan.
4. **Pemberitahuan & Audio**: Memutar notifikasi audio Windows asli saat unduhan selesai dan memunculkan dialog `Open File` / `Open Folder`.

---

---

## 🇬🇧 English

### 📌 Overview
PyIDM is a standalone Windows **`.exe`** application (no `.bat` scripts needed) that implements the core acceleration architecture and UI popularized by **Internet Download Manager (IDM)**:
* **Multi-threaded dynamic segmentation (1 - 32 streams)** for maximum network speed.
* **Chrome / Edge / Brave Browser Extension** with auto-intercept and floating video download button.
* **Native GUI Installer (`Installer.exe`)** with Desktop/Start Menu shortcuts and clean uninstallation.
* **GitHub Auto-Update System** directly from your repository releases.

---

### ❓ Why Didn't "Download with..." Show Up Before?
In the initial extension version:
1. **Restricted Contexts**: The context menu was registered strictly for `<a href>` elements. Many modern websites wrap download links inside `<div>`, `<button>`, or JavaScript event handlers. Chrome did not recognize these as traditional links, causing the option not to appear.
2. **Missing Media Sniffer**: IDM uses an in-page content script to detect `<video>` and `<audio>` streams directly in the DOM.

#### 🛠️ What Was Fixed in Extension v2.0:
* **Universal Context (`contexts: ["all"]`)**: The **"⚡ Download with PyIDM"** option is now guaranteed to show on **every single right-click**.
* **Floating Video Bar**: Displays a sleek floating **"⚡ Download Video (PyIDM)"** badge over HTML5 videos on any website.
* **Auto-Catch Downloads**: Automatically catches browser downloads and file extension clicks (`.zip`, `.exe`, `.iso`, `.mp4`, `.pdf`).

---

### 🚀 Installing the Browser Extension
1. Open your browser:
   * **Chrome / Brave**: `chrome://extensions`
   * **Microsoft Edge**: `edge://extensions`
2. Enable **"Developer mode"** in the top-right corner.
3. Click **"Load unpacked"** in the top-left.
4. Select the folder:
   ```text
   C:\Users\asus\Downloads\11-12-IDM\browser_extension
   ```

---

### 💻 Installing the Application (No .bat)
Everything is packaged into native Windows **`.exe`** executables:

| File | Purpose |
| :--- | :--- |
| **`Installer.exe`** | Setup wizard that installs PyIDM, creates Desktop/Start Menu shortcuts, and configures PATH |
| **`PyIDM.exe`** | The main desktop application GUI |
| **`idm.exe`** | Terminal / command-line downloader |
| **`Uninstall.exe`** | Cleanly removes all application files, shortcuts, and registry entries |

---

### 📤 How to Push This Project to Your GitHub

```powershell
git init
git add .
git commit -m "Initial commit: PyIDM full app with installer and browser extension"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/PyIDM.git
git push -u origin main
```

To release a new version that triggers the auto-updater:
```powershell
git tag -a v1.0.1 -m "Release v1.0.1"
git push origin v1.0.1
```
The included GitHub Actions workflow ([`.github/workflows/release.yml`](file:///c:/Users/asus/Downloads/11-12-IDM/.github/workflows/release.yml)) will automatically build the `.exe` files and publish a GitHub Release!
