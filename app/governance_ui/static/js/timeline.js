/** Timeline interaction — scroll-to-screenshot on replay link */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-replay-link]').forEach((el) => {
    el.addEventListener('click', (e) => {
      const target = el.getAttribute('data-replay-link');
      if (!target) return;
      const node = document.querySelector(target);
      if (node) {
        e.preventDefault();
        node.scrollIntoView({ behavior: 'smooth', block: 'center' });
        node.classList.add('ring-2', 'ring-indigo-400');
        setTimeout(() => node.classList.remove('ring-2', 'ring-indigo-400'), 1500);
      }
    });
  });
});
