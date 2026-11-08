// PyIDM Browser Integration Extension Background Worker

const PYIDM_API = "http://127.0.0.1:18888";

// 1. Setup Context Menus on Installation
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "pyidm_download_link",
    title: "Download with PyIDM",
    contexts: ["link", "image", "video", "audio"]
  });
  
  chrome.contextMenus.create({
    id: "pyidm_download_page",
    title: "Download all links with PyIDM",
    contexts: ["page"]
  });
});

// 2. Handle Context Menu Click
chrome.contextMenus.onClicked.addListener((info, tab) => {
  let targetUrl = info.linkUrl || info.srcUrl;
  if (!targetUrl && info.menuItemId === "pyidm_download_page") {
    targetUrl = tab.url;
  }
  
  if (targetUrl) {
    sendToPyIDM(targetUrl);
  }
});

// 3. Optional: Intercept Browser Downloads
let autoIntercept = false;
chrome.storage.local.get(["autoIntercept"], (res) => {
  autoIntercept = res.autoIntercept || false;
});

chrome.downloads.onCreated.addListener((downloadItem) => {
  if (!autoIntercept) return;
  // Ignore data/blob URLs or if from PyIDM
  if (downloadItem.url.startsWith("http://") || downloadItem.url.startsWith("https://")) {
    chrome.downloads.cancel(downloadItem.id, () => {
      chrome.downloads.erase({ id: downloadItem.id });
      sendToPyIDM(downloadItem.url, downloadItem.filename);
    });
  }
});

// 4. Send URL to Local PyIDM Engine
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
    console.log("Sent to PyIDM:", data);
  } catch (err) {
    console.error("Could not reach PyIDM app. Ensure PyIDM is running:", err);
  }
}

