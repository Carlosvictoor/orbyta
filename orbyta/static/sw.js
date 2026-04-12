/* =============================================================
   Orbyta — Service Worker
   Estratégia:
  - Estáticos (/static/, /manifest.json): stale-while-revalidate
   - Navegação HTML: network-first → offline fallback
   - APIs (/api/*): network-only (nunca sirva cache de dados)
   - Resto: stale-while-revalidate
   ============================================================= */

const CACHE_VERSION = 'v2';
const CACHE_NAME = `orbyta-${CACHE_VERSION}`;

const PRECACHE_URLS = [
  '/',
  '/offline',
  '/manifest.json',
  '/static/style.css',
  '/static/favicon.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/pwa-register.js',
];

// ── Install ──────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(PRECACHE_URLS);
    })
  );
  self.skipWaiting();
});

// ── Activate: remove caches antigos ─────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k.startsWith('orbyta-') && k !== CACHE_NAME)
          .map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch ────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignorar requests não-GET e de outras origens
  if (request.method !== 'GET' || url.origin !== location.origin) return;

  // API: network-only (dados sempre frescos)
  if (url.pathname.startsWith('/api/')) return;

  // Arquivos estáticos e manifest: stale-while-revalidate
  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.json') {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // Navegação HTML: network-first com fallback offline
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstWithOfflineFallback(request));
    return;
  }

  // Demais: stale-while-revalidate
  event.respondWith(staleWhileRevalidate(request));
});

// ── Estratégias ──────────────────────────────────────────────

async function networkFirstWithOfflineFallback(request) {
  try {
    const response = await fetch(request);
    // Salva navegações bem-sucedidas no cache
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return caches.match('/offline');
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then(response => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  });
  return cached || fetchPromise;
}
