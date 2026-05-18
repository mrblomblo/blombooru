class AdminStats {
    constructor() {
        this.charts = {};
        this.isInitialized = false;
        this.lastLoadTime = 0;
        this.minLoadInterval = 5000; // 5 seconds rate limit
    }

    async init() {
        // Check rate limit
        const now = Date.now();
        if (this.isInitialized && now - this.lastLoadTime < this.minLoadInterval) {
            console.log('Stats load rate limited');
            return;
        }

        if (typeof Chart === 'undefined') {
            console.error('Chart.js is not loaded');
            return;
        }

        Chart.defaults.font.family = getComputedStyle(document.documentElement).fontFamily;
        Chart.defaults.color = this.getCSSVariable('--text');
        Chart.defaults.borderColor = this.getCSSVariable('--border');

        await this.loadStats();
        this.lastLoadTime = Date.now();
        this.isInitialized = true;
    }

    getCSSVariable(varName) {
        return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    }

    async loadStats() {
        try {
            this.showLoading();

            const response = await fetch('/api/admin/stats');
            if (!response.ok) {
                throw new Error('Failed to load stats');
            }

            const data = await response.json();
            this.updateStatCards(data);
            this.updateCharts(data);

            this.hideLoading();
        } catch (error) {
            console.error('Error loading stats:', error);
            this.showError(error.message);
        }
    }

    showLoading() {
        const statsContent = document.getElementById('stats-content');
        if (statsContent) {
            statsContent.style.opacity = '0.5';
            statsContent.style.pointerEvents = 'none';
        }
    }

    hideLoading() {
        const statsContent = document.getElementById('stats-content');
        if (statsContent) {
            statsContent.style.opacity = '1';
            statsContent.style.pointerEvents = 'auto';
        }
    }

    showError(message) {
        this.hideLoading();
        if (window.app && window.app.showNotification) {
            window.app.showNotification(message, 'error', window.i18n.t('notifications.admin.error_loading_stats'));
        }
    }

    updateStatCards(data) {
        const totalMediaEl = document.getElementById('stat-total-media');
        if (totalMediaEl) totalMediaEl.textContent = data.media.total.toLocaleString();

        const totalTagsEl = document.getElementById('stat-total-tags');
        if (totalTagsEl) totalTagsEl.textContent = data.tags.total.toLocaleString();

        const totalAlbumsEl = document.getElementById('stat-total-albums');
        if (totalAlbumsEl) totalAlbumsEl.textContent = data.albums.total.toLocaleString();

        const totalStorageEl = document.getElementById('stat-total-storage');
        if (totalStorageEl) totalStorageEl.textContent = this.formatBytes(data.storage.total_bytes);

        const tagAliasesEl = document.getElementById('stat-tag-aliases');
        if (tagAliasesEl) tagAliasesEl.textContent = data.tags.total_aliases.toLocaleString();

        const tagsWithAliasesEl = document.getElementById('stat-tags-with-aliases');
        if (tagsWithAliasesEl) tagsWithAliasesEl.textContent = data.tags.total_with_aliases.toLocaleString();

        const parentMediaEl = document.getElementById('stat-parent-media');
        if (parentMediaEl) parentMediaEl.textContent = (data.media.relationships?.total_parents || 0).toLocaleString();

        const childMediaEl = document.getElementById('stat-child-media');
        if (childMediaEl) childMediaEl.textContent = (data.media.relationships?.total_children || 0).toLocaleString();
    }

    updateCharts(data) {
        this.createMediaTypeChart(data.media.by_type);
        this.createMediaRatingChart(data.media.by_rating);
        this.createUploadTrendsChart(data.upload_trends);
        this.createTopTagsChart(data.tags.top_tags);
        this.createTagCategoryChart(data.tags.by_category);
        this.createAlbumSizeChart(data.albums.size_distribution);

        if (data.tags.top_tags_by_category) {
            this.createTopTagsByCategoryChart('general', data.tags.top_tags_by_category.general);
            this.createTopTagsByCategoryChart('artist', data.tags.top_tags_by_category.artist);
            this.createTopTagsByCategoryChart('character', data.tags.top_tags_by_category.character);
            this.createTopTagsByCategoryChart('copyright', data.tags.top_tags_by_category.copyright);
            this.createTopTagsByCategoryChart('meta', data.tags.top_tags_by_category.meta);
        }
    }

    createMediaTypeChart(data) {
        const ctx = document.getElementById('chart-media-type');
        if (!ctx) return;

        if (this.charts.mediaType) {
            this.charts.mediaType.destroy();
        }

        this.charts.mediaType = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: [
                    window.i18n.t('common.images'),
                    window.i18n.t('common.gifs'),
                    window.i18n.t('common.videos')
                ],
                datasets: [{
                    data: [data.image || 0, data.gif || 0, data.video || 0],
                    backgroundColor: [
                        this.getCSSVariable('--blue'),
                        this.getCSSVariable('--orange'),
                        this.getCSSVariable('--red')
                    ],
                    borderWidth: 2,
                    borderColor: this.getCSSVariable('--background')
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: this.getCSSVariable('--text'),
                            padding: 10,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: this.getCSSVariable('--surface'),
                        titleColor: this.getCSSVariable('--text'),
                        bodyColor: this.getCSSVariable('--text'),
                        borderColor: this.getCSSVariable('--border'),
                        borderWidth: 1
                    }
                }
            }
        });
    }

    createMediaRatingChart(data) {
        const ctx = document.getElementById('chart-media-rating');
        if (!ctx) return;

        if (this.charts.mediaRating) {
            this.charts.mediaRating.destroy();
        }

        this.charts.mediaRating = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: [
                    window.i18n.t('common.safe'),
                    window.i18n.t('common.questionable'),
                    window.i18n.t('common.explicit')
                ],
                datasets: [{
                    data: [data.safe || 0, data.questionable || 0, data.explicit || 0],
                    backgroundColor: [
                        this.getCSSVariable('--rating-safe'),
                        this.getCSSVariable('--rating-questionable'),
                        this.getCSSVariable('--rating-explicit')
                    ],
                    borderWidth: 2,
                    borderColor: this.getCSSVariable('--background')
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: this.getCSSVariable('--text'),
                            padding: 10,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: this.getCSSVariable('--surface'),
                        titleColor: this.getCSSVariable('--text'),
                        bodyColor: this.getCSSVariable('--text'),
                        borderColor: this.getCSSVariable('--border'),
                        borderWidth: 1
                    }
                }
            }
        });
    }

    createUploadTrendsChart(data) {
        const ctx = document.getElementById('chart-upload-trends');
        if (!ctx) return;

        if (this.charts.uploadTrends) {
            this.charts.uploadTrends.destroy();
        }

        const sortedData = data.sort((a, b) => new Date(a.date) - new Date(b.date));
        const labels = sortedData.map(d => new Date(d.date).toLocaleDateString());
        const counts = sortedData.map(d => d.count);

        this.charts.uploadTrends = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: window.i18n.t('admin.stats.uploads_per_day'),
                    data: counts,
                    borderColor: this.getCSSVariable('--primary-color'),
                    backgroundColor: this.getCSSVariable('--primary-color') + '20',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2,
                    pointRadius: 3,
                    pointHoverRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: this.getCSSVariable('--text-secondary'),
                            font: { size: 10 },
                            precision: 0
                        },
                        grid: {
                            color: this.getCSSVariable('--border')
                        }
                    },
                    x: {
                        ticks: {
                            color: this.getCSSVariable('--text-secondary'),
                            font: { size: 9 },
                            maxRotation: 45,
                            minRotation: 45
                        },
                        grid: {
                            display: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: this.getCSSVariable('--surface'),
                        titleColor: this.getCSSVariable('--text'),
                        bodyColor: this.getCSSVariable('--text'),
                        borderColor: this.getCSSVariable('--border'),
                        borderWidth: 1
                    }
                }
            }
        });
    }

    createTopTagsChart(data) {
        const ctx = document.getElementById('chart-top-tags');
        if (!ctx) return;

        if (this.charts.topTags) {
            this.charts.topTags.destroy();
        }

        const labels = data.map(t => {
            const name = t.name;
            return name.length > 20 ? name.substring(0, 20) + '...' : name;
        });
        const counts = data.map(t => t.count);

        this.charts.topTags = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: window.i18n.t('admin.stats.usage_count'),
                    data: counts,
                    backgroundColor: this.getCSSVariable('--primary-color'),
                    borderColor: this.getCSSVariable('--primary-color'),
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            color: this.getCSSVariable('--text-secondary'),
                            font: { size: 10 },
                            precision: 0
                        },
                        grid: {
                            color: this.getCSSVariable('--border')
                        }
                    },
                    y: {
                        ticks: {
                            color: this.getCSSVariable('--text'),
                            font: { size: 10 }
                        },
                        grid: {
                            display: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: this.getCSSVariable('--surface'),
                        titleColor: this.getCSSVariable('--text'),
                        bodyColor: this.getCSSVariable('--text'),
                        borderColor: this.getCSSVariable('--border'),
                        borderWidth: 1,
                        callbacks: {
                            title: function (context) {
                                return data[context[0].dataIndex].name;
                            }
                        }
                    }
                }
            }
        });
    }

    createTagCategoryChart(data) {
        const ctx = document.getElementById('chart-tag-category');
        if (!ctx) return;

        if (this.charts.tagCategory) {
            this.charts.tagCategory.destroy();
        }

        const categories = ['general', 'artist', 'character', 'copyright', 'meta'];
        const labels = categories.map(cat => window.i18n.t(`common.tag_category_${cat}`));
        const counts = categories.map(cat => data[cat] || 0);

        this.charts.tagCategory = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: counts,
                    backgroundColor: [
                        this.getCSSVariable('--tag-general'),
                        this.getCSSVariable('--tag-artist'),
                        this.getCSSVariable('--tag-character'),
                        this.getCSSVariable('--tag-copyright'),
                        this.getCSSVariable('--tag-meta')
                    ],
                    borderWidth: 2,
                    borderColor: this.getCSSVariable('--background')
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: this.getCSSVariable('--text'),
                            padding: 10,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: this.getCSSVariable('--surface'),
                        titleColor: this.getCSSVariable('--text'),
                        bodyColor: this.getCSSVariable('--text'),
                        borderColor: this.getCSSVariable('--border'),
                        borderWidth: 1
                    }
                }
            }
        });
    }

    createAlbumSizeChart(data) {
        const ctx = document.getElementById('chart-album-size');
        if (!ctx) return;

        if (this.charts.albumSize) {
            this.charts.albumSize.destroy();
        }

        const labels = ['0', '1-10', '11-50', '51-100', '100+'];
        const translatedLabels = labels.map(label => {
            if (label === '0') return window.i18n.t('admin.stats.empty_albums');
            return `${label} ${window.i18n.t('common.media')}`;
        });
        const counts = labels.map(label => data[label] || 0);

        const baseColors = [
            this.getCSSVariable('--tag-character'),
            this.getCSSVariable('--tag-general'),
            this.getCSSVariable('--tag-meta'),
            this.getCSSVariable('--tag-artist'),
            this.getCSSVariable('--tag-copyright')
        ];

        this.charts.albumSize = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: translatedLabels,
                datasets: [{
                    data: counts,
                    backgroundColor: baseColors,
                    borderWidth: 2,
                    borderColor: this.getCSSVariable('--background')
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: this.getCSSVariable('--text'),
                            padding: 10,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: this.getCSSVariable('--surface'),
                        titleColor: this.getCSSVariable('--text'),
                        bodyColor: this.getCSSVariable('--text'),
                        borderColor: this.getCSSVariable('--border'),
                        borderWidth: 1
                    }
                }
            }
        });
    }

    createTopTagsByCategoryChart(category, data) {
        const ctx = document.getElementById(`chart-top-${category}`);
        if (!ctx || !data || data.length === 0) return;

        const chartKey = `top${category.charAt(0).toUpperCase() + category.slice(1)}`;
        if (this.charts[chartKey]) {
            this.charts[chartKey].destroy();
        }

        const labels = data.map(t => {
            const name = t.name;
            return name.length > 20 ? name.substring(0, 20) + '...' : name;
        });
        const counts = data.map(t => t.count);
        const categoryColor = this.getCSSVariable(`--tag-${category}`);

        this.charts[chartKey] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: window.i18n.t('admin.stats.usage_count'),
                    data: counts,
                    backgroundColor: categoryColor,
                    borderColor: categoryColor,
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            color: this.getCSSVariable('--text-secondary'),
                            font: { size: 10 },
                            precision: 0
                        },
                        grid: {
                            color: this.getCSSVariable('--border')
                        }
                    },
                    y: {
                        ticks: {
                            color: this.getCSSVariable('--text'),
                            font: { size: 10 }
                        },
                        grid: {
                            display: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: this.getCSSVariable('--surface'),
                        titleColor: this.getCSSVariable('--text'),
                        bodyColor: this.getCSSVariable('--text'),
                        borderColor: this.getCSSVariable('--border'),
                        borderWidth: 1,
                        callbacks: {
                            title: function (context) {
                                return data[context[0].dataIndex].name;
                            }
                        }
                    }
                }
            }
        });
    }

    destroy() {
        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });
        this.charts = {};
        this.isInitialized = false;
    }
}

window.AdminStats = AdminStats;
window.AdminStats = AdminStats;
