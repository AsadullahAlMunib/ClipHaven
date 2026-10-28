const $ = (id) => document.getElementById(id);
let timer = null;
let currentJobId = null;
let previewTimer = null;
let previewSeq = 0;
let lastPreviewUrl = "";
let currentTitleHint = "";
let lastCompletedPath = "";

function status(
  title,
  detail,
  pct = 0,
  pill = "Working",
  cls = "",
  speed = "",
  eta = "",
  showOpenBtn = false,
) {
  $("status").classList.add("show");
  $("title").textContent = title;
  $("title").className = "status-title " + cls;
  $("detail").textContent = detail || "";
  $("progress").value = Math.max(0, Math.min(100, pct));
  $("pill").textContent = pill;

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
      "Backend response was not valid JSON. Check that server.py is running.",
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

// Format & Quality toggle
$("format").onchange = () => {
  const audio = ["mp3", "m4a", "wav"].includes($("format").value);
  $("quality").disabled = audio;
  $("quality").style.opacity = audio ? "0.5" : "1";
};
$("format").onchange();

// Save folder persistence
$("folder").addEventListener("change", () => {
  const val = $("folder").value.trim();
  if (val) localStorage.setItem("cliphaven_folder", val);
});

// Extra Options active badge indicator
function updateExtraOptionsBadge() {
  const hasTrim =
    $("start-time").value.trim() !== "" || $("end-time").value.trim() !== "";
  const hasChecks =
    $("subtitles").checked ||
    $("embed-thumbnail").checked ||
    $("allow-playlist").checked;
  $("active-options-badge").style.display =
    hasTrim || hasChecks ? "inline-block" : "none";
}
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

// Interactive playlist badge toggles full playlist download
$("preview-playlist").onclick = () => {
  const cb = $("allow-playlist");
  cb.checked = !cb.checked;
  updateExtraOptionsBadge();
  $("extra-options").open = true;
};

// Clear URL button visibility & action
function syncClearBtn() {
  $("clear-url-btn").style.display = $("url").value.trim() ? "grid" : "none";
}

$("clear-url-btn").onclick = () => {
  $("url").value = "";
  lastPreviewUrl = "";
  syncClearBtn();
  hidePreview();
  $("url").focus();
};

// One-click Clipboard Paste button
$("paste-btn").onclick = async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      $("url").value = text.trim();
      syncClearBtn();
      triggerPreview();
    }
  } catch {
    $("url").focus();
  }
};

// Auto Video Info Preview with sequence guard against race conditions
function hidePreview() {
  previewSeq++;
  $("preview-card").style.display = "none";
  currentTitleHint = "";
}

async function fetchPreview(rawUrl) {
  const clean = rawUrl.trim().replace(/^http:\/\//i, "https://");
  if (!clean || !clean.includes("http")) {
    hidePreview();
    return;
  }
  if (clean === lastPreviewUrl) return;
  lastPreviewUrl = clean;

  const seq = ++previewSeq;
  $("preview-card").style.display = "flex";
  $("preview-thumb").style.display = "none";
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
    if (info.is_playlist) {
      $("preview-playlist").textContent =
        info.playlist_count > 1
          ? `Playlist (${info.playlist_count} videos)`
          : "Playlist";
      $("preview-playlist").style.display = "inline-block";
    }
  } catch {
    if (seq === previewSeq) {
      hidePreview();
    }
  }
}

function triggerPreview() {
  syncClearBtn();
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(() => fetchPreview($("url").value), 450);
}

$("url").addEventListener("input", triggerPreview);
$("url").addEventListener("paste", () => setTimeout(triggerPreview, 80));

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
      status(
        s.title || s.state,
        s.detail || "",
        s.percent || 0,
        s.stage || s.state || "Working",
        isErr ? "error" : isDone ? "success" : "",
        s.speed || "",
        s.eta || "",
        isDone,
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
  if (timer) clearInterval(timer);
  const b = $("start");
  const cb = $("cancel");
  b.disabled = true;
  b.textContent = "Starting…";
  cb.style.display = "none";
  cb.disabled = false;
  currentJobId = null;

  const chosenFolder = $("folder").value.trim();
  if (chosenFolder) localStorage.setItem("cliphaven_folder", chosenFolder);

  status(
    "Starting download",
    "Checking video link and preparing stream…",
    0,
    "Starting",
  );
  try {
    const d = await api("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url: $("url").value.trim().replace(/^http:\/\//i, "https://"),
        folder: chosenFolder,
        quality: $("quality").value,
        format: $("format").value,
        start_time: $("start-time").value.trim(),
        end_time: $("end-time").value.trim(),
        subtitles: $("subtitles").checked,
        embed_thumbnail: $("embed-thumbnail").checked,
        allow_playlist: $("allow-playlist").checked,
        title_hint: currentTitleHint,
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

// Startup initialization: load config, FFmpeg check, folder memory, and active job recovery
(async function init() {
  renderHistory();
  const savedFolder = localStorage.getItem("cliphaven_folder");
  if (savedFolder) {
    $("folder").value = savedFolder;
  }
  try {
    const cfg = await api("/api/config");
    if (!savedFolder && cfg.default_folder) {
      $("folder").value = cfg.default_folder;
    }
    if (cfg.ffmpeg === false) {
      $("ffmpeg-warning").style.display = "block";
    }
    const savedJob = localStorage.getItem("cliphaven_active_job");
    if (savedJob) {
      const match = (cfg.jobs || []).find((j) => j.id === savedJob);
      if (match && !["Complete", "Error", "Cancelled"].includes(match.state)) {
        startPolling(savedJob);
      } else {
        localStorage.removeItem("cliphaven_active_job");
      }
    }
  } catch {
    if (!$("folder").value) {
      $("folder").value = "Downloads";
    }
  }
})();
