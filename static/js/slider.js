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

  // Global Full-Screen Image Lightbox Viewer with Zoom & Pan Support
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
      '<div class="lightbox-img-container">' +
        '<img class="lightbox-img" src="" alt="Full Product Image">' +
      '</div>' +
      '<div class="lightbox-toolbar">' +
        '<button class="lightbox-zoom-btn zoom-out" type="button" aria-label="Zoom Out" title="Zoom Out (-)">' +
          '<svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line></svg>' +
        '</button>' +
        '<button class="lightbox-zoom-value" type="button" aria-label="Reset Zoom" title="Click to reset (100%)">100%</button>' +
        '<button class="lightbox-zoom-btn zoom-in" type="button" aria-label="Zoom In" title="Zoom In (+)">' +
          '<svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>' +
        '</button>' +
        '<div class="lightbox-counter"></div>' +
      '</div>' +
    '</div>';
  document.body.appendChild(lightbox);

  var lbImg = lightbox.querySelector('.lightbox-img');
  var lbClose = lightbox.querySelector('.lightbox-close');
  var lbPrev = lightbox.querySelector('.lightbox-nav.prev');
  var lbNext = lightbox.querySelector('.lightbox-nav.next');
  var lbCounter = lightbox.querySelector('.lightbox-counter');
  var lbZoomIn = lightbox.querySelector('.lightbox-zoom-btn.zoom-in');
  var lbZoomOut = lightbox.querySelector('.lightbox-zoom-btn.zoom-out');
  var lbZoomValue = lightbox.querySelector('.lightbox-zoom-value');

  var currentGallery = [];
  var currentIndex = 0;
  var activeSlider = null;

  // Zoom & Pan state
  var zoomScale = 1;
  var zoomX = 0;
  var zoomY = 0;
  var isDragging = false;
  var dragStartX = 0;
  var dragStartY = 0;

  function applyTransform(animate) {
    if (animate) {
      lbImg.style.transition = 'transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.18s ease';
    } else {
      lbImg.style.transition = 'none';
    }
    lbImg.style.transform = 'translate(' + zoomX + 'px, ' + zoomY + 'px) scale(' + zoomScale + ')';
  }

  function updateZoomUI() {
    if (lbZoomValue) {
      lbZoomValue.textContent = Math.round(zoomScale * 100) + '%';
      if (zoomScale > 1.05) {
        lbZoomValue.classList.add('is-zoomed');
      } else {
        lbZoomValue.classList.remove('is-zoomed');
      }
    }
    if (zoomScale > 1.05) {
      lbImg.style.cursor = isDragging ? 'grabbing' : 'grab';
    } else {
      lbImg.style.cursor = 'zoom-in';
    }
  }

  function setZoom(newScale, animate) {
    var minZoom = 0.6;
    var maxZoom = 4.0;
    newScale = Math.max(minZoom, Math.min(maxZoom, Math.round(newScale * 100) / 100));
    zoomScale = newScale;
    if (zoomScale <= 1.02) {
      zoomScale = 1;
      zoomX = 0;
      zoomY = 0;
    } else {
      var maxPanX = (window.innerWidth * (zoomScale - 1)) / 2 + 60;
      var maxPanY = (window.innerHeight * (zoomScale - 1)) / 2 + 60;
      zoomX = Math.max(-maxPanX, Math.min(maxPanX, zoomX));
      zoomY = Math.max(-maxPanY, Math.min(maxPanY, zoomY));
    }
    applyTransform(animate !== false);
    updateZoomUI();
  }

  function resetZoom() {
    zoomScale = 1;
    zoomX = 0;
    zoomY = 0;
    isDragging = false;
    applyTransform(true);
    updateZoomUI();
  }

  function renderLightboxImage(animate) {
    if (!currentGallery.length) return;
    var item = currentGallery[currentIndex];
    resetZoom();
    
    if (animate) {
      lbImg.style.opacity = '0';
      lbImg.style.transform = 'scale(0.96)';
      setTimeout(function () {
        lbImg.src = item.src;
        lbImg.alt = item.alt || 'Full Product Image';
        lbImg.style.opacity = '1';
        resetZoom();
      }, 120);
    } else {
      lbImg.src = item.src;
      lbImg.alt = item.alt || 'Full Product Image';
      lbImg.style.opacity = '1';
      resetZoom();
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
    resetZoom();
  }

  // Zoom Button Listeners
  lbZoomIn.addEventListener('click', function (e) {
    e.stopPropagation();
    setZoom(zoomScale + 0.35, true);
  });

  lbZoomOut.addEventListener('click', function (e) {
    e.stopPropagation();
    setZoom(zoomScale - 0.35, true);
  });

  lbZoomValue.addEventListener('click', function (e) {
    e.stopPropagation();
    resetZoom();
  });

  // Double click toggles zoom
  lbImg.addEventListener('dblclick', function (e) {
    e.preventDefault();
    e.stopPropagation();
    if (zoomScale > 1.2) {
      resetZoom();
    } else {
      setZoom(2.2, true);
    }
  });

  // Mouse wheel zoom
  lightbox.addEventListener('wheel', function (e) {
    if (!lightbox.classList.contains('open')) return;
    if (e.target.closest('.lightbox-toolbar, .lightbox-close, .lightbox-nav')) return;
    e.preventDefault();
    var delta = e.deltaY < 0 ? 0.25 : -0.25;
    setZoom(zoomScale + delta, false);
  }, { passive: false });

  // Mouse drag panning when zoomed
  lbImg.addEventListener('mousedown', function (e) {
    if (zoomScale > 1.05) {
      e.preventDefault();
      isDragging = true;
      dragStartX = e.clientX - zoomX;
      dragStartY = e.clientY - zoomY;
      lbImg.style.cursor = 'grabbing';
      lbImg.style.transition = 'none';
    }
  });

  window.addEventListener('mousemove', function (e) {
    if (isDragging && zoomScale > 1.05) {
      zoomX = e.clientX - dragStartX;
      zoomY = e.clientY - dragStartY;
      var maxPanX = (window.innerWidth * (zoomScale - 1)) / 2 + 80;
      var maxPanY = (window.innerHeight * (zoomScale - 1)) / 2 + 80;
      zoomX = Math.max(-maxPanX, Math.min(maxPanX, zoomX));
      zoomY = Math.max(-maxPanY, Math.min(maxPanY, zoomY));
      applyTransform(false);
    }
  });

  window.addEventListener('mouseup', function () {
    if (isDragging) {
      isDragging = false;
      updateZoomUI();
    }
  });

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
    if (e.target === lightbox || e.target.classList.contains('lightbox-content') || e.target.classList.contains('lightbox-img-container')) {
      closeLightbox();
    }
  });

  // Keyboard navigation & zoom shortcuts
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
    } else if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      setZoom(zoomScale + 0.35, true);
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault();
      setZoom(zoomScale - 0.35, true);
    } else if (e.key === '0' || e.key.toLowerCase() === 'r') {
      e.preventDefault();
      resetZoom();
    }
  });

  // Touch Swipe & Pinch-to-zoom support for mobile
  var pinchDist0 = null;
  var pinchScale0 = 1;
  var touchX0 = null;
  var touchY0 = null;
  var touchStartX = 0;
  var touchStartY = 0;
  var isTouchPanning = false;

  lightbox.addEventListener('touchstart', function (e) {
    if (e.touches.length === 2) {
      var dx = e.touches[0].clientX - e.touches[1].clientX;
      var dy = e.touches[0].clientY - e.touches[1].clientY;
      pinchDist0 = Math.hypot(dx, dy);
      pinchScale0 = zoomScale;
    } else if (e.touches.length === 1) {
      touchX0 = e.touches[0].clientX;
      touchY0 = e.touches[0].clientY;
      if (zoomScale > 1.05) {
        isTouchPanning = true;
        touchStartX = e.touches[0].clientX - zoomX;
        touchStartY = e.touches[0].clientY - zoomY;
        lbImg.style.transition = 'none';
      }
    }
  }, { passive: true });

  lightbox.addEventListener('touchmove', function (e) {
    if (e.touches.length === 2 && pinchDist0) {
      var dx = e.touches[0].clientX - e.touches[1].clientX;
      var dy = e.touches[0].clientY - e.touches[1].clientY;
      var dist = Math.hypot(dx, dy);
      var ratio = dist / pinchDist0;
      setZoom(pinchScale0 * ratio, false);
    } else if (e.touches.length === 1 && isTouchPanning && zoomScale > 1.05) {
      zoomX = e.touches[0].clientX - touchStartX;
      zoomY = e.touches[0].clientY - touchStartY;
      var maxPanX = (window.innerWidth * (zoomScale - 1)) / 2 + 80;
      var maxPanY = (window.innerHeight * (zoomScale - 1)) / 2 + 80;
      zoomX = Math.max(-maxPanX, Math.min(maxPanX, zoomX));
      zoomY = Math.max(-maxPanY, Math.min(maxPanY, zoomY));
      applyTransform(false);
    }
  }, { passive: true });

  lightbox.addEventListener('touchend', function (e) {
    if (e.touches.length < 2) {
      pinchDist0 = null;
    }
    if (e.touches.length === 0) {
      if (isTouchPanning) {
        isTouchPanning = false;
        applyTransform(true);
      } else if (zoomScale <= 1.05) {
        if (touchX0 !== null && e.changedTouches.length) {
          var dx = e.changedTouches[0].clientX - touchX0;
          var dy = e.changedTouches[0].clientY - touchY0;
          if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
            navigateLightbox(dx < 0 ? 1 : -1);
          }
        }
      }
      touchX0 = null;
      touchY0 = null;
    }
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
