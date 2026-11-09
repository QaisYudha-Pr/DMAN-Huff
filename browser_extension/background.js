// Dmans Background Service Worker (Manifest V3) - IDM Grade Integration

const DMANS_API = "http://127.0.0.1:18888";
let lastRightClickUrl = "";

// 1. Fail-safe Storage Helper (Never throws undefined errors)
function safeGetSetting(key, defaultValue, callback) {
  try {
    if (typeof chrome !== "undefined" && chrome && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get([key], (res) => {
        if (chrome.runtime && chrome.runtime.lastError) {
          callback(defaultValue);
        } else if (res && res[key] !== undefined) {
          callback(res[key]);
        } else {
          callback(defaultValue);
        }
      });
      return;
    }
  } catch (e) {}
  callback(defaultValue);
}

// 2. Cookie Extractor (Authentic IDM session passing with multi-domain resolution)
async function getCookiesForUrl(targetUrl) {
  try {
    if (typeof chrome !== "undefined" && chrome && chrome.cookies) {
      // 1. First try matching by exact URL (retrieves all matching path and parent-domain cookies)
      let cookies = await chrome.cookies.getAll({ url: targetUrl });
      if (cookies && cookies.length > 0) {
        return cookies.map(c => `${c.name}=${c.value}`).join("; ");
      }

      const parsed = new URL(targetUrl);
      // 2. Try exact hostname
      cookies = await chrome.cookies.getAll({ domain: parsed.hostname });
      if (cookies && cookies.length > 0) {
        return cookies.map(c => `${c.name}=${c.value}`).join("; ");
      }

      // 3. Try parent/root domain (e.g. drive.google.com -> google.com)
      const parts = parsed.hostname.split(".");
      if (parts.length >= 2) {
        const rootDomain = parts.slice(-2).join(".");
        cookies = await chrome.cookies.getAll({ domain: rootDomain });
        if (cookies && cookies.length > 0) {
          return cookies.map(c => `${c.name}=${c.value}`).join("; ");
        }
      }
    }
  } catch (e) {}
  return "";
}

// 3. Guaranteed Context Menu Registration
function registerContextMenu() {
  try {
    if (typeof chrome === "undefined" || !chrome || !chrome.contextMenus) return;
    chrome.contextMenus.removeAll(() => {
      chrome.contextMenus.create({
        id: "dmans_universal_download",
        title: "⚡ Download with Dmans",
        contexts: ["all"]
      }, () => {
        if (chrome.runtime && chrome.runtime.lastError) {
          // Ignore duplicate item warnings
        }
      });
    });
  } catch (e) {}
}

if (typeof chrome !== "undefined" && chrome && chrome.runtime) {
  if (chrome.runtime.onInstalled) {
    chrome.runtime.onInstalled.addListener(registerContextMenu);
  }
  if (chrome.runtime.onStartup) {
    chrome.runtime.onStartup.addListener(registerContextMenu);
  }
}
registerContextMenu();

// 4. Notification Helper
function notifyUser(title, message) {
  try {
    if (typeof chrome !== "undefined" && chrome && chrome.notifications) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: title || "Dmans Download Accelerator",
        message: message,
        priority: 2
      }, () => {
        if (chrome.runtime && chrome.runtime.lastError) {}
      });
    }
  } catch (e) {}
}

// 5. Smart URL Resolver (Distinguishes between YouTube videos, images, and files)
function resolveBestDownloadUrl(info, tab) {
  const isVideoPlatform = (url) => {
    if (!url) return false;
    const u = url.toLowerCase();
    return u.includes("youtube.com/watch") || 
           u.includes("youtube.com/shorts") || 
           u.includes("youtu.be/") ||
           u.includes("tiktok.com/") ||
           u.includes("instagram.com/reel/") ||
           u.includes("twitter.com/") ||
           u.includes("x.com/");
  };

  const isDirectFile = (url) => {
    if (!url) return false;
    const clean = url.split("?")[0].toLowerCase();
    const exts = [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".exe", ".msi", ".apk", ".bin", ".mp4", ".mkv", ".webm", ".avi", ".mp3", ".flac", ".pdf", ".docx", ".xlsx", ".jpg", ".jpeg", ".png", ".webp", ".gif"];
    return exts.some(ext => clean.endsWith(ext));
  };

  // Priority 1: If the link is a video platform link (e.g. YouTube thumbnail/card), we want the VIDEO!
  if (info && info.linkUrl && isVideoPlatform(info.linkUrl)) {
    return info.linkUrl;
  }
  if (lastRightClickUrl && isVideoPlatform(lastRightClickUrl)) {
    return lastRightClickUrl;
  }

  // Priority 2: Direct media under cursor (Image, Audio, Video source)
  if (info && info.srcUrl && !info.srcUrl.startsWith("blob:")) {
    return info.srcUrl;
  }

  // Priority 3: Direct file link (.zip, .exe, .mp4, etc.)
  if (info && info.linkUrl && isDirectFile(info.linkUrl)) {
    return info.linkUrl;
  }

  // Priority 4: Last recorded right-click element from content script
  if (lastRightClickUrl && (!tab || lastRightClickUrl !== tab.url)) {
    return lastRightClickUrl;
  }

  // Priority 5: Enclosing link URL
  if (info && info.linkUrl) {
    return info.linkUrl;
  }

  // Priority 6: Current tab URL (especially on YouTube watch page)
  if (tab && tab.url && (isVideoPlatform(tab.url) || isDirectFile(tab.url))) {
    return tab.url;
  }

  return (info && info.pageUrl) || (tab ? tab.url : "");
}

// 6. Handle Messages from Content Scripts & Popups
if (typeof chrome !== "undefined" && chrome && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    const referer = (sender && sender.tab) ? sender.tab.url : "";
    if (msg.type === "UPDATE_LAST_RIGHTCLICK_URL") {
      lastRightClickUrl = msg.url;
    } else if (msg.type === "DOWNLOAD_URL") {
      sendToDmans(msg.url, msg.filename || "", referer, msg.quality || "best").then(success => {
        try { sendResponse({ success: success, offline: !success }); } catch (e) {}
      });
      return true;
    } else if (msg.type === "INTERCEPT_LINK_CLICK") {
      safeGetSetting("interceptLinks", true, (enabled) => {
        if (enabled) {
          sendToDmans(msg.url, "", referer);
          sendResponse({ handled: true });
        } else {
          sendResponse({ handled: false });
        }
      });
      return true;
    }
  });
}

// 7. Handle Context Menu Click
if (typeof chrome !== "undefined" && chrome && chrome.contextMenus && chrome.contextMenus.onClicked) {
  chrome.contextMenus.onClicked.addListener((info, tab) => {
    let targetUrl = resolveBestDownloadUrl(info, tab);
    let referer = tab ? tab.url : "";
    if (targetUrl) {
      sendToDmans(targetUrl, "", referer);
    }
  });
}

// 8. Smart Download Interception (Never cancels download if Dmans is offline!)
if (typeof chrome !== "undefined" && chrome && chrome.downloads && chrome.downloads.onCreated) {
  chrome.downloads.onCreated.addListener((downloadItem) => {
    if (!downloadItem.url.startsWith("http://") && !downloadItem.url.startsWith("https://")) {
      return;
    }

    safeGetSetting("autoIntercept", true, async (autoIntercept) => {
      if (!autoIntercept) return;

      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1200);
        const ping = await fetch(`${DMANS_API}/ping`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (ping.ok) {
          chrome.downloads.cancel(downloadItem.id, () => {
            chrome.downloads.erase({ id: downloadItem.id });
            sendToDmans(downloadItem.url, downloadItem.filename, downloadItem.referrer || "");
          });
        }
      } catch (err) {
        console.log("[Dmans] Desktop app offline. Browser will continue downloading.");
      }
    });
  });
}

// 9. Send Request to Local Dmans API (Transmits Quality, Cookie, Referer, and User-Agent)
async function sendToDmans(url, filename = "", referer = "", quality = "best") {
  if (!url) return;

  let cookies = "";
  try {
    cookies = await getCookiesForUrl(url);
  } catch (e) {}

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    const res = await fetch(`${DMANS_API}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        filename: filename,
        cookies: cookies,
        referer: referer,
        user_agent: navigator.userAgent,
        quality: quality,
        start_now: true
      }),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      notifyUser("⚡ Dmans Connected", `Download added (${quality}): ${filename || url.split('/').pop().split('?')[0] || url}`);
      return true;
    }
  } catch (err) {
    console.warn("[Dmans] Local API offline, launching Dmans via protocol fallback:", err);
  }

  // Fallback: If Dmans Desktop isn't currently open, invoke dmans:// to trigger Windows to launch it!
  try {
    const protocolUrl = `dmans://${url}`;
    chrome.tabs.create({ url: protocolUrl, active: false }, (newTab) => {
      setTimeout(() => {
        if (newTab && newTab.id) {
          chrome.tabs.remove(newTab.id).catch(() => {});
        }
      }, 1500);
    });
    notifyUser("⚡ Membuka Dmans...", "Aplikasi desktop Dmans sedang diluncurkan untuk memproses unduhan.");
  } catch (e) {
    notifyUser("⚠️ Dmans Belum Dibuka", "Silakan buka Dmans.exe di laptopmu untuk menerima unduhan.");
  }
  return false;
}
