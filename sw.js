// ============================================================
//  LAURION SERVICE WORKER  v2.2
//  Offline-first for rural / low-connectivity users
// ============================================================

const CACHE_NAME   = 'laurion-v6';
const API_CACHE    = 'laurion-api-v6';
const ASSET_CACHE  = 'laurion-assets-v6';

// Core shell — only cache files that definitely exist
const SHELL_URLS = [
  '/',
  '/login',
  '/register',
  '/static/style.css',
  '/static/school.js',
  '/static/offline.js',
  '/static/manifest.json',
  '/static/images/logo.png',
  '/static/images/logoo.png',
  '/static/offline.html',
];

// Optional assets — cached if available, silently skipped if missing (404)
const OPTIONAL_URLS = [
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
];

// ── INSTALL: pre-cache the shell ─────────────────────────────
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      // Cache required shell files
      await cache.addAll(SHELL_URLS);

      // Cache optional assets — silently skip if 404
      await Promise.allSettled(
        OPTIONAL_URLS.map(url =>
          fetch(url).then(res => {
            if (res.ok) cache.put(url, res);
          }).catch(() => {})
        )
      );
    }).then(() => self.skipWaiting())
  );
});

// ── ACTIVATE: wipe ALL old caches ────────────────────────────
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => !['laurion-v6', 'laurion-api-v6', 'laurion-assets-v6'].includes(k))
            .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── FETCH strategy ───────────────────────────────────────────
self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Skip non-GET and chrome-extension requests
  if (request.method !== 'GET' || url.protocol === 'chrome-extension:') return;

  // Never intercept download requests — let them go straight to server
  if (url.pathname.startsWith('/download/')) return;

  // Static assets → Cache First
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(cacheFirst(request, ASSET_CACHE));
    return;
  }

  // API data routes → Network First with offline fallback
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(networkFirst(request, API_CACHE));
    return;
  }

  // Navigation → Stale While Revalidate, fallback to offline page
  e.respondWith(staleWhileRevalidate(request, CACHE_NAME));
});

// ── Strategies ───────────────────────────────────────────────

async function cacheFirst(req, cacheName) {
  const cached = await caches.match(req);
  if (cached) return cached;
  try {
    const fresh = await fetch(req);
    if (fresh.ok && fresh.status === 200 && !fresh.redirected) {
      const cache = await caches.open(cacheName);
      cache.put(req, fresh.clone());
    }
    return fresh;
  } catch {
    return cached || new Response('Offline — asset unavailable', { status: 503 });
  }
}

async function networkFirst(req, cacheName) {
  try {
    const fresh = await fetch(req);
    if (fresh.ok) {
      const cache = await caches.open(cacheName);
      cache.put(req, fresh.clone());
    }
    return fresh;
  } catch {
    const cached = await caches.match(req);
    return cached || new Response(
      JSON.stringify({ offline: true, error: 'No connection' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function staleWhileRevalidate(req, cacheName) {
  const cache  = await caches.open(cacheName);
  const cached = await cache.match(req);

  const fetchPromise = fetch(req).then(fresh => {
    if (fresh.ok && fresh.status === 200 && !fresh.redirected) {
      cache.put(req, fresh.clone());
    }
    return fresh;
  }).catch(() => null);

  if (cached) {
    fetchPromise; // update in background
    return cached;
  }

  const fresh = await fetchPromise;
  if (fresh) return fresh;

  const offline = await caches.match('/static/offline.html');
  return offline || new Response('<h1>You are offline</h1>', {
    headers: { 'Content-Type': 'text/html' }
  });
}

// ── Background sync ────────────────────────────────────────────
self.addEventListener('sync', e => {
  if (e.tag === 'sync-tasks')
    e.waitUntil(syncPendingData('pending-tasks', '/sync-planner'));
  if (e.tag === 'sync-notes')
    e.waitUntil(syncPendingData('pending-notes', '/sync-notes'));
});

async function syncPendingData(storeName, endpoint) {
  try {
    const db = await openDB();
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    const items = await getAllItems(store);
    for (const item of items) {
      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(item.data)
        });
        if (res.ok) store.delete(item.id);
      } catch {}
    }
  } catch {}
}

// ── Push notifications ─────────────────────────────────────────
self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : { title: 'Laurion', body: 'You have a reminder!' };
  e.waitUntil(
    self.registration.showNotification(data.title || 'Laurion', {
      body: data.body,
      icon: '/static/images/icon-192.png',
      badge: '/static/images/icon-192.png',
      vibrate: [200, 100, 200],
      data: { url: data.url || '/planner' }
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data.url || '/'));
});

// ── IndexedDB helpers ──────────────────────────────────────────
function openDB() {
  return new Promise((res, rej) => {
    const req = indexedDB.open('laurion-offline', 1);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending-tasks'))
        db.createObjectStore('pending-tasks', { keyPath: 'id', autoIncrement: true });
      if (!db.objectStoreNames.contains('pending-notes'))
        db.createObjectStore('pending-notes', { keyPath: 'id', autoIncrement: true });
    };
    req.onsuccess = e => res(e.target.result);
    req.onerror   = e => rej(e.target.error);
  });
}

function getAllItems(store) {
  return new Promise((res, rej) => {
    const req = store.getAll();
    req.onsuccess = () => res(req.result);
    req.onerror   = () => rej(req.error);
  });
}
