/* MemoSpace — interaksi sisi klien. Semua perubahan data tetap divalidasi & diotorisasi di backend. */
(function () {
  'use strict';

  // ------------------------------------------------------------------ util
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const csrfToken = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  const icons = () => { if (window.lucide) window.lucide.createIcons(); };

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'fetch' },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await res.json(); } catch (_) { /* bukan JSON */ }
    return { ok: res.ok, status: res.status, data };
  }

  function toast(message, type = 'info') {
    const stack = $('#toastStack');
    if (!stack) return;
    const icon = { success: 'circle-check', error: 'circle-alert', info: 'info' }[type] || 'info';
    const el = document.createElement('div');
    el.className = `toast ms-toast ms-toast-${type}`;
    el.setAttribute('role', 'status');
    el.innerHTML = `<div class="toast-body"><i data-lucide="${icon}"></i><span></span></div>`;
    el.querySelector('span').textContent = message; // textContent -> aman dari XSS
    stack.appendChild(el);
    icons();
    const t = new bootstrap.Toast(el, { delay: 3500 });
    el.addEventListener('hidden.bs.toast', () => el.remove());
    t.show();
  }

  const store = {
    get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch (_) { return null; } },
    set(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (_) { /* penyimpanan penuh/diblokir */ } },
    del(key) { try { localStorage.removeItem(key); } catch (_) { /* abaikan */ } },
  };

  document.addEventListener('DOMContentLoaded', () => {
    icons();
    $$('[data-flash]').forEach((el) => new bootstrap.Toast(el, { delay: 4000 }).show());
    initConfirmForms();
    initCopy();
    initDeleteModal();
    initFavorites();
    initFilters();
    initNoteForm();
    initOnboarding();
  });

  // ------------------------------------------------------------------ konfirmasi, salin
  function initConfirmForms() {
    document.addEventListener('submit', (e) => {
      const msg = e.target.getAttribute && e.target.getAttribute('data-confirm');
      if (msg && !window.confirm(msg)) e.preventDefault();
    });
  }

  function initCopy() {
    document.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-copy]');
      if (!btn) return;
      const target = $(btn.getAttribute('data-copy'));
      if (!target) return;
      try {
        await navigator.clipboard.writeText(target.textContent.trim());
        toast('Kode disalin ke clipboard.', 'success');
      } catch (_) {
        const r = document.createRange(); r.selectNodeContents(target);
        const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
        toast('Tekan Ctrl+C untuk menyalin kode.', 'info');
      }
    });
  }

  // ------------------------------------------------------------------ hapus catatan (modal konfirmasi)
  function initDeleteModal() {
    const modalEl = $('#deleteModal');
    if (!modalEl) return;
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-delete-url]');
      if (!btn) return;
      $('#deleteForm').setAttribute('action', btn.getAttribute('data-delete-url'));
      $('#deleteNoteTitle').textContent = btn.getAttribute('data-delete-title') || '';
      modal.show();
    });
    $('#deleteForm').addEventListener('submit', (e) => {
      const submit = e.target.querySelector('[type="submit"]');
      if (submit) submit.disabled = true; // cegah klik ganda
    });
  }

  // ------------------------------------------------------------------ favorit
  function initFavorites() {
    document.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-fav-url]');
      if (!btn || btn.dataset.busy) return;
      btn.dataset.busy = '1';
      try {
        const { ok, data } = await postJSON(btn.getAttribute('data-fav-url'));
        if (!ok) throw new Error(data.error || 'Gagal memperbarui favorit.');
        btn.classList.toggle('active', data.is_favorite);
        btn.setAttribute('aria-pressed', data.is_favorite ? 'true' : 'false');
        btn.classList.remove('pop'); void btn.offsetWidth; btn.classList.add('pop');
        toast(data.is_favorite ? 'Ditambahkan ke favorit.' : 'Dihapus dari favorit.', 'success');
        // Bila sedang memfilter favorit, segarkan daftar agar konsisten.
        const fav = $('#favToggle');
        if (fav && fav.checked && window.__msRefresh) window.__msRefresh();
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        delete btn.dataset.busy;
      }
    });
  }

  // ------------------------------------------------------------------ pencarian, filter, urutan
  function initFilters() {
    const form = $('#filterForm');
    if (!form) return;
    const results = $('#notesResults');
    const q = $('#searchInput');
    const modeSingle = $('#modeSingle');
    const groupSingle = $('#groupSingle');
    const groupRange = $('#groupRange');
    const catInput = $('#categoryInput');
    let controller = null;
    let timer = null;

    function syncMode() {
      const single = modeSingle.checked;
      groupSingle.classList.toggle('d-none', !single);
      groupRange.classList.toggle('d-none', single);
      // input yang tidak aktif dinonaktifkan agar tidak ikut terkirim
      $$('input', groupSingle).forEach((i) => { i.disabled = !single; });
      $$('input', groupRange).forEach((i) => { i.disabled = single; });
    }

    function updateBadge() {
      const val = (n) => { const el = form.elements[n]; return el && !el.disabled && el.value; };
      const count = (val('date') || val('start') || val('end') ? 1 : 0) + (val('time_from') || val('time_to') ? 1 : 0);
      const btn = $('.ms-filter-btn');
      let badge = $('.ms-badge-dot', btn);
      if (count && !badge) { badge = document.createElement('span'); badge.className = 'ms-badge-dot'; btn.appendChild(badge); }
      if (badge) { if (count) badge.textContent = count; else badge.remove(); }
    }

    function params() {
      const fd = new FormData(form);
      const p = new URLSearchParams();
      for (const [k, v] of fd.entries()) {
        if (k === 'date_mode' || k === 'csrf_token' || v === '') continue;
        p.append(k, v);
      }
      if (p.get('sort') === 'newest') p.delete('sort');
      return p;
    }

    async function refresh() {
      clearTimeout(timer);
      syncMode(); updateBadge();
      const qs = params().toString();
      const url = qs ? `${location.pathname}?${qs}` : location.pathname;
      if (controller) controller.abort();
      controller = new AbortController();
      results.style.opacity = '.55';
      try {
        const res = await fetch(url, {
          headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin', signal: controller.signal,
        });
        if (!res.ok) throw new Error('bad response');
        results.innerHTML = await res.text();
        history.replaceState(null, '', url);
        icons();
      } catch (err) {
        if (err.name === 'AbortError') return;
        location.href = url; // fallback: muat halaman penuh
      } finally {
        results.style.opacity = '';
      }
    }
    window.__msRefresh = refresh;

    function clearAll() {
      q.value = '';
      ['date', 'start', 'end', 'time_from', 'time_to'].forEach((n) => { form.elements[n].value = ''; });
      catInput.value = ''; $('#favToggle').checked = false;
      $$('.ms-chip[data-category]').forEach((c) => c.classList.toggle('active', c.dataset.category === ''));
      refresh();
    }

    q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(refresh, 300); });
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      refresh();
      const toggle = $('.ms-filter-btn');
      bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
    });
    $('#sortSelect').addEventListener('change', refresh);
    $('#favToggle').addEventListener('change', refresh);
    modeSingle.addEventListener('change', syncMode);
    $('#modeRange').addEventListener('change', syncMode);

    $('#filterReset').addEventListener('click', () => {
      ['date', 'start', 'end', 'time_from', 'time_to'].forEach((n) => { form.elements[n].value = ''; });
      refresh();
      bootstrap.Dropdown.getOrCreateInstance($('.ms-filter-btn')).hide();
    });

    $$('.ms-chip[data-category]').forEach((chip) => {
      chip.addEventListener('click', (e) => {
        e.preventDefault();
        catInput.value = chip.dataset.category;
        $$('.ms-chip[data-category]').forEach((c) => c.classList.toggle('active', c === chip));
        refresh();
      });
    });

    results.addEventListener('click', (e) => {
      if (e.target.closest('#clearAll, #clearAllEmpty')) clearAll();
    });

    // Rentang tanggal: selesai tidak boleh sebelum mulai
    form.elements.start.addEventListener('change', () => { form.elements.end.min = form.elements.start.value; });

    syncMode();
  }

  // ------------------------------------------------------------------ form catatan: validasi, autosave, draf
  function initNoteForm() {
    const form = $('#noteForm');
    if (!form) return;
    const title = $('#noteTitle');
    const content = $('#noteContent');
    const category = $('#noteCategory');
    const count = $('#charCount');
    const status = $('#saveStatus');
    const titleError = $('#titleError');
    const autosaveUrl = form.dataset.autosaveUrl;
    const draftKey = form.dataset.draftKey;
    let saveTimer = null;
    let saving = false;
    let queued = false;
    let dirty = false;
    let submitting = false;

    const updateCount = () => { count.textContent = content.value.length.toLocaleString('id-ID'); };
    updateCount();

    function setStatus(kind, html) {
      status.className = `ms-save-status ${kind}`;
      status.innerHTML = html;
      icons();
    }

    function validateTitle() {
      if (!title.value.trim()) {
        title.classList.add('is-invalid');
        titleError.textContent = 'Judul wajib diisi.';
        return false;
      }
      title.classList.remove('is-invalid');
      titleError.textContent = '';
      return true;
    }

    // ----- autosave (halaman edit)
    async function autosave() {
      if (!autosaveUrl || submitting) return;
      if (!title.value.trim()) { setStatus('error', '<i data-lucide="circle-alert"></i> Isi judul agar bisa disimpan'); return; }
      if (saving) { queued = true; return; }
      saving = true; queued = false;
      setStatus('saving', '<i data-lucide="loader-2"></i> Menyimpan…');
      try {
        const { ok, data } = await postJSON(autosaveUrl, {
          title: title.value, content: content.value, category_id: category ? category.value : null,
        });
        if (!ok) throw new Error((data.errors && Object.values(data.errors)[0]) || data.error || 'Gagal menyimpan');
        dirty = false;
        setStatus('saved', `<i data-lucide="cloud-check"></i> Tersimpan pukul ${data.saved_at}`);
      } catch (err) {
        setStatus('error', '<i data-lucide="cloud-off"></i> Gagal menyimpan otomatis');
      } finally {
        saving = false;
        if (queued) autosave();
      }
    }

    // ----- draf lokal (halaman catatan baru)
    function saveDraft() {
      if (!draftKey) return;
      if (!title.value && !content.value) { store.del(draftKey); return; }
      store.set(draftKey, { title: title.value, content: content.value, category: category ? category.value : '' });
      setStatus('saved', '<i data-lucide="hard-drive"></i> Draf tersimpan di perangkat ini');
    }

    function onInput() {
      dirty = true;
      updateCount();
      if (title.value.trim()) { title.classList.remove('is-invalid'); titleError.textContent = ''; }
      if (autosaveUrl) {
        setStatus('saving', '<i data-lucide="pencil-line"></i> Mengetik…');
        clearTimeout(saveTimer); saveTimer = setTimeout(autosave, 1200);
      }
      if (draftKey) { clearTimeout(saveTimer); saveTimer = setTimeout(saveDraft, 500); }
    }
    [title, content, category].forEach((el) => el && el.addEventListener('input', onInput));
    if (category) category.addEventListener('change', onInput);

    if (draftKey) {
      const draft = store.get(draftKey);
      const banner = $('#draftBanner');
      if (title.value || content.value) {
        saveDraft(); // halaman dirender ulang karena galat validasi
      } else if (draft && (draft.title || draft.content) && banner) {
        banner.classList.remove('d-none');
        $('#draftRestore').addEventListener('click', () => {
          title.value = draft.title || ''; content.value = draft.content || '';
          if (category && draft.category) category.value = draft.category;
          banner.classList.add('d-none'); updateCount(); title.focus();
        });
        $('#draftDiscard').addEventListener('click', () => { store.del(draftKey); banner.classList.add('d-none'); });
      }
    }

    form.addEventListener('submit', (e) => {
      if (!validateTitle()) { e.preventDefault(); title.focus(); return; }
      if (submitting) { e.preventDefault(); return; }
      submitting = true; clearTimeout(saveTimer);
      if (draftKey) store.del(draftKey);
      const btn = $('#saveBtn'); btn.disabled = true;
    });

    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); form.requestSubmit(); }
    });

    window.addEventListener('beforeunload', (e) => {
      if (autosaveUrl && dirty && !submitting) { e.preventDefault(); e.returnValue = ''; }
    });
    // simpan segera saat tab disembunyikan agar tidak ada yang hilang
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && autosaveUrl && dirty) { clearTimeout(saveTimer); autosave(); }
    });
  }

  // ------------------------------------------------------------------ onboarding bertahap
  function initOnboarding() {
    const root = $('#onboarding');
    if (!root) return;
    const KEY = 'memospace:onboarding';
    const frames = {};
    $$('.ms-frame', root).forEach((f) => { frames[f.dataset.frame] = f; });
    const nameEl = $('#obName');
    const birthEl = $('#obBirth');
    let current = '1';
    let submitting = false;

    // Batas tanggal lahir: hari ini (waktu lokal perangkat)
    const t = new Date();
    birthEl.max = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;

    function show(id, { animate = true } = {}) {
      const from = frames[current];
      const to = frames[id];
      if (!to || from === to) return;
      const reveal = () => {
        from.hidden = true; from.classList.remove('ms-frame-out');
        to.hidden = false; to.classList.remove('ms-frame-in'); void to.offsetWidth; to.classList.add('ms-frame-in');
        current = id;
        const focusEl = to.querySelector('input'); if (focusEl) setTimeout(() => focusEl.focus(), 60);
        persist();
      };
      if (animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        from.classList.add('ms-frame-out'); setTimeout(reveal, 230);
      } else { reveal(); }
    }

    // Progres sementara tersimpan di perangkat (tanpa data sensitif).
    function persist() {
      if (submitting) return;
      store.set(KEY, { step: current === '2' ? '2' : '1', name: nameEl.value, birth: birthEl.value });
    }
    const saved = store.get(KEY);
    if (saved) {
      nameEl.value = saved.name || ''; birthEl.value = saved.birth || '';
      if (saved.step === '2' && nameEl.value.trim()) { frames['1'].hidden = true; frames['2'].hidden = false; current = '2'; }
    }
    nameEl.addEventListener('input', persist); birthEl.addEventListener('input', persist);
    (frames[current].querySelector('input') || nameEl).focus();

    function fieldError(id, msg) {
      const el = $(id); el.textContent = msg || '';
      const input = el.previousElementSibling && el.previousElementSibling.tagName === 'INPUT' ? el.previousElementSibling : null;
      if (input) input.classList.toggle('is-invalid', !!msg);
      if (msg) { const card = el.closest('.ms-frame'); card.classList.remove('ms-shake'); void card.offsetWidth; card.classList.add('ms-shake'); }
    }

    // ----- Frame 1
    async function next1() {
      const name = nameEl.value.trim().replace(/\s+/g, ' ');
      if (!name) return fieldError('#obNameError', 'Nama wajib diisi.');
      if (name.length > 100) return fieldError('#obNameError', 'Nama maksimal 100 karakter.');
      const { ok, data } = await postJSON(root.dataset.validateUrl, { step: 1, name });
      if (!ok || !data.ok) return fieldError('#obNameError', (data.errors && data.errors.name) || 'Nama tidak valid.');
      fieldError('#obNameError', ''); show('2');
    }
    $('#obNext1').addEventListener('click', next1);
    nameEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); next1(); } });
    nameEl.addEventListener('input', () => fieldError('#obNameError', ''));

    // ----- Frame 2
    async function finish(skipBirth) {
      if (submitting) return; // cegah identitas ganda dari klik berulang
      const name = nameEl.value.trim().replace(/\s+/g, ' ');
      const birth = skipBirth ? '' : birthEl.value;
      if (birth && birth > birthEl.max) return fieldError('#obBirthError', 'Tanggal lahir tidak boleh di masa depan.');
      submitting = true;
      const buttons = $$('#onboarding button'); buttons.forEach((b) => { b.disabled = true; });
      $('#obNext2').innerHTML = '<span class="spinner-border spinner-border-sm"></span> Menyiapkan…';
      try {
        const { ok, data } = await postJSON(root.dataset.completeUrl, { name, birth_date: birth });
        if (ok && data.ok) { store.del(KEY); window.location.href = data.redirect; return; }
        submitting = false; buttons.forEach((b) => { b.disabled = false; }); $('#obNext2').textContent = 'Next';
        const errs = data.errors || {};
        if (errs.name) { show('1'); setTimeout(() => fieldError('#obNameError', errs.name), 300); }
        else if (errs.birth_date) fieldError('#obBirthError', errs.birth_date);
        else $('#obSubmitError').textContent = data.error || 'Terjadi kesalahan. Muat ulang halaman lalu coba lagi.';
      } catch (_) {
        submitting = false; buttons.forEach((b) => { b.disabled = false; }); $('#obNext2').textContent = 'Next';
        $('#obSubmitError').textContent = 'Tidak bisa terhubung ke server. Periksa koneksimu.';
      }
    }
    $('#obNext2').addEventListener('click', () => finish(false));
    $('#obSkip').addEventListener('click', () => { birthEl.value = ''; finish(true); });
    $('#obBack2').addEventListener('click', () => show('1'));
    birthEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); finish(false); } });
    birthEl.addEventListener('input', () => fieldError('#obBirthError', ''));

    // ----- Pemulihan
    const codeEl = $('#obCode');
    $('#obOpenRecover').addEventListener('click', () => show('recover'));
    $('#obBackRecover').addEventListener('click', () => show('1'));
    codeEl.addEventListener('input', () => {
      const raw = codeEl.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 16);
      codeEl.value = raw.replace(/(.{4})(?=.)/g, '$1-');
      fieldError('#obCodeError', '');
    });
    async function recover() {
      if (submitting) return;
      if (codeEl.value.replace(/-/g, '').length !== 16) return fieldError('#obCodeError', 'Kode terdiri dari 16 karakter.');
      submitting = true; $('#obRecover').disabled = true;
      const { ok, data } = await postJSON(root.dataset.recoverUrl, { code: codeEl.value });
      if (ok && data.ok) { store.del(KEY); window.location.href = data.redirect; return; }
      submitting = false; $('#obRecover').disabled = false;
      fieldError('#obCodeError', data.error || 'Kode pemulihan tidak valid.');
    }
    $('#obRecover').addEventListener('click', recover);
    codeEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); recover(); } });
  }
})();
