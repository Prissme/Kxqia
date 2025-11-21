const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => console.log('Socket connecté'));
socket.on('disconnect', () => console.log('Socket déconnecté'));

socket.on('stats_update', (payload) => {
  document.getElementById('members-total').textContent = payload.members_total;
  document.getElementById('messages-total').textContent = payload.messages_today;
  document.getElementById('uptime').textContent = payload.uptime;
});

socket.on('moderation_action', (payload) => {
  const timeline = document.getElementById('timeline');
  if (!timeline) return;
  const li = document.createElement('li');
  li.className = 'p-3 rounded-lg bg-secondary border border-surface/60';
  li.innerHTML = `[${payload.timestamp}] ${payload.user} a ${payload.type} ${payload.channel} (${payload.details})`;
  timeline.prepend(li);
});

socket.on('new_log', (payload) => {
  const container = document.getElementById('logs-container');
  if (!container) return;
  const card = document.createElement('div');
  card.className = 'log-card';
  card.innerHTML = `<div class="flex items-center gap-2 text-sm"><span>${payload.timestamp}</span><span class="badge">${payload.level}</span></div><p>${payload.message}</p>`;
  container.prepend(card);
});

socket.on('bot_status', (payload) => {
  document.getElementById('bot-status').textContent = `Statut: ${payload.status}`;
  document.getElementById('sidebar-status').textContent = payload.status;
  document.getElementById('sidebar-latency').textContent = payload.latency;
  document.getElementById('sidebar-guilds').textContent = payload.guilds;
});

function requestPurge(channelId, amount, reason) {
  socket.emit('request_purge', { channel_id: channelId, amount, reason });
}
