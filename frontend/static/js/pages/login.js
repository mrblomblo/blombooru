// Login page functionality
(function () {
    // Return URL validation helpers
    function isSafeReturnUrl(url) {
        if (!url || typeof url !== 'string') {
            return false;
        }

        // Must start with a single '/' and not '//' or '/\'
        if (!url.startsWith('/') || url.startsWith('//') || url.startsWith('/\\')) {
            return false;
        }

        // Reject ASCII control characters (which browsers strip or normalize)
        for (let i = 0; i < url.length; i++) {
            const code = url.charCodeAt(i);
            if (code < 32 || code === 127) {
                return false;
            }
        }

        return true;
    }

    function getSafeReturnUrl(url, defaultValue = '/') {
        return isSafeReturnUrl(url) ? url : defaultValue;
    }

    // Export for Node tests without leaking globals to window
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { isSafeReturnUrl, getSafeReturnUrl };
    }

    if (typeof document === 'undefined') {
        return;
    }

    (async function init() {
        const loginForm = document.getElementById('login-form');
        const errorDiv = document.getElementById('login-error');
        const loginBtn = document.getElementById('login-btn');
        const returnUrlInput = document.getElementById('return-url');

        // Check if user is already logged in
        try {
            const authResponse = await fetch('/api/admin/settings');
            if (authResponse.ok) {
                const urlParams = new URLSearchParams(window.location.search);
                const rawReturnUrl = urlParams.get('return') || (returnUrlInput ? returnUrlInput.value : '/');
                const returnUrl = getSafeReturnUrl(rawReturnUrl);
                window.location.href = returnUrl;
                return;
            }
        } catch (e) {
            // Not logged in or error, continue normally
        }

        if (!loginForm) return;

        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            // Hide previous errors
            errorDiv.style.display = 'none';
            errorDiv.textContent = '';

            // Disable button and show loading state
            loginBtn.disabled = true;
            loginBtn.textContent = 'Logging in...';

            try {
                const response = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ username, password })
                });

                if (response.ok) {
                    // Login successful
                    const rawReturnUrl = returnUrlInput ? returnUrlInput.value : '/';
                    const returnUrl = getSafeReturnUrl(rawReturnUrl);
                    window.location.href = returnUrl;
                } else {
                    // Login failed
                    const error = await response.json();
                    errorDiv.textContent = error.detail || 'Login failed. Please check your credentials.';
                    errorDiv.style.display = 'block';

                    loginBtn.disabled = false;
                    loginBtn.textContent = 'Login';
                }
            } catch (error) {
                console.error('Login error:', error);
                errorDiv.textContent = 'An error occurred. Please try again.';
                errorDiv.style.display = 'block';

                loginBtn.disabled = false;
                loginBtn.textContent = 'Login';
            }
        });
    })();
})();
