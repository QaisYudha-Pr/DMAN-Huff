// Dmans Extension Popup Controller

document.addEventListener("DOMContentLoaded", () => {
  const dot = document.getElementById("dot");
  const statusText = document.getElementById("status-text");
  const toggle = document.getElementById("intercept-toggle");
  const linksToggle = document.getElementById("links-toggle");

  // Check if Dmans Desktop App is running on localhost:18888
  fetch("http://127.0.0.1:18888/ping")
    .then((r) => r.json())
    .then((d) => {
      if (dot && statusText) {
        dot.className = "dot online";
        statusText.textContent = "Dmans Engine: Connected";
      }
    })
    .catch(() => {
      if (dot && statusText) {
        dot.className = "dot offline";
        statusText.textContent = "Dmans Engine: Offline (Open Dmans)";
      }
    });

  // Load storage settings
  if (typeof chrome !== "undefined" && chrome && chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(["autoIntercept", "interceptLinks"], (res) => {
      if (chrome.runtime && chrome.runtime.lastError) return;
      if (toggle && res) toggle.checked = res.autoIntercept !== false;
      if (linksToggle && res) linksToggle.checked = res.interceptLinks !== false;
    });

    if (toggle) {
      toggle.addEventListener("change", () => {
        try { chrome.storage.local.set({ autoIntercept: toggle.checked }); } catch (e) {}
      });
    }

    if (linksToggle) {
      linksToggle.addEventListener("change", () => {
        try { chrome.storage.local.set({ interceptLinks: linksToggle.checked }); } catch (e) {}
      });
    }
  }
});

