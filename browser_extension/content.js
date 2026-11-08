// Dmans Content Script - Media Sniffer & IDM-Style Floating Video Bar

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

  // 1. Close open quality menu on click outside
  document.addEventListener("click", (e) => {
    if (activeQualityMenu && !activeQualityMenu.contains(e.target)) {
      activeQualityMenu.remove();
      activeQualityMenu = null;
      document.querySelectorAll(".dmans-floating-wrapper.dmans-active").forEach(el => {
        el.classList.remove("dmans-active");
      });
    }
  }, true);

  // 2. Extract clean video page URL or direct stream URL
  function getCleanVideoUrl(media) {
    const pageUrl = window.location.href;
    if (window.location.hostname.includes("youtube.com")) {
      try {
        const parsed = new URL(pageUrl);
        const v = parsed.searchParams.get("v");
        if (v) return `https://www.youtube.com/watch?v=${v}`;
        if (parsed.pathname.startsWith("/shorts/")) return pageUrl.split("?")[0];
      } catch (e) {}
      return pageUrl.split("&list=")[0];
    }
    if (window.location.hostname.includes("youtu.be")) {
      return pageUrl.split("?")[0];
    }
    if (media && media.currentSrc && !media.currentSrc.startsWith("blob:")) {
      return media.currentSrc;
    }
    if (media && media.src && !media.src.startsWith("blob:")) {
      return media.src;
    }
    return pageUrl;
  }

  // 3. Extract human-readable video title
  function getVideoTitle() {
    if (window.location.hostname.includes("youtube.com")) {
      const titleEl = document.querySelector("h1.ytd-watch-metadata yt-formatted-string, #title h1, h1.title, .ytp-title-link");
      if (titleEl && titleEl.textContent && titleEl.textContent.trim()) {
        return titleEl.textContent.trim();
      }
    }
    return document.title.replace(" - YouTube", "").trim() || "video";
  }

  // 4. Capture right-clicked element URL for context menu
  document.addEventListener("contextmenu", (e) => {
    let el = e.target;
    let url = "";

    if (el) {
      let videoLink = el.closest ? el.closest('a[href*="watch?v="], a[href*="youtu.be/"], a[href*="/shorts/"]') : null;
      if (videoLink && videoLink.href) {
        url = videoLink.href;
      }
    }

    if (!url && el) {
      if (el.tagName === "IMG" && el.src) {
        url = el.src;
      } else if ((el.tagName === "VIDEO" || el.tagName === "AUDIO" || el.tagName === "SOURCE") && (el.currentSrc || el.src)) {
        url = el.currentSrc || el.src;
      }
    }

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

  // 5. Intercept downloadable file links
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

  // 6. IDM Floating Bar Dispatch Helper
  function dispatchDownload(streamUrl, quality, bar) {
    const title = getVideoTitle();
    const btnLabel = bar.querySelector(".dmans-btn-main span");
    if (btnLabel) btnLabel.textContent = `⏳ Sending ${quality}...`;

    try {
      if (typeof chrome !== "undefined" && chrome && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({
          type: "DOWNLOAD_URL",
          url: streamUrl,
          filename: title,
          quality: quality
        }, (res) => {
          if (chrome.runtime && chrome.runtime.lastError) return;
          if (btnLabel) {
            if (res && res.offline) {
              btnLabel.textContent = "⚠️ Dmans Belum Dibuka";
            } else {
              btnLabel.textContent = `✓ Started (${quality})`;
            }
          }
        });
      }
    } catch (e) {}

    setTimeout(() => {
      if (btnLabel) btnLabel.textContent = "Download this video";
    }, 2800);
  }

  // 7. Guaranteed IDM Floating Bar Attachment
  function attachToVideo(media) {
    if (!media || !document.contains(media)) return;

    const rect = media.getBoundingClientRect();
    if (rect.width < 80 && rect.height < 60 && media.tagName === "VIDEO") {
      return;
    }

    let container = media.parentElement;
    const ytPlayer = media.closest ? (media.closest(".html5-video-player") || media.closest("#movie_player")) : null;
    if (ytPlayer) {
      container = ytPlayer;
    }
    if (!container) return;

    // Check if bar already exists in this container
    if (container.querySelector(".dmans-floating-wrapper")) {
      return;
    }

    const computedStyle = window.getComputedStyle(container);
    if (computedStyle.position === "static") {
      container.style.position = "relative";
    }

    const wrapper = document.createElement("div");
    wrapper.className = "dmans-floating-wrapper";

    // Isolate clicks completely from video player (never pause or trigger fullscreen)
    ["click", "mousedown", "mouseup", "dblclick", "contextmenu"].forEach(evtName => {
      wrapper.addEventListener(evtName, (e) => {
        e.stopPropagation();
        e.stopImmediatePropagation();
      }, true);
    });

    const bar = document.createElement("div");
    bar.className = "dmans-video-bar";
    bar.innerHTML = `
      <div class="dmans-btn-main" title="Download this video with Dmans (1080p)">
        <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
        <span>Download this video</span>
      </div>
      <div class="dmans-btn-dropdown" title="Choose format & resolution">
        <span class="dmans-caret">▼</span>
      </div>
    `;

    // Click on Main Button -> Download Best / 1080p
    const btnMain = bar.querySelector(".dmans-btn-main");
    btnMain.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const streamUrl = getCleanVideoUrl(media);
      dispatchDownload(streamUrl, "1080p", bar);
    });

    // Click on Dropdown Caret -> Show Quality Menu
    const btnDropdown = bar.querySelector(".dmans-btn-dropdown");
    btnDropdown.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();

      if (activeQualityMenu) {
        activeQualityMenu.remove();
        activeQualityMenu = null;
        wrapper.classList.remove("dmans-active");
        return;
      }

      const streamUrl = getCleanVideoUrl(media);
      const menu = document.createElement("div");
      menu.className = "dmans-quality-menu";
      menu.innerHTML = `
        <div class="dmans-quality-header">
          <span>Video Quality</span>
          <span style="font-size:9px;color:#94a3b8">Dmans</span>
        </div>
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

      menu.querySelectorAll(".dmans-quality-item").forEach(item => {
        item.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const quality = item.dataset.q;
          dispatchDownload(streamUrl, quality, bar);
          menu.remove();
          activeQualityMenu = null;
          wrapper.classList.remove("dmans-active");
        });
      });

      wrapper.appendChild(menu);
      activeQualityMenu = menu;
      wrapper.classList.add("dmans-active");
    });

    wrapper.appendChild(bar);
    container.appendChild(wrapper);
  }

  function scanAndAttach() {
    const mediaElements = document.querySelectorAll("video, audio");
    mediaElements.forEach(attachToVideo);
  }

  // 8. Event triggers for single-page apps (YouTube, TikTok, Netflix, etc.)
  ["yt-navigate-finish", "spfdone", "popstate", "DOMContentLoaded", "load"].forEach(evtName => {
    window.addEventListener(evtName, () => {
      setTimeout(scanAndAttach, 400);
      setTimeout(scanAndAttach, 1200);
    });
  });

  // Watch for dynamic video elements added to DOM
  const observer = new MutationObserver(() => {
    scanAndAttach();
  });
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    document.addEventListener("DOMContentLoaded", () => {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }

  // Fallback poll
  setInterval(scanAndAttach, 1200);
  scanAndAttach();
})();
