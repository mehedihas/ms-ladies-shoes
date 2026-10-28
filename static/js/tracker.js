// Order modal, notes counter and live tracking refresh.
(function () {
  var m = document.getElementById('orderModal');
  document.querySelectorAll('[data-open-order]').forEach(function (b) {
    b.addEventListener('click', function () { m.classList.add('open'); });
  });
  document.querySelectorAll('[data-close-order]').forEach(function (b) {
    b.addEventListener('click', function () { m.classList.remove('open'); });
  });
  var notes = document.getElementById('notes'), cnt = document.getElementById('notesCount');
  if (notes && cnt) notes.addEventListener('input', function () { cnt.textContent = notes.value.length; });
  var live = document.getElementById('liveTracker');
  if (live && live.dataset.status !== 'Received') {
    setInterval(function () {
      if (!document.hidden && !document.querySelector('form :focus')) location.reload();
    }, 30000);
  }
})();
