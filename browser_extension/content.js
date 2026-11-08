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

  // 1. Right-click helper: accurately captures media/link URL under mouse (Prioritizes images & videos over enclosing page links!)
  document.addEventListener("contextmenu", (e) => {
    let el = e.target;
    let url = "";

    // Priority 1: Direct media under the cursor (Image, Video, Audio)
    if (el) {
      if (el.tagName === "IMG" && el.src) {
        url = el.src;
      } else if ((el.tagName === "VIDEO" || el.tagName === "AUDIO" || el.tagName === "SOURCE") && (el.currentSrc || el.src)) {
        url = el.currentSrc || el.src;
      }
    }

    // Priority 2: If no direct media, search parents (Image inside link, Video, or Anchor)
    if (!url) {
      let curr = el;
      while (curr && curr !== document.body) {
        if (curr.tagName === "IMG" && curr.src) {
          url = curr.src;
          break;
        }
        if ((curr.tagName === "VIDEO" || curr.tagName === "AUDIO" || curr.tagName === "SOURCE") && (curr.currentSrc || curr.src)) {
          url = curr.currentSrc || curr.src;
          break;
        }
        if (curr.tagName === "A" && curr.href) {
          url = curr.href;
          break;
        }
        curr = curr.parentElement;
      }
    }

    if (!url) {
      url = window.location.href;
    }

    lastTargetUrl = url;
    try {
      chrome.runtime.sendMessage({ type: "UPDATE_LAST_RIGHTCLICK_URL", url: url });
    } catch (err) {}
  }, true);

  // 2. Intercept direct file link clicks (.zip, .mp4, .exe, etc.)
  document.addEventListener("click", (e) => {
    let link = e.target.closest("a");
    if (!link || !link.href) return;

    let cleanUrl = link.href.split("?")[0].toLowerCase();
    let isDownloadable = DOWNLOAD_EXTS.some((ext) => cleanUrl.endsWith(ext));

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

      // Ensure media element is visible and has dimension
      const rect = media.getBoundingClientRect();
      if (rect.width < 50 && rect.height < 50 && media.tagName === "VIDEO") {
        return; // Ignore invisible tracking video pixels
      }

      media.dataset.dmansAttached = "true";

      // Find appropriate container
      let container = media.parentElement;
      const ytPlayer = media.closest(".html5-video-player") || media.closest("#movie_player");
      if (ytPlayer) {
        container = ytPlayer;
      }

      if (!container) return;

      const computedStyle = window.getComputedStyle(container);
      if (computedStyle.position === "static") {
        container.style.position = "relative";
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

        // If it's a blob URL (MSE streaming)
        if (streamUrl.startsWith("blob:")) {
          bar.innerHTML = `<span>⚠️ Blob Stream (Right-click link)</span>`;
          setTimeout(() => {
            bar.innerHTML = `
              <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
              <span>Download with Dmans</span>
            `;
          }, 2500);
          return;
        }

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

      container.appendChild(bar);
    });
  }

  setInterval(attachVideoButtons, 1500);
  attachVideoButtons();
})();
