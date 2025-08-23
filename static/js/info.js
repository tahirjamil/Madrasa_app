// Info Page JavaScript - Request & Response Log

(function() {
  'use strict';

  // DOM Elements
  const filterText = document.getElementById('filter-text');
  const filterFrom = document.getElementById('filter-from');
  const filterTo = document.getElementById('filter-to');
  const clearBtn = document.getElementById('clear-filters');
  const tableBody = document.querySelector('#log-table tbody');
  const entryCount = document.getElementById('entry-count');
  const scrollBtn = document.getElementById('scroll-top');
  const pauseBtn = document.getElementById('pause-refresh');
  const refreshBtn = document.getElementById('refresh-now');
  const successCount = document.getElementById('success-count');
  const clientErrorCount = document.getElementById('client-error-count');
  const serverErrorCount = document.getElementById('server-error-count');

  // State
  let currentData = [];
  let autoRefresh = true;
  let pollInterval = 5000;
  let pollTimer = null;

  // Initialize
  function init() {
    loadInitialData();
    setupEventListeners();
    startPolling();
    updateStats();
  }

  // Load initial data from the page
  function loadInitialData() {
    try {
      const raw = document.getElementById('init-data').textContent;
      currentData = JSON.parse(raw);
      currentData.reverse(); // Newest at top
      renderRows(currentData);
    } catch (error) {
      console.error('Error loading initial data:', error);
      showEmptyState();
    }
  }

  // Setup event listeners
  function setupEventListeners() {
    // Filter events
    if (filterText) filterText.addEventListener('input', applyFilters);
    if (filterFrom) filterFrom.addEventListener('change', applyFilters);
    if (filterTo) filterTo.addEventListener('change', applyFilters);
    if (clearBtn) clearBtn.addEventListener('click', clearFilters);

    // Control events
    if (pauseBtn) pauseBtn.addEventListener('click', toggleAutoRefresh);
    if (refreshBtn) refreshBtn.addEventListener('click', manualRefresh);
    if (scrollBtn) scrollBtn.addEventListener('click', scrollToTop);

    // Scroll event for scroll-to-top button
    window.addEventListener('scroll', handleScroll);

    // JSON block click events
    attachJsonToggle();
  }

  // Utility functions
  function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function getMethodBadgeClass(method) {
    const methodLower = method.toLowerCase();
    return `badge status-badge method-${methodLower}`;
  }

  // Render table rows
  function renderRows(data) {
    if (!tableBody) return;

    if (data.length === 0) {
      showEmptyState();
      return;
    }

    tableBody.innerHTML = '';
    
    data.forEach(e => {
      const reqCell = e.req_json !== null
        ? `<pre class="json-block">${escapeHtml(JSON.stringify(e.req_json, null, 2))}</pre>`
        : '<span class="text-muted">—</span>';
      
      const resCell = e.res_json !== null
        ? `<pre class="json-block">${escapeHtml(JSON.stringify(e.res_json, null, 2))}</pre>`
        : '<span class="text-muted">—</span>';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><small class="text-muted">${escapeHtml(e.time)}</small></td>
        <td><code class="text-primary">${escapeHtml(e.ip)}</code></td>
        <td><span class="${getMethodBadgeClass(e.method)}">${escapeHtml(e.method)}</span></td>
        <td><code class="text-dark">${escapeHtml(e.path)}</code></td>
        <td>${reqCell}</td>
        <td>${resCell}</td>
      `;
      tableBody.appendChild(tr);
    });

    if (entryCount) entryCount.textContent = data.length;
    attachJsonToggle();
  }

  // Show empty state
  function showEmptyState() {
    if (!tableBody) return;
    
    tableBody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">
          <i class="bi bi-inbox"></i>
          <h5>No logs available</h5>
          <p>No request/response logs have been captured yet.</p>
        </td>
      </tr>
    `;
    
    if (entryCount) entryCount.textContent = '0';
  }

  // Attach JSON toggle functionality
  function attachJsonToggle() {
    document.querySelectorAll('.json-block').forEach(pre => {
      pre.addEventListener('click', () => {
        pre.classList.toggle('expanded');
      });
    });
  }

  // Apply filters
  function applyFilters() {
    const term = filterText ? filterText.value.trim().toLowerCase() : '';
    const from = filterFrom && filterFrom.value ? new Date(filterFrom.value) : null;
    const to = filterTo && filterTo.value ? new Date(filterTo.value) : null;

    const filtered = currentData.filter(e => {
      // Text search
      if (term) {
        let hay = (e.time + e.ip + e.method + e.path).toLowerCase();
        hay += JSON.stringify(e.req_json || {}).toLowerCase();
        hay += JSON.stringify(e.res_json || {}).toLowerCase();
        if (!hay.includes(term)) return false;
      }

      // Date filtering
      if (from || to) {
        const dt = new Date(e.time.replace(' ', 'T'));
        if (from && dt < from) return false;
        if (to && dt > to) return false;
      }
      
      return true;
    });

    renderRows(filtered);
  }

  // Clear filters
  function clearFilters() {
    if (filterText) filterText.value = '';
    if (filterFrom) filterFrom.value = '';
    if (filterTo) filterTo.value = '';
    applyFilters();
  }

  // Toggle auto refresh
  function toggleAutoRefresh() {
    autoRefresh = !autoRefresh;
    
    if (autoRefresh) {
      if (pauseBtn) {
        pauseBtn.innerHTML = '<i class="bi bi-pause-circle me-1"></i>Pause Auto-Refresh';
        pauseBtn.classList.remove('btn-primary');
        pauseBtn.classList.add('btn-outline-primary');
      }
      startPolling();
    } else {
      if (pauseBtn) {
        pauseBtn.innerHTML = '<i class="bi bi-play-circle me-1"></i>Resume Auto-Refresh';
        pauseBtn.classList.remove('btn-outline-primary');
        pauseBtn.classList.add('btn-primary');
      }
      stopPolling();
    }
  }

  // Manual refresh
  async function manualRefresh() {
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1 spin"></i>Refreshing...';
    }
    
    try {
      await poll();
    } finally {
      if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>Refresh Now';
      }
    }
  }

  // Poll for new data
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
          updateStats();
        }
      }
    } catch (error) {
      console.error('Error polling for new data:', error);
    }
  }

  // Start polling
  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(poll, pollInterval);
  }

  // Stop polling
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // Update statistics
  function updateStats() {
    if (!successCount || !clientErrorCount || !serverErrorCount) return;
    
    // For now, just show total count
    // This could be enhanced to show actual status code counts if we add them to the log
    successCount.textContent = currentData.length;
    clientErrorCount.textContent = '0';
    serverErrorCount.textContent = '0';
  }

  // Handle scroll for scroll-to-top button
  function handleScroll() {
    if (!scrollBtn) return;
    
    if (window.pageYOffset > 300) {
      scrollBtn.style.display = 'block';
    } else {
      scrollBtn.style.display = 'none';
    }
  }

  // Scroll to top
  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
