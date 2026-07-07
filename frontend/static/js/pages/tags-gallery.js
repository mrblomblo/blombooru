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

        this.elements.grid.innerHTML = '';

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

        tags.forEach(tag => {
            const element = this.createTagItem(tag);
            this.elements.grid.appendChild(element);
        });
    }

    createTagItem(for_tag) {
        const surface = document.createElement("div")
        surface.className = "surface p-3 border flex flex-wrap items-center gap-2"

        const tag_name = document.createElement("a")
        tag_name.href = `/?q=${encodeURIComponent(for_tag.name)}`
        tag_name.className = `tag ${for_tag.category} tag-text overflow-hidden whitespace-nowrap text-ellipsis`
        tag_name.textContent = `${for_tag.name}`
        surface.appendChild(tag_name)

        const detail_preview_box = document.createElement("div")
        detail_preview_box.className = "flex justify-between items-center gap-2 flex-1"
        surface.appendChild(detail_preview_box)

        const post_count = document.createElement("span")
        post_count.className = "text-xs text-secondary"
        post_count.textContent = `(${for_tag.post_count})`
        detail_preview_box.appendChild(post_count)

        const created_at = document.createElement("span")
        created_at.className = "text-xs text-secondary text-center"
        let creation_date = new Date(for_tag.created_at)
        created_at.textContent = `${
            new Intl.DateTimeFormat(undefined, {dateStyle: "short"}).format(creation_date)
        } ${
            new Intl.DateTimeFormat(undefined, {timeStyle: "short", hour12: false}).format(creation_date)
        }`
        detail_preview_box.appendChild(created_at)

        const category = document.createElement("span")
        category.className = "text-xs text-secondary uppercase flex-1 text-right"
        category.textContent = `${for_tag.category}`
        detail_preview_box.appendChild(category)

        return surface;
    }
}

if (document.getElementById('tags-grid')) {
    window.tagsGallery = new TagsGallery();
}
