/**
 * 用户页面 JavaScript
 * 提供用户中心的基础功能
 */

// 全局状态
let currentSection = 'my-tasks';

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    checkUserRole();
    initNavigation();
    initModals();
    initEventListeners();
    // 默认加载我的任务模块
    loadUserMyTasks();
});

// ==================== 认证检查 ====================

function checkAuth() {
    if (!isLoggedIn()) {
        window.location.href = '/auth';
    }
}

// ==================== 检查用户角色 ====================

async function checkUserRole() {
    try {
        const currentUser = await apiGet('/users/me');
        if (currentUser) {
            const isAdmin = currentUser.is_superuser;

            // 显示/隐藏管理后台按钮和分隔线
            const goToManagerBtn = document.getElementById('goToManagerBtn');
            const navDivider = document.getElementById('navDivider');

            if (isAdmin) {
                if (goToManagerBtn) goToManagerBtn.classList.remove('hidden');
                if (navDivider) navDivider.classList.remove('hidden');
            }
        }
    } catch (error) {
        console.error('检查用户角色失败:', error);
    }
}

// ==================== 导航管理 ====================

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // 如果是跳转到管理页面的按钮，直接跳转
            if (item.id === 'goToManagerBtn') {
                window.location.href = '/manager';
                return;
            }
            const section = item.dataset.section;
            if (section) {
                switchSection(section);
            }
        });
    });

    // 退出登录
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            clearToken();
            window.location.href = '/auth';
        });
    }
}

function switchSection(section) {
    // 更新导航状态
    document.querySelectorAll('.nav-item[data-section]').forEach(item => {
        item.classList.toggle('active', item.dataset.section === section);
    });

    // 更新内容区
    document.querySelectorAll('.content-section').forEach(sec => {
        sec.classList.toggle('active', sec.id === `${section}-section`);
    });

    currentSection = section;

    // 根据section加载对应模块
    switch(section) {
        case 'seed-questions':
            loadUserSeedQuestion();
            break;
        case 'available-tasks':
            loadUserAvailableTasks();
            break;
        case 'my-tasks':
            loadUserMyTasks();
            break;
    }
}

// ==================== 模态框管理 ====================

function initModals() {
    const modal = document.getElementById('modal');
    const closeBtn = document.getElementById('modalClose');
    const cancelBtn = document.getElementById('modalCancel');

    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeModal);
    }
}

function openModal(title, content, onSubmit, hideSubmit = false) {
    const modal = document.getElementById('modal');
    const modalTitle = document.getElementById('modalTitle');
    const modalBody = document.getElementById('modalBody');
    const submitBtn = document.getElementById('modalSubmit');
    const cancelBtn = document.getElementById('modalCancel');

    if (modalTitle) modalTitle.textContent = title;
    if (modalBody) modalBody.innerHTML = content;
    if (submitBtn) {
        submitBtn.style.display = hideSubmit ? 'none' : 'inline-flex';
        submitBtn.onclick = onSubmit || null;
    }
    if (cancelBtn) {
        cancelBtn.onclick = closeModal;
    }
    if (modal) modal.classList.add('active');
}

function closeModal() {
    const modal = document.getElementById('modal');
    if (modal) modal.classList.remove('active');
}

// ==================== 事件监听 ====================

function initEventListeners() {
    // 可以在这里添加其他事件监听
}

// ==================== 用户种子问题模块加载 ====================

async function loadUserSeedQuestion() {
    const container = document.getElementById('user-seed-question-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/user-seed-question.html');
        if (!htmlResponse.ok) {
            throw new Error('加载种子问题HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/user-seed-question.css');
        // 加载表单样式（编辑模态框需要）
        await ensureStylesheetLoaded('/static/css/seed-question.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/user-seed-question.js');

        // 初始化模块
        if (window.UserSeedQuestion) {
            window.UserSeedQuestion.init(container);
        }
    } catch (error) {
        console.error('加载种子问题模块失败:', error);
        showError('加载种子问题模块失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 可领取任务模块加载 ====================

async function loadUserAvailableTasks() {
    const container = document.getElementById('user-available-tasks-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/user-available-tasks.html');
        if (!htmlResponse.ok) {
            throw new Error('加载可领取任务HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/user-task.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/user-available-tasks.js');

        // 初始化模块
        if (window.UserAvailableTasks) {
            window.UserAvailableTasks.init(container);
        }
    } catch (error) {
        console.error('加载可领取任务模块失败:', error);
        showError('加载可领取任务模块失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 我的任务模块加载 ====================

async function loadUserMyTasks() {
    const container = document.getElementById('user-my-tasks-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/user-my-tasks.html');
        if (!htmlResponse.ok) {
            throw new Error('加载我的任务HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/user-task.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/user-my-tasks.js');

        // 初始化模块
        if (window.UserMyTasks) {
            window.UserMyTasks.init(container);
        }
    } catch (error) {
        console.error('加载我的任务模块失败:', error);
        showError('加载我的任务模块失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 依赖加载辅助函数 ====================

// 确保样式表已加载
async function ensureStylesheetLoaded(href) {
    const linkId = href.replace(/[^a-zA-Z0-9]/g, '_');
    if (document.getElementById(linkId)) {
        return;
    }

    const link = document.createElement('link');
    link.id = linkId;
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);

    return new Promise((resolve) => {
        link.onload = resolve;
        link.onerror = resolve; // 即使失败也继续
    });
}

// 确保脚本已加载
async function ensureScriptLoaded(src) {
    const scriptId = src.replace(/[^a-zA-Z0-9]/g, '_');
    if (document.getElementById(scriptId)) {
        return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.id = scriptId;
        script.src = src;
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

// ==================== 工具函数 ====================

function showSuccess(message) {
    // 简单的成功提示，可以后续改进为更好的UI
    alert(message);
}

function showError(message) {
    // 简单的错误提示，可以后续改进为更好的UI
    alert('错误: ' + message);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
