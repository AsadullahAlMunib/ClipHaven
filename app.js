const $ = (id) => document.getElementById(id);
let timer = null;
let currentJobId = null;
let previewTimer = null;
let previewSeq = 0;
let lastPreviewUrl = "";
let currentTitleHint = "";
let currentDurationHint = 0;
let currentPlaylistCount = 0;
let isCurrentUrlPlaylist = false;
let currentPlaylistEntries = [];
let lastCompletedPath = "";
let androidReqSeq = 0;
const androidPending = {};

window.__onAndroidApiResult = (reqId, data) => {
  const cb = androidPending[reqId];
  if (cb) {
    delete androidPending[reqId];
    cb(data);
  }
};

function formatDisplayFolder(path) {
  if (!path) return "";
  let p = String(path).trim();
  // Only format internal storage paths on Android; keep full desktop drive paths (C:\..., D:\..., /home/...) completely untouched
  if (!window.ClipHavenAndroid) return p;
  // Replace the leading storage root prefix with empty string ""
  p = p.replace(/^\/(?:storage\/emulated\/\d+|storage\/sdcard\d+|sdcard)\/?/i, "");
  p = p.replace(/^Internal Storage\/?/i, "");
  return p || "Download/ClipHaven";
}

function normalizeInputUrl(raw) {
  if (!raw) return "";
  const s = String(raw).trim();
  const httpMatch = s.match(/https?:\/\/[^\s<>"']+/i);
  if (httpMatch) {
    return httpMatch[0]
      .replace(/[.,;)!\]>]+$/, "")
      .replace(/^http:\/\//i, "https://");
  }
  const bareMatch = s.match(
    /(?:www\.)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\/[^\s<>"']*/,
  );
  if (bareMatch) {
    return "https://" + bareMatch[0].replace(/[.,;)!\]>]+$/, "");
  }
  return s;
}

function status(
  title,
  detail,
  pct = 0,
  pill = "Working",
  cls = "",
  speed = "",
  eta = "",
  showOpenBtn = false,
  indeterminate = false,
  playlistInfo = null,
) {
  $("status").classList.add("show");
  $("title").textContent = title;
  $("title").className = "status-title " + cls;
  $("detail").textContent = detail || "";

  const progEl = $("progress");
  if (indeterminate) {
    progEl.removeAttribute("value");
    progEl.classList.add("indeterminate");
  } else {
    progEl.classList.remove("indeterminate");
    progEl.value = Math.max(0, Math.min(100, pct));
  }
  $("pill").textContent = pill;

  const plEl = $("playlist-pill");
  if (playlistInfo && playlistInfo.total > 1) {
    const idx = playlistInfo.index || 1;
    const tot = playlistInfo.total;
    const done = playlistInfo.done ?? Math.max(0, idx - 1);
    const left = playlistInfo.left ?? Math.max(0, tot - idx);
    plEl.textContent = `📑 ${idx}/${tot} • ${done} done • ${left} left`;
    plEl.style.display = "inline-block";
  } else {
    plEl.style.display = "none";
  }

  const speedEl = $("speed-pill");
  const etaEl = $("eta-pill");
  if (speed) {
    speedEl.textContent = "⚡ " + speed;
    speedEl.style.display = "inline-block";
  } else {
    speedEl.style.display = "none";
  }
  if (eta) {
    etaEl.textContent = "⏱ ETA " + eta;
    etaEl.style.display = "inline-block";
  } else {
    etaEl.style.display = "none";
  }
  $("open-folder-btn").style.display = showOpenBtn ? "inline-block" : "none";
}

async function api(path, opts = {}) {
  if (window.ClipHavenAndroid) {
    if (typeof window.ClipHavenAndroid.requestAsync === "function") {
      const d = await new Promise((resolve) => {
        const reqId = "req_" + ++androidReqSeq + "_" + Date.now();
        androidPending[reqId] = resolve;
        window.ClipHavenAndroid.requestAsync(
          reqId,
          path,
          opts.method || "GET",
          opts.body || "{}",
        );
      });
      if (!d || d.ok === false) throw Error((d && d.error) || "Request failed");
      return d;
    }
    if (typeof window.ClipHavenAndroid.request === "function") {
      const rawResp = window.ClipHavenAndroid.request(
        path,
        opts.method || "GET",
        opts.body || "{}",
      );
      const d = JSON.parse(rawResp);
      if (d.ok === false) throw Error(d.error || "Request failed");
      return d;
    }
  }

  const r = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  let d;
  try {
    d = await r.json();
  } catch {
    throw Error(
      "Backend response was not valid JSON. Check that ClipHaven is running.",
    );
  }
  if (!r.ok || d.ok === false) throw Error(d.error || "Request failed");
  return d;
}

// Theme management
const themeBtn = $("theme");
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  themeBtn.textContent = t === "light" ? "🌙 Dark" : "☀️ Light";
  localStorage.setItem("theme", t);
}
applyTheme(
  localStorage.getItem("theme") ||
    (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"),
);
themeBtn.onclick = () =>
  applyTheme(
    document.documentElement.getAttribute("data-theme") === "light"
      ? "dark"
      : "light",
  );

function getSelectedPlaylistIndices() {
  const boxes = document.querySelectorAll(".pl-item-checkbox");
  if (!boxes.length) return [];
  const selected = [];
  boxes.forEach((b) => {
    if (b.checked) selected.push(Number(b.value));
  });
  return selected;
}

function getPlaylistItemsParam() {
  if (!$("allow-playlist").checked || !currentPlaylistEntries.length) return "";
  const selected = getSelectedPlaylistIndices();
  if (!selected.length || selected.length === currentPlaylistEntries.length) {
    return "";
  }
  return selected.join(",");
}

function renderPlaylistSelector(entries) {
  const selector = $("playlist-selector");
  const listEl = $("playlist-items-list");
  const scrollHint = $("playlist-scroll-hint");
  listEl.innerHTML = "";
  if (!isCurrentUrlPlaylist || !entries || !entries.length) {
    selector.style.display = "none";
    if (scrollHint) scrollHint.style.display = "none";
    return;
  }
  selector.style.display = "block";
  if (scrollHint) {
    if (entries.length > 5) {
      scrollHint.textContent = `↕ Scroll (${entries.length} videos)`;
      scrollHint.style.display = "inline-block";
    } else {
      scrollHint.style.display = "none";
    }
  }
  entries.forEach((item, i) => {
    const idx = item.index || i + 1;
    const row = document.createElement("label");
    row.className = "playlist-item-row";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "pl-item-checkbox";
    cb.value = String(idx);
    cb.checked = true;
    cb.onchange = () => {
      const sel = getSelectedPlaylistIndices();
      $("allow-playlist").checked = sel.length > 0;
      updateExtraOptionsBadge();
    };

    const idxSpan = document.createElement("span");
    idxSpan.className = "playlist-item-idx";
    idxSpan.textContent = `#${idx}`;

    const titleSpan = document.createElement("span");
    titleSpan.className = "playlist-item-title";
    titleSpan.textContent = item.title || `Video ${idx}`;

    row.appendChild(cb);
    row.appendChild(idxSpan);
    row.appendChild(titleSpan);

    if (item.duration) {
      const durSpan = document.createElement("span");
      durSpan.className = "playlist-item-dur";
      durSpan.textContent = item.duration;
      row.appendChild(durSpan);
    }
    listEl.appendChild(row);
  });
}

// Extra Options active badge indicator & playlist badge sync
function syncPlaylistBadgeText() {
  const badge = $("preview-playlist");
  const selBadge = $("playlist-selector-badge");
  if (!isCurrentUrlPlaylist) {
    badge.style.display = "none";
    if ($("playlist-selector")) $("playlist-selector").style.display = "none";
    return;
  }
  const total = currentPlaylistEntries.length || currentPlaylistCount;
  const selected = getSelectedPlaylistIndices();
  const isAll = $("allow-playlist").checked;

  if (!isAll || (currentPlaylistEntries.length > 0 && selected.length === 0)) {
    const countStr = total > 1 ? ` (${total} videos)` : "";
    badge.textContent = `📑 Playlist${countStr} • Single`;
    if (selBadge) selBadge.textContent = "Single Video Only";
  } else if (currentPlaylistEntries.length > 0 && selected.length < total) {
    badge.textContent = `✅ ${selected.length}/${total} Videos Selected ▾`;
    if (selBadge) selBadge.textContent = `${selected.length} of ${total} Selected ▾`;
  } else {
    const countStr = total > 1 ? ` (${total} videos)` : "";
    badge.textContent = `✅ All Playlist Videos${countStr} ▾`;
    if (selBadge) selBadge.textContent = total > 1 ? `All ${total} Selected ▾` : "All Selected ▾";
  }
  badge.style.display = "inline-block";
}

function updateExtraOptionsBadge() {
  const fmt = $("format").value;
  const isAudio = ["mp3", "m4a", "wav"].includes(fmt);
  const canThumb = ["mp4", "mkv", "mp3", "m4a"].includes(fmt);
  const hasTrim =
    $("start-time").value.trim() !== "" || $("end-time").value.trim() !== "";
  const hasChecks =
    (!isAudio && $("subtitles").checked) ||
    (canThumb && $("embed-thumbnail").checked) ||
    $("allow-playlist").checked;
  $("active-options-badge").style.display =
    hasTrim || hasChecks ? "inline-block" : "none";
  syncPlaylistBadgeText();
}

// Format & Quality toggle (also guards format-specific checkboxes)
$("format").onchange = () => {
  const fmt = $("format").value;
  const audio = ["mp3", "m4a", "wav"].includes(fmt);
  const canThumb = ["mp4", "mkv", "mp3", "m4a"].includes(fmt);

  $("quality").disabled = audio;
  $("quality").style.opacity = audio ? "0.5" : "1";

  $("subtitles").disabled = audio;
  $("subtitles").parentElement.style.opacity = audio ? "0.5" : "1";
  $("subtitles").parentElement.title = audio
    ? "Subtitles apply to video formats (MP4, MKV, WEBM)"
    : "";

  $("embed-thumbnail").disabled = !canThumb;
  $("embed-thumbnail").parentElement.style.opacity = canThumb ? "1" : "0.5";
  $("embed-thumbnail").parentElement.title = canThumb
    ? ""
    : "Cover art embedding is supported for MP4, MKV, MP3, and M4A";

  updateExtraOptionsBadge();
};
$("format").onchange();

// Save folder persistence & Browse button
$("folder").addEventListener("change", () => {
  const val = formatDisplayFolder($("folder").value);
  $("folder").value = val;
  if (val) localStorage.setItem("cliphaven_folder", val);
});

$("browse-folder-btn").onclick = async () => {
  const btn = $("browse-folder-btn");
  const prevText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "📁 Browsing…";
  try {
    const d = await api("/api/pick-folder", {
      method: "POST",
      body: JSON.stringify({ current: $("folder").value.trim() }),
    });
    if (!d.cancelled && d.folder) {
      const displayPath = formatDisplayFolder(d.folder);
      $("folder").value = displayPath;
      localStorage.setItem("cliphaven_folder", displayPath);
    }
  } catch (e) {
    status("Could not open folder picker", e.message, 0, "Error", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = prevText;
  }
};

[
  "start-time",
  "end-time",
  "subtitles",
  "embed-thumbnail",
  "allow-playlist",
].forEach((id) => {
  $(id).addEventListener("input", updateExtraOptionsBadge);
  $(id).addEventListener("change", updateExtraOptionsBadge);
});

// Interactive playlist badge & selector buttons
$("preview-playlist").onclick = () => {
  const selector = $("playlist-selector");
  if (selector && selector.style.display !== "none") {
    selector.open = !selector.open;
  } else {
    const cb = $("allow-playlist");
    cb.checked = !cb.checked;
    updateExtraOptionsBadge();
  }
};

$("allow-playlist").addEventListener("change", () => {
  const checked = $("allow-playlist").checked;
  const boxes = document.querySelectorAll(".pl-item-checkbox");
  if (boxes.length) {
    const sel = getSelectedPlaylistIndices();
    if (checked && sel.length === 0) {
      boxes.forEach((b) => (b.checked = true));
    } else if (!checked) {
      boxes.forEach((b) => (b.checked = false));
    }
  }
  updateExtraOptionsBadge();
});

$("pl-select-all-btn").onclick = () => {
  document.querySelectorAll(".pl-item-checkbox").forEach((b) => (b.checked = true));
  $("allow-playlist").checked = true;
  updateExtraOptionsBadge();
};

$("pl-clear-all-btn").onclick = () => {
  document.querySelectorAll(".pl-item-checkbox").forEach((b) => (b.checked = false));
  $("allow-playlist").checked = false;
  updateExtraOptionsBadge();
};

// Hide broken thumbnail images gracefully
$("preview-thumb").onerror = () => {
  $("preview-thumb").style.display = "none";
};

// Clear URL button visibility & action
function syncClearBtn() {
  $("clear-url-btn").style.display = $("url").value.trim() ? "grid" : "none";
}

$("clear-url-btn").onclick = () => {
  $("url").value = "";
  syncClearBtn();
  hidePreview();
  $("url").focus();
};

function extractYouTubeId(url) {
  const m = String(url || "").match(/(?:v=|youtu\.be\/|\/shorts\/|\/live\/|\/embed\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : "";
}

// One-click Clipboard Paste button (triggers instant 0ms preview)
$("paste-btn").onclick = async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      $("url").value = normalizeInputUrl(text.trim());
      syncClearBtn();
      triggerPreview(true);
    }
  } catch {
    $("url").focus();
  }
};

// Auto Video Info Preview with sequence guard against race conditions
function hidePreview() {
  previewSeq++;
  lastPreviewUrl = "";
  $("preview-card").style.display = "none";
  $("playlist-selector").style.display = "none";
  $("playlist-items-list").innerHTML = "";
  currentTitleHint = "";
  currentDurationHint = 0;
  currentPlaylistCount = 0;
  currentPlaylistEntries = [];
  isCurrentUrlPlaylist = false;
}

async function fetchPreview(rawUrl) {
  const clean = normalizeInputUrl(rawUrl);
  if (!clean || !clean.startsWith("https://")) {
    hidePreview();
    return;
  }
  if (clean === lastPreviewUrl) return;
  lastPreviewUrl = clean;

  const seq = ++previewSeq;
  currentTitleHint = "";
  currentDurationHint = 0;
  currentPlaylistCount = 0;
  currentPlaylistEntries = [];
  isCurrentUrlPlaylist = false;
  $("playlist-selector").style.display = "none";
  $("playlist-items-list").innerHTML = "";
  $("preview-card").style.display = "flex";
  const ytId = extractYouTubeId(clean);
  if (ytId) {
    $("preview-thumb").src = `https://i.ytimg.com/vi/${ytId}/hqdefault.jpg`;
    $("preview-thumb").style.display = "block";
  } else {
    $("preview-thumb").style.display = "none";
  }
  $("preview-title").textContent = "Checking video link…";
  $("preview-uploader").textContent = "Please wait";
  $("preview-dot").style.display = "none";
  $("preview-duration").style.display = "none";
  $("preview-playlist").style.display = "none";

  try {
    const d = await api("/api/info", {
      method: "POST",
      body: JSON.stringify({ url: clean }),
    });
    if (seq !== previewSeq) return;
    const info = d.info || {};
    currentTitleHint = info.title || "";
    currentDurationHint = info.duration_seconds || 0;
    isCurrentUrlPlaylist = Boolean(info.is_playlist);
    currentPlaylistCount = info.playlist_count || 0;
    currentPlaylistEntries = Array.isArray(info.entries) ? info.entries : [];
    // Default to downloading all playlist videos automatically when a playlist link is pasted
    $("allow-playlist").checked = isCurrentUrlPlaylist;
    renderPlaylistSelector(currentPlaylistEntries);
    $("preview-title").textContent = info.title || "Video ready to download";
    $("preview-uploader").textContent = info.uploader || "";
    if (info.thumbnail) {
      $("preview-thumb").src = info.thumbnail;
      $("preview-thumb").style.display = "block";
    }
    if (info.duration) {
      $("preview-dot").style.display = "inline";
      $("preview-duration").textContent = info.duration;
      $("preview-duration").style.display = "inline-block";
    }
    updateExtraOptionsBadge();
  } catch (err) {
    if (seq === previewSeq) {
      $("preview-thumb").style.display = "none";
      $("preview-dot").style.display = "none";
      $("preview-duration").style.display = "none";
      $("preview-playlist").style.display = "none";
      $("preview-title").textContent = "Preview unavailable";
      $("preview-uploader").textContent =
        (err && err.message) || "Check link or click Download Now to try directly.";
    }
  }
}

function triggerPreview(immediate = false) {
  syncClearBtn();
  if (previewTimer) clearTimeout(previewTimer);
  if (immediate) {
    fetchPreview($("url").value);
  } else {
    previewTimer = setTimeout(() => fetchPreview($("url").value), 180);
  }
}

$("url").addEventListener("input", () => triggerPreview(false));
$("url").addEventListener("paste", () =>
  setTimeout(() => {
    const cleaned = normalizeInputUrl($("url").value);
    if (cleaned && cleaned !== $("url").value) {
      $("url").value = cleaned;
    }
    triggerPreview(true);
  }, 20),
);

// Open folder button
async function openFolder(pathOrJobId = {}) {
  try {
    await api("/api/open-folder", {
      method: "POST",
      body: JSON.stringify(pathOrJobId),
    });
  } catch (e) {
    status("Could not open folder", e.message, 0, "Error", "error");
  }
}

$("open-folder-btn").onclick = () => {
  openFolder({ path: lastCompletedPath || $("folder").value.trim() });
};

// Recent Downloads History management
function getSavedHistory() {
  try {
    return JSON.parse(localStorage.getItem("cliphaven_history") || "[]");
  } catch {
    return [];
  }
}

function addToHistory(item) {
  const list = getSavedHistory().filter((x) => x.id !== item.id);
  list.unshift({
    id: item.id,
    title: item.video_title || item.detail || "Downloaded clip",
    format: item.format || "MP4",
    quality: item.quality || "Best",
    file_path: item.file_path || item.folder || "",
    time: new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
  });
  localStorage.setItem("cliphaven_history", JSON.stringify(list.slice(0, 8)));
  renderHistory();
  setTimeout(checkForAppUpdates, 700);
}

function renderHistory() {
  const list = getSavedHistory();
  const section = $("history-section");
  const container = $("history-list");
  if (!list.length) {
    section.style.display = "none";
    return;
  }
  section.style.display = "block";
  container.innerHTML = "";
  list.forEach((item) => {
    const row = document.createElement("div");
    row.className = "history-item";

    const meta = document.createElement("div");
    meta.className = "history-meta";

    const title = document.createElement("div");
    title.className = "history-title";
    title.textContent = item.title;

    const sub = document.createElement("div");
    sub.className = "history-sub";
    sub.textContent = `${item.format} • ${item.quality} • ${item.time}`;

    meta.appendChild(title);
    meta.appendChild(sub);

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "btn secondary small-btn";
    openBtn.textContent = "📂 Show";
    openBtn.onclick = () => openFolder({ path: item.file_path });

    row.appendChild(meta);
    row.appendChild(openBtn);
    container.appendChild(row);
  });
}

$("clear-history").onclick = () => {
  localStorage.removeItem("cliphaven_history");
  renderHistory();
};

// Cancel download button
$("cancel").onclick = async () => {
  if (!currentJobId) return;
  const cb = $("cancel");
  cb.disabled = true;
  try {
    await api("/api/cancel", {
      method: "POST",
      body: JSON.stringify({ id: currentJobId }),
    });
  } catch (e) {
    status("Cancel failed", e.message, 0, "Error", "error");
  } finally {
    cb.disabled = false;
  }
};

// Poll active download job
function startPolling(jobId) {
  if (timer) clearInterval(timer);
  currentJobId = jobId;
  let errCount = 0;
  localStorage.setItem("cliphaven_active_job", jobId);
  const b = $("start");
  const cb = $("cancel");
  b.disabled = true;
  b.textContent = "Downloading…";
  cb.style.display = "inline-block";

  timer = setInterval(async () => {
    try {
      const s = await api("/api/status?id=" + encodeURIComponent(jobId));
      errCount = 0;
      const isDone = s.state === "Complete";
      const isErr = s.state === "Error" || s.state === "Cancelled";
      if (s.file_path || s.folder) {
        lastCompletedPath = s.file_path || s.folder;
      }
      const plInfo =
        s.playlist_total && s.playlist_total > 1
          ? {
              index: s.playlist_index,
              total: s.playlist_total,
              done: s.playlist_done,
              left: s.playlist_left,
            }
          : null;
      status(
        s.title || s.state,
        s.detail || "",
        s.percent || 0,
        s.stage || s.state || "Working",
        isErr ? "error" : isDone ? "success" : "",
        s.speed || "",
        s.eta || "",
        isDone,
        Boolean(s.indeterminate && !isDone && !isErr),
        plInfo,
      );
      if (isDone || isErr) {
        clearInterval(timer);
        timer = null;
        b.disabled = false;
        b.textContent = "⬇ Download Another";
        cb.style.display = "none";
        currentJobId = null;
        localStorage.removeItem("cliphaven_active_job");
        if (isDone) {
          addToHistory({ id: jobId, ...s });
        }
      }
    } catch (err) {
      if (++errCount < 4) return;
      clearInterval(timer);
      timer = null;
      status("Status error", err.message, 0, "Error", "error");
      b.disabled = false;
      b.textContent = "⬇ Download Now";
      cb.style.display = "none";
      currentJobId = null;
      localStorage.removeItem("cliphaven_active_job");
    }
  }, 750);
}

// Form submission
$("form").onsubmit = async (e) => {
  e.preventDefault();
  const b = $("start");
  const cb = $("cancel");
  // Prevent duplicate submission if Enter is pressed in an input while a job is already active
  if (currentJobId || b.disabled) return;
  if (timer) clearInterval(timer);

  b.disabled = true;
  b.textContent = "Starting…";
  cb.style.display = "none";
  cb.disabled = false;
  currentJobId = null;

  const chosenFolder = $("folder").value.trim();
  if (chosenFolder) localStorage.setItem("cliphaven_folder", formatDisplayFolder(chosenFolder));

  const fmt = $("format").value;
  const isAudio = ["mp3", "m4a", "wav"].includes(fmt);
  const canThumb = ["mp4", "mkv", "mp3", "m4a"].includes(fmt);
  const cleanUrl = normalizeInputUrl($("url").value);
  if (cleanUrl && cleanUrl !== $("url").value) {
    $("url").value = cleanUrl;
    syncClearBtn();
  }

  status(
    "Starting download",
    "Checking video link and preparing stream…",
    0,
    "Starting",
    "",
    "",
    "",
    false,
    true,
  );
  try {
    const d = await api("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url: cleanUrl,
        folder: chosenFolder,
        quality: $("quality").value,
        format: fmt,
        start_time: $("start-time").value.trim(),
        end_time: $("end-time").value.trim(),
        subtitles: !isAudio && $("subtitles").checked,
        embed_thumbnail: canThumb && $("embed-thumbnail").checked,
        allow_playlist: $("allow-playlist").checked,
        playlist_items: getPlaylistItemsParam(),
        title_hint: currentTitleHint,
        duration_hint: currentDurationHint,
      }),
    });
    startPolling(d.id);
  } catch (err) {
    status("Could not start download", err.message, 0, "Error", "error");
    b.disabled = false;
    b.textContent = "⬇ Download Now";
    cb.style.display = "none";
    currentJobId = null;
  }
};


// In-App Update Check & Self-Updater (Android Auto-Install + Desktop Modal)
let updatePollTimer = null;
let latestUpdateInfo = null;

function showUpdateModal(info) {
  latestUpdateInfo = info;
  const modal = $("update-modal");
  if (!modal) return;
  $("update-version-line").textContent = `v${info.current_version} → v${info.latest_version}`;
  $("update-notes-content").textContent =
    info.release_notes || "Performance improvements and updated platform extractors.";
  const isAndroid = Boolean(window.ClipHavenAndroid || info.is_android);
  $("update-modal-desc").textContent = isAndroid
    ? "Tap Update Now to download and install the update directly inside ClipHaven."
    : "A newer version of ClipHaven is ready. Click below to view and download the update.";
  $("update-now-btn").textContent = isAndroid ? "🚀 Update Now" : "🌐 View & Download Update";
  $("update-now-btn").disabled = false;
  $("update-later-btn").disabled = false;
  $("update-progress-wrap").style.display = "none";
  modal.style.display = "grid";
}

$("update-later-btn").onclick = () => {
  if (updatePollTimer) {
    clearInterval(updatePollTimer);
    updatePollTimer = null;
  }
  $("update-modal").style.display = "none";
};

$("update-now-btn").onclick = async () => {
  if (!latestUpdateInfo) return;
  const isAndroid = Boolean(window.ClipHavenAndroid || latestUpdateInfo.is_android);
  if (!isAndroid) {
    window.open(
      latestUpdateInfo.release_url || "https://github.com/AsadullahAlMunib/ClipHaven/releases/latest",
      "_blank",
      "noopener,noreferrer",
    );
    $("update-modal").style.display = "none";
    return;
  }

  const nowBtn = $("update-now-btn");
  const laterBtn = $("update-later-btn");
  nowBtn.disabled = true;
  nowBtn.textContent = "Downloading…";
  $("update-progress-wrap").style.display = "block";
  $("update-progress-bar").value = 0;
  $("update-progress-text").textContent = "Starting background update download…";

  try {
    await api("/api/self-update", {
      method: "POST",
      body: JSON.stringify({ apk_url: latestUpdateInfo.apk_url || "" }),
    });
    if (updatePollTimer) clearInterval(updatePollTimer);
    updatePollTimer = setInterval(async () => {
      try {
        const st = await api("/api/self-update-status");
        $("update-progress-bar").value = Math.max(0, Math.min(100, st.percent || 0));
        $("update-progress-text").textContent = st.detail || "Downloading update…";
        if (st.state === "Complete") {
          clearInterval(updatePollTimer);
          updatePollTimer = null;
          nowBtn.disabled = false;
          nowBtn.textContent = "✅ Install Update";
          laterBtn.disabled = false;
        } else if (st.state === "Error") {
          clearInterval(updatePollTimer);
          updatePollTimer = null;
          nowBtn.disabled = false;
          nowBtn.textContent = "🔄 Retry Update";
          laterBtn.disabled = false;
        }
      } catch {
        // Ignore transient poll errors
      }
    }, 500);
  } catch (err) {
    $("update-progress-text").textContent = err.message || "Update failed.";
    nowBtn.disabled = false;
    nowBtn.textContent = "🔄 Retry Update";
  }
};

async function checkForAppUpdates() {
  try {
    const info = await api("/api/check-update");
    if (info && info.update_available) {
      showUpdateModal(info);
    }
  } catch {
    // Silent failover if offline or GitHub API unreachable
  }
}

// Startup initialization: load config, FFmpeg check, folder memory, and active job recovery
(async function init() {
  renderHistory();
  const savedFolder = formatDisplayFolder(
    localStorage.getItem("cliphaven_folder") || "",
  );
  if (savedFolder) {
    $("folder").value = savedFolder;
  }
  try {
    const cfg = await api("/api/config");
    if (!savedFolder && cfg.default_folder) {
      $("folder").value = formatDisplayFolder(cfg.default_folder);
    }
    if (cfg.ffmpeg === false) {
      $("ffmpeg-warning").style.display = "block";
    }
    const jobsList = cfg.jobs || [];
    const savedJob = localStorage.getItem("cliphaven_active_job");
    const activeServerJob = jobsList
      .slice()
      .reverse()
      .find((j) => !["Complete", "Error", "Cancelled"].includes(j.state));

    if (savedJob) {
      const match = jobsList.find((j) => j.id === savedJob);
      if (match && !["Complete", "Error", "Cancelled"].includes(match.state)) {
        startPolling(savedJob);
      } else {
        if (match && match.state === "Complete") {
          lastCompletedPath = match.file_path || match.folder || "";
          addToHistory(match);
          status(
            match.title || "Download complete!",
            match.detail || "",
            100,
            "Complete",
            "success",
            "",
            "",
            true,
          );
        }
        localStorage.removeItem("cliphaven_active_job");
        if (activeServerJob) {
          startPolling(activeServerJob.id);
        }
      }
    } else if (activeServerJob) {
      startPolling(activeServerJob.id);
    }
  } catch {
    if (!$("folder").value) {
      $("folder").value = "Downloads";
    }
  }
})();
