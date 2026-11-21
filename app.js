const $ = (id) => document.getElementById(id);
let timer = null;
let currentJobId = null;
let activeDownloadUrl = "";
let previewTimer = null;
let previewSeq = 0;
let lastPreviewUrl = "";
let currentTitleHint = "";
let currentDurationHint = 0;
const PLAYLIST_BATCH_INTERVAL_MS = 500;
const PLAYLIST_INITIAL_RENDER_BATCH = 38;
const PLAYLIST_RENDER_CHUNK_SIZE = 38;
let currentPlaylistCount = 0;
let isCurrentUrlPlaylist = false;
let currentPlaylistEntries = [];
let renderedPlaylistCount = 0;
let isPlaylistLoading = false;
let playlistSelectAllMode = true;
let playlistBatchTimer = null;
let playlistPollInFlight = false;
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


// 0-KB Offline Subtle Sound FX (Web Audio API) & Haptic Feedback
let _uiAudioCtx = null;
function playUiTone(kind) {
  try {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Avoid double-ding on Android where system completion notification already plays sound
    if (kind === "complete" && typeof window.ClipHavenAndroid !== "undefined") return;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!_uiAudioCtx) _uiAudioCtx = new Ctx();
    if (_uiAudioCtx.state === "suspended") _uiAudioCtx.resume().catch(() => {});
    const now = _uiAudioCtx.currentTime;
    const playNote = (freq, startOffset, dur, peakGain, endFreq) => {
      const osc = _uiAudioCtx.createOscillator();
      const gain = _uiAudioCtx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now + startOffset);
      if (endFreq) osc.frequency.exponentialRampToValueAtTime(endFreq, now + startOffset + dur);
      gain.gain.setValueAtTime(0.0001, now + startOffset);
      gain.gain.exponentialRampToValueAtTime(peakGain, now + startOffset + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + startOffset + dur);
      osc.connect(gain);
      gain.connect(_uiAudioCtx.destination);
      osc.start(now + startOffset);
      osc.stop(now + startOffset + dur + 0.01);
    };
    if (kind === "complete") {
      playNote(523.25, 0, 0.14, 0.055);
      playNote(659.25, 0.09, 0.18, 0.055);
    } else if (kind === "pop") {
      playNote(620, 0, 0.06, 0.032, 780);
    } else if (kind === "error") {
      playNote(240, 0, 0.16, 0.04, 180);
    }
  } catch (_) {}
}

function triggerHaptic(kind) {
  try {
    if (!navigator.vibrate) return;
    if (kind === "complete") navigator.vibrate([14, 40, 22]);
    else if (kind === "error") navigator.vibrate([28, 30, 28]);
    else navigator.vibrate(10);
  } catch (_) {}
}
let _lastStatusFeedbackKey = "";

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
  const titleEl = $("title");
  titleEl.className = "status-title " + cls;
  if (cls === "ok") {
    titleEl.textContent = "";
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "status-check-svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.6");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    const p = document.createElementNS(svgNS, "path");
    p.setAttribute("d", "M20 6L9 17l-5-5");
    svg.appendChild(p);
    titleEl.appendChild(svg);
    titleEl.appendChild(document.createTextNode(title));
  } else {
    titleEl.textContent = title;
  }
  const fbKey = `${cls}|${pill}|${title}`;
  if (fbKey !== _lastStatusFeedbackKey) {
    _lastStatusFeedbackKey = fbKey;
    if (cls === "ok") {
      playUiTone("complete");
      triggerHaptic("complete");
    } else if (cls === "err" || cls === "error") {
      playUiTone("error");
      triggerHaptic("error");
    }
  }
  $("detail").textContent = String(detail || "").replace(/([KMGTP])iB/g, "$1B");

  const progEl = $("progress");
  const fillEl = $("progress-fill");
  const clampedPct = Math.max(0, Math.min(100, pct));
  const isDoneOrErr = cls === "ok" || cls === "err" || pill === "Cancelled";
  if (indeterminate) {
    progEl.removeAttribute("value");
    progEl.classList.add("indeterminate");
    if (fillEl) {
      fillEl.classList.add("is-active", "is-indeterminate");
      fillEl.style.width = "42%";
    }
  } else {
    progEl.classList.remove("indeterminate");
    progEl.value = clampedPct;
    if (fillEl) {
      fillEl.classList.remove("is-indeterminate");
      fillEl.style.width = `${clampedPct}%`;
      fillEl.classList.toggle("is-active", !isDoneOrErr && clampedPct > 0 && clampedPct < 100);
    }
  }
  $("pill").textContent = pill;
  $("pill").classList.toggle("done-pop", cls === "ok");

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
    speedEl.textContent = "⚡ " + String(speed).replace(/([KMGTP])iB/g, "$1B");
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
function applyTheme(t, animate = false) {
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("theme", t);
  const isLight = t === "light";
  const langNow = localStorage.getItem("cliphaven_lang") || "en";
  const lbl = $("theme-label");
  if (lbl) lbl.textContent = langNow === "bn" ? (isLight ? "ডার্ক" : "লাইট") : (isLight ? "Dark" : "Light");
  const ic = $("theme-icon");
  if (ic) {
    ic.innerHTML = isLight
      ? '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
      : '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
    if (animate) {
      ic.classList.remove("icon-spin");
      void ic.offsetWidth;
      ic.classList.add("icon-spin");
    }
  }
}
applyTheme(
  localStorage.getItem("theme") ||
    (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"),
  false,
);
themeBtn.onclick = () =>
  applyTheme(
    document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light",
    true,
  );

function compressPlaylistIndices(indices) {
  if (!Array.isArray(indices) || !indices.length) return "";
  const sorted = Array.from(
    new Set(indices.map(Number).filter((n) => Number.isInteger(n) && n > 0)),
  ).sort((a, b) => a - b);
  if (!sorted.length) return "";
  const ranges = [];
  let start = sorted[0];
  let prev = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    const cur = sorted[i];
    if (cur === prev + 1) {
      prev = cur;
    } else {
      ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
      start = cur;
      prev = cur;
    }
  }
  ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
  return ranges.join(",");
}

function getSelectedPlaylistIndices() {
  const boxes = document.querySelectorAll(".pl-item-checkbox");
  const totalKnown = Math.max(currentPlaylistEntries.length, currentPlaylistCount);
  if (!boxes.length && !totalKnown) return [];
  const selected = [];
  boxes.forEach((b) => {
    if (b.checked) selected.push(Number(b.value));
  });
  if (
    playlistSelectAllMode &&
    $("allow-playlist").checked &&
    totalKnown > boxes.length
  ) {
    for (let i = boxes.length; i < totalKnown; i++) {
      const item = currentPlaylistEntries[i];
      const idx = (item && item.index) || i + 1;
      selected.push(Number(idx));
    }
  }
  return selected;
}

function getPlaylistItemsParam() {
  const totalKnown = Math.max(currentPlaylistEntries.length, currentPlaylistCount);
  if (!totalKnown) return "";
  const boxes = document.querySelectorAll(".pl-item-checkbox");
  if (!boxes.length) {
    if (!$("allow-playlist").checked) {
      return /\/playlist\b/i.test($("url").value) ? "1" : "";
    }
    return "";
  }
  const selected = getSelectedPlaylistIndices();
  const allDomChecked =
    boxes.length > 0 &&
    Array.from(boxes).every((b) => b.checked) &&
    playlistSelectAllMode;
  if (!selected.length || (allDomChecked && selected.length >= totalKnown)) {
    return "";
  }
  return compressPlaylistIndices(selected);
}

function updatePlaylistScrollHint() {
  const scrollHint = $("playlist-scroll-hint");
  if (!scrollHint) return;
  const totalLoaded = currentPlaylistEntries.length;
  const totalExpected = Math.max(totalLoaded, currentPlaylistCount);
  if (!isCurrentUrlPlaylist || totalLoaded === 0) {
    scrollHint.style.display = "none";
    return;
  }
  if (isPlaylistLoading || renderedPlaylistCount < totalLoaded) {
    const suffix = totalExpected > renderedPlaylistCount ? ` / ${totalExpected}` : "";
    scrollHint.textContent = `⏳ Loaded ${renderedPlaylistCount}${suffix} videos…`;
    scrollHint.style.display = "inline-block";
  } else if (renderedPlaylistCount > 5) {
    scrollHint.textContent = `↕ Scroll (${renderedPlaylistCount} videos)`;
    scrollHint.style.display = "inline-block";
  } else {
    scrollHint.style.display = "none";
  }
}

function stopPlaylistStream(notifyBackend = false) {
  if (playlistBatchTimer) {
    clearInterval(playlistBatchTimer);
    playlistBatchTimer = null;
  }
  isPlaylistLoading = false;
  playlistPollInFlight = false;
  updatePlaylistScrollHint();
  syncPlaylistBadgeText();
  if (notifyBackend) {
    api("/api/cancel-preview", { method: "POST", body: "{}" }).catch(() => {});
  }
}

function createPlaylistRowElement(item, i, shouldCheck = true) {
  const idx = item.index || i + 1;
  const row = document.createElement("label");
  row.className = "playlist-item-row";

  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.className = "pl-item-checkbox";
  cb.value = String(idx);
  cb.checked = shouldCheck;
  cb.onchange = () => {
    const boxes = document.querySelectorAll(".pl-item-checkbox");
    const allChecked = boxes.length > 0 && Array.from(boxes).every((b) => b.checked);
    playlistSelectAllMode = allChecked;
    $("allow-playlist").checked = allChecked;
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
  return row;
}

function appendPlaylistBatch(maxCount = 100) {
  const listEl = $("playlist-items-list");
  if (!listEl || renderedPlaylistCount >= currentPlaylistEntries.length) return 0;
  const endIdx = Math.min(
    currentPlaylistEntries.length,
    renderedPlaylistCount + maxCount,
  );
  const frag = document.createDocumentFragment();
  const shouldCheck = playlistSelectAllMode && $("allow-playlist").checked;
  for (let i = renderedPlaylistCount; i < endIdx; i++) {
    const item = currentPlaylistEntries[i];
    frag.appendChild(createPlaylistRowElement(item, i, shouldCheck));
  }
  listEl.appendChild(frag);
  const added = endIdx - renderedPlaylistCount;
  renderedPlaylistCount = endIdx;
  return added;
}

function startPlaylistBatchLoop(cleanUrl, seq) {
  if (playlistBatchTimer) clearInterval(playlistBatchTimer);
  playlistBatchTimer = setInterval(async () => {
    if (seq !== previewSeq || currentJobId) {
      stopPlaylistStream(false);
      return;
    }
    if (isPlaylistLoading && cleanUrl && !playlistPollInFlight) {
      playlistPollInFlight = true;
      try {
        const d = await api("/api/info", {
          method: "POST",
          body: JSON.stringify({ url: cleanUrl, poll: true }),
        });
        if (seq !== previewSeq || currentJobId) {
          stopPlaylistStream(false);
          return;
        }
        const info = (d && d.info) || {};
        if (
          Array.isArray(info.entries) &&
          info.entries.length >= currentPlaylistEntries.length
        ) {
          currentPlaylistEntries = info.entries;
        }
        currentPlaylistCount = Math.max(
          currentPlaylistCount,
          info.playlist_count || 0,
          currentPlaylistEntries.length,
        );
        isPlaylistLoading = Boolean(info.playlist_loading);
      } catch {
        isPlaylistLoading = false;
      } finally {
        playlistPollInFlight = false;
      }
    }
    if (renderedPlaylistCount < currentPlaylistEntries.length) {
      const remaining = currentPlaylistEntries.length - renderedPlaylistCount;
      const chunk = Math.min(PLAYLIST_RENDER_CHUNK_SIZE, remaining);
      appendPlaylistBatch(chunk);
    }
    updatePlaylistScrollHint();
    updateExtraOptionsBadge();
    if (!isPlaylistLoading && renderedPlaylistCount >= currentPlaylistEntries.length) {
      stopPlaylistStream(false);
    }
  }, PLAYLIST_BATCH_INTERVAL_MS);
}

function renderPlaylistSelector(entries, cleanUrl = "", seq = previewSeq) {
  const selector = $("playlist-selector");
  const listEl = $("playlist-items-list");
  const scrollHint = $("playlist-scroll-hint");
  if (playlistBatchTimer) {
    clearInterval(playlistBatchTimer);
    playlistBatchTimer = null;
  }
  listEl.innerHTML = "";
  renderedPlaylistCount = 0;
  if (!isCurrentUrlPlaylist || ((!entries || !entries.length) && !isPlaylistLoading)) {
    selector.style.display = "none";
    if (scrollHint) scrollHint.style.display = "none";
    return;
  }
  selector.style.display = "block";
  appendPlaylistBatch(PLAYLIST_INITIAL_RENDER_BATCH);
  updatePlaylistScrollHint();
  syncPlaylistBadgeText();

  if (isPlaylistLoading || renderedPlaylistCount < currentPlaylistEntries.length) {
    startPlaylistBatchLoop(cleanUrl, seq);
  }
}

function isPlaylistUrlPattern(u) {
  return /[?&]list=[^&#]+|\/playlist\b/i.test(String(u || ""));
}

function syncPlaylistCheckboxState(urlHint = "") {
  const cb = $("allow-playlist");
  if (!cb) return;
  const canPlaylist = Boolean(
    isCurrentUrlPlaylist || isPlaylistUrlPattern(urlHint || $("url").value),
  );
  cb.disabled = !canPlaylist;
  if (!canPlaylist) {
    cb.checked = false;
  }
  if (cb.parentElement) {
    cb.parentElement.style.opacity = canPlaylist ? "1" : "0.5";
    cb.parentElement.style.cursor = canPlaylist ? "pointer" : "not-allowed";
    cb.parentElement.title = canPlaylist
      ? ""
      : "Download Entire Playlist is only available for playlist links";
  }
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
  const total = Math.max(currentPlaylistEntries.length, currentPlaylistCount);
  const shownCount = renderedPlaylistCount || currentPlaylistEntries.length || total;
  const stillWorking = isPlaylistLoading || renderedPlaylistCount < currentPlaylistEntries.length;
  const boxes = document.querySelectorAll(".pl-item-checkbox");
  let checkedDomCount = 0;
  boxes.forEach((b) => {
    if (b.checked) checkedDomCount++;
  });
  const isAll = $("allow-playlist").checked;
  const hasCustomUncheck = boxes.length > 0 && checkedDomCount < boxes.length && checkedDomCount > 0;

  if (boxes.length > 0 && checkedDomCount === 0) {
    const countStr = shownCount > 1 ? ` (${shownCount}${stillWorking ? "…" : ""} videos)` : "";
    badge.textContent = `📑 Playlist${countStr} • 0 Selected`;
    if (selBadge) selBadge.textContent = "0 Selected";
  } else if (hasCustomUncheck) {
    badge.textContent = `✅ ${checkedDomCount}/${shownCount}${stillWorking ? "…" : ""} Videos Selected ▾`;
    if (selBadge) selBadge.textContent = `${checkedDomCount} of ${shownCount}${stillWorking ? "…" : ""} Selected ▾`;
  } else if (!isAll && boxes.length === 0) {
    const countStr = shownCount > 1 ? ` (${shownCount}${stillWorking ? "…" : ""} videos)` : "";
    badge.textContent = `📑 Playlist${countStr} • Single`;
    if (selBadge) selBadge.textContent = "Single Video Only";
  } else if (stillWorking) {
    const targetStr = total > shownCount ? `/${total}` : "";
    badge.textContent = `⏳ Playlist (${shownCount}${targetStr} loaded…) ▾`;
    if (selBadge) selBadge.textContent = `⏳ ${shownCount}${targetStr} Loaded ▾`;
  } else {
    const countStr = shownCount > 1 ? ` (${shownCount} videos)` : "";
    badge.textContent = `✅ All Playlist Videos${countStr} ▾`;
    if (selBadge) selBadge.textContent = shownCount > 1 ? `All ${shownCount} Selected ▾` : "All Selected ▾";
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
  syncPlaylistCheckboxState();
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
  playlistSelectAllMode = checked;
  if (boxes.length) {
    boxes.forEach((b) => (b.checked = checked));
  }
  updateExtraOptionsBadge();
});

$("pl-select-all-btn").onclick = () => {
  playlistSelectAllMode = true;
  document.querySelectorAll(".pl-item-checkbox").forEach((b) => (b.checked = true));
  $("allow-playlist").checked = true;
  updateExtraOptionsBadge();
};

$("pl-clear-all-btn").onclick = () => {
  playlistSelectAllMode = false;
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
      if (window.__clipHavenUpdatePlatformIcon) window.__clipHavenUpdatePlatformIcon($("url").value);
      if (window.__clipHavenSyncPrimaryBtn) window.__clipHavenSyncPrimaryBtn();
      playUiTone("pop");
      triggerHaptic("tap");
      triggerPreview(true);
    }
  } catch {
    $("url").focus();
  }
};

// Auto Video Info Preview with sequence guard against race conditions
function hidePreview() {
  if (window.__clipHavenUpdatePlatformIcon && !$("url").value.trim()) window.__clipHavenUpdatePlatformIcon("");
  previewSeq++;
  lastPreviewUrl = "";
  stopPlaylistStream(true);
  $("preview-card").style.display = "none";
  $("playlist-selector").style.display = "none";
  $("playlist-items-list").innerHTML = "";
  currentTitleHint = "";
  currentDurationHint = 0;
  currentPlaylistCount = 0;
  currentPlaylistEntries = [];
  renderedPlaylistCount = 0;
  isPlaylistLoading = false;
  playlistSelectAllMode = true;
  isCurrentUrlPlaylist = false;
  syncPlaylistCheckboxState("");
  updateExtraOptionsBadge();
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
  stopPlaylistStream(false);
  currentTitleHint = "";
  currentDurationHint = 0;
  currentPlaylistCount = 0;
  currentPlaylistEntries = [];
  renderedPlaylistCount = 0;
  isPlaylistLoading = false;
  playlistSelectAllMode = true;
  isCurrentUrlPlaylist = isPlaylistUrlPattern(clean);
  syncPlaylistCheckboxState(clean);
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
    if (window.__clipHavenSetDuration && currentDurationHint > 0) window.__clipHavenSetDuration(currentDurationHint);
    isCurrentUrlPlaylist = Boolean(info.is_playlist);
    currentPlaylistCount = info.playlist_count || 0;
    currentPlaylistEntries = Array.isArray(info.entries) ? info.entries : [];
    isPlaylistLoading = Boolean(info.playlist_loading);
    playlistSelectAllMode = isCurrentUrlPlaylist;
    // Default to downloading all playlist videos automatically when a playlist link is pasted
    $("allow-playlist").checked = isCurrentUrlPlaylist;
    renderPlaylistSelector(currentPlaylistEntries, clean, seq);
    $("preview-title").textContent = info.title || "Video ready to download";
    $("preview-uploader").textContent = info.uploader || "";
    if (info.thumbnail) {
      $("preview-thumb").src = info.thumbnail;
      $("preview-thumb").style.display = "block";
    }
    let durationVerifiedByEngine = Boolean(info.duration && !info.duration_approx);
    if (info.duration) {
      $("preview-duration").textContent = info.duration;
      $("preview-duration").style.display = "inline-flex";
    }
    if (!isCurrentUrlPlaylist && !currentJobId && (!info.duration || info.duration_approx)) {
      // 1. Instant (~0.3-0.6s) lightweight duration fetch for YouTube single videos
      if (!info.duration && ytId) {
        api("/api/info", {
          method: "POST",
          body: JSON.stringify({ url: clean, fast_duration: true }),
        })
          .then((fastRes) => {
            if (seq !== previewSeq || durationVerifiedByEngine || !fastRes || !fastRes.info || !fastRes.info.duration) return;
            currentDurationHint = fastRes.info.duration_seconds || 0;
            if (window.__clipHavenSetDuration && currentDurationHint > 0) window.__clipHavenSetDuration(currentDurationHint);
            $("preview-duration").textContent = fastRes.info.duration;
            $("preview-duration").style.display = "inline-flex";
          })
          .catch(() => {});
      }
      // 2. Non-blocking background yt-dlp verification/reconciliation & fallback
      api("/api/info", {
        method: "POST",
        body: JSON.stringify({ url: clean, full: true, verify: true }),
      })
        .then((res) => {
          if (seq !== previewSeq || !res || !res.info) return;
          if (res.info.thumbnail && ($("preview-thumb").style.display === "none" || !$("preview-thumb").getAttribute("src"))) {
            $("preview-thumb").src = res.info.thumbnail;
            $("preview-thumb").style.display = "block";
          }
          if (!res.info.duration) return;
          durationVerifiedByEngine = true;
          const exactSec = res.info.duration_seconds || 0;
          if (exactSec !== currentDurationHint || $("preview-duration").style.display === "none") {
            currentDurationHint = exactSec;
            if (window.__clipHavenSetDuration && currentDurationHint > 0) window.__clipHavenSetDuration(currentDurationHint);
            $("preview-duration").textContent = res.info.duration;
            $("preview-duration").style.display = "inline-flex";
          }
        })
        .catch(() => {});
    }
    updateExtraOptionsBadge();
  } catch (err) {
    if (seq === previewSeq) {
      $("preview-thumb").style.display = "none";
      $("preview-dot").style.display = "none";
      $("preview-duration").style.display = "none";
      $("preview-playlist").style.display = "none";
      syncPlaylistCheckboxState(clean);
      $("preview-title").textContent = "Preview unavailable";
      $("preview-uploader").textContent =
        (err && err.message) || "Check link or click Download Now to try directly.";
    }
  }
}

function triggerPreview(immediate = false) {
  syncClearBtn();
  if (window.__clipHavenUpdatePlatformIcon) window.__clipHavenUpdatePlatformIcon($("url").value);
  if (window.__clipHavenSyncPrimaryBtn) window.__clipHavenSyncPrimaryBtn();
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
    if (window.__clipHavenUpdatePlatformIcon) window.__clipHavenUpdatePlatformIcon($("url").value);
    if (window.__clipHavenSyncPrimaryBtn) window.__clipHavenSyncPrimaryBtn();
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
    row.className = "list-row history-item";

    const meta = document.createElement("div");
    meta.className = "list-meta history-meta";

    const title = document.createElement("div");
    title.className = "list-title history-title";
    title.textContent = item.title;
    title.title = item.title;

    const sub = document.createElement("div");
    sub.className = "list-sub history-sub";
    const fmtTag = document.createElement("span");
    fmtTag.className = "fmt-tag";
    fmtTag.textContent = item.format || "MP4";
    const subInfo = document.createElement("span");
    subInfo.textContent = `${item.quality} • ${item.time}`;
    sub.appendChild(fmtTag);
    sub.appendChild(subInfo);

    meta.appendChild(title);
    meta.appendChild(sub);

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "btn secondary sm";
    openBtn.style.flexShrink = "0";
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
  window.__clipHavenSetBtn && window.__clipHavenSetBtn("downloading");
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
        window.__clipHavenSetBtn && window.__clipHavenSetBtn("ready");
        cb.style.display = "none";
        currentJobId = null;
        localStorage.removeItem("cliphaven_active_job");
        if (isDone) {
          const pillEl = $("pill");
          if (pillEl) {
            pillEl.className = "pill done-pop";
            pillEl.textContent = "✓ Done";
          }
          addToHistory({ id: jobId, url: activeDownloadUrl || $("url").value.trim(), format: $("format").value, ...s });
        }
        activeDownloadUrl = "";
        if (window.__clipHavenOnTransferEnd) window.__clipHavenOnTransferEnd(isDone);
      }
    } catch (err) {
      if (++errCount < 4) return;
      clearInterval(timer);
      timer = null;
      status("Status error", err.message, 0, "Error", "error");
      b.disabled = false;
      window.__clipHavenSetBtn && window.__clipHavenSetBtn("ready");
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
  if (window.__clipHavenIsPlaylistZero && window.__clipHavenIsPlaylistZero()) {
    window.__clipHavenFlashPlaylistErr && window.__clipHavenFlashPlaylistErr();
    return;
  }
  if (currentJobId) {
    if (window.__clipHavenTryAddUpNext && window.__clipHavenTryAddUpNext()) return;
    return;
  }
  if (b.disabled) return;
  if (timer) clearInterval(timer);
  // Stop any active background playlist preview stream so download gets 100% bandwidth & CPU
  stopPlaylistStream(true);

  b.disabled = true;
  window.__clipHavenSetBtn && window.__clipHavenSetBtn("starting");
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
        allow_playlist: $("allow-playlist").checked || Boolean(getPlaylistItemsParam()) || /\/playlist\b/i.test(cleanUrl),
        playlist_items: getPlaylistItemsParam(),
        title_hint: currentTitleHint,
        duration_hint: currentDurationHint,
        lang: localStorage.getItem("cliphaven_lang") || "en",
        thumb_url: ($("preview-thumb") && /^https?:/i.test($("preview-thumb").src || "")) ? $("preview-thumb").src : "",
      }),
    });
    activeDownloadUrl = cleanUrl;
    startPolling(d.id);
    window.__clipHavenSyncPrimaryBtn && window.__clipHavenSyncPrimaryBtn();
  } catch (err) {
    status("Could not start download", err.message, 0, "Error", "error");
    b.disabled = false;
    window.__clipHavenSetBtn && window.__clipHavenSetBtn("ready");
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
          nowBtn.textContent = "📂 Open Downloads to Install";
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
  setTimeout(checkForAppUpdates, 1500);
})();


// ============================================================================
// ClipHaven v3.3.0 UI Controller
// ============================================================================
(function initClipHavenV330UI() {
  const I18N = {
    en: {
      tagline: "Paste a link, pick a format, and save your clip in seconds.",
      docs_btn: "Docs",
      docs_full: "Documentation",
      url_label: "Video or Playlist URL",
      paste: "Paste",
      playlist_select: "Select Playlist Videos",
      select_all: "Select All",
      single_only: "Single Video",
      playlist_select_err: "Please select at least 1 video from the playlist to download.",
      mode_video: "Video",
      mode_audio: "Audio Only",
      format_label: "Format",
      quality_label: "Resolution",
      save_folder: "Save Folder",
      browse: "Browse",
      folder_hint: "Remembered automatically for next time.",
      extra_dropdown: "Clip Trimmer, Subtitles (CC) & Options",
      trim_title: "Trim Range",
      full_video: "Full video",
      reset: "Reset",
      start_time: "Start Time",
      end_time: "End Time",
      subtitles: "Original Subtitles (CC)",
      embed_thumb: "Embed Cover Art",
      entire_playlist: "Entire Playlist",
      download_now: "Download Now",
      download_next: "Download Next",
      downloading: "Downloading...",
      starting: "Starting...",
      skip_next: "Skip",
      cancel: "Cancel",
      ready: "Ready",
      ready_detail: "Paste a video link to begin.",
      open_folder: "Open Folder",
      up_next: "Up Next",
      history_title: "Recent Downloads",
      clear: "Clear",
      privacy_prefix: "100% local on",
      privacy_suffix: "Downloads run one by one to keep speed steady.",
      update_title: "New Update Available",
      update_desc: "A newer version of ClipHaven is available with latest improvements and extractor fixes.",
      release_notes: "View Release Notes",
      update_now: "Update Now",
      later: "Later",
      clamped_max: (m) => `Cannot exceed video length (${m}) — adjusted automatically.`,
      clamped_order: "Start time must be before End time — adjusted automatically.",
      clip_len: (s) => `Clip: ${s}`,
      added_next: "Added to Up Next — ready for another link.",
      copied: "Link copied!",
      dropped: "Link dropped!",
      already_running: "This video is already downloading. Paste a new link to download next.",
    },
    bn: {
      tagline: "লিংক পেস্ট করুন, ফরম্যাট বেছে নিন আর কয়েক সেকেন্ডেই সেভ করুন।",
      docs_btn: "নথি",
      docs_full: "নির্দেশিকা",
      url_label: "ভিডিও বা প্লেলিস্ট লিংক",
      paste: "পেস্ট",
      playlist_select: "প্লেলিস্টের ভিডিও বেছে নাও",
      select_all: "সব সিলেক্ট",
      single_only: "শুধু ১টি ভিডিও",
      playlist_select_err: "ডাউনলোড করতে প্লেলিস্ট থেকে অন্তত ১টি ভিডিও সিলেক্ট করুন।",
      mode_video: "ভিডিও",
      mode_audio: "শুধু অডিও",
      format_label: "ফরম্যাট",
      quality_label: "রেজুলেশন",
      save_folder: "সেভ ফোল্ডার",
      browse: "ব্রাউজ",
      folder_hint: "পরবর্তী ডাউনলোডের জন্য অটোমেটিক মনে থাকবে।",
      extra_dropdown: "ক্লিপ ট্রিমার, সাবটাইটেল (CC) ও অতিরিক্ত অপশন",
      trim_title: "ক্লিপ রেঞ্জ",
      full_video: "সম্পূর্ণ ভিডিও",
      reset: "রিসেট",
      start_time: "শুরুর সময়",
      end_time: "শেষের সময়",
      subtitles: "অরিজিনাল সাবটাইটেল (CC)",
      embed_thumb: "কভার আর্ট এম্বেড",
      entire_playlist: "পুরো প্লেলিস্ট",
      download_now: "ডাউনলোড শুরু",
      download_next: "পরে ডাউনলোড করুন",
      downloading: "ডাউনলোড চলছে...",
      starting: "শুরু হচ্ছে...",
      skip_next: "পরেরটি",
      cancel: "বাতিল",
      ready: "প্রস্তুত",
      ready_detail: "শুরু করতে একটি ভিডিও লিংক পেস্ট করুন।",
      open_folder: "ফোল্ডার খোলো",
      up_next: "পরবর্তী ডাউনলোড",
      history_title: "সম্প্রতি ডাউনলোড করা",
      clear: "ক্লিয়ার",
      privacy_prefix: "১০০% লোকাল ইঞ্জিন",
      privacy_suffix: "একের পর এক ডাউনলোড হওয়ায় স্পিড একদম স্থির থাকে।",
      update_title: "নতুন আপডেট পাওয়া গেছে",
      update_desc: "নতুন উন্নতি ও এক্সট্র্যাক্টর ফিক্সসহ ClipHaven-এর নতুন ভার্সন প্রস্তুত।",
      release_notes: "রিলিজ নোট দেখুন",
      update_now: "আপডেট করুন",
      later: "পরে",
      clamped_max: (m) => `ভিডিওর মোট সময়ের (${m}) বেশি দেওয়া যাবে না — অটো ঠিক করা হয়েছে।`,
      clamped_order: "শুরুর সময় শেষের সময়ের আগে হতে হবে — অটো ঠিক করা হয়েছে।",
      clip_len: (s) => `ক্লিপ: ${s}`,
      added_next: "পরবর্তী ডাউনলোডে যুক্ত হয়েছে — নতুন লিংক দিতে পারো।",
      copied: "লিংক কপি হয়েছে!",
      dropped: "লিংক ড্রপ করা হয়েছে!",
      already_running: "এই ভিডিওটি এখন ডাউনলোড হচ্ছে। নতুন লিংক পেস্ট করলে পরে ডাউনলোড হবে।",
    },
  };

  let lang = localStorage.getItem("cliphaven_lang") || "en";
  let toastTimer = null;
  function showToast(msg) {
    const el = $("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }

  function applyLang(next) {
    lang = next === "bn" ? "bn" : "en";
    localStorage.setItem("cliphaven_lang", lang);
    if ($("lang-flag")) $("lang-flag").textContent = lang === "en" ? "🇧🇩" : "🇬🇧";
    if ($("lang-sm")) $("lang-sm").textContent = lang === "en" ? "বাং" : "EN";
    if ($("lang-md")) $("lang-md").textContent = lang === "en" ? "বাংলা" : "ENG";
    if ($("lang-lg")) $("lang-lg").textContent = lang === "en" ? "বাংলা" : "English";

    const dict = I18N[lang];
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const k = el.getAttribute("data-i18n");
      if (dict[k] && typeof dict[k] === "string") el.textContent = dict[k];
    });
    applyTheme(document.documentElement.getAttribute("data-theme") || "dark", false);
    updateClipBadge();
    syncPrimaryBtn();
  }

  if ($("lang-btn")) {
    $("lang-btn").addEventListener("click", () => applyLang(lang === "en" ? "bn" : "en"));
  }

  const VIDEO_FMTS = [{ v: "mp4", l: "MP4" }, { v: "mkv", l: "MKV" }, { v: "webm", l: "WEBM" }];
  const AUDIO_FMTS = [{ v: "mp3", l: "MP3" }, { v: "m4a", l: "M4A" }, { v: "wav", l: "WAV" }];
  let activeMode = "video";

  function renderFormatChips(selectedVal) {
    const wrap = $("format-chips");
    if (!wrap) return;
    const list = activeMode === "video" ? VIDEO_FMTS : AUDIO_FMTS;
    wrap.innerHTML = "";
    list.forEach((item, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip" + ((selectedVal ? item.v === selectedVal : idx === 0) ? " active" : "");
      btn.textContent = item.l;
      btn.addEventListener("click", () => {
        wrap.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        btn.classList.add("active");
        $("format").value = item.v;
        $("format").dispatchEvent(new Event("change"));
      });
      wrap.appendChild(btn);
    });
    $("format").value = selectedVal || list[0].v;
    $("format").dispatchEvent(new Event("change"));
    if ($("quality-section")) $("quality-section").style.display = activeMode === "video" ? "flex" : "none";
  }

  if ($("mode-video") && $("mode-audio")) {
    $("mode-video").addEventListener("click", () => {
      activeMode = "video";
      $("mode-tabs").classList.remove("is-audio");
      $("mode-video").classList.add("active");
      $("mode-audio").classList.remove("active");
      renderFormatChips("mp4");
    });
    $("mode-audio").addEventListener("click", () => {
      activeMode = "audio";
      $("mode-tabs").classList.add("is-audio");
      $("mode-audio").classList.add("active");
      $("mode-video").classList.remove("active");
      renderFormatChips("mp3");
    });
    renderFormatChips($("format").value || "mp4");
  }

  if ($("quality-chips")) {
    $("quality-chips").querySelectorAll(".chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        $("quality-chips").querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        btn.classList.add("active");
        $("quality").value = btn.dataset.q;
      });
    });
  }

  let knownDurationSec = 0;
  function secToTime(sec) {
    sec = Math.max(0, Math.floor(sec));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  }

  function parseTimeSec(raw) {
    const s = String(raw || "").trim();
    if (!s) return null;
    if (/^\d+$/.test(s)) return parseInt(s, 10);
    const parts = s.split(":").map((p) => p.trim());
    if (parts.length < 2 || parts.length > 3 || parts.some((p) => !/^\d+$/.test(p))) return null;
    if (parts.length === 2) return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    return parseInt(parts[0], 10) * 3600 + parseInt(parts[1], 10) * 60 + parseInt(parts[2], 10);
  }

  let clampTimer = null;
  function showClampWarn(msg, inputEl) {
    if (!$("clamp-msg")) return;
    $("clamp-msg-text").textContent = msg;
    $("clamp-msg").classList.add("show");
    if (inputEl) inputEl.classList.add("input-clamped");
    clearTimeout(clampTimer);
    clampTimer = setTimeout(() => {
      $("clamp-msg").classList.remove("show");
      $("start-time").classList.remove("input-clamped");
      $("end-time").classList.remove("input-clamped");
    }, 3000);
  }

  function updateClipBadge() {
    const badge = $("clip-len-badge");
    const resetBtn = $("reset-trim-btn");
    if (!badge) return;
    const sVal = $("start-time").value.trim();
    const eVal = $("end-time").value.trim();
    if (!sVal && !eVal) {
      badge.textContent = I18N[lang].full_video;
      if (resetBtn) resetBtn.style.display = "none";
      return;
    }
    if (resetBtn) resetBtn.style.display = "inline-flex";
    const sSec = parseTimeSec(sVal) || 0;
    const eSec = parseTimeSec(eVal) || knownDurationSec || 0;
    badge.textContent = eSec > sSec ? I18N[lang].clip_len(secToTime(eSec - sSec)) : `${sVal || "00:00"} – ${eVal || "End"}`;
  }

  function updateSliderVisual() {
    if (!knownDurationSec || !$("range-start") || !$("range-end")) return;
    const s = Number($("range-start").value);
    const e = Number($("range-end").value);
    $("slider-fill").style.left = `${(s / knownDurationSec) * 100}%`;
    $("slider-fill").style.width = `${((e - s) / knownDurationSec) * 100}%`;
    updateClipBadge();
    updateExtraOptionsBadge();
  }

  window.__clipHavenSetDuration = function (sec) {
    knownDurationSec = Math.max(0, Math.floor(sec || 0));
    const wrap = $("trim-slider-wrap");
    if (!wrap) return;
    if (knownDurationSec > 1) {
      wrap.style.display = "block";
      $("range-start").max = knownDurationSec;
      $("range-end").max = knownDurationSec;
      $("range-start").value = 0;
      $("range-end").value = knownDurationSec;
      $("slider-max-label").textContent = `Max: ${secToTime(knownDurationSec)}`;
      $("end-time").placeholder = `${secToTime(knownDurationSec)} (Full)`;
      updateSliderVisual();
    } else {
      wrap.style.display = "none";
    }
  };

  function showTip(which, sec) {
    if (!knownDurationSec) return;
    const tip = $(which === "start" ? "tip-start" : "tip-end");
    if (!tip) return;
    const pct = (sec / knownDurationSec) * 100;
    tip.style.left = `${Math.max(6, Math.min(94, pct))}%`;
    tip.textContent = secToTime(sec);
    tip.classList.add("show");
  }
  function hideTips() {
    $("tip-start") && $("tip-start").classList.remove("show");
    $("tip-end") && $("tip-end").classList.remove("show");
  }

  if ($("range-start") && $("range-end")) {
    $("range-start").addEventListener("input", () => {
      let s = Number($("range-start").value);
      const e = Number($("range-end").value);
      if (s >= e) { s = Math.max(0, e - 1); $("range-start").value = s; }
      $("start-time").value = s > 0 ? secToTime(s) : "";
      updateSliderVisual();
      showTip("start", s);
    });
    $("range-end").addEventListener("input", () => {
      const s = Number($("range-start").value);
      let e = Number($("range-end").value);
      if (e <= s) { e = Math.min(knownDurationSec, s + 1); $("range-end").value = e; }
      $("end-time").value = e < knownDurationSec ? secToTime(e) : "";
      updateSliderVisual();
      showTip("end", e);
    });
    ["pointerup", "mouseup", "touchend", "change"].forEach((ev) => {
      $("range-start").addEventListener(ev, hideTips);
      $("range-end").addEventListener(ev, hideTips);
    });
  }

  function validateManualTime(which) {
    const sEl = $("start-time");
    const eEl = $("end-time");
    let sSec = parseTimeSec(sEl.value);
    let eSec = parseTimeSec(eEl.value);
    if (knownDurationSec > 0) {
      if (which === "start" && sEl.value.trim() !== "" && sSec !== null) {
        if (sSec > knownDurationSec - 1) {
          sSec = Math.max(0, knownDurationSec - 1);
          sEl.value = secToTime(sSec);
          showClampWarn(I18N[lang].clamped_max(secToTime(knownDurationSec)), sEl);
        }
        const curEnd = eSec !== null ? Math.min(eSec, knownDurationSec) : knownDurationSec;
        if (sSec >= curEnd) {
          sSec = Math.max(0, curEnd - 1);
          sEl.value = secToTime(sSec);
          showClampWarn(I18N[lang].clamped_order, sEl);
        }
        $("range-start").value = sSec;
      } else if (which === "start") {
        $("range-start").value = 0;
      }

      if (which === "end" && eEl.value.trim() !== "" && eSec !== null) {
        if (eSec > knownDurationSec) {
          eSec = knownDurationSec;
          eEl.value = secToTime(eSec);
          showClampWarn(I18N[lang].clamped_max(secToTime(knownDurationSec)), eEl);
        }
        const curStart = sSec !== null ? Math.max(0, sSec) : 0;
        if (eSec <= curStart) {
          eSec = Math.min(knownDurationSec, curStart + 1);
          eEl.value = secToTime(eSec);
          showClampWarn(I18N[lang].clamped_order, eEl);
        }
        $("range-end").value = eSec;
      } else if (which === "end") {
        $("range-end").value = knownDurationSec;
      }
      updateSliderVisual();
    } else {
      updateClipBadge();
    }
  }

  ["change", "blur"].forEach((ev) => {
    $("start-time").addEventListener(ev, () => validateManualTime("start"));
    $("end-time").addEventListener(ev, () => validateManualTime("end"));
  });

  if ($("reset-trim-btn")) {
    $("reset-trim-btn").addEventListener("click", () => {
      $("start-time").value = "";
      $("end-time").value = "";
      if (knownDurationSec > 0) {
        $("range-start").value = 0;
        $("range-end").value = knownDurationSec;
        updateSliderVisual();
      } else {
        updateClipBadge();
        updateExtraOptionsBadge();
      }
    });
  }

  window.__clipHavenIsPlaylistZero = function () {
    const boxes = document.querySelectorAll(".pl-item-checkbox");
    if (!isCurrentUrlPlaylist || boxes.length === 0) return false;
    let checked = 0;
    boxes.forEach((b) => { if (b.checked) checked++; });
    return checked === 0;
  };

  window.__clipHavenFlashPlaylistErr = function () {
    const err = $("playlist-err");
    if (!err) return;
    err.classList.add("show");
    err.classList.remove("shake");
    void err.offsetWidth;
    err.classList.add("shake");
    if ($("playlist-selector")) $("playlist-selector").open = true;
  };

  function syncPlaylistZeroGuard() {
    const blocked = window.__clipHavenIsPlaylistZero();
    const err = $("playlist-err");
    if (err) err.classList.toggle("show", blocked);
    syncPrimaryBtn();
  }

  if ($("playlist-items-list")) {
    $("playlist-items-list").addEventListener("change", syncPlaylistZeroGuard);
  }
  if ($("pl-select-all-btn")) {
    $("pl-select-all-btn").addEventListener("click", () => {
      document.querySelectorAll(".pl-item-checkbox").forEach((cb) => { cb.checked = true; });
      $("allow-playlist").checked = true;
      updateExtraOptionsBadge();
      syncPlaylistZeroGuard();
    });
  }
  if ($("pl-clear-all-btn")) {
    $("pl-clear-all-btn").addEventListener("click", () => {
      document.querySelectorAll(".pl-item-checkbox").forEach((cb) => { cb.checked = false; });
      $("allow-playlist").checked = false;
      updateExtraOptionsBadge();
      syncPlaylistZeroGuard();
    });
  }
  if ($("allow-playlist")) {
    $("allow-playlist").addEventListener("change", (e) => {
      const isChecked = Boolean(e.target.checked);
      document.querySelectorAll(".pl-item-checkbox").forEach((cb) => { cb.checked = isChecked; });
      updateExtraOptionsBadge();
      syncPlaylistZeroGuard();
    });
  }
  if ($("playlist-search")) {
    $("playlist-search").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      document.querySelectorAll("#playlist-items-list .playlist-item-row").forEach((row) => {
        row.style.display = !q || row.textContent.toLowerCase().includes(q) ? "flex" : "none";
      });
    });
  }

  const STORAGE_UPNEXT = "cliphaven_upnext_v33";
  let upNext = [];
  try { upNext = JSON.parse(localStorage.getItem(STORAGE_UPNEXT) || "[]") || []; } catch (_) { upNext = []; }
  function saveUpNext() { try { localStorage.setItem(STORAGE_UPNEXT, JSON.stringify(upNext)); } catch (_) {} }

  function setPrimaryVisual(mode) {
    const btn = $("start");
    const lbl = $("start-label");
    const ic = $("start-icon");
    if (!btn || !lbl || !ic) return;
    if (mode === "blocked") {
      btn.classList.add("is-blocked");
      btn.classList.remove("mode-next");
      btn.disabled = false;
      btn.setAttribute("aria-disabled", "true");
      return;
    }
    btn.classList.remove("is-blocked");
    btn.removeAttribute("aria-disabled");

    if (mode === "next") {
      const wasNext = btn.classList.contains("mode-next");
      btn.classList.add("mode-next");
      btn.disabled = false;
      lbl.textContent = I18N[lang].download_next;
      ic.innerHTML = '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>';
      if (!wasNext) {
        btn.classList.remove("morph-pop");
        void btn.offsetWidth;
        btn.classList.add("morph-pop");
      }
    } else if (mode === "downloading" || mode === "starting") {
      btn.classList.remove("mode-next");
      btn.disabled = true;
      lbl.textContent = mode === "starting" ? I18N[lang].starting : I18N[lang].downloading;
      ic.innerHTML = '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 15"/>';
    } else {
      btn.classList.remove("mode-next");
      btn.disabled = false;
      lbl.textContent = I18N[lang].download_now;
      ic.innerHTML = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>';
    }
  }

  function syncPrimaryBtn() {
    if (window.__clipHavenIsPlaylistZero()) {
      setPrimaryVisual("blocked");
      return;
    }
    const curUrl = normalizeInputUrl($("url").value);
    if (!currentJobId) {
      setPrimaryVisual("ready");
    } else if (curUrl && curUrl !== activeDownloadUrl) {
      setPrimaryVisual("next");
    } else {
      setPrimaryVisual("downloading");
    }
    if ($("skip-btn")) {
      $("skip-btn").style.display = currentJobId && upNext.length > 0 ? "inline-flex" : "none";
    }
  }

  window.__clipHavenSetBtn = setPrimaryVisual;
  window.__clipHavenSyncPrimaryBtn = syncPrimaryBtn;

  function renderUpNext() {
    saveUpNext();
    const sec = $("upnext-section");
    if (!sec) return;
    $("upnext-count").textContent = String(upNext.length);
    if ($("skip-btn")) $("skip-btn").style.display = currentJobId && upNext.length > 0 ? "inline-flex" : "none";
    if (!upNext.length) {
      sec.style.display = "none";
      return;
    }
    sec.style.display = "flex";
    const list = $("upnext-list");
    list.innerHTML = "";
    upNext.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "list-row";
      const meta = document.createElement("div");
      meta.className = "list-meta";
      const t = document.createElement("div");
      t.className = "list-title";
      t.textContent = `${idx + 1}. ${item.title || item.url}`;
      const sub = document.createElement("div");
      sub.className = "list-sub";
      const fmtTag = document.createElement("span");
      fmtTag.className = "fmt-tag";
      fmtTag.textContent = item.format;
      sub.appendChild(fmtTag);
      const qSpan = document.createElement("span");
      qSpan.textContent = ["mp3", "m4a", "wav"].includes(item.format) ? "Audio" : (item.quality === "best" ? "Best" : `${item.quality}p`);
      sub.appendChild(qSpan);
      if (item.start_time || item.end_time) {
        const cSpan = document.createElement("span");
        cSpan.textContent = `• ${item.start_time || "00:00"}–${item.end_time || "End"}`;
        sub.appendChild(cSpan);
      }
      if (item.subtitles) {
        const ccSpan = document.createElement("span");
        ccSpan.textContent = "• CC";
        sub.appendChild(ccSpan);
      }
      meta.append(t, sub);

      const acts = document.createElement("div");
      acts.className = "row-actions";
      if (idx > 0) {
        const upBtn = document.createElement("button");
        upBtn.type = "button";
        upBtn.className = "icon-sq-btn";
        upBtn.title = "Move up";
        upBtn.innerHTML = '<svg class="icon" style="width:13px;height:13px" viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"/></svg>';
        upBtn.addEventListener("click", () => {
          const [m] = upNext.splice(idx, 1);
          upNext.splice(idx - 1, 0, m);
          renderUpNext();
        });
        acts.appendChild(upBtn);
      }
      const rmBtn = document.createElement("button");
      rmBtn.type = "button";
      rmBtn.className = "icon-sq-btn";
      rmBtn.title = "Remove";
      rmBtn.innerHTML = '<svg class="icon" style="width:13px;height:13px" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
      rmBtn.addEventListener("click", () => {
        upNext.splice(idx, 1);
        renderUpNext();
      });
      acts.appendChild(rmBtn);

      row.append(meta, acts);
      list.appendChild(row);
    });
  }

  window.__clipHavenTryAddUpNext = function () {
    const cleanUrl = normalizeInputUrl($("url").value);
    if (!cleanUrl || cleanUrl === activeDownloadUrl) {
      showToast(I18N[lang].already_running);
      return true;
    }
    const fmt = $("format").value;
    const isAudio = ["mp3", "m4a", "wav"].includes(fmt);
    const canThumb = ["mp4", "mkv", "mp3", "m4a"].includes(fmt);
    upNext.push({
      url: cleanUrl,
      title: ($("preview-card").style.display !== "none" && $("preview-title").textContent) || cleanUrl.replace(/^https?:\/\/(www\.)?/, "").slice(0, 44),
      folder: $("folder").value.trim(),
      quality: $("quality").value,
      format: fmt,
      start_time: $("start-time").value.trim(),
      end_time: $("end-time").value.trim(),
      subtitles: !isAudio && $("subtitles").checked,
      embed_thumbnail: canThumb && $("embed-thumbnail").checked,
      allow_playlist: $("allow-playlist").checked || Boolean(getPlaylistItemsParam()) || /\/playlist\b/i.test(cleanUrl),
      playlist_items: getPlaylistItemsParam(),
      title_hint: currentTitleHint,
      duration_hint: currentDurationHint,
      lang: localStorage.getItem("cliphaven_lang") || "en",
      thumb_url: ($("preview-thumb") && /^https?:/i.test($("preview-thumb").src || "")) ? $("preview-thumb").src : "",
    });
    renderUpNext();
    showToast(I18N[lang].added_next);
    $("url").value = "";
    syncClearBtn();
    hidePreview();
    updatePlatformIcon("");
    syncPrimaryBtn();
    return true;
  };

  async function launchQueuedItem(item) {
    activeDownloadUrl = item.url;
    try {
      const d = await api("/api/download", {
        method: "POST",
        body: JSON.stringify(item),
      });
      startPolling(d.id);
      syncPrimaryBtn();
    } catch (err) {
      status("Could not start queued download", err.message, 0, "Error", "error");
      activeDownloadUrl = "";
      syncPrimaryBtn();
    }
  }

  window.__clipHavenOnTransferEnd = function () {
    syncPrimaryBtn();
    if (upNext.length > 0) {
      const next = upNext.shift();
      renderUpNext();
      setTimeout(() => launchQueuedItem(next), 350);
    }
  };

  if ($("clear-upnext-btn")) {
    $("clear-upnext-btn").addEventListener("click", () => { upNext = []; renderUpNext(); });
  }
  if ($("skip-btn")) {
    $("skip-btn").addEventListener("click", async () => {
      if (!upNext.length) return;
      if (currentJobId) {
        try { await api("/api/cancel", { method: "POST", body: JSON.stringify({ id: currentJobId }) }); } catch (_) {}
      }
    });
  }

  let _lastPlatformSig = "";
  function updatePlatformIcon(raw) {
    const ic = $("url-platform-icon");
    if (!ic) return;
    const u = String(raw || "").toLowerCase();
    const prevHtml = ic.innerHTML;
    if (u.includes("youtube.com") || u.includes("youtu.be") || u.includes("youtube-nocookie.com")) {
      ic.style.color = "#ef4444";
      ic.innerHTML = '<rect x="2" y="5" width="20" height="14" rx="4"/><polygon points="10 9 15 12 10 15" fill="currentColor" stroke="none"/>';
    } else if (u.includes("facebook.com") || u.includes("fb.watch") || u.includes("fb.com") || u.includes("fb.gg")) {
      ic.style.color = "#3b82f6";
      ic.innerHTML = '<path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/>';
    } else if (u.includes("instagram.com") || u.includes("instagr.am")) {
      ic.style.color = "#ec4899";
      ic.innerHTML = '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/>';
    } else if (u.includes("threads.net") || u.includes("threads.com")) {
      ic.style.color = "var(--text)";
      ic.innerHTML = '<circle cx="12" cy="12" r="9"/><path d="M15.5 11.5c0-2-1.4-3.5-3.5-3.5s-3.5 1.5-3.5 3.5 1.4 3.5 3.5 3.5c1.5 0 2.7-.7 3.2-1.8"/>';
    } else if (u.includes("tiktok.com")) {
      ic.style.color = "#14b8a6";
      ic.innerHTML = '<path d="M9 12a4 4 0 1 0 4 4V4a5 5 0 0 0 5 5"/>';
    } else if (u.includes("twitter.com") || u.includes("x.com") || u.includes("t.co/")) {
      ic.style.color = "var(--text)";
      ic.innerHTML = '<path d="M4 4l16 16M20 4L4 20"/>';
    } else if (u.includes("linkedin.com") || u.includes("lnkd.in")) {
      ic.style.color = "#0a66c2";
      ic.innerHTML = '<rect x="3" y="3" width="18" height="18" rx="3"/><line x1="8" y1="11" x2="8" y2="16"/><circle cx="8" cy="8" r="0.8" fill="currentColor"/><path d="M12 16v-5m0 2a2 2 0 0 1 4 0v3"/>';
    } else if (u.includes("reddit.com") || u.includes("redd.it")) {
      ic.style.color = "#ff4500";
      ic.innerHTML = '<circle cx="12" cy="14" r="6"/><circle cx="9.8" cy="13.5" r="0.9" fill="currentColor" stroke="none"/><circle cx="14.2" cy="13.5" r="0.9" fill="currentColor" stroke="none"/><path d="M12 8l1.5-4 3 .8"/>';
    } else if (u.includes("vimeo.com")) {
      ic.style.color = "#1ab7ea";
      ic.innerHTML = '<path d="M4 7c1.5-1.5 3.2-1 4 1.2l1.8 6.3c.6 2 1.6 2.5 3.2 1.2 2.4-2 4.8-5.2 5.4-7.2.5-1.6-.4-2.5-2-2.2-1.1.2-2 1-2.5 2"/>';
    } else if (u.includes("dailymotion.com") || u.includes("dai.ly")) {
      ic.style.color = "#00aaff";
      ic.innerHTML = '<circle cx="11" cy="13" r="5"/><line x1="16" y1="5" x2="16" y2="18"/>';
    } else if (u.includes("twitch.tv")) {
      ic.style.color = "#9146ff";
      ic.innerHTML = '<path d="M4 3h16v11l-4 4h-4l-3 3v-3H4z"/><line x1="10" y1="8" x2="10" y2="12"/><line x1="15" y1="8" x2="15" y2="12"/>';
    } else if (u.includes("pinterest.com") || u.includes("pin.it")) {
      ic.style.color = "#e60023";
      ic.innerHTML = '<circle cx="12" cy="12" r="9"/><path d="M10 18l1.5-6.5M9.5 11.5a3 3 0 1 1 5.2 2c-.7 1-1.9 1.3-2.9.8"/>';
    } else if (u.includes("soundcloud.com") || u.includes("snd.sc")) {
      ic.style.color = "#ff5500";
      ic.innerHTML = '<path d="M17.5 17H8a4 4 0 0 1-.5-7.97A5 5 0 0 1 17 10a3.5 3.5 0 0 1 .5 7z"/><line x1="3" y1="13" x2="3" y2="16"/>';
    } else {
      ic.style.color = "var(--text-dim)";
      ic.innerHTML = '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>';
    }
    const sig = ic.style.color + "|" + ic.innerHTML;
    if (_lastPlatformSig && sig !== _lastPlatformSig && prevHtml !== ic.innerHTML) {
      ic.classList.remove("icon-pop");
      void ic.offsetWidth;
      ic.classList.add("icon-pop");
    }
    _lastPlatformSig = sig;
  }

  window.__clipHavenUpdatePlatformIcon = updatePlatformIcon;
  window.__clipHavenSyncPrimaryBtn = syncPrimaryBtn;
  updatePlatformIcon($("url").value);

  $("url").addEventListener("input", () => {
    updatePlatformIcon($("url").value);
    syncPrimaryBtn();
  });

  const formCard = $("form");
  if (formCard) {
    formCard.addEventListener("dragover", (e) => { e.preventDefault(); formCard.classList.add("drag-over"); });
    ["dragleave", "dragend"].forEach((ev) => formCard.addEventListener(ev, () => formCard.classList.remove("drag-over")));
    formCard.addEventListener("drop", (e) => {
      e.preventDefault();
      formCard.classList.remove("drag-over");
      const dropped = (e.dataTransfer?.getData("text/uri-list") || e.dataTransfer?.getData("text/plain") || "").trim();
      if (dropped && /^https?:\/\//i.test(dropped)) {
        $("url").value = dropped;
        syncClearBtn();
        updatePlatformIcon(dropped);
        triggerPreview(true);
        syncPrimaryBtn();
        showToast(I18N[lang].dropped);
      }
    });
  }

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") $("form").requestSubmit();
  });

  applyLang(lang);
  renderUpNext();
})();
