const $ = (id) => document.getElementById(id);

const state = {
  settings: null,
  queue: [],
  queueSeq: 0,
  jobs: [],
  jobsRequest: false,
};

const STATUS_LABELS = {
  queued: "Queued",
  running: "Downloading",
  finished: "Complete",
  error: "Failed",
  cancelled: "Cancelled",
};

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const EXIT_MS = 160;

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );
}

/* ─── Motion helpers ────────────────────────────────────────── */

// Re-trigger the soft text-swap animation when a message changes.
function swap(el) {
  el.classList.remove("swap");
  void el.offsetWidth; // restart animation
  el.classList.add("swap");
}

// One-shot reveal for panels the first time they appear.
function reveal(el) {
  if (!el.classList.contains("hidden")) return;
  el.classList.remove("hidden");
  el.classList.remove("reveal");
  void el.offsetWidth;
  el.classList.add("reveal");
}

// Play the exit transition, then run the callback. Instant under reduced motion.
function leave(el, done) {
  if (!el) return done();
  if (reduceMotion.matches) return done();
  el.classList.add("leaving");
  setTimeout(done, EXIT_MS);
}

function setBusy(button, busy, busyText) {
  const label = button.querySelector(".btn-label") || button;
  if (busy) {
    button.dataset.original = label.textContent;
    button.disabled = true;
    button.classList.add("is-busy");
    label.textContent = busyText;
  } else {
    button.disabled = false;
    button.classList.remove("is-busy");
    if (button.dataset.original !== undefined) label.textContent = button.dataset.original;
  }
}

/* ─── Errors ────────────────────────────────────────────────── */

function showError(message) {
  $("error-text").textContent = message;
  const box = $("error");
  box.classList.add("hidden");
  reveal(box);
}

function clearError() {
  $("error").classList.add("hidden");
  $("error-text").textContent = "";
}

$("error-close").addEventListener("click", clearError);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok) {
    let message = data.detail || `Request failed (${response.status})`;
    if (message && typeof message === "object") {
      message = message.message || JSON.stringify(message);
    }
    throw new Error(message);
  }
  return data;
}

/* ─── Formatting ────────────────────────────────────────────── */

function formatDuration(seconds) {
  if (!seconds || !Number.isFinite(seconds)) return "";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function formatSize(bytes) {
  if (!bytes || !Number.isFinite(bytes)) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond || !Number.isFinite(bytesPerSecond)) return "";
  return `${formatSize(bytesPerSecond)}/s`;
}

function formatEta(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "";
  if (seconds < 60) return `${Math.round(seconds)}s left`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}m ${secs}s left`;
}

function codecLabel(vcodec) {
  const codec = (vcodec || "").toLowerCase();
  if (!codec || codec === "unknown" || codec === "none") return "";
  if (codec.startsWith("avc") || codec.startsWith("h264")) return "H.264";
  if (codec.includes("hevc") || codec.startsWith("hev") || codec.startsWith("hvc")) return "HEVC";
  if (codec.startsWith("av01") || codec.includes("av1")) return "AV1";
  if (codec.startsWith("vp9") || codec.startsWith("vp09")) return "VP9";
  if (codec.startsWith("vp8")) return "VP8";
  return "";
}

function formatLabel(format) {
  const parts = [];
  if (format.height) {
    parts.push(`${format.height}p`);
    parts.push(format.ext);
  } else {
    parts.push(format.note || format.ext.toUpperCase());
  }
  const codec = codecLabel(format.vcodec);
  if (codec) parts.push(codec);
  if (format.fps && format.fps > 30) parts.push(`${Math.round(format.fps)}fps`);
  if (format.filesize_label) parts.push(format.filesize_label);
  if (format.needs_audio) parts.push("+ audio");
  return parts.join(" · ");
}

function dedupeFormats(formats) {
  const seen = new Set();
  const result = [];
  for (const format of formats) {
    const key = [format.height, format.ext, Math.round(format.fps || 0), format.vcodec].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(format);
  }
  return result;
}

function setMessage(element, text, kind) {
  const changed = element.textContent !== text;
  element.textContent = text;
  element.classList.remove("ok", "bad");
  if (kind) element.classList.add(kind);
  if (changed && text) swap(element);
}

/* ─── Empty state ───────────────────────────────────────────── */

function updateEmptyState() {
  const empty = $("empty-state");
  const isEmpty = !state.queue.length && !state.jobs.length;
  if (isEmpty && empty.classList.contains("hidden")) {
    empty.classList.remove("hidden");
    empty.classList.remove("reveal");
    void empty.offsetWidth;
    empty.classList.add("reveal");
  } else if (!isEmpty) {
    empty.classList.add("hidden");
  }
}

/* ─── Settings ──────────────────────────────────────────────── */

function speedProfile(settings) {
  const profiles = settings?.speed_profiles || [];
  return profiles.find((profile) => profile.id === settings?.speed_profile) || null;
}

function showSpeedHint(settings, prefix) {
  const profile = speedProfile(settings);
  if (!profile) {
    setMessage($("speed-msg"), "", null);
    return;
  }
  const text = prefix
    ? `${prefix} ${profile.label} mode is active. ${profile.description}`
    : `${profile.label}: ${profile.description}`;
  setMessage($("speed-msg"), text, prefix ? "ok" : null);
}

async function loadSettings() {
  try {
    const current = await api("/api/settings");
    state.settings = current;
    $("download-dir").value = current.download_dir;
    $("settings-path").textContent = current.download_dir;

    const profileSelect = $("speed-profile");
    profileSelect.innerHTML = "";
    for (const profile of current.speed_profiles || []) {
      const option = document.createElement("option");
      option.value = profile.id;
      option.textContent = `${profile.label} — ${profile.description}`;
      profileSelect.appendChild(option);
    }
    profileSelect.value = current.speed_profile || "fast";
    showSpeedHint(current);
    const aria2 = $("aria2-status");
    if (current.aria2_available) {
      aria2.textContent = "aria2c ready";
      aria2.classList.add("good");
    } else {
      aria2.textContent = "Native downloader";
      aria2.classList.remove("good");
    }
    aria2.classList.remove("hidden");
    if (current.settings_error) {
      setMessage($("settings-msg"), current.settings_error, "bad");
    } else {
      setMessage(
        $("settings-msg"),
        `New downloads save here. Finished files are removed after ${current.file_ttl_minutes} minutes.`,
        null
      );
    }
  } catch (error) {
    $("settings-path").textContent = "Could not load the download location.";
    setMessage($("settings-msg"), error.message, "bad");
  }
}

$("settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const button = $("save-settings");
  setBusy(button, true, "Saving…");

  try {
    const current = await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ download_dir: $("download-dir").value.trim() }),
    });
    state.settings = current;
    $("download-dir").value = current.download_dir;
    $("settings-path").textContent = current.download_dir;
    swap($("settings-path"));
    setMessage($("settings-msg"), `Saved. New downloads will be written to ${current.download_dir}.`, "ok");
  } catch (error) {
    setMessage($("settings-msg"), error.message, "bad");
  } finally {
    setBusy(button, false);
  }
});

$("speed-profile").addEventListener("change", async () => {
  const select = $("speed-profile");
  const profile = select.value;
  select.disabled = true;

  try {
    const current = await api("/api/settings/speed", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    });
    state.settings = current;
    select.value = current.speed_profile;
    showSpeedHint(current, "Saved.");
  } catch (error) {
    select.value = state.settings?.speed_profile || "fast";
    setMessage($("speed-msg"), error.message, "bad");
  } finally {
    select.disabled = false;
  }
});

$("reset-settings").addEventListener("click", () => {
  if (!state.settings) return;
  $("download-dir").value = state.settings.default_download_dir;
  $("settings-form").requestSubmit();
});

$("browse-dir").addEventListener("click", async () => {
  clearError();
  const button = $("browse-dir");
  setBusy(button, true, "Opening…");

  try {
    const result = await api("/api/settings/browse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initial_dir: $("download-dir").value.trim() || null }),
    });

    if (result.cancelled || !result.download_dir) {
      setMessage($("settings-msg"), "No folder chosen. Your current location is unchanged.", null);
      return;
    }

    $("download-dir").value = result.download_dir;
    setMessage($("settings-msg"), "Folder selected. Saving…", "ok");
    $("settings-form").requestSubmit();
  } catch (error) {
    setMessage($("settings-msg"), error.message, "bad");
  } finally {
    setBusy(button, false);
  }
});

/* ─── Queue ─────────────────────────────────────────────────── */

function estimateFor(item) {
  const info = item.info;
  if (item.audioOnly) {
    const audio = (info.audio_formats || [])[0];
    return audio ? { bytes: audio.size_bytes, estimate: audio.size_is_estimate } : null;
  }
  if (item.formatId) {
    const format = (info.video_formats || []).find((c) => c.format_id === item.formatId);
    if (format) return { bytes: format.size_bytes, estimate: format.size_is_estimate };
  }
  const best = (info.video_formats || [])[0];
  return best ? { bytes: best.size_bytes, estimate: best.size_is_estimate } : null;
}

function estimateText(item) {
  const estimate = estimateFor(item);
  if (!estimate || !estimate.bytes) return "Size shown once download starts";
  return `${estimate.estimate ? "About " : "Size "}${formatSize(estimate.bytes)}`;
}

function makeThumbnail(info) {
  if (info.thumbnail) {
    const img = document.createElement("img");
    img.className = "queue-thumb";
    img.src = info.thumbnail;
    img.alt = "";
    img.loading = "lazy";
    return img;
  }
  const placeholder = document.createElement("div");
  placeholder.className = "queue-thumb placeholder";
  placeholder.textContent = "No preview";
  return placeholder;
}

function buildQueueItem(item, animate) {
  const wrapper = document.createElement("div");
  wrapper.className = "queue-item" + (animate ? " enter" : "");
  wrapper.dataset.key = item.key;

  wrapper.appendChild(makeThumbnail(item.info));

  const body = document.createElement("div");
  body.className = "queue-body";

  const title = document.createElement("h3");
  title.className = "queue-title";
  title.textContent = item.info.title || item.url;
  body.appendChild(title);

  const metaParts = [];
  if (item.info.uploader) metaParts.push(item.info.uploader);
  if (item.info.duration) metaParts.push(formatDuration(item.info.duration));
  if (item.info.extractor) metaParts.push(item.info.extractor);
  const meta = document.createElement("p");
  meta.className = "queue-meta";
  meta.textContent = metaParts.join(" · ");
  body.appendChild(meta);

  const controls = document.createElement("div");
  controls.className = "queue-controls";

  const field = document.createElement("div");
  field.className = "field";
  const select = document.createElement("select");
  select.setAttribute("aria-label", "Quality and format");

  const best = document.createElement("option");
  best.value = "";
  best.textContent = "Best available";
  best.dataset.needsAudio = "0";
  select.appendChild(best);

  for (const format of dedupeFormats((item.info.video_formats || []).filter((c) => c.format_id))) {
    const option = document.createElement("option");
    option.value = format.format_id;
    option.textContent = formatLabel(format);
    option.dataset.needsAudio = format.needs_audio ? "1" : "0";
    select.appendChild(option);
  }

  select.value = item.formatId || "";
  const selected = select.selectedOptions[0];
  item.needsAudio = selected ? selected.dataset.needsAudio === "1" : false;
  select.disabled = item.audioOnly;

  const audioLabel = document.createElement("label");
  audioLabel.className = "check";
  const audioCheckbox = document.createElement("input");
  audioCheckbox.type = "checkbox";
  audioCheckbox.checked = item.audioOnly;
  audioLabel.appendChild(audioCheckbox);
  audioLabel.appendChild(document.createTextNode("Audio only (MP3)"));

  const estimate = document.createElement("span");
  estimate.className = "estimate";
  estimate.setAttribute("aria-live", "polite");

  const updateEstimate = (animateIt) => {
    estimate.textContent = estimateText(item);
    if (animateIt) swap(estimate);
  };
  updateEstimate(false);

  select.addEventListener("change", () => {
    item.formatId = select.value;
    const choice = select.selectedOptions[0];
    item.needsAudio = choice ? choice.dataset.needsAudio === "1" : false;
    updateEstimate(true);
  });

  audioCheckbox.addEventListener("change", () => {
    item.audioOnly = audioCheckbox.checked;
    select.disabled = item.audioOnly;
    updateEstimate(true);
  });

  field.appendChild(select);
  controls.appendChild(field);

  const audioWrap = document.createElement("div");
  audioWrap.appendChild(audioLabel);
  audioWrap.appendChild(estimate);
  controls.appendChild(audioWrap);

  body.appendChild(controls);
  wrapper.appendChild(body);

  const actions = document.createElement("div");
  actions.className = "queue-actions";

  const downloadButton = document.createElement("button");
  downloadButton.type = "button";
  downloadButton.className = "small";
  downloadButton.innerHTML = '<span class="spinner" aria-hidden="true"></span><span class="btn-label">Download</span>';
  downloadButton.addEventListener("click", () => startItems([item], downloadButton));
  actions.appendChild(downloadButton);

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "secondary small";
  removeButton.textContent = "Remove";
  removeButton.addEventListener("click", () => removeQueueItem(item.key));
  actions.appendChild(removeButton);

  wrapper.appendChild(actions);
  return wrapper;
}

function updateQueueChrome() {
  const count = state.queue.length;
  if (!count) {
    $("queue-card").classList.add("hidden");
    $("queue-count").textContent = "";
  } else {
    reveal($("queue-card"));
    $("queue-count").textContent = `${count} video${count === 1 ? "" : "s"}`;
  }
  updateEmptyState();
}

// Add one row: the existing rows stay put, only the new one animates.
function appendQueueItem(item) {
  updateQueueChrome();
  $("queue").appendChild(buildQueueItem(item, true));
}

function removeQueueItem(key) {
  state.queue = state.queue.filter((c) => c.key !== key);
  const el = $("queue").querySelector(`[data-key="${key}"]`);
  leave(el, () => {
    if (el) el.remove();
    updateQueueChrome();
  });
}

function removeQueueItems(keys) {
  state.queue = state.queue.filter((c) => !keys.includes(c.key));
  const els = keys
    .map((k) => $("queue").querySelector(`[data-key="${k}"]`))
    .filter(Boolean);
  els.forEach((el) => !reduceMotion.matches && el.classList.add("leaving"));
  setTimeout(() => {
    els.forEach((el) => el.remove());
    updateQueueChrome();
  }, reduceMotion.matches ? 0 : EXIT_MS);
}

/* ─── Add video ─────────────────────────────────────────────── */

$("add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const input = $("url");
  const url = input.value.trim();
  if (!url) return;

  const button = $("add-btn");
  setBusy(button, true, "Looking it up…");

  try {
    const info = await api("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (info.drm) {
      showError(`${info.title || "This video"} is DRM-protected, so it can’t be downloaded.`);
      return;
    }

    const item = {
      key: `q${++state.queueSeq}`,
      url,
      info,
      formatId: "",
      needsAudio: false,
      audioOnly: false,
    };
    state.queue.push(item);
    input.value = "";
    input.focus();
    appendQueueItem(item);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(button, false);
  }
});

// One-tap paste, with graceful fallback when clipboard access is blocked.
$("paste-btn").addEventListener("click", async () => {
  try {
    const text = (await navigator.clipboard.readText()).trim();
    if (text) {
      $("url").value = text;
      $("url").focus();
    }
  } catch {
    $("url").focus();
    showError("Your browser blocked clipboard access. Press Ctrl/⌘ + V in the field instead.");
  }
});

async function startItems(items, triggerButton) {
  if (!items.length) return;
  clearError();

  if (triggerButton) setBusy(triggerButton, true, "Starting…");

  const failures = [];
  const started = [];
  for (const item of items) {
    try {
      await api("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: item.info.webpage_url || item.url,
          format_id: item.audioOnly ? null : item.formatId || null,
          needs_audio: !item.audioOnly && item.needsAudio,
          audio_only: item.audioOnly,
          title: item.info.title,
        }),
      });
      started.push(item.key);
    } catch (error) {
      failures.push(`${item.info.title || item.url}: ${error.message}`);
    }
  }

  removeQueueItems(started);
  await refreshJobs();

  if (failures.length) {
    showError(`Some videos could not be queued. ${failures.join(" ")}`);
  }

  if (triggerButton) setBusy(triggerButton, false);
}

$("download-all").addEventListener("click", () => {
  clearError();
  startItems([...state.queue], $("download-all"));
});

$("clear-queue").addEventListener("click", () => {
  removeQueueItems(state.queue.map((i) => i.key));
});

/* ─── Jobs (keyed in-place updates, so polling never replays animation) ── */

function jobDetail(job) {
  if (job.status === "queued") return "Waiting for a free slot";
  if (job.status === "running") {
    const parts = [];
    if (job.stage) parts.push(job.stage);
    parts.push(`${Math.round(job.progress)}%`);
    if (job.downloaded_bytes !== null && job.downloaded_bytes !== undefined) {
      const downloaded = formatSize(job.downloaded_bytes);
      if (job.total_bytes) {
        const total = `${job.total_bytes_is_estimate ? "~" : ""}${formatSize(job.total_bytes)}`;
        parts.push(`${downloaded} / ${total}`);
      } else {
        parts.push(`${downloaded} downloaded`);
      }
    }
    if (job.speed) parts.push(formatSpeed(job.speed));
    if (job.eta) parts.push(formatEta(job.eta));
    return parts.join(" · ");
  }
  if (job.status === "finished") {
    return [job.filename, formatSize(job.file_size)].filter(Boolean).join(" · ");
  }
  if (job.status === "error") return job.error || "Download failed.";
  if (job.status === "cancelled") return "The download was cancelled.";
  return "";
}

function buildJobEl(job, animate) {
  const el = document.createElement("article");
  el.className = "job-item" + (animate ? " enter" : "");
  el.dataset.jobId = job.id;
  el.innerHTML = `
    <div class="job-top">
      <div>
        <h3 class="job-title"></h3>
        <p class="job-path hidden"></p>
      </div>
      <span class="pill"></span>
    </div>
    <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar"></div></div>
    <div class="job-foot">
      <p class="job-detail"></p>
      <div class="job-actions">
        <span class="save-slot"></span>
        <button type="button" class="secondary small" data-job-action="remove"></button>
      </div>
    </div>`;
  return el;
}

function updateJobEl(el, job, justFinished) {
  const percent = Math.max(0, Math.min(100, Number(job.progress) || 0));
  const terminal = ["finished", "error", "cancelled"].includes(job.status);

  el.dataset.status = job.status;
  el.querySelector(".job-title").textContent = job.title || job.filename || "Download";

  const pathEl = el.querySelector(".job-path");
  if (job.output_dir) {
    pathEl.textContent = `Saving to ${job.output_dir}`;
    pathEl.title = job.output_dir;
    pathEl.classList.remove("hidden");
  } else {
    pathEl.classList.add("hidden");
  }

  const pill = el.querySelector(".pill");
  pill.className = `pill ${job.status}`;
  pill.textContent = STATUS_LABELS[job.status] || job.status;

  const bar = el.querySelector(".progress-bar");
  const shown = job.status === "finished" ? 100 : percent;
  bar.style.transform = `scaleX(${shown / 100})`;
  el.querySelector(".progress").setAttribute("aria-valuenow", String(Math.round(shown)));
  el.querySelector(".progress").setAttribute("aria-label", `${STATUS_LABELS[job.status] || job.status}`);

  const detail = el.querySelector(".job-detail");
  const detailText = jobDetail(job);
  if (detail.textContent !== detailText) detail.textContent = detailText;
  detail.title = job.error_detail || "";

  // Save link: created once when the file is ready, so it never flickers.
  const slot = el.querySelector(".save-slot");
  if (job.status === "finished" && job.download_url) {
    if (!slot.firstChild) {
      const a = document.createElement("a");
      a.className = "button small";
      a.href = job.download_url;
      a.setAttribute("download", job.filename || "download");
      a.textContent = "Save file";
      slot.appendChild(a);
    }
  } else if (slot.firstChild) {
    slot.textContent = "";
  }

  const remove = el.querySelector("[data-job-action]");
  const label = terminal ? "Delete" : "Cancel";
  if (remove.textContent !== label) remove.textContent = label;
  remove.dataset.jobId = job.id;

  // Rare, meaningful moment: celebrate once, on the live transition only.
  if (justFinished && !reduceMotion.matches) {
    el.classList.add("celebrate");
    setTimeout(() => el.classList.remove("celebrate"), 700);
  }
}

function renderJobs() {
  const card = $("downloads-card");
  const container = $("downloads");

  if (!state.jobs.length) {
    card.classList.add("hidden");
    container.innerHTML = "";
    $("downloads-summary").textContent = "";
    updateEmptyState();
    return;
  }

  const active = state.jobs.filter((j) => j.status === "queued" || j.status === "running").length;
  reveal(card);
  $("downloads-summary").textContent =
    active > 0 ? `${active} active · ${state.jobs.length} total` : `${state.jobs.length} total`;

  const existing = new Map();
  container.querySelectorAll(".job-item").forEach((el) => existing.set(el.dataset.jobId, el));
  const firstPaint = existing.size === 0;
  const seen = new Set();

  state.jobs.forEach((job, index) => {
    seen.add(job.id);
    let el = existing.get(job.id);
    let justFinished = false;
    if (!el) {
      // Animate only genuinely new rows, not the initial page load
      el = buildJobEl(job, !firstPaint);
      container.insertBefore(el, container.children[index] || null);
    } else {
      justFinished = el.dataset.status !== "finished" && job.status === "finished" &&
        ["running", "queued"].includes(el.dataset.status);
      if (container.children[index] !== el) container.insertBefore(el, container.children[index] || null);
    }
    updateJobEl(el, job, justFinished);
  });

  existing.forEach((el, id) => {
    if (!seen.has(id) && !el.classList.contains("leaving")) el.remove();
  });

  updateEmptyState();
}

async function refreshJobs() {
  if (state.jobsRequest) return;
  state.jobsRequest = true;
  try {
    const data = await api("/api/jobs");
    state.jobs = data.jobs || [];
    renderJobs();
  } catch {
    // Transient polling failures should not disrupt the UI.
  } finally {
    state.jobsRequest = false;
  }
}

$("downloads").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-job-action]");
  if (!button) return;

  const jobId = button.dataset.jobId;
  button.disabled = true;
  try {
    await api(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
    state.jobs = state.jobs.filter((job) => job.id !== jobId);
    const el = button.closest(".job-item");
    leave(el, () => renderJobs());
  } catch (error) {
    showError(error.message);
    button.disabled = false;
  }
});

/* ─── Boot ──────────────────────────────────────────────────── */

updateEmptyState();
loadSettings();
refreshJobs();
setInterval(() => {
  if (!document.hidden) refreshJobs();
}, 1200);