document.addEventListener('DOMContentLoaded', function () {
  var paletteSwitcher = document.querySelector('[data-md-component=palette]');

  function currentTheme() {
    var palette = window.__md_get && window.__md_get('__palette');

    if (palette && typeof palette.color === 'object') {
      return palette.color.scheme === 'slate' ? 'transparent_dark' : 'light';
    }

    return document.body.getAttribute('data-md-color-scheme') === 'slate'
      ? 'transparent_dark'
      : 'light';
  }

  function syncGiscusTheme() {
    var frame = document.querySelector('.giscus-frame');

    if (!frame || !frame.contentWindow) {
      return;
    }

    frame.contentWindow.postMessage(
      { giscus: { setConfig: { theme: currentTheme() } } },
      'https://giscus.app'
    );
  }

  if (paletteSwitcher) {
    paletteSwitcher.addEventListener('change', function () {
      window.setTimeout(syncGiscusTheme, 120);
    });
  }

  syncGiscusTheme();
});