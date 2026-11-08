// Dmans Background Service Worker (Manifest V3)

const DMANS_API = "http://127.0.0.1:18888";
let lastRightClickUrl = "";

function initContextMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "dmans_universal_download",
      title: "⚡ Download with Dmans",
      contexts: ["all"]
    });
  });
}

chrome.runtime.onInstalled.addListener(initContextMenus);
chrome.runtime.onStartup.addListener(initContextMenus);
initContextMenus();

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "UPDATE_LAST_RIGHTCLICK_URL") {
    lastRightClickUrl = msg.url;
  } else if (msg.type === "DOWNLOAD_URL") {
    sendToDmans(msg.url);
  }
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  let targetUrl = info.linkUrl || info.srcUrl || info.pageUrl || lastRightClickUrl || (tab ? tab.url : "");
  if (targetUrl) {
    sendToDmans(targetUrl);
  }
});

chrome.downloads.onCreated.addListener((downloadItem) => {
  chrome.storage.local.get(["autoIntercept"], (res) => {
    if (res.autoIntercept !== false) {
      if (downloadItem.url.startsWith("http://") || downloadItem.url.startsWith("https://")) {
        chrome.downloads.cancel(downloadItem.id, () => {
          chrome.downloads.erase({ id: downloadItem.id });
          sendToDmans(downloadItem.url, downloadItem.filename);
        });
      }
    }
  });
});

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
    console.log("[Dmans] Sent successfully:", data);
  } catch (err) {
    console.warn("[Dmans] Could not connect to Dmans desktop app. Is Dmans running?", err);
  }
}
