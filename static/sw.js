/* ============================================================
   研途追踪 Service Worker
   策略：
   - 静态资源（本应用 + CDN 库）：缓存优先，离线秒开
   - 页面导航：仅网络（不缓存任何页面——页面含个人数据，
     避免隐私残留与陈旧内容）；离线时展示 offline.html
   - /api/ 请求：直接走网络，绝不缓存
   版本升级：修改 CACHE 名称（如 yantu-v2）即可强制全量刷新
   ============================================================ */
const CACHE = 'yantu-v2';
const PRECACHE = [
  '/static/style.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/offline.html',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => Promise.allSettled(PRECACHE.map((u) => cache.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // 只处理 http/https 请求；其它协议（如 chrome-extension、blob）直接放行，
  // 否则 Cache API 会抛「Request scheme ... is unsupported」
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return;
  }

  // API 与表单提交：直接走网络
  if (url.pathname.startsWith('/api/') || req.method !== 'GET') {
    return;
  }

  // 页面导航：仅网络，失败时展示离线页（不缓存页面内容）
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('/static/offline.html'))
    );
    return;
  }

  // 静态资源：缓存优先，回源更新缓存
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req).then((res) => {
        if (res && res.ok && (res.type === 'basic' || res.type === 'cors' || res.type === 'opaque')) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
