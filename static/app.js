(function(){
  const copyButtons = document.querySelectorAll('[data-copy]');
  copyButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
      const value = btn.getAttribute('data-copy') || '';
      try {
        await navigator.clipboard.writeText(value);
        btn.textContent = 'Copied';
        setTimeout(() => (btn.textContent = 'Copy'), 1200);
      } catch (e) {
        alert('Copy failed');
      }
    });
  });

  const favButtons = document.querySelectorAll('[data-fav]');
  favButtons.forEach(btn => {
    const originalHtml = btn.innerHTML;
    btn.addEventListener('click', () => {
      const key = 'favs';
      const current = JSON.parse(localStorage.getItem(key) || '[]');
      const value = btn.getAttribute('data-fav');
      if (!current.includes(value)) current.push(value);
      localStorage.setItem(key, JSON.stringify(current));

      btn.innerHTML = `
        <span class="receipt-action-graphic" aria-hidden="true">
          <svg viewBox="0 0 64 64" role="img" focusable="false">
            <path d="M32 11.5l5.4 11 12.2 1.8-8.8 8.5 2.1 12.1L32 39.2l-10.9 5.7 2.1-12.1-8.8-8.5 12.2-1.8L32 11.5z" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round"/>
          </svg>
        </span>
        <span class="receipt-action-label"><span>Saved</span><span>✓</span></span>
      `;
      setTimeout(() => (btn.innerHTML = originalHtml), 1200);
    });
  });


  const extraActionButtons = document.querySelectorAll('.receipt-action-reverse, .receipt-action-share');
  extraActionButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const label = btn.getAttribute('aria-label') || 'Action';
      btn.classList.add('action-pulse');
      setTimeout(() => btn.classList.remove('action-pulse'), 350);
      console.log(label);
    });
  });

  const contactSearch = document.getElementById('contactSearch');
  const contactList = document.getElementById('contactList');
  if (contactSearch && contactList) {
    contactSearch.addEventListener('input', () => {
      const q = contactSearch.value.toLowerCase();
      [...contactList.children].forEach(node => {
        const t = node.textContent.toLowerCase();
        node.style.display = t.includes(q) ? '' : 'none';
      });
    });
  }


  function persistFormState(form) {
    if (!form) return;
    const fields = Array.from(form.querySelectorAll('input[name], textarea[name], select[name]'));
    if (!fields.length) return;

    const storageKey = `form:${window.location.pathname}:${form.getAttribute('action') || 'self'}:${form.getAttribute('id') || form.getAttribute('class') || 'form'}`;

    const loadState = () => {
      try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return;
        const state = JSON.parse(raw);
        fields.forEach(field => {
          const name = field.name;
          if (!(name in state)) return;
          const value = state[name];
          if (field.type === 'checkbox') {
            field.checked = !!value;
          } else if (field.type === 'radio') {
            field.checked = value === field.value;
          } else {
            field.value = value;
          }
        });
      } catch (e) {}
    };

    const saveState = () => {
      try {
        const state = {};
        fields.forEach(field => {
          if (!field.name) return;
          if (field.type === 'checkbox') {
            state[field.name] = field.checked;
          } else if (field.type === 'radio') {
            if (field.checked) state[field.name] = field.value;
          } else {
            state[field.name] = field.value;
          }
        });
        localStorage.setItem(storageKey, JSON.stringify(state));
      } catch (e) {}
    };

    loadState();
    fields.forEach(field => {
      field.addEventListener('input', saveState);
      field.addEventListener('change', saveState);
    });

    form.addEventListener('reset', () => {
      try {
        localStorage.removeItem(storageKey);
      } catch (e) {}
    });
  }

  document.querySelectorAll('form').forEach(persistFormState);

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js').catch(() => {});
    });
  }
})();
