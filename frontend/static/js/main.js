// Core functionality
class Blombooru {
    constructor() {
        this.isAdminMode = this.getCookie('admin_mode') === 'true';
        this.isAuthenticated = !!this.getCookie('admin_token');
        this.currentPage = 1;
        this.isLoading = false;
        this.hasMore = true;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.updateUI();
        
        // Load settings from cookie
        const savedRating = this.getCookie('rating_filter');
        if (savedRating) {
            this.setRatingFilter(savedRating);
        }
    }
    
    setupEventListeners() {
        // Admin mode toggle
        const adminToggle = document.getElementById('admin-mode-toggle');
        if (adminToggle) {
            adminToggle.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleAdminToggle();
            });
        }
        
        // Logout
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }
        
        // Rating filter
        const ratingInputs = document.querySelectorAll('input[name="rating"]');
        ratingInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                this.setRatingFilter(e.target.value);
                this.setCookie('rating_filter', e.target.value, 365);
            });
        });
        
        // Search form
        const searchForm = document.getElementById('search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.performSearch();
            });
        }
    }
    
    handleAdminToggle() {
        // If not authenticated, go to admin panel
        if (!this.isAuthenticated) {
            window.location.href = '/admin';
            return;
        }
        
        // If on admin panel page, don't toggle - it's auto-enabled
        if (window.location.pathname === '/admin') {
            return;
        }
        
        // Toggle admin mode
        this.toggleAdminMode();
    }
    
    async toggleAdminMode() {
        const newMode = !this.isAdminMode;
        
        try {
            const response = await fetch('/api/admin/toggle-admin-mode?enabled=' + newMode, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.isAdminMode = newMode;
                this.updateUI();
                
                // Show notification
                this.showNotification(
                    newMode ? 'Admin mode enabled' : 'Admin mode disabled',
                    newMode ? 'success' : 'info'
                );
            }
        } catch (error) {
            console.error('Error toggling admin mode:', error);
        }
    }
    
    async logout() {
        try {
            await fetch('/api/admin/logout', { method: 'POST' });
            window.location.href = '/';
        } catch (error) {
            console.error('Error logging out:', error);
        }
    }
    
    updateUI() {
        const body = document.body;
        const adminToggle = document.getElementById('admin-mode-toggle');
        const adminModeText = document.getElementById('admin-mode-text');
        const logoutBtn = document.getElementById('logout-btn');
        
        // Update body class
        if (this.isAdminMode) {
            body.classList.add('admin-mode');
        } else {
            body.classList.remove('admin-mode');
        }
        
        // Update admin toggle button
        if (adminToggle && adminModeText) {
            if (!this.isAuthenticated) {
                adminModeText.textContent = 'Admin Panel';
                adminToggle.style.color = '';
            } else if (window.location.pathname === '/admin') {
                adminModeText.textContent = 'Admin Panel';
                adminToggle.style.color = 'var(--primary-color)';
            } else if (this.isAdminMode) {
                adminModeText.textContent = '✓ Admin Mode';
                adminToggle.style.color = 'var(--success)';
            } else {
                adminModeText.textContent = 'Enable Admin Mode';
                adminToggle.style.color = '';
            }
        }
        
        // Show/hide logout button
        if (logoutBtn) {
            logoutBtn.style.display = this.isAuthenticated ? 'block' : 'none';
        }
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            padding: 1rem 1.5rem;
            background-color: ${type === 'success' ? 'var(--success)' : type === 'error' ? 'var(--danger)' : 'var(--primary-color)'};
            color: white;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
        `;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
    
    setRatingFilter(rating) {
        const input = document.querySelector(`input[name="rating"][value="${rating}"]`);
        if (input) {
            input.checked = true;
        }
    }
    
    performSearch() {
        const searchInput = document.getElementById('search-input');
        const query = searchInput.value;
        
        if (query) {
            window.location.href = `/?q=${encodeURIComponent(query)}`;
        }
    }
    
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }
    
    setCookie(name, value, days) {
        const expires = new Date();
        expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
        document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
    }
    
    async apiCall(endpoint, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json'
            }
        };
        
        const response = await fetch(endpoint, { ...defaultOptions, ...options });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'API call failed');
        }
        
        return response.json();
    }
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
    
    .admin-mode-btn {
        font-weight: 500 !important;
    }
`;
document.head.appendChild(style);

// Initialize app
const app = new Blombooru();
