function themeController() {
  return {
    theme: localStorage.getItem('theme') || 'dark',
    initTheme() {
      document.documentElement.classList.toggle('light', this.theme === 'light');
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('theme', this.theme);
      document.documentElement.classList.toggle('light', this.theme === 'light');
    },
    isActive(path) {
      return window.location.pathname === path ? 'active' : '';
    },
  };
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error('Requête échouée');
  return res.json();
}

const DEFAULT_CONFIG = {
  prefix: '!',
  language: 'fr',
  timezone: 'Europe/Brussels',
  auto_refresh: true,
  notifications: true,
  page_size: 20,
  log_level: 'INFO',
  retention_days: 30,
  cleanup: true,
  slow_mode: {
    enabled: true,
    window_seconds: 60,
    min_update_interval_seconds: 15,
    tiers: [
      { threshold: 60, seconds: 10 },
      { threshold: 30, seconds: 5 },
      { threshold: 15, seconds: 2 },
    ],
  },
};

function cloneDefaultConfig() {
  return JSON.parse(JSON.stringify(DEFAULT_CONFIG));
}

let configState = cloneDefaultConfig();

async function loadOverview() {
  try {
    const data = await fetchJSON('/api/stats/overview');
    document.getElementById('members-total').textContent = data.members_total ?? '--';
    document.getElementById('messages-total').textContent = data.messages_total ?? '--';
    document.getElementById('alerts-total').textContent = data.alerts ?? '0';
    document.getElementById('uptime').textContent = data.uptime ?? '--';
    document.getElementById('members-delta').textContent = `+${data.members_today || 0} aujourd'hui`;
    document.getElementById('messages-delta').textContent = `+${data.messages_today || 0} aujourd'hui`;
    document.getElementById('alerts-pending').textContent = `${data.alerts_pending || 0} en attente`;
    document.getElementById('bot-status').textContent = `Statut: ${data.bot_status || 'unknown'}`;
    document.getElementById('sidebar-status').textContent = data.bot_status === 'online' ? 'Online' : 'Offline';
    document.getElementById('sidebar-latency').textContent = data.latency ?? '--';
    document.getElementById('sidebar-guilds').textContent = data.guilds ?? '--';
    if (window.charts && data.chart_data) {
      window.charts.updateOverviewCharts(data.chart_data);
    }
    renderTimeline(data.timeline || []);
    renderGuild(data.guild || {});
  } catch (error) {
    console.error(error);
  }
}

const analyticsState = {
  range: '7d',
  custom: false,
  data: { contributors: [] },
};

const analyticsCharts = {
  members: null,
  topMembers: null,
  roomActivity: null,
};

function applyRangeActive(range) {
  document.querySelectorAll('[data-range]').forEach((btn) => {
    btn.classList.toggle('btn-chip-active', btn.dataset.range === range);
  });
}

function bindRangeControls() {
  document.querySelectorAll('[data-range]').forEach((btn) => {
    btn.addEventListener('click', () => {
      analyticsState.range = btn.dataset.range;
      analyticsState.custom = false;
      applyRangeActive(btn.dataset.range);
      loadAnalytics();
    });
  });

  const start = document.getElementById('range-start');
  const end = document.getElementById('range-end');
  const applyBtn = document.getElementById('range-apply');
  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      if (start?.value && end?.value) {
        analyticsState.custom = true;
        applyRangeActive('');
        loadAnalytics();
      }
    });
  }
}

async function loadAnalytics() {
  const activeCard = document.getElementById('analytics-active');
  if (!activeCard) return;

  const params = new URLSearchParams();
  if (analyticsState.custom) {
    params.set('start', document.getElementById('range-start')?.value || '');
    params.set('end', document.getElementById('range-end')?.value || '');
  } else {
    params.set('range', analyticsState.range);
  }

  try {
    const data = await fetchJSON(`/api/analytics?${params.toString()}`);
    analyticsState.data.contributors = data.top_members || [];
    updateAnalyticsSummary(data.summary || {}, data);
    renderMembersChart(data.members_chart || []);
    renderTopMembersChart(data.top_members || []);
    renderRoomActivity(data.top_channels || []);
    renderHeatmap(data.heatmap || []);
    renderContributorsTable(data.top_members || []);
    applyRangeActive(analyticsState.custom ? '' : data.range || analyticsState.range);
  } catch (error) {
    console.error('Analytics error', error);
  }
}

function updateAnalyticsSummary(summary, meta) {
  const formatter = new Intl.NumberFormat('fr-FR');
  const startLabel = meta.start ? new Date(meta.start).toLocaleString('fr-FR') : '';
  const endLabel = meta.end ? new Date(meta.end).toLocaleString('fr-FR') : '';
  document.getElementById('analytics-active').textContent = formatter.format(summary.active_members || 0);
  document.getElementById('analytics-messages').textContent = formatter.format(summary.total_messages || 0);
  document.getElementById('analytics-average').textContent = formatter.format(summary.average_per_day || 0);
  const rangeLabel = document.getElementById('analytics-active-range');
  if (rangeLabel && startLabel && endLabel) {
    rangeLabel.textContent = `${startLabel} → ${endLabel}`;
  }
}

function destroyChart(key) {
  if (analyticsCharts[key]) {
    analyticsCharts[key].destroy();
    analyticsCharts[key] = null;
  }
}

function renderMembersChart(entries) {
  const ctx = document.getElementById('chart-members');
  if (!ctx) return;
  destroyChart('members');
  analyticsCharts.members = new Chart(ctx, {
    type: 'line',
    data: {
      labels: entries.map((e) => e.label),
      datasets: [
        {
          label: 'Net Joins',
          data: entries.map((e) => e.value ?? e.net ?? 0),
          borderColor: '#8B5CF6',
          backgroundColor: 'rgba(139, 92, 246, 0.2)',
          tension: 0.35,
          fill: true,
        },
      ],
    },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });
}

function renderTopMembersChart(entries) {
  const ctx = document.getElementById('chart-top-members');
  if (!ctx) return;
  destroyChart('topMembers');
  analyticsCharts.topMembers = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: entries.map((e) => e.username ?? e.user_id),
      datasets: [
        {
          label: 'Messages',
          data: entries.map((e) => e.count),
          backgroundColor: '#57F287',
          borderRadius: 8,
        },
      ],
    },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });
}

function renderRoomActivity(entries) {
  const ctx = document.getElementById('chart-room-activity');
  if (!ctx) return;
  destroyChart('roomActivity');
  analyticsCharts.roomActivity = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: entries.map((e) => e.name || `#${e.channel_id}`),
      datasets: [
        {
          label: 'Messages',
          data: entries.map((e) => e.message_count),
          backgroundColor: '#FEE75C',
          borderRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#b9bbbe' } },
        y: { ticks: { color: '#b9bbbe' } },
      },
    },
  });
}

function renderHeatmap(entries) {
  const container = document.getElementById('analytics-heatmap');
  if (!container) return;
  const dayMap = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
  container.innerHTML = '';
  entries.forEach((cell) => {
    const intensity = Math.min(1, (cell.count || 0) / 50);
    const el = document.createElement('div');
    el.className = 'heat-cell';
    el.style.setProperty('--intensity', intensity.toString());
    el.innerHTML = `<p class="text-[10px] text-muted">${dayMap[cell.weekday] || '?' } • ${String(cell.hour).padStart(2, '0')}h</p><p class="text-lg font-semibold">${cell.count}</p>`;
    container.appendChild(el);
  });
}

function renderContributorsTable(entries) {
  const tbody = document.getElementById('contributors-table');
  const search = document.getElementById('search-contrib')?.value?.toLowerCase() || '';
  if (!tbody) return;
  tbody.innerHTML = '';
  const filtered = entries.filter((row) => (row.username || row.user_id || '').toLowerCase().includes(search));
  filtered.forEach((row, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="px-3 py-2">#${idx + 1}</td>
      <td class="px-3 py-2 font-semibold">${row.username || row.user_id}</td>
      <td class="px-3 py-2">${row.count}</td>
      <td class="px-3 py-2">${row.percentage || 0}%</td>
      <td class="px-3 py-2 text-sm">${row.trend || '↗️ Stable'}</td>
    `;
    tbody.appendChild(tr);
  });
}

function exportContributors() {
  const rows = analyticsState.data.contributors || [];
  const header = ['Rang', 'Utilisateur', 'Messages', 'Pourcentage'];
  const csv = [header.join(',')]
    .concat(
      rows.map((row, idx) => [idx + 1, row.username || row.user_id, row.count, row.percentage].join(',')),
    )
    .join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'contributors.csv';
  link.click();
}

function renderTimeline(items) {
  const container = document.getElementById('timeline');
  if (!container) return;
  container.innerHTML = '';
  items.slice(0, 10).forEach((item) => {
    const li = document.createElement('li');
    li.className = 'p-3 rounded-lg bg-secondary border border-surface/60';
    li.innerHTML = `<strong>[${item.timestamp || '--'}]</strong> ${item.message || ''}`;
    container.appendChild(li);
  });
}

function renderGuild(guild) {
  const defaults = {
    name: 'Serveur',
    id: '--',
    members: '--',
    online: '--',
    bots: '--',
    created_at: '--',
    owner: '--',
    roles: [],
  };
  const data = { ...defaults, ...guild };
  const ids = {
    'guild-name': data.name,
    'guild-id': data.id,
    'guild-members': data.members,
    'guild-online': data.online,
    'guild-bots': data.bots,
    'guild-created': data.created_at,
    'guild-owner': data.owner,
  };
  Object.entries(ids).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  });
  const roles = document.getElementById('guild-roles');
  if (roles) {
    roles.innerHTML = '';
    (data.roles || []).slice(0, 5).forEach((role) => {
      const li = document.createElement('li');
      li.textContent = role;
      roles.appendChild(li);
    });
  }
}

async function loadLogs() {
  const container = document.getElementById('logs-container');
  if (!container) return;
  const type = document.getElementById('log-type').value;
  const search = document.getElementById('log-search').value;
  const start = document.getElementById('log-start').value;
  const end = document.getElementById('log-end').value;
  const params = new URLSearchParams({ type, search, start, end });
  const data = await fetchJSON(`/api/logs?${params.toString()}`);
  container.innerHTML = '';
  data.logs.forEach((log) => {
    const card = document.createElement('div');
    card.className = 'log-card';
    card.innerHTML = `
      <div class="flex items-center gap-2 text-sm">
        <span>${levelEmoji(log.level)} ${log.timestamp}</span>
        <span class="badge">${log.type}</span>
      </div>
      <p class="mt-2">${log.message}</p>
      <p class="text-muted text-xs">${log.user_name || ''}</p>
    `;
    container.appendChild(card);
  });
  updateLogStats(data.stats || {});
}

function levelEmoji(level) {
  switch ((level || '').toLowerCase()) {
    case 'error':
      return '🔴';
    case 'warning':
      return '🟡';
    case 'success':
      return '🟢';
    case 'info':
    default:
      return '🔵';
  }
}

function updateLogStats(stats) {
  const mapping = {
    'logs-total': stats.total,
    'logs-errors': stats.errors,
    'logs-warnings': stats.warnings,
    'logs-mod': stats.moderation,
    'logs-analytics': stats.analytics,
  };
  Object.entries(mapping).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? 0;
  });
}

async function loadModeration() {
  const table = document.getElementById('moderation-table');
  if (!table) return;
  const type = document.getElementById('filter-type').value;
  const date = document.getElementById('filter-date').value;
  const params = new URLSearchParams({ type, date });
  const data = await fetchJSON(`/api/moderation/history?${params.toString()}`);
  table.innerHTML = '';
  data.actions.forEach((action) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td class="px-3 py-2">${action.timestamp}</td>
      <td class="px-3 py-2">${action.action_type}</td>
      <td class="px-3 py-2">${action.channel_name || '#inconnu'}</td>
      <td class="px-3 py-2">${action.user_name || 'bot'}</td>
      <td class="px-3 py-2">${action.details || ''}</td>
    `;
    table.appendChild(row);
  });
  populateChannels(data.channels || []);
}

function populateChannels(channels) {
  const purge = document.getElementById('purge-channel');
  const unpurge = document.getElementById('unpurge-channel');
  [purge, unpurge].forEach((select) => {
    if (!select) return;
    select.innerHTML = '';
    channels.forEach((channel) => {
      const option = document.createElement('option');
      option.value = channel.id;
      option.textContent = `#${channel.name}`;
      select.appendChild(option);
    });
  });
}

function updatePurgeLabel() {
  const slider = document.getElementById('purge-amount');
  const value = document.getElementById('purge-value');
  if (slider && value) value.textContent = slider.value;
}

async function submitPurge() {
  const payload = {
    channel_id: document.getElementById('purge-channel').value,
    amount: Number(document.getElementById('purge-amount').value),
    reason: document.getElementById('purge-reason').value,
  };
  await fetch('/api/moderation/purge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  loadModeration();
}

async function submitUnpurge() {
  const payload = {
    channel_id: document.getElementById('unpurge-channel').value,
    reason: document.getElementById('unpurge-reason').value,
  };
  await fetch('/api/moderation/unpurge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  loadModeration();
}

async function loadSettings() {
  try {
    const config = await fetchJSON('/api/config');
    configState = { ...cloneDefaultConfig(), ...config, slow_mode: { ...cloneDefaultConfig().slow_mode, ...(config.slow_mode || {}) } };
    applyConfigToForm(configState);
    applySlowModeConfig(configState.slow_mode);
  } catch (error) {
    console.error(error);
  }
}

async function saveConfig() {
  const payload = collectConfigPayload();
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  configState = payload;
}

async function saveSlowMode() {
  const payload = collectConfigPayload();
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  configState = payload;
}

function setValueIfPresent(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.type === 'checkbox') {
    el.checked = Boolean(value);
  } else {
    el.value = value ?? '';
  }
}

function applyConfigToForm(config) {
  setValueIfPresent('config-prefix', config.prefix);
  setValueIfPresent('config-language', config.language);
  setValueIfPresent('config-timezone', config.timezone);
  setValueIfPresent('config-auto-refresh', config.auto_refresh);
  setValueIfPresent('config-notifications', config.notifications);
  setValueIfPresent('config-page-size', config.page_size);
  setValueIfPresent('config-log-level', config.log_level);
  setValueIfPresent('config-retention', config.retention_days);
  setValueIfPresent('config-cleanup', config.cleanup);
}

function applySlowModeConfig(slowMode) {
  const config = slowMode || cloneDefaultConfig().slow_mode;
  setValueIfPresent('slowmode-enabled', config.enabled);
  setValueIfPresent('slowmode-window', config.window_seconds);
  setValueIfPresent('slowmode-interval', config.min_update_interval_seconds);
  renderSlowModeTiers(config.tiers || []);
}

function renderSlowModeTiers(tiers) {
  const container = document.getElementById('slowmode-tiers');
  if (!container) return;
  container.innerHTML = '';
  const list = tiers.length ? tiers : cloneDefaultConfig().slow_mode.tiers;
  list.forEach((tier) => addSlowModeTier(tier));
}

function addSlowModeTier(tier = { threshold: 10, seconds: 1 }) {
  const container = document.getElementById('slowmode-tiers');
  if (!container) return;
  const row = document.createElement('div');
  row.className = 'grid grid-cols-7 gap-2 items-end';
  row.setAttribute('data-slow-tier', '');
  row.innerHTML = `
    <div class="col-span-3">
      <label class="block text-xs text-muted">Seuil (msgs/min)</label>
      <input type="number" class="input" min="1" value="${tier.threshold ?? ''}" data-threshold>
    </div>
    <div class="col-span-3">
      <label class="block text-xs text-muted">Slowmode (s)</label>
      <input type="number" class="input" min="0" value="${tier.seconds ?? ''}" data-seconds>
    </div>
    <div class="col-span-1 flex items-end">
      <button class="btn-danger w-full text-sm" type="button" onclick="removeSlowModeTier(this)">Supprimer</button>
    </div>
  `;
  container.appendChild(row);
}

function removeSlowModeTier(button) {
  const container = document.getElementById('slowmode-tiers');
  const row = button.closest('[data-slow-tier]');
  if (row) row.remove();
  if (container && container.querySelectorAll('[data-slow-tier]').length === 0) {
    addSlowModeTier(cloneDefaultConfig().slow_mode.tiers[0]);
  }
}

function collectSlowModeConfig(previous = cloneDefaultConfig().slow_mode) {
  const config = { ...cloneDefaultConfig().slow_mode, ...previous };
  const enabledInput = document.getElementById('slowmode-enabled');
  const windowInput = document.getElementById('slowmode-window');
  const intervalInput = document.getElementById('slowmode-interval');
  if (enabledInput) config.enabled = enabledInput.checked;
  if (windowInput && windowInput.value) config.window_seconds = Number(windowInput.value);
  if (intervalInput && intervalInput.value) config.min_update_interval_seconds = Number(intervalInput.value);

  const container = document.getElementById('slowmode-tiers');
  if (container) {
    const tiers = Array.from(container.querySelectorAll('[data-slow-tier]'))
      .map((row) => ({
        threshold: Number(row.querySelector('[data-threshold]')?.value ?? 0),
        seconds: Number(row.querySelector('[data-seconds]')?.value ?? 0),
      }))
      .filter((tier) => tier.threshold > 0 && tier.seconds >= 0);
    if (tiers.length) config.tiers = tiers;
  }

  return config;
}

function collectConfigPayload() {
  const payload = { ...cloneDefaultConfig(), ...configState };
  const assign = (id, setter) => {
    const el = document.getElementById(id);
    if (!el) return;
    setter(el);
  };

  assign('config-prefix', (el) => {
    payload.prefix = el.value || '!';
  });
  assign('config-language', (el) => {
    payload.language = el.value || 'fr';
  });
  assign('config-timezone', (el) => {
    payload.timezone = el.value || 'Europe/Brussels';
  });
  assign('config-auto-refresh', (el) => {
    payload.auto_refresh = el.checked;
  });
  assign('config-notifications', (el) => {
    payload.notifications = el.checked;
  });
  assign('config-page-size', (el) => {
    payload.page_size = Number(el.value) || payload.page_size;
  });
  assign('config-log-level', (el) => {
    payload.log_level = el.value || payload.log_level;
  });
  assign('config-retention', (el) => {
    payload.retention_days = Number(el.value) || payload.retention_days;
  });
  assign('config-cleanup', (el) => {
    payload.cleanup = el.checked;
  });

  payload.slow_mode = collectSlowModeConfig(payload.slow_mode);
  return payload;
}

function exportLogs() { window.location = '/api/export/logs'; }
function exportConfig() { window.location = '/api/export/config'; }
function exportStats() { window.location = '/api/export/stats'; }
function resetDashboard() { alert('Reset virtuel : implémentation à brancher sur API.'); }

function refreshData() {
  loadOverview();
  loadLogs();
  loadModeration();
  loadAnalytics();
}

function toggleMobileNav() {
  document.querySelector('aside').classList.toggle('hidden');
}

window.addEventListener('DOMContentLoaded', () => {
  loadOverview();
  loadLogs();
  loadModeration();
  loadSettings();
  updatePurgeLabel();
  bindRangeControls();
  loadAnalytics();
  const search = document.getElementById('search-contrib');
  const exportBtn = document.getElementById('export-contrib');
  search?.addEventListener('input', () => renderContributorsTable(analyticsState.data.contributors));
  exportBtn?.addEventListener('click', exportContributors);
});
