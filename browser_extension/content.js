// Dmans Content Script - Media Sniffer & Floating Download Bar

(function () {
  const DOWNLOAD_EXTS = [
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
    ".exe", ".msi", ".apk", ".dmg", ".bin",
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv",
    ".mp3", ".wav", ".flac", ".aac", ".ogg",
    ".pdf", ".epub", ".docx", ".xlsx"
  ];

  let lastTargetUrl = "";

  // 1. Right-click helper: captures target link/media url
  document.addEventListener("contextmenu", (e) => {
    let el = e.target;
    let url = "";

    while (el && el !== document.body) {
      if (el.tagName === "A" && el.href) {
        url = el.href;
        break;
      }
      if ((el.tagName === "VIDEO" || el.tagName === "AUDIO" || el.tagName === "SOURCE") && el.src) {
        url = el.src;
        break;
      }
      if (el.currentSrc) {
        url = el.currentSrc;
        break;
      }
      el = el.parentElement;
    }

    if (!url) {
      url = window.location.href;
    }

    lastTargetUrl = url;
    try {
      chrome.runtime.sendMessage({ type: "UPDATE_LAST_RIGHTCLICK_URL", url: url });
    } catch (err) {}
  }, true);

  // 2. Intercept direct file links
  document.addEventListener("click", (e) => {
    let link = e.target.closest("a");
    if (!link || !link.href) return;

    let href = link.href.split("?")[0].toLowerCase();
    let isDownloadable = DOWNLOAD_EXTS.some((ext) => href.endsWith(ext));

    if (isDownloadable) {
      try {
        chrome.runtime.sendMessage({
          type: "INTERCEPT_LINK_CLICK",
          url: link.href
        }, (res) => {
          if (chrome.runtime.lastError) return;
          if (res && res.handled) {
            e.preventDefault();
            e.stopPropagation();
          }
        });
      } catch (err) {}
    }
  }, true);

  // 3. IDM-style Floating Video & Audio Download Bar
  function attachVideoButtons() {
    const mediaElements = document.querySelectorAll("video, audio");
    mediaElements.forEach((media) => {
      if (media.dataset.dmansAttached) return;
      media.dataset.dmansAttached = "true";

      const parent = media.parentElement;
      if (!parent) return;

      const computedStyle = window.getComputedStyle(parent);
      if (computedStyle.position === "static") {
        parent.style.position = "relative";
      }

      const bar = document.createElement("div");
      bar.className = "pyidm-video-bar";
      bar.innerHTML = `
        <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
        <span>Download with Dmans</span>
      `;

      bar.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();

        let streamUrl = media.currentSrc || media.src;
        if (!streamUrl) {
          const source = media.querySelector("source");
          if (source) streamUrl = source.src;
        }
        if (!streamUrl) streamUrl = window.location.href;

        try {
          chrome.runtime.sendMessage({
            type: "DOWNLOAD_URL",
            url: streamUrl
          });
        } catch (err) {}

        bar.innerHTML = `<span>✓ Sent to Dmans</span>`;
        setTimeout(() => {
          bar.innerHTML = `
            <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
            <span>Download with Dmans</span>
          `;
        }, 2000);
      });

      parent.appendChild(bar);
    });
  }

  setInterval(attachVideoButtons, 2000);
  attachVideoButtons();
})();
