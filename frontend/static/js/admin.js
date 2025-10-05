class AdminPanel {
    constructor() {
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadSettings();
        this.loadThemes();
    }
    
    setupEventListeners() {
        // Settings form
        const settingsForm = document.getElementById('settings-form');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveSettings();
            });
        }
        
        // Scan media button
        const scanBtn = document.getElementById('scan-media-btn');
        if (scanBtn) {
            scanBtn.addEventListener('click', () => this.scanMedia());
        }
        
        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.login();
            });
        }
    }
    
    async loadSettings() {
        try {
            const response = await fetch('/api/admin/settings');
            
            if (!response.ok) {
                console.log('Not authenticated or settings not available');
                return;
            }
            
            const settings = await response.json();
            
            // Populate form fields
            if (settings.app_name) {
                const appNameInput = document.getElementById('app-name');
                if (appNameInput) appNameInput.value = settings.app_name;
            }
            
            if (settings.default_rating_filter) {
                const ratingInput = document.querySelector(
                    `input[name="default-rating"][value="${settings.default_rating_filter}"]`
                );
                if (ratingInput) ratingInput.checked = true;
            }
            
            if (settings.theme) {
                const themeSelect = document.getElementById('theme-select');
                if (themeSelect) themeSelect.value = settings.theme;
            }
            
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }
    
    async loadThemes() {
        try {
            const data = await app.apiCall('/api/admin/themes');
            const themeSelect = document.getElementById('theme-select');
            
            if (themeSelect) {
                themeSelect.innerHTML = '';
                data.themes.forEach(theme => {
                    const option = document.createElement('option');
                    option.value = theme;
                    option.textContent = theme.charAt(0).toUpperCase() + theme.slice(1);
                    themeSelect.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading themes:', error);
        }
    }
    
    async saveSettings() {
        const appName = document.getElementById('app-name').value;
        const defaultRating = document.querySelector('input[name="default-rating"]:checked')?.value;
        const theme = document.getElementById('theme-select')?.value;
        
        const settings = {
            app_name: appName,
            default_rating_filter: defaultRating,
            theme: theme
        };
        
        try {
            await app.apiCall('/api/admin/settings', {
                method: 'PATCH',
                body: JSON.stringify(settings)
            });
            
            alert('Settings saved successfully!');
            location.reload();
        } catch (error) {
            alert('Error saving settings: ' + error.message);
        }
    }
    
    async scanMedia() {
        const scanBtn = document.getElementById('scan-media-btn');
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning...';
        
        try {
            const result = await app.apiCall('/api/admin/scan-media', {
                method: 'POST'
            });
            
            alert(`Scan complete!\nNew files: ${result.new_files}\n${result.files.join('\n')}`);
            
        } catch (error) {
            alert('Error scanning media: ' + error.message);
        } finally {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Scan for New Media';
        }
    }
    
    async login() {
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorDiv = document.getElementById('login-error');
        const submitBtn = document.querySelector('#login-form button[type="submit"]');
        
        // Clear previous error
        errorDiv.style.display = 'none';
        submitBtn.disabled = true;
        submitBtn.textContent = 'Logging in...';
        
        try {
            const response = await fetch('/api/admin/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });
            
            if (response.ok) {
                console.log('Login successful, redirecting...');
                window.location.href = '/admin';
            } else {
                const error = await response.json();
                console.error('Login failed:', error);
                errorDiv.textContent = error.detail || 'Invalid username or password';
                errorDiv.style.display = 'block';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Login';
            }
        } catch (error) {
            console.error('Login error:', error);
            errorDiv.textContent = 'Network error. Please try again.';
            errorDiv.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.textContent = 'Login';
        }
    }
}

// Initialize admin panel
if (document.getElementById('admin-panel')) {
    const adminPanel = new AdminPanel();
}
