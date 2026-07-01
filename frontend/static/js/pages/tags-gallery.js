class TagsGallery extends BaseGallery {
    constructor() {
        super({
            gridSelector: '#tags-grid',
            defaultSort: 'post_count',
            enableRatingFilter: false,
            enableTooltips: false
        });

        if (this.elements.grid) {
            this.init();
        }
    }

    async init() {
        this.initCommon();
        this.currentPage = parseInt(this.getUrlParam('page',1));

        await this.loadContent();
    }

    async loadContent() {
        if (this.isLoading) return;

        this.isLoading = true;
        this.showLoading();

        try {
            const params = new URLSearchParams({
               page: this.currentPage,
               sort: this.getSortValue(),
               order: this.getOrderValue()
            });

            const response = await fetch(`/api/tags/list?${params}`);
            if (!response.ok) throw new Error(window.i18n.t('tags_gallery.failed_load_list'));

            const data = await response.json();
            this.totalPages = data.pages || 1;

            const responseItems = data.items || [];
            this.renderTagList(responseItems);
            this.renderPagination();
        } catch (error) {
            console.error('Error loading tags:', error);
            this.showError(window.i18n.t('tags_gallery.failed_load_list'));
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    renderTagList(tags){
        if (!this.elements.grid) return;

        if (tags.length === 0) {
            this.showEmptyState(window.i18n.t('tags_gallery.no_visible_tags'));
            return;
        }

        this.elements.grid.innerHTML = tags.map(tag => this.createTagDataContainer(tag)).join('');
    }

    createTagDataContainer(tag){
        return `
            <div class="surface p-3 border flex justify-between items-center">
                <div class="flex items-center gap-2">
                    <a href="/?q=${encodeURIComponent(tag.name)}" class="tag ${tag.category} tag-text">${tag.name}</a>
                    <span class="text-xs text-secondary">(${tag.post_count})</span>
                    <span class="text-xs text-secondary">(${new Date(tag.created_at).toLocaleString()})</span>
                </div>
                <span class="text-xs text-secondary uppercase">${tag.category}</span>
            </div>
        `;
    }
}

if (document.getElementById('tags-grid')) {
    window.tagsGallery = new TagsGallery();
}
