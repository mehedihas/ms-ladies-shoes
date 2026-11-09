// Modern Touch-Enabled Carousel & Image Lightbox System
document.addEventListener('DOMContentLoaded', function () {
  // Initialize all sliders
  document.querySelectorAll('.slider').forEach(function (s) {
    var track = s.querySelector('.slide-items');
    if (!track) return;

    var slides = Array.from(track.children);
    var n = slides.length;
    var i = 0;
    var dots = s.querySelector('.dots') || (s.parentElement ? s.parentElement.querySelector('.dots') : null);
    var prevBtn = s.querySelector('.nav-arrow.prev');
    var nextBtn = s.querySelector('.nav-arrow.next');
    var timer = null;

    // Create dots if container exists
    if (dots && n > 1) {
      dots.innerHTML = '';
      if (dots.parentElement && dots.parentElement.classList.contains('slider-dots-wrap')) {
        dots.parentElement.style.display = '';
      }
      dots.style.display = '';
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
      if (dots.parentElement && dots.parentElement.classList.contains('slider-dots-wrap')) {
        dots.parentElement.style.display = 'none';
      }
    }

    function show(x) {
      i = (x + n) % n;
      track.style.transform = 'translateX(-' + i * 100 + '%)';
      s.setAttribute('data-active-index', i);

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
    }

    function start() {
      if (n > 1) {
        timer = setInterval(function () {
          if (!document.body.classList.contains('lightbox-active')) {
            show(i + 1);
          }
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

  // Global Full-Screen Image Lightbox Viewer with Previous/Next Navigation
  var lightbox = document.createElement('div');
  lightbox.id = 'imageLightbox';
  lightbox.className = 'lightbox-overlay';
  lightbox.innerHTML = 
    '<div class="lightbox-content">' +
      '<button class="lightbox-close" type="button" aria-label="Close image viewer" title="Close (Esc)">&times;</button>' +
      '<button class="lightbox-nav prev" type="button" aria-label="Previous image" title="Previous image (Left Arrow)">' +
        '<svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"></polyline></svg>' +
      '</button>' +
      '<button class="lightbox-nav next" type="button" aria-label="Next image" title="Next image (Right Arrow)">' +
        '<svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>' +
      '</button>' +
      '<img class="lightbox-img" src="" alt="Full Product Image">' +
      '<div class="lightbox-counter"></div>' +
    '</div>';
  document.body.appendChild(lightbox);

  var lbImg = lightbox.querySelector('.lightbox-img');
  var lbClose = lightbox.querySelector('.lightbox-close');
  var lbPrev = lightbox.querySelector('.lightbox-nav.prev');
  var lbNext = lightbox.querySelector('.lightbox-nav.next');
  var lbCounter = lightbox.querySelector('.lightbox-counter');

  var currentGallery = [];
  var currentIndex = 0;
  var activeSlider = null;

  function renderLightboxImage(animate) {
    if (!currentGallery.length) return;
    var item = currentGallery[currentIndex];
    
    if (animate) {
      lbImg.style.opacity = '0';
      lbImg.style.transform = 'scale(0.96)';
      setTimeout(function () {
        lbImg.src = item.src;
        lbImg.alt = item.alt || 'Full Product Image';
        lbImg.style.opacity = '1';
        lbImg.style.transform = 'scale(1)';
      }, 120);
    } else {
      lbImg.src = item.src;
      lbImg.alt = item.alt || 'Full Product Image';
      lbImg.style.opacity = '1';
      lbImg.style.transform = 'scale(1)';
    }

    if (currentGallery.length > 1) {
      lbPrev.style.display = 'flex';
      lbNext.style.display = 'flex';
      if (lbCounter) {
        lbCounter.style.display = 'block';
        lbCounter.textContent = (currentIndex + 1) + ' / ' + currentGallery.length;
      }
    } else {
      lbPrev.style.display = 'none';
      lbNext.style.display = 'none';
      if (lbCounter) lbCounter.style.display = 'none';
    }

    // Keep associated background slider in sync
    if (activeSlider) {
      activeSlider.dispatchEvent(new CustomEvent('jump', { detail: currentIndex }));
    }
  }

  function navigateLightbox(dir) {
    if (currentGallery.length <= 1) return;
    currentIndex = (currentIndex + dir + currentGallery.length) % currentGallery.length;
    renderLightboxImage(true);
  }

  function openLightbox(items, startIndex, slider) {
    if (!items || !items.length) return;
    currentGallery = items;
    currentIndex = Math.max(0, Math.min(startIndex || 0, currentGallery.length - 1));
    activeSlider = slider || null;

    renderLightboxImage(false);
    lightbox.classList.add('open');
    document.body.style.overflow = 'hidden';
    document.body.classList.add('lightbox-active');
  }

  function closeLightbox() {
    lightbox.classList.remove('open');
    document.body.style.overflow = '';
    document.body.classList.remove('lightbox-active');
  }

  lbPrev.addEventListener('click', function (e) {
    e.stopPropagation();
    navigateLightbox(-1);
  });

  lbNext.addEventListener('click', function (e) {
    e.stopPropagation();
    navigateLightbox(1);
  });

  lbClose.addEventListener('click', function (e) {
    e.stopPropagation();
    closeLightbox();
  });

  lightbox.addEventListener('click', function (e) {
    if (e.target === lightbox || e.target.classList.contains('lightbox-content')) {
      closeLightbox();
    }
  });

  // Keyboard navigation support
  document.addEventListener('keydown', function (e) {
    if (!lightbox.classList.contains('open')) return;
    if (e.key === 'ArrowRight' || e.key === 'Right') {
      e.preventDefault();
      navigateLightbox(1);
    } else if (e.key === 'ArrowLeft' || e.key === 'Left') {
      e.preventDefault();
      navigateLightbox(-1);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeLightbox();
    }
  });

  // Touch Swipe support for lightbox on mobile
  var lbTouchX0 = null;
  var lbTouchY0 = null;
  lightbox.addEventListener('touchstart', function (e) {
    if (e.touches.length === 1) {
      lbTouchX0 = e.touches[0].clientX;
      lbTouchY0 = e.touches[0].clientY;
    }
  }, { passive: true });

  lightbox.addEventListener('touchend', function (e) {
    if (lbTouchX0 !== null && e.changedTouches.length) {
      var dx = e.changedTouches[0].clientX - lbTouchX0;
      var dy = e.changedTouches[0].clientY - lbTouchY0;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
        if (dx < 0) {
          navigateLightbox(1);
        } else {
          navigateLightbox(-1);
        }
      }
    }
    lbTouchX0 = null;
    lbTouchY0 = null;
  });

  // Attach zoom lightbox listener to all product images
  document.addEventListener('click', function (e) {
    var img = e.target.closest('img[data-zoom-src], .zoomable-img');
    if (img) {
      e.preventDefault();

      var slider = img.closest('.slider');
      var galleryWrap = img.closest('.product-gallery-wrap');
      var container = slider || galleryWrap;

      var items = [];
      if (container) {
        var imgs = container.querySelectorAll('.slide-items img[data-zoom-src], .slide-items img, img[data-zoom-src], .zoomable-img');
        var seen = new Set();
        imgs.forEach(function (el) {
          if (container.querySelector('.slide-items') && !el.closest('.slide-items')) {
            return;
          }
          var src = el.getAttribute('data-zoom-src') || el.src;
          if (src && !seen.has(src)) {
            seen.add(src);
            items.push({
              src: src,
              alt: el.alt || ''
            });
          }
        });
      }

      var currentSrc = img.getAttribute('data-zoom-src') || img.src;
      if (items.length === 0) {
        items.push({ src: currentSrc, alt: img.alt || '' });
      }

      var idx = items.findIndex(function (it) {
        return it.src === currentSrc;
      });
      if (idx === -1) {
        if (slider && slider.getAttribute('data-active-index')) {
          idx = parseInt(slider.getAttribute('data-active-index'), 10) || 0;
        } else {
          idx = 0;
        }
      }

      openLightbox(items, idx, slider);
    }
  });
});
