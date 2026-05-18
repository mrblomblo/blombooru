class AdminAccount {
    constructor(adminPanel) {
        this.app = adminPanel;
    }

    async changePassword() {
        const newPassword = document.getElementById('new-admin-password').value;
        const statusDiv = document.getElementById('change-password-status');
        const resultDiv = document.getElementById('change-password-result');

        try {
            const result = await app.apiCall('/api/admin/update-admin-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password: newPassword })
            });

            statusDiv.style.display = 'block';
            resultDiv.className = 'text-success';
            resultDiv.textContent = window.i18n.t('notifications.admin.password_updated');

            // Clear the password field
            document.getElementById('new-admin-password').value = '';

            // Hide success message after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);

        } catch (error) {
            statusDiv.style.display = 'block';
            resultDiv.className = 'text-danger';
            resultDiv.textContent = error.message;
        }
    }

    async changeUsername() {
        const newUsername = document.getElementById('new-admin-username').value;
        const statusDiv = document.getElementById('change-username-status');
        const resultDiv = document.getElementById('change-username-result');

        try {
            const result = await app.apiCall('/api/admin/update-admin-username', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_username: newUsername })
            });

            statusDiv.style.display = 'block';
            resultDiv.className = 'text-success';
            resultDiv.textContent = window.i18n.t('notifications.admin.username_updated', { username: result.new_username });

            // Update displayed username if you show it anywhere
            app.showNotification(window.i18n.t('notifications.admin.username_updated', { username: result.new_username }), 'success');

            // Clear the username field
            document.getElementById('new-admin-username').value = '';

            // Hide success message after 3 seconds
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);

        } catch (error) {
            statusDiv.style.display = 'block';
            resultDiv.className = 'text-danger';
            resultDiv.textContent = error.message;
        }
    }

}
