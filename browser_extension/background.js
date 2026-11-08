// Dmans Background Service Worker (Manifest V3)

const DMANS_API = "http://127.0.0.1:18888";
let lastRightClickUrl = "";

// 1. Fail-safe Storage Helper (Prevents any 'reading local of undefined' errors)
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

// 2. Guaranteed Context Menu Registration
chrome.runtime.onInstalled.addListener(() => {
  try {
    chrome.contextMenus.removeAll(() => {
      chrome.contextMenus.create({
        id: "dmans_universal_download",
        title: "⚡ Download with Dmans",
        contexts: ["all"]
      }, () => {
        if (chrome.runtime.lastError) {
          // Benign duplicate suppression
        }
      });
    });
  } catch (e) {}
});

// 3. Notification Helper
function notifyUser(title, message) {
  try {
    if (typeof chrome !== "undefined" && chrome.notifications) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: title || "Dmans Download Accelerator",
        message: message,
        priority: 2
      }, () => {
        if (chrome.runtime.lastError) {}
      });
    }
  } catch (e) {}
}

// 4. Handle Messages from Content Scripts & Popups
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "UPDATE_LAST_RIGHTCLICK_URL") {
    lastRightClickUrl = msg.url;
  } else if (msg.type === "DOWNLOAD_URL") {
    sendToDmans(msg.url, msg.filename || "");
  } else if (msg.type === "INTERCEPT_LINK_CLICK") {
    safeGetSetting("interceptLinks", true, (enabled) => {
      if (enabled) {
        sendToDmans(msg.url);
        sendResponse({ handled: true });
      } else {
        sendResponse({ handled: false });
      }
    });
    return true; // Keep message channel open for async response
  }
});

// 5. Handle Context Menu Click
chrome.contextMenus.onClicked.addListener((info, tab) => {
  let targetUrl = info.linkUrl || info.srcUrl || lastRightClickUrl || info.pageUrl || (tab ? tab.url : "");
  if (targetUrl) {
    sendToDmans(targetUrl);
  }
});

// 6. Smart Download Interception (Never cancels download if Dmans is offline!)
chrome.downloads.onCreated.addListener((downloadItem) => {
  if (!downloadItem.url.startsWith("http://") && !downloadItem.url.startsWith("https://")) {
    return;
  }

  safeGetSetting("autoIntercept", true, async (autoIntercept) => {
    if (!autoIntercept) return;

    // Check if Dmans Desktop App is running before cancelling browser download
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1200);
      const ping = await fetch(`${DMANS_API}/ping`, { signal: controller.signal });
      clearTimeout(timeoutId);

      if (ping.ok) {
        // Dmans is online! Safe to intercept and pass to Dmans
        chrome.downloads.cancel(downloadItem.id, () => {
          chrome.downloads.erase({ id: downloadItem.id });
          sendToDmans(downloadItem.url, downloadItem.filename);
        });
      }
    } catch (err) {
      // Dmans Desktop is offline. Let browser download normally without breaking!
      console.log("[Dmans] Desktop app offline. Browser will continue downloading.");
    }
  });
});

// 7. Send Request to Local Dmans API (or trigger dmans:// protocol fallback)
async function sendToDmans(url, filename = "") {
  if (!url) return;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);

    const res = await fetch(`${DMANS_API}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        filename: filename,
        start_now: true
      }),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      notifyUser("⚡ Dmans Connected", `Download added: ${filename || url.split('/').pop().split('?')[0] || url}`);
      return;
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
}
