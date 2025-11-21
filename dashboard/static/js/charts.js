const charts = {
  overview: null,
  channels: null,
  events: null,
  heatmap: null,
  members: null,
  topMembers: null,
  roomActivity: null,
  updateOverviewCharts(payload) {
    this.renderLine('chart-messages', payload.messages || []);
    this.renderBar('chart-channels', payload.channels || []);
    this.renderDonut('chart-events', payload.events || []);
    this.renderHeatmap('heatmap', payload.heatmap || []);
  },
  renderLine(id, entries) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    const labels = entries.map((e) => e.label);
    const data = entries.map((e) => e.value);
    new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Messages',
          data,
          borderColor: '#5865F2',
          tension: 0.35,
        }],
      },
      options: { responsive: true, plugins: { legend: { display: false } } },
    });
  },
  renderBar(id, entries) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: entries.map((e) => e.label),
        datasets: [{
          label: 'Messages',
          data: entries.map((e) => e.value),
          backgroundColor: '#57F287',
        }],
      },
      options: { responsive: true, plugins: { legend: { display: false } } },
    });
  },
  renderDonut(id, entries) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: entries.map((e) => e.label),
        datasets: [{
          data: entries.map((e) => e.value),
          backgroundColor: ['#5865F2', '#57F287', '#FEE75C', '#ED4245'],
        }],
      },
      options: { responsive: true },
    });
  },
  renderHeatmap(id, entries) {
    const container = document.getElementById(id);
    if (!container) return;
    container.innerHTML = '';
    entries.forEach((item) => {
      const cell = document.createElement('div');
      cell.className = 'p-3 rounded bg-secondary border border-surface/40';
      cell.innerHTML = `<p class="text-xs text-muted">${item.label}</p><p class="text-lg font-semibold">${item.value}</p>`;
      container.appendChild(cell);
    });
  },
};
window.charts = charts;
