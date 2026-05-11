const queueBody = document.querySelector("#queueBody");
const urlInput = document.querySelector("#urlInput");
const addBtn = document.querySelector("#addBtn");
const removeBtn = document.querySelector("#removeBtn");
const clearBtn = document.querySelector("#clearBtn");
const folderBtn = document.querySelector("#folderBtn");
const startBtn = document.querySelector("#startBtn");
const helpBtn = document.querySelector("#helpBtn");
const savePath = document.querySelector("#savePath");
const saveAs = document.querySelector("#saveAs");
const groupByComic = document.querySelector("#groupByComic");
const groupByChapter = document.querySelector("#groupByChapter");
const statusText = document.querySelector("#statusText");
const progressBar = document.querySelector("#progressBar");
const logs = document.querySelector("#logs");
const addFeedback = document.querySelector("#addFeedback");
const toast = document.querySelector("#toast");
const helpModal = document.querySelector("#helpModal");
const closeHelpBtn = document.querySelector("#closeHelpBtn");

let queue = [];
let selectedId = "";
let poller = null;

function api() {
  return window.pywebview.api;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 3200);
}

function collectRows() {
  return [...queueBody.querySelectorAll("tr[data-id]")].map((row) => ({
    id: row.dataset.id,
    start: row.querySelector("[data-field='start']").value,
    end: row.querySelector("[data-field='end']").value,
  }));
}

async function syncRows() {
  if (!queue.length) return;
  const response = await api().update_queue(collectRows());
  queue = response.queue;
}

function renderQueue(rows) {
  queue = rows;
  queueBody.innerHTML = "";

  if (!queue.length) {
    selectedId = "";
    queueBody.innerHTML = `<tr class="empty-row"><td colspan="3">Nenhum link na fila.</td></tr>`;
    return;
  }

  for (const item of queue) {
    const row = document.createElement("tr");
    row.dataset.id = item.id;
    row.className = item.id === selectedId ? "selected" : "";
    row.innerHTML = `
      <td>${escapeHtml(item.name)}</td>
      <td><input data-field="start" value="${escapeHtml(item.start)}" /></td>
      <td><input data-field="end" value="${escapeHtml(item.end)}" /></td>
    `;
    row.addEventListener("click", () => {
      selectedId = item.id;
      renderQueue(queue);
    });
    row.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", syncRows);
      input.addEventListener("click", (event) => event.stopPropagation());
    });
    queueBody.appendChild(row);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function refreshState() {
  const state = await api().get_state();
  statusText.textContent = state.status;
  progressBar.style.width = `${state.progress || 0}%`;
  startBtn.disabled = Boolean(state.active);
  addBtn.disabled = Boolean(state.active);
  clearBtn.disabled = Boolean(state.active);
  removeBtn.disabled = Boolean(state.active);
  logs.textContent = (state.logs || []).slice(-6).join("\n");

  if (state.error) {
    showToast(state.error);
  }

  if (!state.active && poller) {
    window.clearInterval(poller);
    poller = null;
  }
}

addBtn.addEventListener("click", async () => {
  const text = urlInput.value.trim();
  if (!text) {
    showToast("Cole pelo menos um link do Webtoon.");
    return;
  }

  const response = await api().add_urls(text);
  renderQueue(response.queue);
  urlInput.value = "";
  addFeedback.textContent = `${response.added.length} adicionado(s), ${response.ignored.length} ignorado(s).`;
});

removeBtn.addEventListener("click", async () => {
  if (!selectedId) {
    showToast("Selecione uma obra na fila.");
    return;
  }
  const response = await api().remove_item(selectedId);
  selectedId = "";
  renderQueue(response.queue);
});

clearBtn.addEventListener("click", async () => {
  const response = await api().clear_queue();
  renderQueue(response.queue);
});

folderBtn.addEventListener("click", async () => {
  const folder = await api().choose_folder();
  if (folder) {
    savePath.value = folder;
  }
});

saveAs.addEventListener("change", () => {
  const multipleImages = saveAs.value === "images";
  groupByChapter.disabled = !multipleImages;
  if (!multipleImages) {
    groupByChapter.checked = false;
  }
});

startBtn.addEventListener("click", async () => {
  await syncRows();
  const response = await api().start_download({
    savePath: savePath.value,
    saveAs: saveAs.value,
    groupByComic: groupByComic.checked,
    groupByChapter: groupByChapter.checked,
  });

  showToast(response.message);
  refreshState();
  if (response.ok && !poller) {
    poller = window.setInterval(refreshState, 650);
  }
});

function openHelp() {
  helpModal.classList.remove("hidden");
  helpModal.setAttribute("aria-hidden", "false");
}

function closeHelp() {
  helpModal.classList.add("hidden");
  helpModal.setAttribute("aria-hidden", "true");
}

helpBtn.addEventListener("click", openHelp);
closeHelpBtn.addEventListener("click", closeHelp);
helpModal.addEventListener("click", (event) => {
  if (event.target.matches("[data-close-help]")) {
    closeHelp();
  }
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeHelp();
  }
});

window.addEventListener("pywebviewready", async () => {
  renderQueue(await api().get_queue());
  await refreshState();
  saveAs.dispatchEvent(new Event("change"));
});
