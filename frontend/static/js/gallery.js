class Gallery {
    constructor() {
        this.currentPage = 1;
        this.isLoading = false;
        this.hasMore = true;
        this.selectedItems = new Set();
        this.tagCounts = new Map(); // Track tag counts
        
        this.galleryContainer = document.getElementById('gallery-grid');
        this.loadingIndicator = document.getElementById('loading-indicator');
        this.popularTagsContainer = document.getElementById('popular-tags');
        
        if (this.galleryContainer) {
            this.init();
        }
    }
    
    init() {
        this.setupInfiniteScroll();
        this.setupBulkActions();
        this.setupRatingFilter();
        
        // Load initial page if empty
        if (this.galleryContainer.children.length === 0) {
            this.loadPage();
        }
    }
    
    setupInfiniteScroll() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !this.isLoading && this.hasMore) {
                    this.loadPage();
                }
            });
        }, {
            rootMargin: '200px'
        });
        
        if (this.loadingIndicator) {
            observer.observe(this.loadingIndicator);
        }
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
        
        this.currentPage = 1;
        this.hasMore = true;
        
        // Update URL with rating parameter
        const url = new URL(window.location);
        url.searchParams.set('rating', rating);
        window.history.replaceState({}, '', url);
        
        this.loadPage();
    }
    
    async loadPage() {
        if (this.isLoading || !this.hasMore) return;
        
        this.isLoading = true;
        this.showLoading();
        
        try {
            const params = new URLSearchParams(window.location.search);
            params.set('page', this.currentPage);
            params.set('limit', 30);
            
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
            
            if (data.items && data.items.length > 0) {
                this.processTagCounts(data.items);
                this.renderItems(data.items);
                this.updatePopularTags();
                this.currentPage++;
                this.hasMore = this.currentPage <= data.pages;
            } else {
                this.hasMore = false;
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
            this.popularTagsContainer.innerHTML = '<p class="text-[#94a3b8]">No tags found</p>';
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
            
            // Visual indicator if tag is already in query
            const activeClass = isInQuery ? 'opacity-50' : '';
            
            return `
                <div class="popular-tag-item ${activeClass}">
                    <a href="/?${params.toString()}" class="popular-tag-name tag ${data.category}" ${isInQuery ? 'style="pointer-events: none;"' : ''}>${tagName}</a>
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
        link.href = `/media/${media.id}`;
        link.appendChild(img);
        
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
        const bulkTagBtn = document.getElementById('bulk-tag-btn');
        const bulkDeleteBtn = document.getElementById('bulk-delete-btn');
        
        if (bulkTagBtn) {
            bulkTagBtn.addEventListener('click', () => this.bulkTag());
        }
        
        if (bulkDeleteBtn) {
            bulkDeleteBtn.addEventListener('click', () => this.bulkDelete());
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
    
    async bulkTag() {
        const tags = prompt('Enter tags (comma-separated):');
        if (!tags) return;
        
        const tagList = tags.split(',').map(t => t.trim());
        
        for (const id of this.selectedItems) {
            try {
                await app.apiCall(`/api/media/${id}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ tags: tagList })
                });
            } catch (error) {
                console.error(`Error tagging media ${id}:`, error);
            }
        }
        
        this.clearSelection();
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
            this.popularTagsContainer.innerHTML = '<p class="text-[#94a3b8]">No tags found</p>';
        }
    }
    
    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
            grid-column: 1 / -1;
            background-color: var(--danger);
            color: white;
            padding: 1rem;
            border-radius: 0.5rem;
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
