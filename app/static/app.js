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

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[ch]
  );
}

function showError(message) {
  const box = $("error");
  box.textContent = message;
  box.classList.remove("hidden");
}

function clearError() {
  $("error").classList.add("hidden");
  $("error").textContent = "";
}

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
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "";
  }
  if (seconds < 60) return `${Math.round(seconds)}s left`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}m ${secs}s left`;
}

function codecLabel(vcodec) {
  const codec = (vcodec || "").toLowerCase();
  if (!codec || codec === "unknown" || codec === "none") return "";
  if (codec.startsWith("avc") || codec.startsWith("h264")) return "H.264";
  if (codec.includes("hevc") || codec.startsWith("hev") || codec.startsWith("hvc")) {
    return "HEVC";
  }
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
  if (format.fps && format.fps > 30) {
    parts.push(`${Math.round(format.fps)}fps`);
  }
  if (format.filesize_label) {
    parts.push(format.filesize_label);
  }
  if (format.needs_audio) {
    parts.push("+ audio");
  }
  return parts.join(" · ");
}

function dedupeFormats(formats) {
  const seen = new Set();
  const result = [];
  for (const format of formats) {
    const key = [
      format.height,
      format.ext,
      Math.round(format.fps || 0),
      format.vcodec,
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(format);
  }
  return result;
}

function setMessage(element, text, kind) {
  element.textContent = text;
  element.classList.remove("ok", "bad");
  if (kind) element.classList.add(kind);
}

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

    // Populate speed profile <select> from backend data.
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
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Saving...";

  try {
    const current = await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ download_dir: $("download-dir").value.trim() }),
    });
    state.settings = current;
    $("download-dir").value = current.download_dir;
    $("settings-path").textContent = current.download_dir;
    setMessage(
      $("settings-msg"),
      `Saved. New downloads will be written to ${current.download_dir}.`,
      "ok"
    );
  } catch (error) {
    setMessage($("settings-msg"), error.message, "bad");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
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
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Opening...";

  try {
    const result = await api("/api/settings/browse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        initial_dir: $("download-dir").value.trim() || null,
      }),
    });

    if (result.cancelled || !result.download_dir) {
      setMessage($("settings-msg"), "Folder selection cancelled.", null);
      return;
    }

    $("download-dir").value = result.download_dir;
    setMessage($("settings-msg"), "Folder selected. Saving...", "ok");
    $("settings-form").requestSubmit();
  } catch (error) {
    setMessage($("settings-msg"), error.message, "bad");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

function estimateFor(item) {
  const info = item.info;
  if (item.audioOnly) {
    const audio = (info.audio_formats || [])[0];
    return audio
      ? { bytes: audio.size_bytes, estimate: audio.size_is_estimate }
      : null;
  }
  if (item.formatId) {
    const format = (info.video_formats || []).find(
      (candidate) => candidate.format_id === item.formatId
    );
    if (format) {
      return { bytes: format.size_bytes, estimate: format.size_is_estimate };
    }
  }
  const best = (info.video_formats || [])[0];
  return best ? { bytes: best.size_bytes, estimate: best.size_is_estimate } : null;
}

function estimateText(item) {
  const estimate = estimateFor(item);
  if (!estimate || !estimate.bytes) return "Size unknown until download";
  return `${estimate.estimate ? "Estimated ~" : "Size "}${formatSize(estimate.bytes)}`;
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

function buildQueueItem(item) {
  const wrapper = document.createElement("div");
  wrapper.className = "queue-item";
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
  select.setAttribute("aria-label", "Format");

  const best = document.createElement("option");
  best.value = "";
  best.textContent = "Best available";
  best.dataset.needsAudio = "0";
  select.appendChild(best);

  for (const format of dedupeFormats(
    (item.info.video_formats || []).filter((candidate) => candidate.format_id)
  )) {
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

  const updateEstimate = () => {
    estimate.textContent = estimateText(item);
  };
  updateEstimate();

  select.addEventListener("change", () => {
    item.formatId = select.value;
    const choice = select.selectedOptions[0];
    item.needsAudio = choice ? choice.dataset.needsAudio === "1" : false;
    updateEstimate();
  });

  audioCheckbox.addEventListener("change", () => {
    item.audioOnly = audioCheckbox.checked;
    select.disabled = item.audioOnly;
    updateEstimate();
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
  downloadButton.textContent = "Download";
  downloadButton.addEventListener("click", () => startItems([item], downloadButton));
  actions.appendChild(downloadButton);

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "secondary small";
  removeButton.textContent = "Remove";
  removeButton.addEventListener("click", () => {
    state.queue = state.queue.filter((candidate) => candidate.key !== item.key);
    renderQueue();
  });
  actions.appendChild(removeButton);

  wrapper.appendChild(actions);
  return wrapper;
}

function renderQueue() {
  const card = $("queue-card");
  const count = state.queue.length;

  if (!count) {
    card.classList.add("hidden");
    $("queue").innerHTML = "";
    $("queue-count").textContent = "";
    return;
  }

  card.classList.remove("hidden");
  $("queue-count").textContent = `${count} video${count === 1 ? "" : "s"}`;

  const container = $("queue");
  container.innerHTML = "";
  for (const item of state.queue) {
    container.appendChild(buildQueueItem(item));
  }
}

$("add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const input = $("url");
  const url = input.value.trim();
  if (!url) return;

  const button = $("add-btn");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Adding...";

  try {
    const info = await api("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (info.drm) {
      showError(`${info.title || "This video"} is DRM-protected and cannot be downloaded.`);
      return;
    }

    state.queue.push({
      key: `q${++state.queueSeq}`,
      url,
      info,
      formatId: "",
      needsAudio: false,
      audioOnly: false,
    });
    input.value = "";
    input.focus();
    renderQueue();
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

async function startItems(items, triggerButton) {
  if (!items.length) return;
  clearError();

  let originalText = null;
  if (triggerButton) {
    originalText = triggerButton.textContent;
    triggerButton.disabled = true;
    triggerButton.textContent = "Starting...";
  }

  const failures = [];
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
      state.queue = state.queue.filter((candidate) => candidate.key !== item.key);
    } catch (error) {
      failures.push(`${item.info.title || item.url}: ${error.message}`);
    }
  }

  renderQueue();
  await refreshJobs();

  if (failures.length) {
    showError(`Some videos could not be queued. ${failures.join(" ")}`);
  }

  if (triggerButton && originalText !== null) {
    triggerButton.disabled = false;
    triggerButton.textContent = originalText;
  }
}

$("download-all").addEventListener("click", () => {
  clearError();
  startItems([...state.queue], $("download-all"));
});

$("clear-queue").addEventListener("click", () => {
  state.queue = [];
  renderQueue();
});

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

function jobHtml(job) {
  const percent = Math.max(0, Math.min(100, Number(job.progress) || 0));
  const terminal = ["finished", "error", "cancelled"].includes(job.status);
  const actionLabel = terminal ? "Delete" : "Cancel";
  const saveLink =
    job.status === "finished" && job.download_url
      ? `<a class="button small" href="${esc(job.download_url)}" download="${esc(
          job.filename || "download"
        )}">Save file</a>`
      : "";
  const path = job.output_dir
    ? `<p class="job-path" title="${esc(job.output_dir)}">Saving to ${esc(
        job.output_dir
      )}</p>`
    : "";
  const title = job.title || job.filename || "Download";
  const detailTitle = job.error_detail
    ? ` title="${esc(job.error_detail)}"`
    : "";

  return `
    <article class="job-item" data-job-id="${esc(job.id)}">
      <div class="job-top">
        <div>
          <h3 class="job-title">${esc(title)}</h3>
          ${path}
        </div>
        <span class="pill ${esc(job.status)}">${esc(
          STATUS_LABELS[job.status] || job.status
        )}</span>
      </div>
      <div class="progress"><div class="progress-bar" style="width:${percent}%"></div></div>
      <div class="job-foot">
        <p class="job-detail"${detailTitle}>${esc(jobDetail(job))}</p>
        <div class="job-actions">
          ${saveLink}
          <button type="button" class="secondary small" data-job-action="remove" data-job-id="${esc(
            job.id
          )}">${actionLabel}</button>
        </div>
      </div>
    </article>`;
}

function renderJobs() {
  const card = $("downloads-card");
  if (!state.jobs.length) {
    card.classList.add("hidden");
    $("downloads").innerHTML = "";
    $("downloads-summary").textContent = "";
    return;
  }

  const active = state.jobs.filter(
    (job) => job.status === "queued" || job.status === "running"
  ).length;
  card.classList.remove("hidden");
  $("downloads-summary").textContent = `${active} active · ${state.jobs.length} total`;
  $("downloads").innerHTML = state.jobs.map(jobHtml).join("");
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
    renderJobs();
  } catch (error) {
    showError(error.message);
    button.disabled = false;
  }
});

loadSettings();
refreshJobs();
setInterval(() => {
  if (!document.hidden) refreshJobs();
}, 1200);
