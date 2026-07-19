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



  const shareButtons = document.querySelectorAll('[data-share-url]');
  shareButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
      const url = btn.getAttribute('data-share-url') || window.location.href;
      try {
        if (navigator.share) {
          await navigator.share({ title: document.title, url });
          return;
        }
      } catch (e) {
        // fall through to copy
      }
      try {
        await navigator.clipboard.writeText(url);
        const prev = btn.innerHTML;
        btn.innerHTML = '<span aria-hidden="true">Copied</span>';
        setTimeout(() => (btn.innerHTML = prev), 1000);
      } catch (e) {
        alert('Share failed');
      }
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

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js').catch(() => {});
    });
  }
})();
