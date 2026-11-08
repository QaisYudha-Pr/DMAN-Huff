// PyIDM Background Service Worker (Manifest V3)

const PYIDM_API = "http://127.0.0.1:18888";
let lastRightClickUrl = "";

// 1. Setup Context Menus (Guaranteed to show on ALL elements)
function initContextMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "pyidm_universal_download",
      title: "⚡ Download with PyIDM",
      contexts: ["all"] // "all" ensures it shows on every right-click!
    });
  });
}

chrome.runtime.onInstalled.addListener(initContextMenus);
chrome.runtime.onStartup.addListener(initContextMenus);
initContextMenus();

// 2. Handle Messages from Content Script
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "UPDATE_LAST_RIGHTCLICK_URL") {
    lastRightClickUrl = msg.url;
  } else if (msg.type === "DOWNLOAD_URL") {
    sendToPyIDM(msg.url);
  }
});

// 3. Handle Context Menu Click
chrome.contextMenus.onClicked.addListener((info, tab) => {
  let targetUrl = info.linkUrl || info.srcUrl || info.pageUrl || lastRightClickUrl || (tab ? tab.url : "");
  if (targetUrl) {
    sendToPyIDM(targetUrl);
  }
});

// 4. Auto-Intercept Chrome Downloads
chrome.downloads.onCreated.addListener((downloadItem) => {
  chrome.storage.local.get(["autoIntercept"], (res) => {
    // If autoIntercept is enabled (default true)
    if (res.autoIntercept !== false) {
      if (downloadItem.url.startsWith("http://") || downloadItem.url.startsWith("https://")) {
        // Cancel Chrome's slow download
        chrome.downloads.cancel(downloadItem.id, () => {
          chrome.downloads.erase({ id: downloadItem.id });
          sendToPyIDM(downloadItem.url, downloadItem.filename);
        });
      }
    }
  });
});

// 5. Send Download to PyIDM API
async function sendToPyIDM(url, filename = "") {
  try {
    const res = await fetch(`${PYIDM_API}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        filename: filename,
        start_now: true
      })
    });
    const data = await res.json();
    console.log("[PyIDM] Success:", data);
  } catch (err) {
    console.warn("[PyIDM] Could not connect to PyIDM desktop app. Is PyIDM running?", err);
  }
}
