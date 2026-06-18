'use strict';

// ---------------------------------------------------------------------------
// State & DOM
// ---------------------------------------------------------------------------
const state = {
  folders: [],
  mode: 'clean',
  currentJobId: null,
  pollTimer: null,
  lastScan: null,
  lastScanJobId: null,
};

const $ = (sel) => document.querySelector(sel);

const el = {
  capabilities: $('#capabilities'),
  pickFolderBtn: $('#pickFolderBtn'),
  manualFolder: $('#manualFolder'),
  addManualBtn: $('#addManualBtn'),
  clearFoldersBtn: $('#clearFoldersBtn'),
  folderList: $('#folderList'),
  folderCount: $('#folderCount'),
  profileSelect: $('#profileSelect'),
  loadProfileBtn: $('#loadProfileBtn'),
  deleteProfileBtn: $('#deleteProfileBtn'),
  profileName: $('#profileName'),
  saveProfileBtn: $('#saveProfileBtn'),
  includeAll: $('#includeAll'),
  keepRule: $('#keepRule'),
  minSize: $('#minSize'),
  maxSize: $('#maxSize'),
  findExact: $('#findExact'),
  findSimilarImages: $('#findSimilarImages'),
  imageSimilarity: $('#imageSimilarity'),
  excludePatterns: $('#excludePatterns'),
  cleanPane: $('#cleanPane'),
  consolidatePane: $('#consolidatePane'),
  cleanMode: $('#cleanMode'),
  scanBtn: $('#scanBtn'),
  targetFolder: $('#targetFolder'),
  pickTargetBtn: $('#pickTargetBtn'),
  targetInfo: $('#targetInfo'),
  structure: $('#structure'),
  operation: $('#operation'),
  onConflict: $('#onConflict'),
  dedupeSimilar: $('#dedupeSimilar'),
  previewBtn: $('#previewBtn'),
  consolidateBtn: $('#consolidateBtn'),
  progress: $('#progress'),
  progressMessage: $('#progressMessage'),
  progressBar: $('#progressBar'),
  progressPhase: $('#progressPhase'),
  cancelBtn: $('#cancelBtn'),
  status: $('#status'),
  summary: $('#summary'),
  resultActions: $('#resultActions'),
  selectRecommendedBtn: $('#selectRecommendedBtn'),
  clearSelectionBtn: $('#clearSelectionBtn'),
  reportJsonBtn: $('#reportJsonBtn'),
  reportCsvBtn: $('#reportCsvBtn'),
  cleanBtn: $('#cleanBtn'),
  results: $('#results'),
  quarantineToggle: $('#quarantineToggle'),
  quarantineBody: $('#quarantineBody'),
  loadQuarantineBtn: $('#loadQuarantineBtn'),
  restoreSelectedBtn: $('#restoreSelectedBtn'),
  quarantineList: $('#quarantineList'),
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 2)} ${units[index]}`;
}

function formatDate(timestamp) {
  return new Date(timestamp * 1000).toLocaleString('de-DE');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function setStatus(message, kind = 'info') {
  el.status.className = `status ${kind === 'error' ? 'error' : kind === 'success' ? 'success' : ''}`;
  el.status.textContent = message;
  el.status.classList.remove('hidden');
}

function hideStatus() { el.status.classList.add('hidden'); }

async function api(url, options) {
  const response = await fetch(url, options);
  let data = null;
  try { data = await response.json(); } catch { /* no body */ }
  if (!response.ok) {
    throw new Error((data && (data.detail || data.message)) || `Fehler ${response.status}`);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------
function renderFolders() {
  el.folderCount.textContent = `${state.folders.length} Ordner`;
  el.folderList.innerHTML = '';
  if (state.folders.length === 0) {
    el.folderList.innerHTML = '<li class="empty-row">Noch keine Quellordner. Über „+ Ordner auswählen" hinzufügen.</li>';
    return;
  }
  state.folders.forEach((folder, index) => {
    const li = document.createElement('li');
    li.className = 'folder-item';
    li.innerHTML = `
      <div><div class="path">${escapeHtml(folder)}</div><div class="meta">Quelle ${index + 1}</div></div>
      <button data-index="${index}" type="button">Entfernen</button>`;
    li.querySelector('button').addEventListener('click', () => {
      state.folders.splice(index, 1);
      renderFolders();
    });
    el.folderList.appendChild(li);
  });
}

function addFolder(folder) {
  const trimmed = (folder || '').trim();
  if (!trimmed) return;
  const exists = state.folders.some((item) => item.toLowerCase() === trimmed.toLowerCase());
  if (!exists) state.folders.push(trimmed);
  renderFolders();
}

el.pickFolderBtn.addEventListener('click', async () => {
  el.pickFolderBtn.disabled = true;
  setStatus('Ordnerauswahl wird geöffnet …');
  try {
    const data = await api('/api/select-folder');
    if (data.folder) { addFolder(data.folder); hideStatus(); }
    else setStatus('Keine Auswahl getroffen.');
  } catch (error) {
    setStatus(`${error.message} Du kannst den Pfad auch manuell eintippen.`, 'error');
  } finally {
    el.pickFolderBtn.disabled = false;
  }
});

el.addManualBtn.addEventListener('click', () => { addFolder(el.manualFolder.value); el.manualFolder.value = ''; });
el.manualFolder.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { addFolder(el.manualFolder.value); el.manualFolder.value = ''; }
});
el.clearFoldersBtn.addEventListener('click', () => { state.folders = []; renderFolders(); });

// ---------------------------------------------------------------------------
// Options / config
// ---------------------------------------------------------------------------
function selectedCategories() {
  return [...document.querySelectorAll('.category:checked')].map((input) => input.value);
}

function baseOptions() {
  const maxValue = el.maxSize.value.trim();
  return {
    folders: state.folders,
    include_all_files: el.includeAll.checked,
    categories: selectedCategories(),
    min_size_mb: Number(el.minSize.value || 0),
    max_size_mb: maxValue ? Number(maxValue) : null,
    exclude_patterns: el.excludePatterns.value.split(',').map((v) => v.trim()).filter(Boolean),
    keep_rule: el.keepRule.value,
  };
}

function scanOptions() {
  return {
    ...baseOptions(),
    find_exact: el.findExact.checked,
    find_similar_images: el.findSimilarImages.checked,
    image_similarity: Number(el.imageSimilarity.value || 8),
  };
}

function consolidateOptions(dryRun) {
  return {
    ...baseOptions(),
    target: el.targetFolder.value.trim(),
    dedupe_similar_images: el.dedupeSimilar.checked,
    image_similarity: Number(el.imageSimilarity.value || 8),
    operation: el.operation.value,
    structure: el.structure.value,
    on_conflict: el.onConflict.value,
    dry_run: !!dryRun,
  };
}

function gatherConfig() {
  return {
    folders: state.folders,
    mode: state.mode,
    options: scanOptions(),
    target: el.targetFolder.value.trim(),
    structure: el.structure.value,
    operation: el.operation.value,
    on_conflict: el.onConflict.value,
    dedupe_similar: el.dedupeSimilar.checked,
    clean_mode: el.cleanMode.value,
  };
}

function applyConfig(config) {
  if (!config) return;
  state.folders = Array.isArray(config.folders) ? [...config.folders] : [];
  renderFolders();
  const options = config.options || {};
  el.includeAll.checked = !!options.include_all_files;
  document.querySelectorAll('.category').forEach((input) => {
    input.checked = !options.categories || options.categories.length === 0 || options.categories.includes(input.value);
  });
  if (options.keep_rule) el.keepRule.value = options.keep_rule;
  el.minSize.value = options.min_size_mb ?? 0;
  el.maxSize.value = options.max_size_mb ?? '';
  el.excludePatterns.value = (options.exclude_patterns || []).join(', ');
  el.findExact.checked = options.find_exact !== false;
  el.findSimilarImages.checked = !!options.find_similar_images;
  el.imageSimilarity.value = options.image_similarity ?? 8;
  if (config.target) el.targetFolder.value = config.target;
  if (config.structure) el.structure.value = config.structure;
  if (config.operation) el.operation.value = config.operation;
  if (config.on_conflict) el.onConflict.value = config.on_conflict;
  el.dedupeSimilar.checked = !!config.dedupe_similar;
  if (config.clean_mode) el.cleanMode.value = config.clean_mode;
  if (config.mode) switchMode(config.mode);
}

// ---------------------------------------------------------------------------
// Mode tabs
// ---------------------------------------------------------------------------
function switchMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.mode === mode));
  el.cleanPane.classList.toggle('hidden', mode !== 'clean');
  el.consolidatePane.classList.toggle('hidden', mode !== 'consolidate');
}

document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => switchMode(tab.dataset.mode));
});

// ---------------------------------------------------------------------------
// Target folder picker + disk info
// ---------------------------------------------------------------------------
el.pickTargetBtn.addEventListener('click', async () => {
  el.pickTargetBtn.disabled = true;
  try {
    const data = await api('/api/select-target');
    if (data.folder) { el.targetFolder.value = data.folder; refreshTargetInfo(); }
  } catch (error) {
    setStatus(`${error.message} Du kannst den Zielpfad auch manuell eintippen.`, 'error');
  } finally {
    el.pickTargetBtn.disabled = false;
  }
});

el.targetFolder.addEventListener('change', refreshTargetInfo);

async function refreshTargetInfo() {
  const target = el.targetFolder.value.trim();
  if (!target) { el.targetInfo.textContent = ''; return; }
  try {
    const data = await api(`/api/disk-usage?path=${encodeURIComponent(target)}`);
    el.targetInfo.textContent = `Freier Speicher am Ziel: ${formatBytes(data.free)} von ${formatBytes(data.total)}`;
  } catch {
    el.targetInfo.textContent = '';
  }
}

// ---------------------------------------------------------------------------
// Background job runner with live progress
// ---------------------------------------------------------------------------
function showProgress(show) {
  el.progress.classList.toggle('hidden', !show);
}

function updateProgress(job) {
  el.progressMessage.textContent = job.message || 'Wird verarbeitet …';
  el.progressPhase.textContent = job.total > 0 ? `${job.phase} · ${job.processed} / ${job.total}` : job.phase;
  if (job.total > 0) {
    el.progressBar.classList.remove('indeterminate');
    el.progressBar.style.width = `${job.percent || 0}%`;
  } else {
    el.progressBar.classList.add('indeterminate');
  }
}

function stopPolling() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
}

function runJob(startUrl, body) {
  return new Promise((resolve, reject) => {
    api(startUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((start) => {
      state.currentJobId = start.job_id;
      showProgress(true);
      updateProgress({ phase: 'queued', total: 0, message: 'In Warteschlange …' });

      state.pollTimer = setInterval(async () => {
        try {
          const job = await api(`/api/v1/jobs/${start.job_id}`);
          if (['queued', 'running'].includes(job.status)) {
            updateProgress(job);
            return;
          }
          stopPolling();
          showProgress(false);
          state.currentJobId = null;
          if (job.status === 'completed') {
            const result = await api(`/api/v1/jobs/${start.job_id}/result`);
            resolve({ jobId: start.job_id, result });
          } else if (job.status === 'cancelled') {
            reject(new Error('Vorgang abgebrochen.'));
          } else {
            reject(new Error(job.error || job.message || 'Vorgang fehlgeschlagen.'));
          }
        } catch (error) {
          stopPolling();
          showProgress(false);
          state.currentJobId = null;
          reject(error);
        }
      }, 350);
    }).catch((error) => {
      showProgress(false);
      reject(error);
    });
  });
}

el.cancelBtn.addEventListener('click', async () => {
  if (!state.currentJobId) return;
  try { await api(`/api/v1/jobs/${state.currentJobId}/cancel`, { method: 'POST' }); } catch { /* ignore */ }
  setStatus('Abbruch angefordert …');
});

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------
function validateSources() {
  if (state.folders.length === 0) {
    setStatus('Bitte zuerst mindestens einen Quellordner hinzufügen.', 'error');
    return false;
  }
  return true;
}

function setBusy(busy) {
  [el.scanBtn, el.previewBtn, el.consolidateBtn].forEach((button) => { button.disabled = busy; });
}

// ---------------------------------------------------------------------------
// SCAN flow
// ---------------------------------------------------------------------------
el.scanBtn.addEventListener('click', async () => {
  if (!validateSources()) return;
  if (!el.findExact.checked && !el.findSimilarImages.checked) {
    setStatus('Bitte mindestens eine Erkennungsart aktivieren (exakt oder ähnliche Bilder).', 'error');
    return;
  }
  setBusy(true);
  resetResults();
  setStatus('Analyse läuft …');
  try {
    const { jobId, result } = await runJob('/api/v1/scans', scanOptions());
    state.lastScan = result;
    state.lastScanJobId = jobId;
    hideStatus();
    renderScanSummary(result.summary);
    renderScanResults(result);
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    setBusy(false);
  }
});

function resetResults() {
  el.results.innerHTML = '';
  el.summary.classList.add('hidden');
  el.resultActions.classList.add('hidden');
}

function renderScanSummary(summary) {
  el.summary.classList.remove('hidden');
  const categories = summary.by_category || {};
  el.summary.innerHTML = `
    <div class="summary-item"><strong>${summary.scanned_files.toLocaleString('de-DE')}</strong><span>gescannte Dateien</span></div>
    <div class="summary-item"><strong>${summary.duplicate_groups}</strong><span>Fund-Gruppen</span></div>
    <div class="summary-item"><strong>${summary.duplicate_files}</strong><span>Bereinigungsvorschläge</span></div>
    <div class="summary-item accent"><strong>${formatBytes(summary.wasted_bytes)}</strong><span>potenziell frei</span></div>
    <div class="summary-item"><strong>${summary.duration_seconds}s</strong><span>Scan-Zeit</span></div>
    <div class="summary-item"><strong>${categories.image || 0}</strong><span>Bilder</span></div>
    <div class="summary-item"><strong>${categories.video || 0}</strong><span>Videos</span></div>
    <div class="summary-item"><strong>${(categories.document || 0) + (categories.audio || 0) + (categories.archive || 0)}</strong><span>weitere</span></div>`;
}

function previewHtml(file) {
  if (file.category === 'image') {
    return `<img class="preview" loading="lazy" src="/api/preview?path=${encodeURIComponent(file.path)}" alt="Vorschau">`;
  }
  const icons = { video: '🎬', document: '📄', archive: '🗜️', audio: '🎵' };
  return `<div class="preview">${icons[file.category] || '📦'}</div>`;
}

function renderScanResults(data) {
  el.results.innerHTML = '';
  const hasGroups = data.groups.length > 0;
  el.resultActions.classList.toggle('hidden', !hasGroups);
  if (!hasGroups) {
    el.results.innerHTML = '<section class="group-card">Keine Duplikate oder ähnlichen Bilder gefunden. 🎉</section>';
    return;
  }
  data.groups.forEach((group, groupIndex) => {
    const card = document.createElement('section');
    card.className = `group-card ${group.type}`;
    const label = group.type === 'similar_image'
      ? `Ähnliche Bilder · Toleranz ${group.similarity_distance}` : 'Exakte Duplikate · SHA-256';
    card.innerHTML = `
      <div class="group-head">
        <div>
          <div class="group-title">Gruppe ${groupIndex + 1} · ${group.all_files.length} Datei(en)</div>
          <div class="file-meta">${label} · Potenziell frei: ${formatBytes(group.wasted_bytes)}</div>
        </div>
        <span class="tag ${group.type}">${group.type === 'similar_image' ? 'ÄHNLICH' : 'EXAKT'}</span>
      </div>
      <div class="file-list"></div>`;
    const list = card.querySelector('.file-list');
    group.all_files.forEach((file) => {
      const isKeep = file.path === group.keep.path;
      const dims = file.width && file.height ? ` · ${file.width}×${file.height}` : '';
      const row = document.createElement('label');
      row.className = `file-row ${isKeep ? 'keep-row' : ''}`;
      row.innerHTML = `
        <input type="checkbox" class="file-check" value="${escapeHtml(file.path)}" ${isKeep ? 'disabled' : 'data-recommended="true"'}>
        ${previewHtml(file)}
        <div>
          <div class="file-path">${escapeHtml(file.path)}</div>
          <div class="file-meta">${escapeHtml(file.category)} · ${formatBytes(file.size)}${dims} · ${formatDate(file.modified)}</div>
        </div>
        <span class="${isKeep ? 'keep-label' : 'delete-label'}">${isKeep ? 'Behalten' : 'Vorschlag'}</span>`;
      list.appendChild(row);
    });
    el.results.appendChild(card);
  });
}

// ---------------------------------------------------------------------------
// Result actions: select / clean / report
// ---------------------------------------------------------------------------
el.selectRecommendedBtn.addEventListener('click', () => {
  document.querySelectorAll('.file-check[data-recommended="true"]').forEach((input) => { input.checked = true; });
});
el.clearSelectionBtn.addEventListener('click', () => {
  document.querySelectorAll('.file-check').forEach((input) => { input.checked = false; });
});
el.reportJsonBtn.addEventListener('click', () => {
  if (state.lastScanJobId) window.location.href = `/api/v1/jobs/${state.lastScanJobId}/report?format=json`;
});
el.reportCsvBtn.addEventListener('click', () => {
  if (state.lastScanJobId) window.location.href = `/api/v1/jobs/${state.lastScanJobId}/report?format=csv`;
});

el.cleanBtn.addEventListener('click', async () => {
  if (!state.lastScan) return;
  const filePaths = [...document.querySelectorAll('.file-check:checked')].map((input) => input.value);
  if (filePaths.length === 0) {
    setStatus('Bitte zuerst mindestens ein vorgeschlagenes Duplikat auswählen.', 'error');
    return;
  }
  const mode = el.cleanMode.value;
  const modeText = mode === 'recycle_bin' ? 'in den Papierkorb' : 'in die Quarantäne';
  if (!confirm(`${filePaths.length} Datei(en) ${modeText} verschieben?`)) return;
  el.cleanBtn.disabled = true;
  setStatus('Bereinigung läuft …');
  try {
    const data = await api('/api/clean', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders: state.lastScan.folders, file_paths: filePaths, mode }),
    });
    setStatus(`${data.changed.length} Datei(en) verschoben · ${data.skipped.length} übersprungen. Wiederherstellung über „Quarantäne".`, 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    el.cleanBtn.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// CONSOLIDATE flow
// ---------------------------------------------------------------------------
async function runConsolidation(dryRun) {
  if (!validateSources()) return;
  if (!el.targetFolder.value.trim()) {
    setStatus('Bitte einen Zielordner für die sauberen Dateien angeben.', 'error');
    return;
  }
  if (!dryRun) {
    const verb = el.operation.value === 'move' ? 'verschoben' : 'kopiert';
    if (!confirm(`Saubere, duplikatfreie Dateien werden jetzt in den Zielordner ${verb}. Fortfahren?`)) return;
  }
  setBusy(true);
  resetResults();
  setStatus(dryRun ? 'Probelauf läuft …' : 'Zusammenführung läuft …');
  try {
    const { result } = await runJob('/api/v1/consolidations', consolidateOptions(dryRun));
    hideStatus();
    renderConsolidateSummary(result.summary);
    renderConsolidatePlan(result);
    const s = result.summary;
    setStatus(
      s.dry_run
        ? `Probelauf fertig: ${s.output_files} saubere Datei(en) würden erstellt, ${s.removed_total} Duplikat(e) entfallen.`
        : `Fertig: ${result.executed_count} Datei(en) im Zielordner. ${s.removed_total} Duplikat(e) übersprungen, ${s.errors} Fehler.`,
      s.errors > 0 ? 'error' : 'success',
    );
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    setBusy(false);
  }
}

el.previewBtn.addEventListener('click', () => runConsolidation(true));
el.consolidateBtn.addEventListener('click', () => runConsolidation(false));

function renderConsolidateSummary(summary) {
  el.summary.classList.remove('hidden');
  el.summary.innerHTML = `
    <div class="summary-item"><strong>${summary.source_files.toLocaleString('de-DE')}</strong><span>Quelldateien</span></div>
    <div class="summary-item accent"><strong>${summary.output_files.toLocaleString('de-DE')}</strong><span>saubere Dateien im Ziel</span></div>
    <div class="summary-item"><strong>${summary.removed_total}</strong><span>Duplikate entfernt</span></div>
    <div class="summary-item"><strong>${formatBytes(summary.saved_bytes)}</strong><span>gespart</span></div>
    <div class="summary-item"><strong>${formatBytes(summary.output_bytes)}</strong><span>Zielgröße</span></div>
    <div class="summary-item"><strong>${summary.operation === 'move' ? 'Verschieben' : 'Kopieren'}</strong><span>Modus</span></div>
    <div class="summary-item"><strong>${summary.errors}</strong><span>Fehler</span></div>
    <div class="summary-item"><strong>${summary.duration_seconds}s</strong><span>Dauer</span></div>`;
}

function renderConsolidatePlan(data) {
  el.results.innerHTML = '';
  const card = document.createElement('section');
  card.className = 'group-card';
  const ops = data.operations || [];
  const title = data.summary.dry_run ? 'Vorschau: geplante Dateien im Zielordner' : 'Im Zielordner erstellte Dateien';
  let rows = ops.map((op) => `
    <div class="plan-row">
      <span class="src">${escapeHtml(op.from)}</span>
      <span class="arrow">→</span>
      <span class="dst">${escapeHtml(op.to)}</span>
    </div>`).join('');
  if (data.operations_truncated) {
    rows += `<div class="plan-row"><span class="src">… Liste gekürzt (insgesamt ${data.summary.output_files} Dateien)</span><span class="arrow"></span><span class="dst"></span></div>`;
  }
  const errorsHtml = (data.errors && data.errors.length)
    ? `<p class="file-meta" style="color:#fca5a5">${data.errors.length} Fehler – erste: ${escapeHtml(data.errors[0].reason)}</p>` : '';
  card.innerHTML = `
    <div class="group-head">
      <div>
        <div class="group-title">${title}</div>
        <div class="file-meta">Ziel: ${escapeHtml(data.target)}</div>
      </div>
      <span class="tag exact">${ops.length} Einträge</span>
    </div>
    ${errorsHtml}
    <div class="plan-list">${rows || '<div class="empty-row">Keine Dateien zu übertragen.</div>'}</div>`;
  el.results.appendChild(card);
}

// ---------------------------------------------------------------------------
// Profiles
// ---------------------------------------------------------------------------
async function loadProfiles() {
  try {
    const data = await api('/api/v1/profiles');
    el.profileSelect.innerHTML = '<option value="">— Profil laden —</option>';
    data.items.forEach((profile) => {
      const option = document.createElement('option');
      option.value = profile.name;
      option.textContent = profile.name;
      option.dataset.config = JSON.stringify(profile.config);
      el.profileSelect.appendChild(option);
    });
  } catch { /* store optional */ }
}

el.saveProfileBtn.addEventListener('click', async () => {
  const name = el.profileName.value.trim();
  if (!name) { setStatus('Bitte einen Profilnamen eingeben.', 'error'); return; }
  try {
    await api('/api/v1/profiles', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, config: gatherConfig() }),
    });
    el.profileName.value = '';
    await loadProfiles();
    setStatus(`Profil „${name}" gespeichert.`, 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  }
});

el.loadProfileBtn.addEventListener('click', () => {
  const option = el.profileSelect.selectedOptions[0];
  if (!option || !option.value) { setStatus('Bitte ein Profil auswählen.', 'error'); return; }
  applyConfig(JSON.parse(option.dataset.config || '{}'));
  setStatus(`Profil „${option.value}" geladen.`, 'success');
});

el.deleteProfileBtn.addEventListener('click', async () => {
  const name = el.profileSelect.value;
  if (!name) { setStatus('Bitte ein Profil auswählen.', 'error'); return; }
  if (!confirm(`Profil „${name}" löschen?`)) return;
  try {
    await api(`/api/v1/profiles/${encodeURIComponent(name)}`, { method: 'DELETE' });
    await loadProfiles();
    setStatus(`Profil „${name}" gelöscht.`, 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  }
});

// ---------------------------------------------------------------------------
// Quarantine / undo
// ---------------------------------------------------------------------------
el.quarantineToggle.addEventListener('click', () => {
  el.quarantineBody.classList.toggle('hidden');
});

el.loadQuarantineBtn.addEventListener('click', async () => {
  if (!validateSources()) return;
  setStatus('Quarantäne wird geladen …');
  try {
    const data = await api('/api/quarantine/list', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders: state.folders }),
    });
    renderQuarantine(data.items);
    hideStatus();
  } catch (error) {
    setStatus(error.message, 'error');
  }
});

function renderQuarantine(items) {
  el.quarantineList.innerHTML = '';
  if (!items.length) {
    el.quarantineList.innerHTML = '<li class="empty-row">Keine Einträge in Quarantäne für diese Ordner.</li>';
    return;
  }
  items.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'folder-item';
    li.innerHTML = `
      <label style="display:flex;gap:10px;align-items:center;font-weight:400">
        <input type="checkbox" class="quarantine-check" value="${escapeHtml(item.quarantined)}" ${item.available ? '' : 'disabled'}>
        <div>
          <div class="path">${escapeHtml(item.original)}</div>
          <div class="meta">${item.available ? 'wiederherstellbar' : 'nicht mehr vorhanden'} · ${item.moved_at ? formatDate(item.moved_at) : ''}</div>
        </div>
      </label>`;
    el.quarantineList.appendChild(li);
  });
}

el.restoreSelectedBtn.addEventListener('click', async () => {
  const paths = [...document.querySelectorAll('.quarantine-check:checked')].map((input) => input.value);
  if (paths.length === 0) { setStatus('Bitte mindestens einen Eintrag auswählen.', 'error'); return; }
  setStatus('Wiederherstellung läuft …');
  try {
    const data = await api('/api/quarantine/restore', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders: state.folders, quarantined_paths: paths }),
    });
    setStatus(`${data.restored.length} Datei(en) wiederhergestellt · ${data.skipped.length} übersprungen.`, 'success');
    el.loadQuarantineBtn.click();
  } catch (error) {
    setStatus(error.message, 'error');
  }
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
async function init() {
  renderFolders();
  switchMode('clean');
  loadProfiles();
  try {
    const caps = await api('/api/v1/capabilities');
    const labels = {
      live_progress: 'Live-Fortschritt', cancellable: 'Abbrechbar', consolidation: 'Zusammenführung',
      quarantine_undo: 'Quarantäne-Undo', profiles: 'Profile', local_first: 'Lokal',
    };
    el.capabilities.innerHTML = Object.entries(labels)
      .filter(([key]) => caps[key]).map(([, label]) => `<span class="cap">${label}</span>`).join('');
  } catch { /* offline-friendly */ }
}

init();
