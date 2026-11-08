// Dmans Background Service Worker (Manifest V3)

const DMANS_API = "http://127.0.0.1:18888";
let lastRightClickUrl = "";

// 1. Context Menu Registration (Only inside onInstalled to avoid Status Code 15)
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "dmans_universal_download",
      title: "⚡ Download with Dmans",
      contexts: ["all"]
    }, () => {
      if (chrome.runtime.lastError) {
        // Suppress benign duplicate ID warnings
      }
    });
  });
});

// 2. Handle Messages from Content Script & Popups
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "UPDATE_LAST_RIGHTCLICK_URL") {
    lastRightClickUrl = msg.url;
  } else if (msg.type === "DOWNLOAD_URL") {
    sendToDmans(msg.url);
  } else if (msg.type === "INTERCEPT_LINK_CLICK") {
    if (chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(["interceptLinks"], (res) => {
        if (!res || res.interceptLinks !== false) {
          sendToDmans(msg.url);
          sendResponse({ handled: true });
        } else {
          sendResponse({ handled: false });
        }
      });
      return true; // Keep message channel open for async response
    } else {
      sendToDmans(msg.url);
      sendResponse({ handled: true });
    }
  }
});

// 3. Handle Context Menu Click
chrome.contextMenus.onClicked.addListener((info, tab) => {
  let targetUrl = info.linkUrl || info.srcUrl || info.pageUrl || lastRightClickUrl || (tab ? tab.url : "");
  if (targetUrl) {
    sendToDmans(targetUrl);
  }
});

// 4. Handle Browser Download Shelf Interception
chrome.downloads.onCreated.addListener((downloadItem) => {
  if (chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(["autoIntercept"], (res) => {
      if (!res || res.autoIntercept !== false) {
        if (downloadItem.url.startsWith("http://") || downloadItem.url.startsWith("https://")) {
          chrome.downloads.cancel(downloadItem.id, () => {
            chrome.downloads.erase({ id: downloadItem.id });
            sendToDmans(downloadItem.url, downloadItem.filename);
          });
        }
      }
    });
  }
});

// 5. Send Request to Local Dmans API (127.0.0.1:18888)
async function sendToDmans(url, filename = "") {
  try {
    const res = await fetch(`${DMANS_API}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        filename: filename,
        start_now: true
      })
    });
    const data = await res.json();
    console.log("[Dmans] Download dispatched:", data);
  } catch (err) {
    console.warn("[Dmans] Desktop app is offline or not running at http://127.0.0.1:18888:", err);
  }
}
