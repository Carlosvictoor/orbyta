/* Orbyta — Registro do Service Worker e estado PWA global */
(function () {
  const root = document.documentElement;
  const body = document.body;
  const standaloneMedia = window.matchMedia('(display-mode: standalone)');
  let deferredPrompt = null;
  let refreshing = false;

  function activateWaitingWorker(registration) {
    if (registration && registration.waiting) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
  }

  function watchRegistration(registration) {
    if (!registration) return;

    if (registration.waiting) {
      activateWaitingWorker(registration);
    }

    registration.addEventListener('updatefound', () => {
      const installingWorker = registration.installing;
      if (!installingWorker) return;

      installingWorker.addEventListener('statechange', () => {
        if (installingWorker.state === 'installed' && navigator.serviceWorker.controller) {
          activateWaitingWorker(registration);
        }
      });
    });
  }

  function isStandaloneMode() {
    return standaloneMedia.matches || window.navigator.standalone === true;
  }

  function syncDisplayMode() {
    const standalone = isStandaloneMode();
    root.dataset.displayMode = standalone ? 'standalone' : 'browser';
    if (body) {
      body.classList.toggle('standalone-app', standalone);
    }
  }

  window.orbytaPwa = {
    isStandalone: isStandaloneMode,
    canInstall: () => Boolean(deferredPrompt),
    promptInstall: async () => {
      if (!deferredPrompt) return null;
      const promptEvent = deferredPrompt;
      deferredPrompt = null;
      promptEvent.prompt();
      const choice = await promptEvent.userChoice;
      window.dispatchEvent(new CustomEvent('orbyta:pwa-install-finished', { detail: choice }));
      return choice;
    },
  };

  syncDisplayMode();
  standaloneMedia.addEventListener('change', syncDisplayMode);
  window.addEventListener('DOMContentLoaded', syncDisplayMode, { once: true });
  window.addEventListener('pageshow', syncDisplayMode);

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    window.dispatchEvent(new CustomEvent('orbyta:pwa-install-available'));
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    syncDisplayMode();
    window.dispatchEvent(new CustomEvent('orbyta:pwa-installed'));
  });

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });

    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js', { scope: '/' })
        .then((reg) => {
          watchRegistration(reg);
          reg.update();
        })
        .catch((err) => console.warn('[PWA] Falha ao registrar service worker:', err));
    });
  }
})();
