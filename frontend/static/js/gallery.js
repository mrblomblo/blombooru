class Gallery {
    constructor() {
        this.currentPage = 1;
        this.totalPages = 1;
        this.isLoading = false;
        this.selectedItems = new Set();
        this.tagCounts = new Map();
        this.activeTooltip = null;
        
        this.galleryContainer = document.getElementById('gallery-grid');
        this.loadingIndicator = document.getElementById('loading-indicator');
        this.popularTagsContainer = document.getElementById('popular-tags');
        this.pageNavTop = document.getElementById('page-nav-top');
        
        if (this.galleryContainer) {
            this.init();
        }
    }
    
    init() {
        this.setupBulkActions();
        this.setupRatingFilter();
        this.setupPageJumpModal();
        this.createTooltip();
        
        // Get page from URL or default to 1
        const params = new URLSearchParams(window.location.search);
        this.currentPage = parseInt(params.get('page')) || 1;
        
        // Load initial page
        this.loadPage();
    }
    
    createTooltip() {
        // Create tooltip element if it doesn't exist
        if (!document.getElementById('gallery-tooltip')) {
            const tooltip = document.createElement('div');
            tooltip.id = 'gallery-tooltip';
            tooltip.style.cssText = `
                position: absolute;
                background: rgba(0, 0, 0, 0.95);
                color: white;
                padding: 8px 12px;
                font-size: 13px;
                pointer-events: none;
                z-index: 10000;
                max-width: 300px;
                word-wrap: break-word;
                display: none;
                border: 1px solid rgba(255, 255, 255, 0.1);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
            `;
            document.body.appendChild(tooltip);
        }
        this.tooltipElement = document.getElementById('gallery-tooltip');
    }
    
    showTooltip(element, tags) {
        if (!tags || tags.length === 0) return;
        
        // Sort tags alphabetically
        const sortedTags = tags
            .map(tag => tag.name || tag)
            .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
        
        // Create comma-separated list
        const tagList = sortedTags.join(', ');
        
        this.tooltipElement.textContent = tagList;
        this.tooltipElement.style.display = 'block';
        
        // Position tooltip
        this.positionTooltip(element);
        
        this.activeTooltip = element;
    }
    
    positionTooltip(element) {
        const rect = element.getBoundingClientRect();
        const tooltipRect = this.tooltipElement.getBoundingClientRect();
        
        // Calculate position (above the element by default)
        let top = rect.top - tooltipRect.height - 10;
        let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
        
        // If tooltip would go off top of screen, show below instead
        if (top < 10) {
            top = rect.bottom + 10;
        }
        
        // Keep tooltip within viewport horizontally
        if (left < 10) {
            left = 10;
        } else if (left + tooltipRect.width > window.innerWidth - 10) {
            left = window.innerWidth - tooltipRect.width - 10;
        }
        
        // Add scroll offset
        top += window.scrollY;
        left += window.scrollX;
        
        this.tooltipElement.style.top = `${top}px`;
        this.tooltipElement.style.left = `${left}px`;
    }
    
    hideTooltip() {
        if (this.tooltipElement) {
            this.tooltipElement.style.display = 'none';
        }
        this.activeTooltip = null;
    }
    
    setupRatingFilter() {
        document.querySelectorAll('.rating-filter-input').forEach(radio => {
            radio.addEventListener('change', (e) => {
                const selectedRating = e.target.value;
                
                // Store the selected rating in localStorage for persistence
                localStorage.setItem('selectedRating', selectedRating);
                
                this.reloadWithRating(selectedRating);
            });
        });
        
        const savedRating = localStorage.getItem('selectedRating') || 'explicit';
        const savedRadio = document.querySelector(`input[value="${savedRating}"]`);
        
        if (savedRadio) {
            savedRadio.checked = true;
        }
    }
    
    reloadWithRating(rating) {
        this.galleryContainer.innerHTML = '';
        this.tagCounts.clear();
        
        const url = new URL(window.location);
        url.searchParams.set('rating', rating);
        window.history.replaceState({}, '', url);
        
        this.loadPage();
    }
    
    async loadPage() {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.showLoading();
        
        // Clear gallery for new page
        this.galleryContainer.innerHTML = '';
        this.tagCounts.clear();
        
        try {
            const params = new URLSearchParams(window.location.search);
            params.set('page', this.currentPage);
            
            // Add rating filter
            const ratingFilter = document.querySelector('input[name="rating"]:checked');
            if (ratingFilter) {
                params.set('rating', ratingFilter.value);
            }
            
            const endpoint = params.has('q') ? '/api/search' : '/api/media/';
            const url = `${endpoint}?${params.toString()}`;
            
            console.log('Loading gallery page:', url);
            
            const response = await fetch(url);
            
            // Check if response is ok
            if (!response.ok) {
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const error = await response.json();
                    throw new Error(error.detail || `HTTP ${response.status}`);
                } else {
                    const text = await response.text();
                    console.error('Non-JSON response:', text);
                    throw new Error(`Server returned ${response.status}: ${text.substring(0, 100)}`);
                }
            }
            
            const data = await response.json();
            console.log('Gallery data loaded:', data);
            
            this.totalPages = data.pages || 1;
            
            if (data.items && data.items.length > 0) {
                this.processTagCounts(data.items);
                this.renderItems(data.items);
                this.updatePopularTags();
                this.renderPagination();
            } else {
                if (this.currentPage === 1) {
                    this.showEmptyState();
                }
            }
            
        } catch (error) {
            console.error('Error loading gallery:', error);
            this.showError(error.message);
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }
    
    renderPagination() {
        if (this.totalPages <= 1) {
            this.pageNavTop.style.display = 'none';
            return;
        }
        
        const paginationHTML = this.generatePaginationHTML();
        
        this.pageNavTop.querySelector('div').innerHTML = paginationHTML;
        this.pageNavTop.style.display = 'block';
                
        // Add click handlers
        this.setupPaginationHandlers(this.pageNavTop);
    }
    
    generatePaginationHTML() {
        const pages = [];
        const current = this.currentPage;
        const total = this.totalPages;
        
        // Always show first page
        pages.push(this.createPageButton(1, current === 1));
        
        if (total <= 7) {
            // Show all pages if 7 or fewer
            for (let i = 2; i <= total; i++) {
                pages.push(this.createPageButton(i, current === i));
            }
        } else {
            // Show with ellipsis
            if (current <= 4) {
                // Near the start: 1 2 3 4 5 ... 27
                for (let i = 2; i <= 5; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
                pages.push(this.createEllipsis());
                pages.push(this.createPageButton(total, false));
            } else if (current >= total - 3) {
                // Near the end: 1 ... 23 24 25 26 27
                pages.push(this.createEllipsis());
                for (let i = total - 4; i <= total; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
            } else {
                // In the middle: 1 ... 12 13 14 ... 27
                pages.push(this.createEllipsis());
                for (let i = current - 1; i <= current + 1; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
                pages.push(this.createEllipsis());
                pages.push(this.createPageButton(total, false));
            }
        }
        
        return pages.join(' <span class="text-secondary">|</span> ');
    }
    
    createPageButton(pageNum, isActive) {
        if (isActive) {
            return `<span class="px-2 py-1 font-bold text-primary">${pageNum}</span>`;
        }
        return `<a href="#" class="px-2 py-1 hover:text-primary page-link" data-page="${pageNum}">${pageNum}</a>`;
    }
    
    createEllipsis() {
        return `<a href="#" class="px-2 py-1 hover:text-primary page-ellipsis">...</a>`;
    }
    
    setupPaginationHandlers(container) {
        container.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                this.goToPage(page);
            });
        });
        
        container.querySelectorAll('.page-ellipsis').forEach(ellipsis => {
            ellipsis.addEventListener('click', (e) => {
                e.preventDefault();
                this.showPageJumpModal();
            });
        });
    }
    
    setupPageJumpModal() {
        const modal = document.getElementById('page-jump-modal');
        const input = document.getElementById('page-jump-input');
        const goBtn = document.getElementById('page-jump-go');
        const cancelBtn = document.getElementById('page-jump-cancel');
        
        goBtn.addEventListener('click', () => {
            const page = parseInt(input.value);
            if (page >= 1 && page <= this.totalPages) {
                modal.style.display = 'none';
                this.goToPage(page);
            }
        });
        
        cancelBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });
        
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                goBtn.click();
            }
        });
        
        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    }
    
    showPageJumpModal() {
        const modal = document.getElementById('page-jump-modal');
        const input = document.getElementById('page-jump-input');
        
        input.max = this.totalPages;
        input.value = this.currentPage;
        modal.style.display = 'flex';
        input.focus();
        input.select();
    }
    
    goToPage(page) {
        if (page < 1 || page > this.totalPages || page === this.currentPage) return;
        
        this.currentPage = page;
        
        const url = new URL(window.location);
        url.searchParams.set('page', page);
        window.history.pushState({}, '', url);
        
        this.loadPage();
    }
    
    processTagCounts(items) {
        items.forEach(item => {
            if (item.tags && Array.isArray(item.tags)) {
                item.tags.forEach(tag => {
                    const currentCount = this.tagCounts.get(tag.name) || { count: 0, category: tag.category };
                    this.tagCounts.set(tag.name, {
                        count: currentCount.count + 1,
                        category: tag.category
                    });
                });
            }
        });
    }
    
    updatePopularTags() {
        if (!this.popularTagsContainer) return;
        
        // Convert map to array and sort by count
        const sortedTags = Array.from(this.tagCounts.entries())
            .sort((a, b) => b[1].count - a[1].count)
            .slice(0, 20);
        
        if (sortedTags.length === 0) {
            this.popularTagsContainer.innerHTML = '<p class="text-secondary">No tags found</p>';
            return;
        }
        
        // Get current search query
        const currentParams = new URLSearchParams(window.location.search);
        const currentQuery = currentParams.get('q') || '';
        const currentTags = currentQuery.split(/\s+/).filter(t => t.length > 0);
        
        this.popularTagsContainer.innerHTML = sortedTags.map(([tagName, data]) => {
            // Check if this tag is already in the search
            const isInQuery = currentTags.includes(tagName);
            
            // Build the new query
            let newQuery;
            if (isInQuery) {
                // If clicking the same tag that's already searched, don't change anything
                newQuery = currentQuery;
            } else if (currentQuery) {
                // Append to existing query
                newQuery = currentQuery + ' ' + tagName;
            } else {
                // No existing query, just use this tag
                newQuery = tagName;
            }
            
            const params = new URLSearchParams(window.location.search);
            params.set('q', newQuery);
            params.delete('page');
            
            return `
                <div class="${isInQuery ? 'popular-tag-item opacity-50' : 'popular-tag-item'}">
                    <a href="/?${params.toString()}" class="popular-tag-name tag ${data.category} tag-text" ${isInQuery ? 'style="pointer-events: none;"' : ''}>${tagName}</a>
                    <span class="popular-tag-count">${data.count}</span>
                </div>
            `;
        }).join('');
    }
    
    renderItems(items) {
        items.forEach(item => {
            const element = this.createGalleryItem(item);
            this.galleryContainer.appendChild(element);
        });
    }
    
    createGalleryItem(media) {
        const item = document.createElement('div');
        item.className = `gallery-item ${media.file_type}`;
        item.dataset.id = media.id;
        item.dataset.rating = media.rating;

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'checkbox';
        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                this.selectedItems.add(media.id);
                item.classList.add('selected');
            } else {
                this.selectedItems.delete(media.id);
                item.classList.remove('selected');
            }
            this.updateBulkActionsUI();
        });
        
        const img = document.createElement('img');
        img.src = `/api/media/${media.id}/thumbnail`;
        img.alt = media.filename;
        img.loading = 'lazy';
        img.onerror = () => {
            console.error('Failed to load thumbnail for media:', media.id);
            img.src = '/static/images/no-thumbnail.png'; // Fallback image
        };
        
        const link = document.createElement('a');
        const params = new URLSearchParams(window.location.search);
        const queryString = params.toString();
        link.href = `/media/${media.id}${queryString ? '?' + queryString : ''}`;
        link.appendChild(img);
        
        // Add hover events for tooltip
        let hoverTimeout;
        item.addEventListener('mouseenter', (e) => {
            // Add a small delay to prevent tooltip from showing on quick mouseovers
            hoverTimeout = setTimeout(() => {
                if (media.tags && media.tags.length > 0) {
                    this.showTooltip(item, media.tags);
                }
            }, 300);
        });
        
        item.addEventListener('mouseleave', () => {
            clearTimeout(hoverTimeout);
            this.hideTooltip();
        });
        
        // Update tooltip position on scroll if it's visible
        const handleScroll = () => {
            if (this.activeTooltip === item) {
                this.positionTooltip(item);
            }
        };
        window.addEventListener('scroll', handleScroll, { passive: true });
        
        item.appendChild(checkbox);
        item.appendChild(link);
        
        // Add share icon if shared
        if (media.is_shared) {
            const shareIcon = document.createElement('div');
            shareIcon.className = 'share-icon';
            shareIcon.textContent = 'SHARED';
            item.appendChild(shareIcon);
        }
        
        return item;
    }
    
    setupBulkActions() {
        const bulkDeleteBtn = document.getElementById('bulk-delete-btn');
        const selectAllBtn = document.getElementById('select-all-btn');
        
        if (bulkDeleteBtn) {
            bulkDeleteBtn.addEventListener('click', () => this.bulkDelete());
        }
        
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => this.selectAll());
        }
    }
    
    updateBulkActionsUI() {
        const bulkActions = document.getElementById('bulk-actions');
        if (bulkActions) {
            bulkActions.style.display = this.selectedItems.size > 0 ? 'block' : 'none';
        }
        
        const count = document.getElementById('selected-count');
        if (count) {
            count.textContent = this.selectedItems.size;
        }
    }
    
    async bulkDelete() {
        if (!confirm(`Delete ${this.selectedItems.size} items?`)) return;
        
        for (const id of this.selectedItems) {
            try {
                await app.apiCall(`/api/media/${id}`, {
                    method: 'DELETE'
                });
                
                const element = document.querySelector(`[data-id="${id}"]`);
                if (element) {
                    element.remove();
                }
            } catch (error) {
                console.error(`Error deleting media ${id}:`, error);
            }
        }
        
        this.clearSelection();
        this.loadPage();
    }
    
    clearSelection() {
        this.selectedItems.clear();
        document.querySelectorAll('.gallery-item').forEach(item => {
            item.classList.remove('selected');
            const checkbox = item.querySelector('.checkbox');
            if (checkbox) checkbox.checked = false;
        });
        this.updateBulkActionsUI();
    }

    selectAll() {
        document.querySelectorAll('.gallery-item').forEach(item => {
            const id = parseInt(item.dataset.id);
            const checkbox = item.querySelector('.checkbox');
            
            if (checkbox && !checkbox.checked) {
                checkbox.checked = true;
                this.selectedItems.add(id);
                item.classList.add('selected');
            }
        });
        this.updateBulkActionsUI();
    }
    
    showLoading() {
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'block';
        }
    }
    
    hideLoading() {
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'none';
        }
    }
    
    showEmptyState() {
        this.galleryContainer.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 4rem; color: var(--text-secondary);">
                <h2>No media found</h2>
                <p>Upload some images to get started!</p>
                ${app.isAuthenticated ? '<a href="/admin" class="btn">Go to Admin Panel</a>' : ''}
            </div>
        `;
        
        if (this.popularTagsContainer) {
            this.popularTagsContainer.innerHTML = '<p class="text-secondary">No tags found</p>';
        }
    }
    
    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
            grid-column: 1 / -1;
            background-color: var(--danger);
            color: white;
            padding: 1rem;
            margin: 1rem 0;
        `;
        errorDiv.innerHTML = `
            <strong>Error loading gallery:</strong> ${message}
            <br><small>Check the browser console for more details</small>
        `;
        this.galleryContainer.appendChild(errorDiv);
    }
}

// Initialize gallery if on gallery page
if (document.getElementById('gallery-grid')) {
    const gallery = new Gallery();
}
