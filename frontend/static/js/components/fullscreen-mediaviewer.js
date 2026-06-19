class FullscreenMediaViewer {
    constructor() {
        this.overlay = null;
        this.image = null;
        this.wrapper = null;
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this.isDragging = false;
        this.startX = 0;
        this.startY = 0;
        this.lastX = 0;
        this.lastY = 0;

        this.init();
    }

    init() {
        this.overlay = document.getElementById('fullscreen-overlay');

        if (!this.overlay) {
            this.createOverlayElements();
            this.overlay = document.getElementById('fullscreen-overlay');
        }

        this.image = document.getElementById('fullscreen-image');
        this.wrapper = document.getElementById('fullscreen-image-wrapper');

        // Check if video element exists, if not create it
        this.video = document.getElementById('fullscreen-video');
        if (!this.video && this.wrapper) {
            this.video = document.createElement('video');
            this.video.id = 'fullscreen-video';
            this.video.controls = true;
            this.video.loop = true;
            this.video.style.display = 'none';
            this.video.style.width = '100%';
            this.video.style.height = '100%';
            this.video.style.objectFit = 'contain';
            this.wrapper.appendChild(this.video);
        }

        this.activeElement = this.image; // Tracks whether currently showing image or video

        // Prevent default drag behaviors
        [this.image, this.video].forEach(el => {
            if (!el) return;
            el.addEventListener('dragstart', (e) => {
                e.preventDefault();
                return false;
            });
            el.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                return false;
            });
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.overlay.classList.contains('active')) {
                e.stopImmediatePropagation();
                this.close();
            }
        });

        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });

        this.wrapper.addEventListener('click', (e) => {
            if (e.target === this.wrapper) {
                this.close();
            }
            e.stopPropagation();
        });

        this.wrapper.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            this.zoom(delta, e.clientX, e.clientY);
        }, { passive: false });

        this.setupMouseEvents();
        this.setupTouchEvents();
    }

    createOverlayElements() {
        const overlay = document.createElement('div');
        overlay.id = 'fullscreen-overlay';
        overlay.innerHTML = `
            <div id="fullscreen-image-wrapper">
                <img id="fullscreen-image" src="" alt="" style="display: none;">
                <video id="fullscreen-video" src="" controls loop style="display: none; width: 100%; height: 100%; object-fit: contain;"></video>
            </div>
            <div class="fullscreen-close-hint">Press ESC or click outside the media to close</div>
        `;
        document.body.appendChild(overlay);
    }

    setupMouseEvents() {
        // We attach listeners to both, but logic will use activeElement
        [this.image, this.video].forEach(el => {
            if (!el) return;
            el.addEventListener('mousedown', (e) => {
                // Don't interfere with video controls
                if (this.activeElement === this.video && e.offsetY > this.video.clientHeight - 50) return;

                e.preventDefault();
                if (this.scale > 1) {
                    this.startDrag(e.clientX, e.clientY);
                }
            });
        });

        document.addEventListener('mousemove', (e) => {
            if (this.isDragging) {
                this.drag(e.clientX, e.clientY);
            }
        });

        document.addEventListener('mouseup', () => {
            this.stopDrag();
        });
    }

    setupTouchEvents() {
        let touchDistance = 0;

        const handleTouchStart = (e) => {
            if (e.touches.length === 1) {
                if (this.scale > 1) {
                    this.startDrag(e.touches[0].clientX, e.touches[0].clientY);
                }
            } else if (e.touches.length === 2) {
                e.preventDefault();
                const dx = e.touches[0].clientX - e.touches[1].clientX;
                const dy = e.touches[0].clientY - e.touches[1].clientY;
                touchDistance = Math.sqrt(dx * dx + dy * dy);
            }
        };

        const handleTouchMove = (e) => {
            if (e.touches.length === 1 && this.isDragging) {
                e.preventDefault();
                this.drag(e.touches[0].clientX, e.touches[0].clientY);
            } else if (e.touches.length === 2) {
                e.preventDefault();
                const dx = e.touches[0].clientX - e.touches[1].clientX;
                const dy = e.touches[0].clientY - e.touches[1].clientY;
                const newDistance = Math.sqrt(dx * dx + dy * dy);

                if (touchDistance > 0) {
                    const delta = newDistance / touchDistance;
                    const centerX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
                    const centerY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
                    this.zoom(delta, centerX, centerY);
                }

                touchDistance = newDistance;
            }
        };

        const handleTouchEnd = (e) => {
            if (e.touches.length === 0) {
                this.stopDrag();
                touchDistance = 0;
            }
        };

        [this.image, this.video].forEach(el => {
            if (!el) return;
            el.addEventListener('touchstart', handleTouchStart, { passive: false });
            el.addEventListener('touchmove', handleTouchMove, { passive: false });
            el.addEventListener('touchend', handleTouchEnd);
        });
    }

    open(source, isVideo = false) {
        this.overlay.classList.add('active');
        this.reset();

        if (isVideo && this.video) {
            this.image.style.display = 'none';
            this.video.style.display = 'block';
            this.video.src = source;
            this.activeElement = this.video;
            this.image.src = ''; // Clear image source

            // Auto play video
            this.video.play().catch(e => console.log('Auto-play failed:', e));
        } else {
            if (this.video) {
                this.video.style.display = 'none';
                this.video.pause();
                this.video.src = ''; // Clear video source
            }
            this.image.style.display = 'block';
            this.image.src = source;
            this.activeElement = this.image;
        }

        // Wait for load to size
        const loadEvent = isVideo ? 'loadedmetadata' : 'onload';
        if (isVideo) {
            if (this.video) {
                this.video.onloadedmetadata = () => {
                    this.sizeImageToViewport();
                };
            }
        } else {
            this.image.onload = () => {
                this.sizeImageToViewport();
            };
        }

        document.body.style.overflow = 'hidden';
    }

    sizeImageToViewport() {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        let naturalWidth, naturalHeight;

        if (this.activeElement === this.video) {
            naturalWidth = this.video.videoWidth;
            naturalHeight = this.video.videoHeight;
        } else {
            naturalWidth = this.image.naturalWidth;
            naturalHeight = this.image.naturalHeight;
        }

        const imageRatio = naturalWidth / naturalHeight;
        const viewportRatio = viewportWidth / viewportHeight;

        if (viewportRatio > imageRatio) {
            this.activeElement.style.width = 'auto';
            this.activeElement.style.height = '98vh';
        } else {
            this.activeElement.style.width = '98vw';
            this.activeElement.style.height = 'auto';
        }
    }

    close() {
        this.overlay.classList.remove('active');
        this.reset();

        // Cleanup sources
        if (this.video) {
            this.video.pause();
            this.video.src = '';
        }
        this.image.src = '';

        document.body.style.overflow = '';
    }

    reset() {
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this.updateTransform();
    }

    zoom(delta, centerX, centerY) {
        const oldScale = this.scale;
        this.scale *= delta;
        this.scale = Math.max(1, Math.min(10, this.scale));

        if (this.scale === 1) {
            this.translateX = 0;
            this.translateY = 0;
            this.translateY = 0;
        } else {
            const rect = this.activeElement.getBoundingClientRect();
            const x = centerX - rect.left - rect.width / 2;
            const y = centerY - rect.top - rect.height / 2;

            const scaleChange = this.scale / oldScale - 1;
            this.translateX -= x * scaleChange;
            this.translateY -= y * scaleChange;

            this.constrainPosition();
        }

        this.updateTransform();
        this.updateCursor();
    }

    startDrag(x, y) {
        this.isDragging = true;
        this.startX = x - this.translateX;
        this.startY = y - this.translateY;
        this.lastX = x;
        this.lastY = y;
        this.activeElement.classList.add('dragging');
    }

    drag(x, y) {
        if (!this.isDragging) return;

        this.translateX = x - this.startX;
        this.translateY = y - this.startY;

        this.constrainPosition();
        this.updateTransform();
    }

    stopDrag() {
        this.isDragging = false;
        this.image.classList.remove('dragging');
        if (this.video) {
            this.video.classList.remove('dragging');
        }
    }

    constrainPosition() {
        const rect = this.activeElement.getBoundingClientRect();
        // Use natural dimensions * scale to prevent drift if rect changes
        // For video/img this can be tricky, relying on bounding client rect is safer if transform is applied

        // Actually we need the element's current dimensions relative to viewport
        const width = rect.width / this.scale; // unscaled width
        const height = rect.height / this.scale; // unscaled height

        const maxX = (width * this.scale - width) / 2;
        const maxY = (height * this.scale - height) / 2;

        this.translateX = Math.max(-maxX, Math.min(maxX, this.translateX));
        this.translateY = Math.max(-maxY, Math.min(maxY, this.translateY));
    }

    updateTransform() {
        this.activeElement.style.transform = `translate(${this.translateX}px, ${this.translateY}px) scale(${this.scale})`;
    }

    updateCursor() {
        if (this.scale > 1) {
            this.activeElement.classList.add('zoomed');
            this.overlay.style.cursor = 'default';
        } else {
            this.activeElement.classList.remove('zoomed');
            this.overlay.style.cursor = 'zoom-out';
        }
    }
}

// Global function for expand/collapse functionality
window.toggleExpand = function (id) {
    const truncated = document.getElementById(id + '-truncated');
    const full = document.getElementById(id + '-full');

    if (full.style.display === 'none') {
        truncated.style.display = 'none';
        full.style.display = 'inline';
    } else {
        truncated.style.display = 'inline';
        full.style.display = 'none';
    }
};
