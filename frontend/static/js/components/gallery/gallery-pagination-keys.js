// BaseGallery pagination controls, page jump modal, and keyboard navigation
Object.assign(BaseGallery.prototype, {
    // ==================== Pagination ====================

    adjustPageIfNeeded(totalPages) {
        this.totalPages = Math.max(1, totalPages || 1);

        if (this.currentPage > this.totalPages) {
            this.currentPage = this.totalPages;
            this.updateUrlParams({ page: this.currentPage });
            return true; // Signal that we need to reload
        }
        return false;
    },

    setupPageJumpModal() {
        const modal = document.getElementById('page-jump-modal');
        const input = document.getElementById('page-jump-input');
        const goBtn = document.getElementById('page-jump-go');
        const cancelBtn = document.getElementById('page-jump-cancel');

        if (!modal || !input || !goBtn || !cancelBtn) return;

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

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    },

    showPageJumpModal() {
        const modal = document.getElementById('page-jump-modal');
        const input = document.getElementById('page-jump-input');

        if (!modal || !input) return;

        input.max = this.totalPages;
        input.value = this.currentPage;
        modal.style.display = 'flex';
        input.focus();
        input.select();
    },

    async goToPage(page) {
        const pageTop = document.getElementById('main-scroll');
        if (this.isLoading || page < 1 || page > this.totalPages || page === this.currentPage) return;

        this.unloadAllGifs();
        this.currentPage = page;
        this.updateUrlParams({ page });
        await this.loadContent();
        if (pageTop && !this.pendingFocus) {
            pageTop.scrollTo({ top: 0, behavior: 'smooth' });
        }
    },

    renderPagination() {
        if (this.pendingFocus) {
            const target = this.pendingFocus;
            this.pendingFocus = null;
            requestAnimationFrame(() => {
                const links = this.getGalleryItemLinks();
                if (links.length > 0) {
                    const el = target === 'last' ? links[links.length - 1] : links[0];
                    el.focus({ preventScroll: true });
                    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
                }
            });
        }

        if (!this.elements.pageNav) return;

        if (document.body.classList.contains('reorder-active-mode')) {
            this.elements.pageNav.style.display = 'none';
            return;
        }

        if (this.totalPages <= 1) {
            this.elements.pageNav.style.display = 'none';
            return;
        }

        const paginationHTML = this.generatePaginationHTML();
        const container = this.elements.pageNav.querySelector('div');
        if (container) {
            container.innerHTML = paginationHTML;
        }
        this.elements.pageNav.style.display = 'block';
        this.setupPaginationHandlers();
    },

    getGalleryItemLinks() {
        const subAlbumsGrid = document.getElementById('sub-albums-grid');
        const grids = [];
        if (subAlbumsGrid && subAlbumsGrid.children.length > 0 && subAlbumsGrid.style.display !== 'none' && subAlbumsGrid.parentElement?.style.display !== 'none') {
            grids.push(subAlbumsGrid);
        }
        if (this.elements.grid) {
            grids.push(this.elements.grid);
        }
        if (grids.length === 0) return [];

        const rawLinks = [];
        grids.forEach(grid => {
            rawLinks.push(...grid.querySelectorAll('.gallery-item a, .album-card a, a.gallery-item, a.album-card, a.block'));
        });

        const uniqueLinks = [];
        const seen = new Set();
        for (const link of rawLinks) {
            if (link.classList.contains('select-indicator') || link.closest('.select-indicator')) continue;
            if (!seen.has(link)) {
                seen.add(link);
                uniqueLinks.push(link);
            }
        }
        return uniqueLinks;
    },

    getGridRows(links) {
        const rows = [];
        let currentRow = [];
        let currentTop = null;

        links.forEach(link => {
            const el = link.closest('.gallery-item, .album-card') || link;
            const top = el.offsetTop || 0;
            if (currentTop === null || Math.abs(top - currentTop) < 5) {
                currentRow.push(link);
                currentTop = top;
            } else {
                rows.push(currentRow);
                currentRow = [link];
                currentTop = top;
            }
        });
        if (currentRow.length > 0) rows.push(currentRow);
        return rows;
    },

    setupKeybindings() {
        document.addEventListener('keydown', async (e) => {
            const activeEl = document.activeElement;
            const isTyping = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.isContentEditable ||
                activeEl.closest('.modal') ||
                activeEl.closest('#page-jump-modal')
            );
            if (isTyping) return;

            if (!window.keybindings) return;

            let action = null;
            if (window.keybindings.matches(e, 'gallery_nav_up')) action = 'up';
            else if (window.keybindings.matches(e, 'gallery_nav_down')) action = 'down';
            else if (window.keybindings.matches(e, 'gallery_nav_left')) action = 'left';
            else if (window.keybindings.matches(e, 'gallery_nav_right')) action = 'right';

            if (!action) return;

            const links = this.getGalleryItemLinks();
            if (links.length === 0) return;

            e.preventDefault();

            if (this.isLoading) return;

            const currentFocused = document.activeElement;
            const currentIndex = links.findIndex(link => link === currentFocused || link.contains(currentFocused));

            const focusItem = (item) => {
                if (!item) return;
                item.focus({ preventScroll: true });
                item.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
            };

            if (currentIndex === -1) {
                focusItem(links[0]);
                return;
            }

            const rows = this.getGridRows(links);
            const topRow = rows[0] || [];
            const bottomRow = rows[rows.length - 1] || [];

            let currRowIdx = -1;
            let currColIdx = -1;
            for (let r = 0; r < rows.length; r++) {
                const cIdx = rows[r].findIndex(link => link === currentFocused || link.contains(currentFocused));
                if (cIdx !== -1) {
                    currRowIdx = r;
                    currColIdx = cIdx;
                    break;
                }
            }

            if (action === 'left') {
                if (currentIndex === 0) {
                    if (this.currentPage > 1) {
                        this.pendingFocus = 'last';
                        await this.goToPage(this.currentPage - 1);
                    }
                } else {
                    focusItem(links[currentIndex - 1]);
                }
            } else if (action === 'right') {
                if (currentIndex === links.length - 1) {
                    if (this.currentPage < this.totalPages) {
                        this.pendingFocus = 'first';
                        await this.goToPage(this.currentPage + 1);
                    }
                } else {
                    focusItem(links[currentIndex + 1]);
                }
            } else if (action === 'up') {
                if (currRowIdx === 0 || currRowIdx === -1) {
                    if (currentIndex === 0) {
                        if (this.currentPage > 1) {
                            this.pendingFocus = 'last';
                            await this.goToPage(this.currentPage - 1);
                        }
                    } else {
                        focusItem(topRow[0]);
                    }
                } else if (currRowIdx > 0) {
                    const prevRow = rows[currRowIdx - 1];
                    const targetCol = Math.min(currColIdx, prevRow.length - 1);
                    focusItem(prevRow[targetCol]);
                }
            } else if (action === 'down') {
                if (currRowIdx === rows.length - 1) {
                    if (currentIndex === links.length - 1) {
                        if (this.currentPage < this.totalPages) {
                            this.pendingFocus = 'first';
                            await this.goToPage(this.currentPage + 1);
                        }
                    } else {
                        focusItem(bottomRow[bottomRow.length - 1]);
                    }
                } else if (currRowIdx >= 0 && currRowIdx < rows.length - 1) {
                    const nextRow = rows[currRowIdx + 1];
                    const targetCol = Math.min(currColIdx, nextRow.length - 1);
                    focusItem(nextRow[targetCol]);
                }
            }
        });
    },

    generatePaginationHTML() {
        const pages = [];
        const current = this.currentPage;
        const total = this.totalPages;

        // Always show first page
        pages.push(this.createPageButton(1, current === 1));

        if (total <= 7) {
            for (let i = 2; i <= total; i++) {
                pages.push(this.createPageButton(i, current === i));
            }
        } else {
            if (current <= 4) {
                for (let i = 2; i <= 5; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
                pages.push(this.createEllipsis());
                pages.push(this.createPageButton(total, false));
            } else if (current >= total - 3) {
                pages.push(this.createEllipsis());
                for (let i = total - 4; i <= total; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
            } else {
                pages.push(this.createEllipsis());
                for (let i = current - 1; i <= current + 1; i++) {
                    pages.push(this.createPageButton(i, current === i));
                }
                pages.push(this.createEllipsis());
                pages.push(this.createPageButton(total, false));
            }
        }

        return `
            <div class="flex flex-wrap justify-center items-center gap-1.5 select-none">
                ${pages.join('')}
            </div>
        `;
    },

    createPageButton(pageNum, isActive) {
        const baseClass = "min-w-[2rem] h-8 px-2 flex items-center justify-center text-xs font-medium transition-all duration-200";

        if (isActive) {
            return `
                <span class="${baseClass} bg-primary border-primary primary-text hover:bg-primary hover:border-primary cursor-default">
                    ${pageNum}
                </span>`;
        }

        return `
            <a href="#" class="page-link ${baseClass} btn-dark text-secondary cursor-pointer" 
               data-page="${pageNum}">
               ${pageNum}
            </a>`;
    },

    createEllipsis() {
        const dotsIcon = window.Icons.dots({ size: 16 });
        return `
            <a href="#" class="page-ellipsis btn-dark min-w-[2rem] h-8 px-2 flex items-center justify-center transition-all duration-200 text-secondary cursor-pointer" 
               title="${window.i18n.t('gallery.jump_to_page')}">
               ${dotsIcon}
            </a>`;
    },

    setupPaginationHandlers() {
        if (!this.elements.pageNav) return;

        this.elements.pageNav.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                this.goToPage(page);
            });
        });

        this.elements.pageNav.querySelectorAll('.page-ellipsis').forEach(ellipsis => {
            ellipsis.addEventListener('click', (e) => {
                e.preventDefault();
                this.showPageJumpModal();
            });
        });
    },
});
