(function () {
  var bootNode = document.getElementById('chapter-editor-html');
  var bootHtml = bootNode ? JSON.parse(bootNode.textContent) : '';
  var editorEl = document.getElementById('chapter-editor');
  var form = document.getElementById('chapter-edit-form');
  var hiddenHtml = document.getElementById('content_html');
  var split = document.querySelector('.editor-split');
  var previewEl = document.getElementById('mobile-preview');
  var fnContainer = document.getElementById('footnote-items');
  var fnHidden = document.getElementById('footnote_items');
  var fnHeading = document.getElementById('footnote_heading');
  var fnDataNode = document.getElementById('chapter-footnotes-data');
  var fnPanel = document.querySelector('.footnotes-panel');
  if (!editorEl || !form || !hiddenHtml || typeof Quill === 'undefined') return;

  var quill = new Quill('#chapter-editor', {
    theme: 'snow',
    placeholder: 'Fəsil mətnini buraya yazın…',
    modules: {
      toolbar: [
        [{ header: [1, 2, false] }],
        ['bold', 'italic'],
        [{ align: [] }],
        [{ list: 'ordered' }, { list: 'bullet' }],
        ['blockquote'],
        ['clean'],
      ],
    },
  });

  function stripInlineColors(root) {
    if (!root) return;
    root.querySelectorAll('[style]').forEach(function (el) {
      el.style.removeProperty('color');
      el.style.removeProperty('background');
      el.style.removeProperty('background-color');
    });
    root.querySelectorAll('font[color]').forEach(function (el) {
      el.removeAttribute('color');
    });
  }

  function cleanPasteDelta(delta) {
    if (!delta || !delta.ops) return delta;
    delta.ops.forEach(function (op) {
      if (!op.attributes) return;
      delete op.attributes.color;
      delete op.attributes.background;
      delete op.attributes.backgroundColor;
    });
    return delta;
  }

  quill.clipboard.addMatcher(Node.ELEMENT_NODE, function (_node, delta) {
    return cleanPasteDelta(delta);
  });

  quill.root.addEventListener('paste', function () {
    window.setTimeout(function () {
      stripInlineColors(quill.root);
      schedulePreview();
    }, 0);
  });

  if (bootHtml && String(bootHtml).trim()) {
    quill.clipboard.dangerouslyPasteHTML(0, bootHtml);
    stripInlineColors(quill.root);
  }

  var suggestNext = 1;
  if (fnPanel) {
    var rawSuggest = fnPanel.getAttribute('data-fn-suggest');
    suggestNext = parseInt(rawSuggest, 10) || 1;
  }

  function parseBootFootnotes(parsed) {
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(function (item, idx) {
        if (item && typeof item === 'object' && item.n != null) {
          return {
            n: parseInt(item.n, 10) || idx + 1,
            text: String(item.text || ''),
          };
        }
        return { n: idx + 1, text: String(item || '') };
      })
      .filter(function (e) {
        return e.n >= 1;
      });
  }

  var footnotes = [];
  if (fnDataNode) {
    try {
      footnotes = parseBootFootnotes(JSON.parse(fnDataNode.textContent));
    } catch (e) {
      footnotes = [];
    }
  }

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function footnoteMaxInEditor() {
    var max = 0;
    footnotes.forEach(function (e) {
      if (e.n > max) max = e.n;
    });
    return max;
  }

  function nextFreeNumber() {
    var max = footnoteMaxInEditor();
    return max > 0 ? max + 1 : suggestNext;
  }

  function syncFootnotesHidden() {
    if (fnHidden) {
      footnotes.sort(function (a, b) {
        return a.n - b.n;
      });
      fnHidden.value = JSON.stringify(
        footnotes.map(function (e) {
          return { n: e.n, text: e.text };
        }),
      );
    }
  }

  function renderFootnotes() {
    if (!fnContainer) return;
    fnContainer.innerHTML = '';
    footnotes
      .slice()
      .sort(function (a, b) {
        return a.n - b.n;
      })
      .forEach(function (entry, idx) {
        var row = document.createElement('div');
        row.className = 'fn-row';

        var top = document.createElement('div');
        top.className = 'fn-row-top';

        var numWrap = document.createElement('label');
        numWrap.className = 'fn-num-wrap';
        numWrap.textContent = '№';

        var numInput = document.createElement('input');
        numInput.type = 'number';
        numInput.min = '1';
        numInput.step = '1';
        numInput.className = 'fn-num-input';
        numInput.value = String(entry.n);
        numInput.title = 'Qeyd nömrəsi — kitab üzrə davam edə bilər';
        numInput.addEventListener('change', function () {
          var next = parseInt(numInput.value, 10);
          if (!next || next < 1) {
            numInput.value = String(entry.n);
            return;
          }
          entry.n = next;
          syncFootnotesHidden();
          schedulePreview();
        });

        numWrap.appendChild(numInput);

        var actions = document.createElement('div');
        actions.className = 'fn-row-actions';

        var insertBtn = document.createElement('button');
        insertBtn.type = 'button';
        insertBtn.className = 'fmt-btn fn-mini';
        insertBtn.textContent = 'Mətndə [' + entry.n + ']';
        insertBtn.title = 'Kursor yerinə [' + entry.n + '] yaz';
        insertBtn.addEventListener('click', function () {
          insertFootnoteRef(entry.n);
        });

        var delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'fmt-btn fn-mini fn-del';
        delBtn.textContent = 'Sil';
        delBtn.addEventListener('click', function () {
          var pos = footnotes.indexOf(entry);
          if (pos >= 0) footnotes.splice(pos, 1);
          renderFootnotes();
          schedulePreview();
        });

        actions.appendChild(insertBtn);
        actions.appendChild(delBtn);

        top.appendChild(numWrap);
        top.appendChild(actions);

        var ta = document.createElement('textarea');
        ta.rows = 2;
        ta.placeholder = 'Haşiyə / istinad mətni…';
        ta.value = entry.text;
        ta.addEventListener('input', function () {
          entry.text = ta.value;
          syncFootnotesHidden();
          schedulePreview();
        });

        row.appendChild(top);
        row.appendChild(ta);
        fnContainer.appendChild(row);
      });
    syncFootnotesHidden();
  }

  function insertFootnoteRef(n) {
    var mark = '[' + n + ']';
    var range = quill.getSelection(true);
    var index = range ? range.index : quill.getLength();
    quill.insertText(index, mark, 'user');
    quill.setSelection(index + mark.length, 0);
    schedulePreview();
  }

  var fnAdd = document.getElementById('fn-add');
  if (fnAdd) {
    fnAdd.addEventListener('click', function () {
      var n = nextFreeNumber();
      footnotes.push({ n: n, text: '' });
      renderFootnotes();
      insertFootnoteRef(n);
      var inputs = fnContainer && fnContainer.querySelectorAll('textarea');
      if (inputs && inputs.length) inputs[inputs.length - 1].focus();
      schedulePreview();
    });
  }

  var fnInsert = document.getElementById('fn-insert');
  if (fnInsert) {
    fnInsert.addEventListener('click', function () {
      var n = nextFreeNumber();
      if (footnotes.length === 0) {
        footnotes.push({ n: n, text: '' });
        renderFootnotes();
      }
      insertFootnoteRef(n);
    });
  }

  renderFootnotes();

  form.addEventListener('submit', function () {
    stripInlineColors(quill.root);
    hiddenHtml.value = quill.root.innerHTML;
    syncFootnotesHidden();
  });

  window.siracChapterQuill = quill;

  var titleEl = document.getElementById('chapter_title');
  var previewUrl = split ? split.getAttribute('data-preview-url') : '';
  var bookLang = split ? split.getAttribute('data-book-lang') || 'az' : 'az';
  var previewTimer = null;

  function updateMobilePreview() {
    if (!previewEl || !previewUrl) return;

    fetch(previewUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({
        title: titleEl ? titleEl.value : '',
        content_html: quill.root.innerHTML,
        language: bookLang,
        footnote_items: footnotes.map(function (e) {
          return { n: e.n, text: e.text };
        }),
        footnote_heading: fnHeading ? fnHeading.value : 'Qeydlər və istinadlar',
      }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error('Önizləmə alınmadı');
        return res.text();
      })
      .then(function (html) {
        previewEl.innerHTML = html;
      })
      .catch(function () {
        previewEl.innerHTML =
          '<p class="rp-empty">Önizləmə yüklənmədi — mətni yadda saxlayıb tətbiqdə yoxlayın.</p>';
      });
  }

  function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(updateMobilePreview, 320);
  }

  quill.on('text-change', schedulePreview);
  if (titleEl) titleEl.addEventListener('input', schedulePreview);
  if (fnHeading) fnHeading.addEventListener('input', schedulePreview);
  updateMobilePreview();

  var aiBtn = document.getElementById('fmt-ai');
  if (!aiBtn || !titleEl) return;

  aiBtn.addEventListener('click', function () {
    var plain = quill.getText().trim();
    if (!plain && !titleEl.value.trim()) {
      window.alert('Əvvəlcə fəsil başlığı və ya mətn yazın.');
      return;
    }
    if (
      !window.confirm('AI mətni yoxlayıb orfoqrafiya/format səhvlərini düzəldəcək. Davam edilsin?')
    ) {
      return;
    }

    var prevLabel = aiBtn.textContent;
    aiBtn.disabled = true;
    aiBtn.textContent = '…';

    fetch(aiBtn.getAttribute('data-url'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({
        title: titleEl.value,
        content: quill.getText(),
        content_html: quill.root.innerHTML,
        language: aiBtn.getAttribute('data-lang') || bookLang,
      }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.error || 'AI xətası');
          return data;
        });
      })
      .then(function (data) {
        if (typeof data.title === 'string' && data.title.trim()) {
          titleEl.value = data.title;
        }
        if (typeof data.content_html === 'string' && data.content_html.trim()) {
          quill.setContents([]);
          quill.clipboard.dangerouslyPasteHTML(0, data.content_html);
        } else if (typeof data.content === 'string') {
          quill.setText(data.content);
        }
        updateMobilePreview();
        window.alert('AI düzəliş hazırdır. «Yadda saxla» ilə qeyd edin.');
      })
      .catch(function (err) {
        window.alert(err.message || 'AI düzəliş alınmadı.');
      })
      .finally(function () {
        aiBtn.disabled = false;
        aiBtn.textContent = prevLabel;
      });
  });
})();
