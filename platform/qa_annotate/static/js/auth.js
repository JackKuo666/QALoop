// 工具函数：显示消息
function showMessage(elementId, message, type = 'error') {
    const messageEl = document.getElementById(elementId);
    messageEl.textContent = message;
    messageEl.className = `message ${type} show`;

    // 3秒后自动隐藏成功消息
    if (type === 'success') {
        setTimeout(() => {
            messageEl.classList.remove('show');
        }, 3000);
    }
}

// 工具函数：隐藏消息
function hideMessage(elementId) {
    const messageEl = document.getElementById(elementId);
    messageEl.classList.remove('show');
}

// 密码哈希工具函数（使用crypto-js库，兼容HTTP环境）
function sha256(message) {
    // 使用crypto-js库进行SHA-256哈希
    if (typeof CryptoJS !== 'undefined' && CryptoJS.SHA256) {
        return CryptoJS.SHA256(message).toString();
    } else {
        console.error(window.t ? window.t('error.cryptoJsNotLoaded') : 'crypto-js库未加载，请检查CDN连接');
        throw new Error(window.t ? window.t('error.encryptionLibraryNotLoaded') : '加密库未加载');
    }
}

// 翻译函数由 i18n-helper.js 提供

// 对密码进行哈希（用于注册，只做一次SHA-256）
function hashPassword(password) {
    return sha256(password);
}

// 对密码哈希加上时间戳再次哈希（用于登录，防止重放攻击）
function hashPasswordWithTimestamp(password) {
    // 第一次SHA-256
    const passwordHash = sha256(password);
    // 获取当前时间戳（秒）
    const timestamp = Math.floor(Date.now() / 1000);
    // 加上时间戳再次哈希
    const finalHash = sha256(`${passwordHash}:${timestamp}`);
    return { hash: finalHash, timestamp: timestamp };
}

// 切换表单标签
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;

        // 更新按钮状态
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // 切换表单
        document.querySelectorAll('.form-container').forEach(form => {
            form.classList.remove('active');
        });

        if (tab === 'login') {
            document.getElementById('login-form').classList.add('active');
        } else {
            document.getElementById('register-form').classList.add('active');
        }

        // 清除消息
        hideMessage('login-message');
        hideMessage('register-message');
    });
});

// 登录表单提交
document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;

    // 隐藏之前的消息
    hideMessage('login-message');

    // 禁用提交按钮
    submitBtn.disabled = true;
    submitBtn.textContent = t('common.loggingIn');

    try {
        // 对密码进行哈希+时间戳处理
        const { hash: passwordHash, timestamp } = hashPasswordWithTimestamp(password);

        // 使用通用API接口
        const data = await apiPost('/users/login', {
            username,
            password: passwordHash,
            timestamp: timestamp
        }, { requireAuth: false });

        // 登录成功
        saveToken(data.access_token);
        showMessage('login-message', t('auth.loginSuccess', { username: data.user.username }) || `登录成功！欢迎，${data.user.username}`, 'success');

        // 获取重定向URL（从URL参数中读取）
        const urlParams = new URLSearchParams(window.location.search);
        const redirectUrl = urlParams.get('redirect');

        // 2秒后跳转
        setTimeout(() => {
            if (redirectUrl) {
                // 如果有redirect参数，跳转到指定页面
                window.location.href = decodeURIComponent(redirectUrl);
            } else {
                // 否则跳转到首页
                window.location.href = '/';
            }
        }, 2000);
    } catch (error) {
        console.error(t('error.loginFailedCheckCredentials') || '登录错误:', error);
        // 显示错误信息
        const errorMessage = error.data?.detail || error.message || t('error.loginFailedCheckCredentials');
        showMessage('login-message', errorMessage, 'error');
    } finally {
        // 恢复提交按钮
        submitBtn.disabled = false;
        submitBtn.textContent = t('common.login');
    }
});

// 注册表单提交
document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value;
    const fullName = document.getElementById('register-fullname').value.trim();
    const organization = document.getElementById('register-organization').value;
    const team = document.getElementById('register-team').value.trim();
    const species = document.getElementById('register-species').value.trim();

    // 隐藏之前的消息
    hideMessage('register-message');

    // 验证输入
    if (username.length < 3) {
        showMessage('register-message', t('error.usernameMinLength'), 'error');
        return;
    }

    if (password.length < 6) {
        showMessage('register-message', t('error.passwordMinLength'), 'error');
        return;
    }

    // 禁用提交按钮
    submitBtn.disabled = true;
    submitBtn.textContent = t('common.registering');

    try {
        // 对密码进行哈希（注册时只做一次SHA-256，后端存储）
        const passwordHash = hashPassword(password);

        // 使用通用API接口
        const data = await apiPost('/users/register', {
            username,
            password: passwordHash,
            full_name: fullName || null,
            organization: organization || null,
            team: team || null,
            species: species || null
        }, { requireAuth: false });

        // 注册成功
        showMessage('register-message', t('auth.registerSuccess', { username: data.username }) || `注册成功！用户名：${data.username}`, 'success');

        // 清空表单
        form.reset();

        // 2秒后切换到登录表单
        setTimeout(() => {
            document.querySelector('.tab-btn[data-tab="login"]').click();
            document.getElementById('login-username').value = username;
        }, 2000);
    } catch (error) {
        console.error(t('error.registerFailedTryAgain') || '注册错误:', error);
        // 显示错误信息
        const errorMessage = error.data?.detail || error.message || t('error.registerFailedTryAgain');
        showMessage('register-message', errorMessage, 'error');
    } finally {
        // 恢复提交按钮
        submitBtn.disabled = false;
        submitBtn.textContent = t('common.register');
    }
});

// 页面加载时检查是否已登录
window.addEventListener('DOMContentLoaded', () => {
    if (isLoggedIn()) {
        // 如果已登录，可以显示用户信息或跳转到其他页面
        // 这里可以根据需要实现
    }
});
