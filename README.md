# ⚡ Dmans - Fast Download Accelerator

<p align="center">
  <img src="https://img.shields.io/badge/Release-v1.0.0-0284c7?style=for-the-badge" alt="Release" />
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?style=for-the-badge&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/Engine-RFC%207233%20Dynamic%20Threading-16A34A?style=for-the-badge" alt="Engine" />
  <img src="https://img.shields.io/badge/License-MIT-amber?style=for-the-badge" alt="License" />
</p>

<p align="center">
  <b>High-Performance Multi-Connection Download Accelerator for Windows</b><br>
  <i>Akselerator Unduhan Cepat Berbasis Segmentasi Dinamis dengan Integrasi Browser Lengkap & Tanpa File Script .bat</i>
</p>

---

## 📑 Daftar Isi / Table of Contents
* [🇮🇩 Bahasa Indonesia](#-bahasa-indonesia)
  * [1. Tentang Dmans](#1-tentang-dmans)
  * [2. Kenapa Sempat Terdeteksi Antivirus? (Penjelasan & Solusi)](#2-kenapa-sempat-terdeteksi-antivirus-penjelasan--solusi)
  * [3. Optimasi & Fitur Utama](#3-optimasi--fitur-utama)
  * [4. Cara Pasang Aplikasi (Installer.exe)](#4-cara-pasang-aplikasi-installerexe)
  * [5. Cara Pasang Ekstensi Browser (Chrome / Edge / Brave)](#5-cara-pasang-ekstensi-browser)
  * [6. Penggunaan CLI di Terminal](#6-penggunaan-cli-di-terminal)
* [🇬🇧 English](#-english)
  * [1. Overview](#1-overview)
  * [2. Why Did Windows Antivirus / SmartScreen Flag It?](#2-why-did-windows-antivirus--smartscreen-flag-it)
  * [3. Key Optimizations & Features](#3-key-optimizations--features)
  * [4. Installation Guide (Installer.exe)](#4-installation-guide-installerexe)
  * [5. Browser Extension Setup](#5-browser-extension-setup)
  * [6. Pushing to GitHub](#6-pushing-to-github)

---

## 🇮🇩 Bahasa Indonesia

### 1. Tentang Dmans
**Dmans** adalah aplikasi akselerator unduhan mandiri untuk Windows yang dirancang untuk memaksimalkan kecepatan unduhan internet Anda menggunakan protokol **RFC 7233 HTTP Range Slicing**. Berbeda dengan downloader konvensional yang hanya membuka satu koneksi, Dmans memecah file menjadi hingga 32 koneksi simultan secara dinamis dan menulis langsung ke disk secara *in-place sparse allocation*.

---

### 2. Kenapa Sempat Terdeteksi Antivirus? (Penjelasan & Solusi)

Peringatan dari Windows Defender atau Windows SmartScreen pada aplikasi buatan sendiri (kompilasi lokal) adalah hal yang **sangat umum dan wajar (100% False Positive)**. Berikut penyebab teknisnya:

1. **Reputasi Windows SmartScreen**:
   * Microsoft SmartScreen menandai semua file `.exe` yang baru dibuat dan belum memiliki reputasi unduhan global atau belum ditandatangani sertifikat digital berbayar ($400+/tahun EV Code Signing).
2. **Karakteristik PyInstaller Bundler**:
   * Kompiler executable Python membungkus interpreter dan payload ke dalam satu biner yang mengekstrak dirinya ke folder memori sementara (`%TEMP%`). Pola ini sering dicurigai oleh pemindai heuristik antivirus generik sebagai tanda "dropper".
3. **Penyematan Metadata PE Resmi di Versi Ini**:
   * Pada versi ini, kami telah menyematkan **Microsoft PE Version Resource resmi** (`version_info.txt`) lengkap dengan `CompanyName`, `FileDescription`, `LegalCopyright`, dan `ProductVersion` ke dalam setiap biner executable (`Dmans.exe`, `dmans-cli.exe`, `Installer.exe`, dan `Uninstall.exe`), serta menghapus pola pemanggilan shell berbahaya. Hal ini secara signifikan mereduksi pemicu alarm palsu antivirus.

#### 🛡️ Cara Mengizinkannya jika SmartScreen Muncul:
Jika muncul layar biru Windows SmartScreen (*"Windows protected your PC"*):
1. Klik teks **"More info"** (*Info selengkapnya*).
2. Klik tombol **"Run anyway"** (*Tetap jalankan*).
3. Aplikasi akan langsung berjalan normal dan aman.

---

### 3. Optimasi & Fitur Utama

* **Optimasi Buffer I/O 256 KB**:
  Chunk data dinaikkan ke 256 KB untuk mempercepat transfer data jaringan dan memangkas waktu tunggu lock multi-threading pada disk NVMe/SSD.
* **In-Place Sparse File Writing (Bebas Macet di 99%)**:
  File target langsung dialokasikan di awal melalui fungsi NTFS sparse `truncate()`. Setiap thread menulis tepat di posisinya. Tidak ada proses penggabungan lambat saat unduhan mencapai 99%.
* **Dynamic Work Stealing**:
  Jika salah satu koneksi selesai lebih dulu sementara koneksi lain masih lambat, thread yang nganggur akan secara otomatis membelah dua sisa pekerjaan koneksi yang lambat tersebut sehingga kecepatan unduhan tetap maksimal hingga byte terakhir.
* **Ekstensi Browser v2.0**:
  * **Konteks Universal**: Opsi klik kanan **"⚡ Download with Dmans"** selalu muncul di mana saja.
  * **Floating Video Bar**: Tombol download otomatis melayang di atas video web (YouTube, streaming, dsb.).
  * **Auto-Catch**: Otomatis mencegat unduhan file `.zip`, `.exe`, `.iso`, `.mp4`, `.pdf`.
* **GitHub Auto-Updater**:
  Mengecek rilis baru di repositori GitHub Anda secara otomatis melalui menu `Help -> Check for Updates`.

---

### 4. Cara Pasang Aplikasi (`Installer.exe`)

Semua komponen sudah berupa file biner **`.exe`** (tanpa script `.bat`):

1. Klik dua kali **[`Installer.exe`](file:///c:/Users/asus/Downloads/11-12-IDM/Installer.exe)**.
2. Dmans akan dipasang ke direktori standar Windows (`%LOCALAPPDATA%\Programs\Dmans`).
3. Shortcut otomatis dibuat di **Desktop** dan **Start Menu**.
4. Perintah `dmans` otomatis aktif di PowerShell & Command Prompt.

---

### 5. Cara Pasang Ekstensi Browser

1. Buka browser:
   * **Chrome / Brave**: `chrome://extensions`
   * **Microsoft Edge**: `edge://extensions`
2. Aktifkan **"Developer mode"** di pojok kanan atas.
3. Klik **"Load unpacked"** di pojok kiri atas.
4. Pilih folder:
   ```text
   C:\Users\asus\Downloads\11-12-IDM\browser_extension
   ```
5. Buka video web apa saja atau klik kanan di mana saja — tombol Dmans akan langsung muncul.

---

### 6. Penggunaan CLI di Terminal

Anda dapat mengunduh langsung dari PowerShell atau CMD:
```powershell
dmans "https://example.com/file.zip" -c 16 -o "C:\Downloads"
```
* `-c`: Jumlah koneksi paralel (1 - 32, default: 8).
* `-o`: Folder tujuan penyimpanan.
* `-l`: Batas kecepatan dalam KB/s (misal: `-l 2048` untuk limit 2 MB/s).

---

---

## 🇬🇧 English

### 1. Overview
**Dmans** is a standalone Windows download accelerator designed to saturate your network bandwidth using **RFC 7233 dynamic HTTP Range segmentation**. Unlike traditional browsers that download files through a single bottlenecked stream, Dmans partitions downloads into up to 32 concurrent threads with in-place disk allocation.

---

### 2. Why Did Windows Antivirus / SmartScreen Flag It?

Antivirus warnings on newly compiled binaries are **standard false positives**:
* **SmartScreen Reputation Gate**: Windows Defender SmartScreen blocks unrecognized executables that lack thousands of download reputations or a paid Microsoft Authenticode certificate.
* **PyInstaller Heuristics**: Single-file Python compilers unpack into memory on startup. Heuristic scanners often classify this generic unpacking pattern as suspicious.
* **Resolution in this Release**:
  * Embedded official **Microsoft PE Version Resource headers** (`version_info.txt`) with Company Name, Copyright, and Product info.
  * Recompiled with clean native C# wrappers and zero suspicious shell commands.

#### 🛡️ How to Bypass SmartScreen:
When the blue *"Windows protected your PC"* dialog appears:
1. Click **"More info"**.
2. Click **"Run anyway"**.

---

### 3. Key Optimizations & Features
* **256 KB Tuned Buffer**: High-throughput memory pipeline minimizing lock contention and disk I/O latency.
* **Instant Sparse Allocation**: Avoids the "stuck at 99%" merge delay by pre-allocating the target size and streaming chunks directly into file offsets.
* **Work Stealing Algorithm**: Idle threads automatically divide the remaining range of slower active connections.
* **Universal Browser Integration**: Manifest V3 extension featuring context menu support and floating video download badges.
* **Built-in GitHub Auto-Updater**: Directly fetches changelogs and new releases from your GitHub repository.

---

### 4. Installation Guide (`Installer.exe`)

| File | Description |
| :--- | :--- |
| **`Installer.exe`** | One-click setup wizard (creates shortcuts & registers PATH) |
| **`Dmans.exe`** | Main desktop GUI application |
| **`dmans-cli.exe`** | Fast terminal command-line tool (`dmans <url>`) |
| **`Uninstall.exe`** | Clean uninstaller removing all files and shortcuts |

---

### 5. Browser Extension Setup
1. Navigate to `chrome://extensions` or `edge://extensions`.
2. Toggle on **Developer mode**.
3. Click **Load unpacked** and select the `browser_extension` folder.

---

### 6. Pushing to GitHub

```powershell
git add .
git commit -m "feat: complete Dmans rebranding, PE metadata, and 256KB buffer optimization"
git push origin main
```

To release a new update that triggers the built-in auto-updater:
```powershell
git tag -a v1.0.1 -m "Release v1.0.1"
git push origin v1.0.1
```
The automated GitHub Actions workflow will compile the binaries and publish the release package!
