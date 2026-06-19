// Login page functionality
(async function () {
    const loginForm = document.getElementById('login-form');
    const errorDiv = document.getElementById('login-error');
    const loginBtn = document.getElementById('login-btn');
    const returnUrlInput = document.getElementById('return-url');

    // Check if user is already logged in
    try {
        const authResponse = await fetch('/api/admin/settings');
        if (authResponse.ok) {
            const urlParams = new URLSearchParams(window.location.search);
            const returnUrl = urlParams.get('return') || (returnUrlInput ? returnUrlInput.value : '/');
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
                const returnUrl = returnUrlInput ? returnUrlInput.value : '/';
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
