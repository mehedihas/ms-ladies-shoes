// Modern Touch-Enabled Carousel & Image Lightbox System
document.addEventListener('DOMContentLoaded', function () {
  // Initialize all sliders
  document.querySelectorAll('.slider').forEach(function (s) {
    var track = s.querySelector('.slide-items');
    if (!track) return;

    var slides = Array.from(track.children);
    var n = slides.length;
    var i = 0;
    var dots = s.querySelector('.dots');
    var prevBtn = s.querySelector('.nav-arrow.prev');
    var nextBtn = s.querySelector('.nav-arrow.next');
    var timer = null;

    // Create dots if container exists
    if (dots && n > 1) {
      dots.innerHTML = '';
      for (var k = 0; k < n; k++) {
        (function (index) {
          var dot = document.createElement('i');
          dot.addEventListener('click', function (e) {
            e.stopPropagation();
            show(index);
            resetTimer();
          });
          dots.appendChild(dot);
        })(k);
      }
    } else if (dots && n <= 1) {
      dots.style.display = 'none';
    }

    function show(x) {
      i = (x + n) % n;
      track.style.transform = 'translateX(-' + i * 100 + '%)';

      // Update dots
      if (dots && dots.children.length) {
        Array.from(dots.children).forEach(function (d, j) {
          d.className = j === i ? 'on' : '';
        });
      }

      // Sync product page thumbnails if present
      var thumbs = document.querySelectorAll('.slider-thumb-item');
      if (thumbs.length) {
        thumbs.forEach(function (t, j) {
          if (j === i) t.classList.add('active');
          else t.classList.remove('active');
        });
      }

      // Handle video play/pause
      slides.forEach(function (el, j) {
        if (el.tagName === 'VIDEO') {
          if (j === i) {
            el.play().catch(function () {});
          } else {
            el.pause();
          }
        }
      });
    }

    function start() {
      if (n > 1) {
        timer = setInterval(function () {
          show(i + 1);
        }, 4500);
      }
    }

    function stop() {
      if (timer) clearInterval(timer);
    }

    function resetTimer() {
      stop();
      start();
    }

    // Prev / Next button listeners
    if (prevBtn) {
      prevBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        show(i - 1);
        resetTimer();
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        show(i + 1);
        resetTimer();
      });
    }

    // Custom jump event listener
    s.addEventListener('jump', function (e) {
      if (e.detail !== undefined) {
        show(e.detail);
        resetTimer();
      }
    });

    // Hover pause
    s.addEventListener('mouseenter', stop);
    s.addEventListener('mouseleave', start);

    // Touch Swipe support for mobile
    var x0 = null, y0 = null;
    s.addEventListener('touchstart', function (e) {
      x0 = e.touches[0].clientX;
      y0 = e.touches[0].clientY;
      stop();
    }, { passive: true });

    s.addEventListener('touchend', function (e) {
      if (x0 !== null && e.changedTouches.length) {
        var dx = e.changedTouches[0].clientX - x0;
        var dy = e.changedTouches[0].clientY - y0;
        if (Math.abs(dx) > 35 && Math.abs(dx) > Math.abs(dy)) {
          show(i + (dx < 0 ? 1 : -1));
        }
      }
      x0 = null;
      y0 = null;
      start();
    });

    show(0);
    start();
  });

  // Global Full-Screen Image Lightbox Viewer
  var lightbox = document.createElement('div');
  lightbox.id = 'imageLightbox';
  lightbox.className = 'lightbox-overlay';
  lightbox.innerHTML = 
    '<div class="lightbox-content">' +
      '<button class="lightbox-close">&times;</button>' +
      '<img class="lightbox-img" src="" alt="Zoom View">' +
    '</div>';
  document.body.appendChild(lightbox);

  var lbImg = lightbox.querySelector('.lightbox-img');
  var lbClose = lightbox.querySelector('.lightbox-close');

  function openLightbox(src) {
    if (!src) return;
    lbImg.src = src;
    lightbox.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeLightbox() {
    lightbox.classList.remove('open');
    document.body.style.overflow = '';
  }

  lbClose.addEventListener('click', closeLightbox);
  lightbox.addEventListener('click', function (e) {
    if (e.target === lightbox || e.target.classList.contains('lightbox-content')) {
      closeLightbox();
    }
  });

  // Attach zoom lightbox listener to all product images
  document.addEventListener('click', function (e) {
    var img = e.target.closest('img[data-zoom-src], .zoomable-img');
    if (img) {
      e.preventDefault();
      var src = img.getAttribute('data-zoom-src') || img.src;
      openLightbox(src);
    }
  });
});
