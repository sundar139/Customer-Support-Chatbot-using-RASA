(() => {
  const elMessages = document.getElementById('messages');
  const elComposer = document.getElementById('composer');
  const elInput = document.getElementById('input');
  const elServer = document.getElementById('serverUrl');
  const elClear = document.getElementById('clearChat');

  const senderId = `web-${Date.now()}`;

  function addBubble(text, who = 'bot') {
    const wrap = document.createElement('div');
    wrap.className = `bubble bubble--${who}`;
    wrap.textContent = text;
    elMessages.appendChild(wrap);
    elMessages.scrollTop = elMessages.scrollHeight;
  }

  function addSystem(text) {
    const s = document.createElement('div');
    s.className = 'system';
    s.textContent = text;
    elMessages.appendChild(s);
  }

  async function sendMessage(text) {
    const base = elServer.value || 'http://localhost:5005';
    const url = `${base}/webhooks/rest/webhook`;

    addBubble(text, 'user');
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender: senderId, message: text })
      });
      if (!res.ok) {
        addSystem(`Server error: ${res.status} ${res.statusText}`);
        return;
      }
      const payload = await res.json();
      if (Array.isArray(payload) && payload.length) {
        for (const m of payload) {
          if (m.text) addBubble(m.text, 'bot');
          if (m.image) addBubble(`[image] ${m.image}`, 'bot');
        }
      } else {
        addSystem('No response from bot.');
      }
    } catch (err) {
      addSystem(`Network error: ${String(err)}`);
    }
  }

  elComposer.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = elInput.value.trim();
    if (!text) return;
    elInput.value = '';
    sendMessage(text);
  });

  elClear.addEventListener('click', () => {
    elMessages.innerHTML = '';
    addSystem('Chat cleared.');
  });

  // Greet message
  addSystem('Connected. Choose server and start chatting.');
})();