/**
 * Admin: YouTube link yapışdırılanda ad/başlıq avtomatik dolsun.
 * URL sahəsi dəyişəndə (və ad boşdursa) /api/youtube-title/ çağırılır.
 */
(function () {
  function lookup(url, onDone) {
    if (!url || !/^https?:\/\//i.test(url.trim())) {
      onDone(null);
      return;
    }
    var endpoint =
      '/api/youtube-title/?url=' + encodeURIComponent(url.trim());
    fetch(endpoint, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        onDone(data && data.ok ? data.title : null);
      })
      .catch(function () {
        onDone(null);
      });
  }

  function wire(urlInput, titleInput) {
    if (!urlInput || !titleInput || urlInput.dataset.ytWired) return;
    urlInput.dataset.ytWired = '1';

    var timer = null;
    function run() {
      var url = urlInput.value;
      var current = (titleInput.value || '').trim();
      // İstifadəçi özü ad yazıbsa toxunma
      if (current && titleInput.dataset.ytAuto !== '1') return;

      clearTimeout(timer);
      timer = setTimeout(function () {
        titleInput.placeholder = 'Başlık yüklənir…';
        lookup(url, function (title) {
          titleInput.placeholder = '';
          if (!title) return;
          if ((titleInput.value || '').trim() && titleInput.dataset.ytAuto !== '1') {
            return;
          }
          titleInput.value = title;
          titleInput.dataset.ytAuto = '1';
          titleInput.dispatchEvent(new Event('input', { bubbles: true }));
          titleInput.dispatchEvent(new Event('change', { bubbles: true }));
        });
      }, 400);
    }

    urlInput.addEventListener('paste', function () {
      setTimeout(run, 50);
    });
    urlInput.addEventListener('change', run);
    urlInput.addEventListener('blur', run);

    titleInput.addEventListener('input', function () {
      if (titleInput.dataset.ytAuto === '1') {
        // istifadəçi auto-title-ı dəyişirsə artıq əl ilə say
        titleInput.dataset.ytAuto = '0';
      }
    });
  }

  function scan(root) {
    root = root || document;

    // Kanal formu: id_url → id_name
    wire(root.querySelector('#id_url'), root.querySelector('#id_name'));

    // Silsilə formu: id_playlist_url → id_title
    wire(root.querySelector('#id_playlist_url'), root.querySelector('#id_title'));

    // Dərs formu / inline: …-url → …-title
    root.querySelectorAll('input[name$="-url"], input[id$="-url"]').forEach(function (urlEl) {
      var name = urlEl.getAttribute('name') || '';
      var titleName = name.replace(/-url$/, '-title');
      var titleEl =
        root.querySelector('input[name="' + titleName + '"]') ||
        document.getElementById(urlEl.id.replace(/-url$/, '-title'));
      // playlist_url üçün ayrıca
      if (!titleEl && name.indexOf('playlist_url') !== -1) {
        titleName = name.replace(/playlist_url$/, 'title');
        titleEl = root.querySelector('input[name="' + titleName + '"]');
      }
      wire(urlEl, titleEl);
    });

    root.querySelectorAll('input[name$="-playlist_url"], input[id$="-playlist_url"]').forEach(
      function (urlEl) {
        var name = urlEl.getAttribute('name') || '';
        var titleName = name.replace(/playlist_url$/, 'title');
        var titleEl = root.querySelector('input[name="' + titleName + '"]');
        if (!titleEl) {
          titleEl = document.getElementById(urlEl.id.replace(/playlist_url$/, 'title'));
        }
        wire(urlEl, titleEl);
      },
    );
  }

  document.addEventListener('DOMContentLoaded', function () {
    scan(document);
  });

  // Inline əlavə olunanda
  document.addEventListener('formset:added', function (e) {
    scan(e.target || document);
  });
})();
