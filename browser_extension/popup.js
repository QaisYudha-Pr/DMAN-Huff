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
  if (chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(["autoIntercept", "interceptLinks"], (res) => {
      if (toggle) toggle.checked = res.autoIntercept !== false;
      if (linksToggle) linksToggle.checked = res.interceptLinks !== false;
    });

    if (toggle) {
      toggle.addEventListener("change", () => {
        chrome.storage.local.set({ autoIntercept: toggle.checked });
      });
    }

    if (linksToggle) {
      linksToggle.addEventListener("change", () => {
        chrome.storage.local.set({ interceptLinks: linksToggle.checked });
      });
    }
  }
});
