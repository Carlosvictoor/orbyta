/* Orbyta — Registro do Service Worker */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then(reg => {
        // Verifica atualização a cada visita
        reg.update();
      })
      .catch(err => console.warn('[PWA] Falha ao registrar service worker:', err));
  });
}
