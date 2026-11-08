// Dmans Content Script - Media Sniffer & IDM-Style Quality Selector

(function () {
  const DOWNLOAD_EXTS = [
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
    ".exe", ".msi", ".apk", ".dmg", ".bin",
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv",
    ".mp3", ".wav", ".flac", ".aac", ".ogg",
    ".pdf", ".epub", ".docx", ".xlsx"
  ];

  let lastTargetUrl = "";
  let activeQualityMenu = null;

  // Close open menus on outside click
  document.addEventListener("click", (e) => {
    if (activeQualityMenu && !activeQualityMenu.contains(e.target)) {
      activeQualityMenu.remove();
      activeQualityMenu = null;
    }
  }, true);

  // 1. Right-click helper: captures exact media/video URL
  document.addEventListener("contextmenu", (e) => {
    let el = e.target;
    let url = "";

    // Priority 0: YouTube video card / link
    if (el) {
      let videoLink = el.closest ? el.closest('a[href*="watch?v="], a[href*="youtu.be/"], a[href*="/shorts/"]') : null;
      if (videoLink && videoLink.href) {
        url = videoLink.href;
      }
    }

    // Priority 1: Direct media under cursor (Image, Video, Audio)
    if (!url && el) {
      if (el.tagName === "IMG" && el.src) {
        url = el.src;
      } else if ((el.tagName === "VIDEO" || el.tagName === "AUDIO" || el.tagName === "SOURCE") && (el.currentSrc || el.src)) {
        url = el.currentSrc || el.src;
      }
    }

    // Priority 2: Direct media inside parent elements (e.g. Pinterest pin image wrapper)
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

    if (!url || url.startsWith("blob:")) {
      url = window.location.href;
    }

    lastTargetUrl = url;
    try {
      if (typeof chrome !== "undefined" && chrome && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ type: "UPDATE_LAST_RIGHTCLICK_URL", url: url });
      }
    } catch (err) {}
  }, true);

  // 2. Intercept direct file links (.zip, .mp4, .exe, etc.)
  document.addEventListener("click", (e) => {
    let link = e.target.closest ? e.target.closest("a") : null;
    if (!link || !link.href) return;

    let cleanUrl = link.href.split("?")[0].toLowerCase();
    let isDownloadable = DOWNLOAD_EXTS.some((ext) => cleanUrl.endsWith(ext));

    if (isDownloadable) {
      try {
        if (typeof chrome !== "undefined" && chrome && chrome.runtime && chrome.runtime.sendMessage) {
          chrome.runtime.sendMessage({
            type: "INTERCEPT_LINK_CLICK",
            url: link.href
          }, (res) => {
            if (chrome.runtime && chrome.runtime.lastError) return;
            if (res && res.handled) {
              e.preventDefault();
              e.stopPropagation();
            }
          });
        }
      } catch (err) {}
    }
  }, true);

  // 3. IDM-Grade Floating Video Bar with Multi-Quality Selection
  function attachVideoButtons() {
    const mediaElements = document.querySelectorAll("video, audio");
    mediaElements.forEach((media) => {
      if (media.dataset.dmansAttached) return;

      const rect = media.getBoundingClientRect();
      if (rect.width < 50 && rect.height < 50 && media.tagName === "VIDEO") {
        return;
      }

      media.dataset.dmansAttached = "true";

      let container = media.parentElement;
      const ytPlayer = media.closest ? (media.closest(".html5-video-player") || media.closest("#movie_player")) : null;
      if (ytPlayer) {
        container = ytPlayer;
      }

      if (!container) return;

      const computedStyle = window.getComputedStyle(container);
      if (computedStyle.position === "static") {
        container.style.position = "relative";
      }

      const wrapper = document.createElement("div");
      wrapper.className = "dmans-floating-wrapper";

      const bar = document.createElement("div");
      bar.className = "dmans-video-bar";
      bar.innerHTML = `
        <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
        <span>Download this video</span>
        <span class="dmans-caret">▼</span>
      `;

      bar.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();

        if (activeQualityMenu) {
          activeQualityMenu.remove();
          activeQualityMenu = null;
          return;
        }

        // Build stream URL
        let streamUrl = "";
        if (window.location.hostname.includes("youtube.com") || window.location.hostname.includes("youtu.be")) {
          streamUrl = window.location.href;
        } else {
          streamUrl = media.currentSrc || media.src;
          if (!streamUrl) {
            const source = media.querySelector("source");
            if (source) streamUrl = source.src;
          }
          if (!streamUrl || streamUrl.startsWith("blob:")) {
            streamUrl = window.location.href;
          }
        }

        // Show IDM-Style Quality Menu
        const menu = document.createElement("div");
        menu.className = "dmans-quality-menu";
        menu.innerHTML = `
          <div class="dmans-quality-header">Download Quality</div>
          <div class="dmans-quality-item" data-q="1080p">
            <span>🎬 1080p</span>
            <span class="dmans-badge">Full HD</span>
          </div>
          <div class="dmans-quality-item" data-q="720p">
            <span>🎬 720p</span>
            <span class="dmans-badge">HD</span>
          </div>
          <div class="dmans-quality-item" data-q="480p">
            <span>🎬 480p</span>
            <span class="dmans-badge">SD</span>
          </div>
          <div class="dmans-quality-item" data-q="360p">
            <span>🎬 360p</span>
            <span class="dmans-badge">Fast</span>
          </div>
          <div class="dmans-quality-item" data-q="audio">
            <span>🎵 Audio Only</span>
            <span class="dmans-badge">MP3/M4A</span>
          </div>
        `;

        menu.querySelectorAll(".dmans-quality-item").forEach((item) => {
          item.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();

            const quality = item.dataset.q;
            try {
              if (typeof chrome !== "undefined" && chrome && chrome.runtime && chrome.runtime.sendMessage) {
                chrome.runtime.sendMessage({
                  type: "DOWNLOAD_URL",
                  url: streamUrl,
                  quality: quality
                });
              }
            } catch (err) {}

            bar.innerHTML = `<span>✓ Sent ${quality} to Dmans</span>`;
            menu.remove();
            activeQualityMenu = null;

            setTimeout(() => {
              bar.innerHTML = `
                <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                <span>Download this video</span>
                <span class="dmans-caret">▼</span>
              `;
            }, 2500);
          });
        });

        wrapper.appendChild(menu);
        activeQualityMenu = menu;
      });

      wrapper.appendChild(bar);
      container.appendChild(wrapper);
    });
  }

  setInterval(attachVideoButtons, 1500);
})();
