const loginForm = document.getElementById('loginForm');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const togglePassword = document.getElementById('togglePassword');
const loginBtn = document.getElementById('loginBtn');
const btnText = loginBtn.querySelector('.btn-text');
const btnSpinner = loginBtn.querySelector('.btn-spinner');
const loginMsg = document.getElementById('loginMsg');

// Toggle Password Visibility
if (togglePassword) {
    togglePassword.addEventListener('click', () => {
        const isPassword = passwordInput.getAttribute('type') === 'password';
        passwordInput.setAttribute('type', isPassword ? 'text' : 'password');
        togglePassword.className = `fa-solid ${isPassword ? 'fa-eye-slash' : 'fa-eye'} toggle-password`;
    });
}

function showLoginAlert(msg, type = 'error') {
    loginMsg.style.display = 'flex';
    loginMsg.className = `toast ${type}`;
    loginMsg.innerHTML = `<i class="fa-solid ${type === 'success' ? 'fa-circle-check' : 'fa-circle-xmark'}"></i> ${msg}`;
}

loginForm.addEventListener('submit', e => {
    e.preventDefault();

    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();

    if (!username || !password) {
        showLoginAlert('Please enter both username and password.', 'error');
        return;
    }

    // Show loading state
    btnText.style.display = 'none';
    btnSpinner.style.display = 'inline-block';
    loginBtn.disabled = true;
    loginMsg.style.display = 'none';

    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    fetch('/login', {
        method: 'POST',
        body: formData
    })
    .then(r => r.json())
    .then(res => {
        if (res.status === 'success') {
            showLoginAlert('Authentication successful! Redirecting...', 'success');
            setTimeout(() => {
                window.location.href = res.redirect || '/dashboard';
            }, 600);
        } else {
            showLoginAlert(res.msg || 'Invalid username or password.', 'error');
            btnText.style.display = 'inline-block';
            btnSpinner.style.display = 'none';
            loginBtn.disabled = false;
        }
    })
    .catch(err => {
        console.error('Login error:', err);
        showLoginAlert('Network error. Please try again.', 'error');
        btnText.style.display = 'inline-block';
        btnSpinner.style.display = 'none';
        loginBtn.disabled = false;
    });
});
