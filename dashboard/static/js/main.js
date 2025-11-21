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
    document.getElementById('config-prefix').value = config.prefix || '!';
    document.getElementById('config-language').value = config.language || 'fr';
    document.getElementById('config-timezone').value = config.timezone || 'Europe/Brussels';
  } catch (error) {
    console.error(error);
  }
}

async function saveConfig() {
  const payload = {
    prefix: document.getElementById('config-prefix').value,
    language: document.getElementById('config-language').value,
    timezone: document.getElementById('config-timezone').value,
  };
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

function exportLogs() { window.location = '/api/export/logs'; }
function exportConfig() { window.location = '/api/export/config'; }
function exportStats() { window.location = '/api/export/stats'; }
function resetDashboard() { alert('Reset virtuel : implémentation à brancher sur API.'); }

function refreshData() {
  loadOverview();
  loadLogs();
  loadModeration();
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
});
