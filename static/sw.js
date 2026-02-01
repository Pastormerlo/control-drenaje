self.addEventListener('install', (e) => {
  console.log('Service Worker instalado');
});

self.addEventListener('fetch', (e) => {
  // Por ahora, solo deja pasar las peticiones
  e.respondWith(fetch(e.request));
});