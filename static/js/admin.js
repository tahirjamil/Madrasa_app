// Admin Page JavaScript for Request & Response Log

(function() {
  const raw = document.getElementById('init-data').textContent;
  let currentData = JSON.parse(raw);
  currentData.reverse(); // Newest at top

  const filterText = document.getElementById('filter-text');
  const filterFrom = document.getElementById('filter-from');
  const filterTo   = document.getElementById('filter-to');
  const clearBtn   = document.getElementById('clear-filters');
  const tableBody  = document.querySelector('#log-table tbody');
  const entryCount = document.getElementById('entry-count');
  const scrollBtn  = document.getElementById('scroll-top');
  const pauseBtn   = document.getElementById('pause-refresh');

  let autoRefresh = true;
  let pollInterval = 5000;
  let pollTimer = null;

  function escapeHtml(unsafe) {
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderRows(data) {
    tableBody.innerHTML = '';
    data.forEach(e => {
      const reqCell = e.req_json !== null
        ? `<pre class="json-block">${escapeHtml(JSON.stringify(e.req_json, null, 2))}</pre>`
        : '—';
      const resCell = e.res_json !== null
        ? `<pre class="json-block">${escapeHtml(JSON.stringify(e.res_json, null, 2))}</pre>`
        : '—';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(e.time)}</td>
        <td>${escapeHtml(e.ip)}</td>
        <td>${escapeHtml(e.method)}</td>
        <td>${escapeHtml(e.path)}</td>
        <td>${reqCell}</td>
        <td>${resCell}</td>
      `;
      tableBody.appendChild(tr);
    });
    entryCount.textContent = data.length;
    attachJsonToggle();
  }

  function attachJsonToggle() {
    document.querySelectorAll('.json-block').forEach(pre => {
      pre.addEventListener('click', () => {
        pre.classList.toggle('expanded');
      });
    });
  }

  function applyFilters() {
    const term = filterText.value.trim().toLowerCase();
    const from = filterFrom.value ? new Date(filterFrom.value) : null;
    const to   = filterTo.value   ? new Date(filterTo.value)   : null;

    const filtered = currentData.filter(e => {
      let hay = (e.time + e.ip + e.method + e.path).toLowerCase();
      hay += JSON.stringify(e.req_json).toLowerCase();
      hay += JSON.stringify(e.res_json).toLowerCase();
      if (term && !hay.includes(term)) return false;

      if (from || to) {
        const dt = new Date(e.time.replace(' ', 'T'));
        if (from && dt < from) return false;
        if (to   && dt > to)   return false;
      }
      return true;
    });

    renderRows(filtered);
  }

  async function poll() {
    if (!autoRefresh) return;
    try {
      const res = await fetch('/info/data');
      if (!res.ok) throw new Error(res.statusText);
      let newData = await res.json();
      newData.reverse(); // Newest at top
      // Only prepend new logs
      if (newData.length > 0 && newData[0].time !== (currentData[0] && currentData[0].time)) {
        // Find the index where new logs start
        let firstOldIdx = newData.findIndex(e => e.time === (currentData[0] && currentData[0].time));
        let toPrepend = firstOldIdx === -1 ? newData : newData.slice(0, firstOldIdx);
        if (toPrepend.length > 0) {
          currentData = toPrepend.concat(currentData);
          applyFilters();
        }
      }
    } catch (err) {
      console.error('Fetch error:', err);
    }
  }

  // event listeners
  [filterText, filterFrom, filterTo].forEach(el =>
    el.addEventListener('input', applyFilters)
  );
  clearBtn.addEventListener('click', () => {
    filterText.value = '';
    filterFrom.value = '';
    filterTo.value   = '';
    applyFilters();
  });
  scrollBtn.addEventListener('click', () => {
    const container = tableBody.parentElement;
    container.scrollTop = 0;
  });
  pauseBtn.addEventListener('click', () => {
    autoRefresh = !autoRefresh;
    pauseBtn.textContent = autoRefresh ? 'Pause Auto-Refresh' : 'Resume Auto-Refresh';
    if (autoRefresh) poll();
  });

  // initial render & polling
  renderRows(currentData);
  applyFilters();
  pollTimer = setInterval(poll, pollInterval);
})();
