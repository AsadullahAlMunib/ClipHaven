const $ = (id) => document.getElementById(id);
let timer = null;
let currentJobId = null;
function status(title, detail, pct = 0, pill = "Working", cls = "") {
  $("status").classList.add("show");
  $("title").textContent = title;
  $("title").className = "status-title " + cls;
  $("detail").textContent = detail || "";
  $("progress").value = Math.max(0, Math.min(100, pct));
  $("pill").textContent = pill;
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
const themeBtn = $("theme");
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  themeBtn.textContent = t === "light" ? "🌙 Dark" : "☀️ Light";
  localStorage.setItem("theme", t);
}
applyTheme(
  localStorage.getItem("theme") ||
    (matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark"),
);
themeBtn.onclick = () =>
  applyTheme(
    document.documentElement.getAttribute("data-theme") === "light"
      ? "dark"
      : "light",
  );
$("pick").onclick = async () => {
  const b = $("pick");
  b.disabled = true;
  try {
    const d = await api("/api/choose-folder", {
      method: "POST",
      body: "{}",
    });
    if (d.folder) $("folder").value = d.folder;
  } catch (e) {
    status("Folder picker failed", e.message, 0, "Error", "error");
  } finally {
    b.disabled = false;
  }
};
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
  status(
    "Starting download",
    "Checking URL and preparing download…",
    0,
    "Starting",
  );
  try {
    const d = await api("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url: $("url").value.trim(),
        folder: $("folder").value.trim(),
        quality: $("quality").value,
        format: $("format").value,
      }),
    });
    currentJobId = d.id;
    cb.style.display = "inline-block";
    timer = setInterval(async () => {
      try {
        const s = await api("/api/status?id=" + encodeURIComponent(d.id));
        status(
          s.title || s.state,
          s.detail || "",
          s.percent || 0,
          s.state || "Working",
          s.state === "Error"
            ? "error"
            : s.state === "Complete"
              ? "success"
              : s.state === "Cancelled"
                ? "error"
                : "",
        );
        if (s.state === "Complete" || s.state === "Error" || s.state === "Cancelled") {
          clearInterval(timer);
          timer = null;
          b.disabled = false;
          b.textContent = "Start another download";
          cb.style.display = "none";
          currentJobId = null;
        }
      } catch (err) {
        clearInterval(timer);
        timer = null;
        status("Status error", err.message, 0, "Error", "error");
        b.disabled = false;
        b.textContent = "Start download";
        cb.style.display = "none";
        currentJobId = null;
      }
    }, 800);
  } catch (err) {
    status("Could not start download", err.message, 0, "Error", "error");
    b.disabled = false;
    b.textContent = "Start download";
    cb.style.display = "none";
    currentJobId = null;
  }
};
$("format").onchange = () => {
  const audio = ["mp3", "m4a", "wav"].includes($("format").value);
  $("quality").disabled = audio;
  $("quality").style.opacity = audio ? "0.5" : "1";
};
$("format").onchange();
