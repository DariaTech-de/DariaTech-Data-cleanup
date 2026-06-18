const refreshBtn = document.querySelector('#refreshBtn');
const statusBox = document.querySelector('#status');
const actionsBox = document.querySelector('#actions');

function setStatus(message, isError = false) {
  statusBox.classList.remove('hidden');
  statusBox.textContent = message;
  statusBox.style.borderColor = isError ? 'rgba(239,68,68,.65)' : 'rgba(255,255,255,.12)';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatDate(timestamp) {
  return timestamp ? new Date(timestamp * 1000).toLocaleString('de-DE') : '—';
}

async function loadActions() {
  setStatus('Lade Aktionen …');
  actionsBox.innerHTML = '';
  try {
    const response = await fetch('/api/v1/actions?limit=200');
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Aktionen konnten nicht geladen werden');
    if (!data.items.length) {
      actionsBox.innerHTML = '<section class="group-card">Noch keine protokollierten Dateiaktionen vorhanden.</section>';
      setStatus('Keine Aktionen vorhanden.');
      return;
    }
    actionsBox.innerHTML = data.items.map(item => `
      <section class="group-card">
        <div class="group-head">
          <div>
            <div class="group-title">${escapeHtml(item.action_mode)} · ${escapeHtml(item.status)}</div>
            <div class="file-meta">${formatDate(item.created_at)} · Scan ${escapeHtml(item.scan_id)}</div>
          </div>
          <div class="file-meta hash">${escapeHtml(item.id).slice(0, 8)}</div>
        </div>
        <div class="file-list">
          <div class="file-row">
            <div class="preview placeholder">↩</div>
            <div>
              <div class="file-path">Von: ${escapeHtml(item.source_path)}</div>
              <div class="file-meta">Nach: ${escapeHtml(item.target_path || '—')}</div>
              ${item.error ? `<div class="file-meta">Fehler: ${escapeHtml(item.error)}</div>` : ''}
            </div>
          </div>
        </div>
      </section>
    `).join('');
    setStatus(`${data.items.length} Aktion(en) geladen.`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

refreshBtn.addEventListener('click', loadActions);
loadActions();
