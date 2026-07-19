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
    btn.addEventListener('click', () => {
      const key = 'favs';
      const current = JSON.parse(localStorage.getItem(key) || '[]');
      const value = btn.getAttribute('data-fav');
      if (!current.includes(value)) current.push(value);
      localStorage.setItem(key, JSON.stringify(current));
      btn.textContent = 'Saved';
      setTimeout(() => (btn.textContent = '☆ Add to favourites'), 1200);
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
