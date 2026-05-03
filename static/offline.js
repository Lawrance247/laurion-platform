// ============================================================
//  LAURION OFFLINE MANAGER  v2.0
//  Registers SW, manages IndexedDB queue, shows banners
// ============================================================

const LAURION_OFFLINE = {

  db: null,
  isOnline: navigator.onLine,

  async init() {
    await this.openDB();
    this.registerSW();
    this.watchConnectivity();
    this.setupOfflineForms();
    this.renderBanner();
  },

  // ── Service Worker ────────────────────────────────────────
  registerSW() {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.register('/static/sw.js', { scope: '/' })
      .then(reg => {
        console.log('[Laurion SW] registered', reg.scope);
        // Check for updates every 30min
        setInterval(() => reg.update(), 30 * 60 * 1000);
      })
      .catch(err => console.warn('[Laurion SW] failed:', err));
  },

  // ── IndexedDB ─────────────────────────────────────────────
  openDB() {
    return new Promise((res, rej) => {
      const req = indexedDB.open('laurion-offline', 1);
      req.onupgradeneeded = e => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains('pending-tasks'))
          db.createObjectStore('pending-tasks', { keyPath: 'id', autoIncrement: true });
        if (!db.objectStoreNames.contains('pending-notes'))
          db.createObjectStore('pending-notes', { keyPath: 'id', autoIncrement: true });
        if (!db.objectStoreNames.contains('cached-materials'))
          db.createObjectStore('cached-materials', { keyPath: 'id' });
      };
      req.onsuccess = e => { this.db = e.target.result; res(); };
      req.onerror   = e => rej(e.target.error);
    });
  },

  saveOffline(storeName, data) {
    return new Promise((res, rej) => {
      const tx    = this.db.transaction(storeName, 'readwrite');
      const store = tx.objectStore(storeName);
      store.add({ data, savedAt: new Date().toISOString() });
      tx.oncomplete = () => res(true);
      tx.onerror    = () => rej();
    });
  },

  // ── Connectivity ──────────────────────────────────────────
  watchConnectivity() {
    window.addEventListener('online',  () => { this.isOnline = true;  this.onComeOnline(); });
    window.addEventListener('offline', () => { this.isOnline = false; this.renderBanner(); });
  },

  onComeOnline() {
    this.renderBanner();
    this.syncPending();
    // Background sync via SW if supported
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      navigator.serviceWorker.ready.then(reg => {
        reg.sync.register('sync-tasks');
        reg.sync.register('sync-notes');
      }).catch(() => {});
    }
  },

  async syncPending() {
    // Sync pending tasks
    try {
      const tx    = this.db.transaction('pending-tasks', 'readwrite');
      const store = tx.objectStore('pending-tasks');
      const items = await new Promise((res, rej) => {
        const r = store.getAll(); r.onsuccess = () => res(r.result); r.onerror = () => rej();
      });
      for (const item of items) {
        try {
          const r = await fetch('/sync-planner', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item.data)
          });
          if (r.ok || r.redirected) store.delete(item.id);
        } catch {}
      }
      if (items.length) this.showToast(`✅ ${items.length} offline task${items.length>1?'s':''} synced!`);
    } catch {}
  },

  // ── Offline forms (queue when offline) ────────────────────
  setupOfflineForms() {
    // Planner form
    document.querySelectorAll('form[data-offline="task"]').forEach(form => {
      form.addEventListener('submit', async e => {
        if (this.isOnline) return; // let normal submit happen
        e.preventDefault();
        const data = Object.fromEntries(new FormData(form));
        await this.saveOffline('pending-tasks', data);
        this.showToast('📋 Task saved offline — will sync when online', 'info');
        form.reset();
      });
    });

    // Notes form
    document.querySelectorAll('form[data-offline="notes"]').forEach(form => {
      form.addEventListener('submit', async e => {
        if (this.isOnline) return;
        e.preventDefault();
        const data = Object.fromEntries(new FormData(form));
        await this.saveOffline('pending-notes', data);
        this.showToast('📝 Notes saved offline — will sync when online', 'info');
      });
    });
  },

  // ── Offline banner ────────────────────────────────────────
  renderBanner() {
    let banner = document.getElementById('laurion-offline-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'laurion-offline-banner';
      banner.style.cssText = `
        position:fixed; bottom:0; left:0; right:0; z-index:9999;
        padding:12px 20px; font-family:'DM Sans',sans-serif; font-size:14px;
        display:flex; align-items:center; justify-content:space-between;
        transform:translateY(100%); transition:transform 0.35s ease;
        border-top:1px solid rgba(255,255,255,0.12);
      `;
      document.body.appendChild(banner);
    }

    if (!this.isOnline) {
      banner.style.background = '#1a3c5e';
      banner.style.color = '#fff';
      banner.innerHTML = `
        <span>📡 <strong>No internet</strong> — Laurion is running offline. Notes & tasks will sync when you reconnect.</span>
        <button onclick="this.parentElement.style.transform='translateY(100%)'"
          style="background:rgba(255,255,255,0.12);border:none;color:#fff;padding:6px 14px;border-radius:8px;cursor:pointer;font-size:13px;flex-shrink:0;margin-left:12px;">
          Dismiss
        </button>`;
      banner.style.transform = 'translateY(0)';
    } else {
      banner.style.background = '#0b2240';
      banner.style.color = '#fff';
      banner.innerHTML = `<span>✅ <strong>Back online!</strong> Syncing your offline data...</span>`;
      banner.style.transform = 'translateY(0)';
      setTimeout(() => { banner.style.transform = 'translateY(100%)'; }, 3500);
    }
  },

  // ── Toast helper ──────────────────────────────────────────
  showToast(msg, type = 'success') {
    let container = document.getElementById('laurion-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'laurion-toast-container';
      container.style.cssText = 'position:fixed;bottom:72px;right:20px;display:flex;flex-direction:column;gap:10px;z-index:9998;';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.style.cssText = `
      background:#0b2240; color:#fff; padding:13px 18px; border-radius:14px;
      font-size:14px; font-family:'DM Sans',sans-serif; font-weight:500;
      box-shadow:0 8px 32px rgba(0,0,0,0.3); max-width:320px;
      border-left:4px solid ${type==='info'?'#f5a623':'#1a9e5c'};
      animation:toastIn 0.35s cubic-bezier(0.34,1.56,0.64,1);
    `;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  },

  // ── Install prompt ────────────────────────────────────────
  initInstallPrompt() {
    let deferredPrompt;
    window.addEventListener('beforeinstallprompt', e => {
      e.preventDefault();
      deferredPrompt = e;
      this.showInstallBanner(deferredPrompt);
    });
  },

  showInstallBanner(prompt) {
    // Only show once per session
    if (sessionStorage.getItem('install-dismissed')) return;
    const banner = document.createElement('div');
    banner.style.cssText = `
      position:fixed; top:76px; left:50%; transform:translateX(-50%);
      background:#0b2240; color:#fff; padding:14px 20px; border-radius:14px;
      font-family:'DM Sans',sans-serif; font-size:14px; z-index:9997;
      box-shadow:0 8px 32px rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1);
      display:flex; align-items:center; gap:14px; max-width:480px; width:calc(100% - 32px);
    `;
    banner.innerHTML = `
      <span>📲 <strong>Install Laurion</strong> — use offline, no app store needed</span>
      <button id="pwa-install"
        style="background:#1a9e5c;border:none;color:#fff;padding:8px 16px;border-radius:9px;cursor:pointer;font-size:13px;font-weight:600;white-space:nowrap;flex-shrink:0;">
        Install
      </button>
      <button
        style="background:rgba(255,255,255,0.1);border:none;color:rgba(255,255,255,0.6);padding:8px 12px;border-radius:9px;cursor:pointer;font-size:13px;flex-shrink:0;"
        onclick="this.closest('div').remove(); sessionStorage.setItem('install-dismissed','1');">
        ✕
      </button>`;
    document.body.appendChild(banner);

    document.getElementById('pwa-install').addEventListener('click', () => {
      prompt.prompt();
      prompt.userChoice.then(c => {
        banner.remove();
        if (c.outcome === 'accepted') this.showToast('🎉 Laurion installed! You can now use it offline.');
        sessionStorage.setItem('install-dismissed', '1');
      });
    });
  }
};

// ── Auto-init ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  LAURION_OFFLINE.init();
  LAURION_OFFLINE.initInstallPrompt();
});
