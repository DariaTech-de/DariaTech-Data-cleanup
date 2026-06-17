const foldersInput = document.querySelector('#folders');
const pickFolderBtn = document.querySelector('#pickFolderBtn');
const includeAllInput = document.querySelector('#includeAll');
const scanBtn = document.querySelector('#scanBtn');
const statusBox = document.querySelector('#status');
const summaryBox = document.querySelector('#summary');
const resultsBox = document.querySelector('#results');
const selectRecommendedBtn = document.querySelector('#selectRecommendedBtn');
const clearSelectionBtn = document.querySelector('#clearSelectionBtn');
const cleanBtn = document.querySelector('#cleanBtn');
const cleanModeInput = document.querySelector('#cleanMode');
const keepRuleInput = document.querySelector('#keepRule');
const minSizeInput = document.querySelector('#minSize');
const maxSizeInput = document.querySelector('#maxSize');
const excludePatternsInput = document.querySelector('#excludePatterns');
const findExactInput = document.querySelector('#findExact');
const findSimilarImagesInput = document.querySelector('#findSimilarImages');
const imageSimilarityInput = document.querySelector('#imageSimilarity');
const reportJsonBtn = document.querySelector('#reportJsonBtn');
const reportCsvBtn = document.querySelector('#reportCsvBtn');

let lastScan = null;

function setStatus(message, isError = false) {
  statusBox.classList.remove('hidden');
  statusBox.textContent = message;
  statusBox.style.borderColor = isError ? 'rgba(239,68,68,.65)' : 'rgba(255,255,255,.12)';
}

function hideStatus() { statusBox.classList.add('hidden'); }
function showActionButtons(show) {
  [selectRecommendedBtn, clearSelectionBtn, cleanBtn, reportJsonBtn, reportCsvBtn].forEach(button => button.classList.toggle('hidden', !show));
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 2)} ${units[index]}`;
}

function formatDate(timestamp) { return new Date(timestamp * 1000).toLocaleString('de-DE'); }
function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function selectedFolders() {
  return foldersInput.value.split('\n').map(line => line.trim()).filter(Boolean);
}

function addFolderToTextarea(folder) {
  const folders = selectedFolders();
  const exists = folders.some(item => item.toLowerCase() === folder.toLowerCase());
  if (!exists) folders.push(folder);
  foldersInput.value = folders.join('\n');
}

function selectedCategories() {
  return [...document.querySelectorAll('.category:checked')].map(input => input.value);
}

function selectedFiles() {
  return [...document.querySelectorAll('.file-check:checked')].map(input => input.value);
}

function scanPayload() {
  const maxValue = maxSizeInput.value.trim();
  return {
    folders: selectedFolders(),
    include_all_files: includeAllInput.checked,
    categories: selectedCategories(),
    min_size_mb: Number(minSizeInput.value || 0),
    max_size_mb: maxValue ? Number(maxValue) : null,
    exclude_patterns: excludePatternsInput.value.split(',').map(v => v.trim()).filter(Boolean),
    keep_rule: keepRuleInput.value,
    find_exact: findExactInput.checked,
    find_similar_images: findSimilarImagesInput.checked,
    image_similarity: Number(imageSimilarityInput.value || 8),
  };
}

function renderSummary(summary) {
  summaryBox.classList.remove('hidden');
  const categories = summary.by_category || {};
  summaryBox.innerHTML = `
    <div class="summary-item"><strong>${summary.scanned_files}</strong><span>gescannte Dateien</span></div>
    <div class="summary-item"><strong>${summary.duplicate_groups}</strong><span>Fund-Gruppen</span></div>
    <div class="summary-item"><strong>${summary.duplicate_files}</strong><span>Bereinigungsvorschläge</span></div>
    <div class="summary-item"><strong>${formatBytes(summary.wasted_bytes)}</strong><span>potenziell frei</span></div>
    <div class="summary-item"><strong>${summary.duration_seconds}s</strong><span>Scan-Zeit</span></div>
    <div class="summary-item"><strong>${categories.image || 0}</strong><span>Bilder</span></div>
    <div class="summary-item"><strong>${categories.video || 0}</strong><span>Videos</span></div>
    <div class="summary-item"><strong>${categories.document || 0}</strong><span>Dokumente</span></div>
  `;
}

function groupLabel(group) {
  if (group.type === 'similar_image') return `Ähnliche Bilder · Toleranz ${group.similarity_distance}`;
  return 'Exakte Duplikate · SHA-256';
}

function previewHtml(file) {
  if (file.category === 'image') {
    return `<img class="preview" src="/api/preview?path=${encodeURIComponent(file.path)}" alt="Vorschau">`;
  }
  if (file.category === 'video') return '<div class="preview placeholder">🎬</div>';
  if (file.category === 'document') return '<div class="preview placeholder">📄</div>';
  if (file.category === 'archive') return '<div class="preview placeholder">🗜️</div>';
  return '<div class="preview placeholder">📦</div>';
}

function renderResults(data) {
  resultsBox.innerHTML = '';
  showActionButtons(data.groups.length > 0);

  if (data.groups.length === 0) {
    resultsBox.innerHTML = '<section class="group-card">Keine Duplikate oder ähnlichen Bilder gefunden.</section>';
    return;
  }

  for (const [groupIndex, group] of data.groups.entries()) {
    const card = document.createElement('section');
    card.className = `group-card ${group.type}`;
    card.innerHTML = `
      <div class="group-head">
        <div>
          <div class="group-title">Gruppe ${groupIndex + 1}: ${group.all_files.length} Datei(en)</div>
          <div class="file-meta">${groupLabel(group)} · Potenziell frei: ${formatBytes(group.wasted_bytes)} · Behalte-Regel: ${escapeHtml(group.keep_rule)}</div>
        </div>
        <div class="file-meta hash">${escapeHtml(String(group.id).slice(0, 16))}…</div>
      </div>
      <div class="file-list"></div>
    `;

    const list = card.querySelector('.file-list');
    for (const file of group.all_files) {
      const isKeep = file.path === group.keep.path;
      const dimensions = file.width && file.height ? ` · ${file.width}×${file.height}` : '';
      const row = document.createElement('label');
      row.className = `file-row ${isKeep ? 'keep-row' : ''}`;
      row.innerHTML = `
        <input type="checkbox" class="file-check" value="${escapeHtml(file.path)}" ${isKeep ? 'disabled' : 'data-recommended="true"'}>
        ${previewHtml(file)}
        <div>
          <div class="file-path">${escapeHtml(file.path)}</div>
          <div class="file-meta">${escapeHtml(file.category)} · ${formatBytes(file.size)}${dimensions} · geändert: ${formatDate(file.modified)}</div>
        </div>
        <span class="${isKeep ? 'keep-label' : 'delete-label'}">${isKeep ? 'Behalten' : 'Vorschlag'}</span>
      `;
      list.appendChild(row);
    }
    resultsBox.appendChild(card);
  }
}

pickFolderBtn.addEventListener('click', async () => {
  pickFolderBtn.disabled = true;
  setStatus('Ordnerauswahl wird geöffnet …');
  try {
    const response = await fetch('/api/select-folder');
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Ordnerauswahl fehlgeschlagen');
    if (data.folder) {
      addFolderToTextarea(data.folder);
      hideStatus();
    } else {
      setStatus('Keine Auswahl getroffen.');
    }
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    pickFolderBtn.disabled = false;
  }
});

scanBtn.addEventListener('click', async () => {
  const folders = selectedFolders();
  if (folders.length === 0) {
    setStatus('Bitte wähle mindestens einen Ordner über den Button aus.', true);
    return;
  }
  if (!findExactInput.checked && !findSimilarImagesInput.checked) {
    setStatus('Bitte mindestens eine Erkennungsart aktivieren.', true);
    return;
  }

  scanBtn.disabled = true;
  resultsBox.innerHTML = '';
  summaryBox.classList.add('hidden');
  showActionButtons(false);
  setStatus('Analyse läuft. Bei vielen Bildern/Videos kann das dauern …');

  try {
    const response = await fetch('/api/scan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(scanPayload()),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Scan fehlgeschlagen');
    lastScan = data;
    hideStatus();
    renderSummary(data.summary);
    renderResults(data);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    scanBtn.disabled = false;
  }
});

selectRecommendedBtn.addEventListener('click', () => {
  document.querySelectorAll('.file-check[data-recommended="true"]').forEach(input => { input.checked = true; });
});
clearSelectionBtn.addEventListener('click', () => {
  document.querySelectorAll('.file-check').forEach(input => { input.checked = false; });
});

cleanBtn.addEventListener('click', async () => {
  if (!lastScan) return;
  const filePaths = selectedFiles();
  if (filePaths.length === 0) {
    setStatus('Bitte wähle zuerst mindestens ein vorgeschlagenes Duplikat aus.', true);
    return;
  }
  const mode = cleanModeInput.value;
  const modeText = mode === 'recycle_bin' ? 'in den Papierkorb verschieben' : 'in Quarantäne verschieben';
  const ok = confirm(`${filePaths.length} Datei(en) ${modeText}? Bitte vorher die Vorschläge kontrollieren.`);
  if (!ok) return;

  cleanBtn.disabled = true;
  setStatus('Bereinigung läuft …');
  try {
    const response = await fetch('/api/clean', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders: lastScan.folders, file_paths: filePaths, mode }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Bereinigung fehlgeschlagen');
    setStatus(`${data.changed.length} Datei(en) verarbeitet. Übersprungen: ${data.skipped.length}.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    cleanBtn.disabled = false;
  }
});

reportJsonBtn.addEventListener('click', () => { window.location.href = '/api/report?format=json'; });
reportCsvBtn.addEventListener('click', () => { window.location.href = '/api/report?format=csv'; });
