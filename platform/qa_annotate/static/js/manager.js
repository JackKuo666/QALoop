/**
 * 管理页面 JavaScript
 * 提供用户管理、数据库管理和标注配置管理功能
 */

// 全局状态
let currentSection = 'users';
let editingId = null;
let currentProjectId = null;
// 用户缓存
let usersCache = null;
// 项目懒加载状态
let projectsLoadedCount = 0;
let projectsLoading = false;
let projectsHasMore = true;
const PROJECTS_LOAD_SIZE = 20; // 每次加载的项目数量
// 项目数据集懒加载状态
let projectDatasetsLoadedCount = 0;
let projectDatasetsLoading = false;
let projectDatasetsHasMore = true;
const PROJECT_DATASETS_LOAD_SIZE = 20; // 每次加载的数据集数量
let projectDatasetsObserver = null;

// ==================== i18n 辅助函数 ====================

/**
 * 更新指定容器内的所有 i18n 翻译
 * @param {HTMLElement} container - 需要更新翻译的容器元素
 */
function updateTemplateTranslations(container) {
    if (!window.i18next) return;

    // 更新所有带有 data-i18n 属性的元素
    container.querySelectorAll('[data-i18n]').forEach(element => {
        const key = element.getAttribute('data-i18n');
        const translation = window.i18next.t(key);

        // 如果元素内有 span 元素，只更新文本节点
        if (element.children.length === 1 && element.children[0].tagName === 'SPAN') {
            const span = element.children[0];
            if (span.hasAttribute('data-i18n')) {
                span.textContent = window.i18next.t(span.getAttribute('data-i18n'));
            } else {
                element.textContent = translation;
            }
        } else {
            element.textContent = translation;
        }
    });

    // 更新带有 data-i18n-title 属性的元素的 title
    container.querySelectorAll('[data-i18n-title]').forEach(element => {
        const key = element.getAttribute('data-i18n-title');
        element.title = window.i18next.t(key);
    });

    // 更新带有 data-i18n-placeholder 属性的 placeholder
    container.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
        const key = element.getAttribute('data-i18n-placeholder');
        element.placeholder = window.i18next.t(key);
    });

    // 更新 select 选项的文本
    container.querySelectorAll('select').forEach(select => {
        select.querySelectorAll('option').forEach(option => {
            const i18nKey = option.getAttribute('data-i18n');
            if (i18nKey) {
                if (option.firstChild) {
                    option.firstChild.textContent = window.i18next.t(i18nKey);
                } else {
                    option.textContent = window.i18next.t(i18nKey);
                }
            }
        });
    });
}

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    initPaginators();
    initNavigation();
    initModals();
    initEventListeners();
    // 如果默认是用户管理section，加载用户管理模块
    if (currentSection === 'users') {
        loadUserManagement();
    }
});

// ==================== 分页器初始化 ====================

function initPaginators() {
    // 初始化项目懒加载
    initProjectsLazyLoad();
}

// ==================== 导航管理 ====================

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // 如果是跳转到用户页面的按钮，直接跳转
            if (item.id === 'goToUserBtn') {
                window.location.href = '/user';
                return;
            }
            const section = item.dataset.section;
            if (section) {
                switchSection(section);
            }
        });
    });
}

function switchSection(section) {
    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.section === section);
    });

    // 更新内容区
    document.querySelectorAll('.content-section').forEach(sec => {
        sec.classList.toggle('active', sec.id === `${section}-section`);
    });

    currentSection = section;

    // 重置各section的tab状态
    switch(section) {
        case 'users':
            loadUserManagement();
            break;
        case 'datasets':
            loadDatasetManagement();
            break;
        case 'projects':
            // 如果当前在详情页，返回项目列表
            const detailContainer = document.getElementById('project-detail-container');
            const projectsList = document.getElementById('projects-list');
            if (detailContainer && detailContainer.style.display !== 'none') {
                // 在详情页，返回列表
                resetProjectsTabs();
            }
            // 重置项目管理页面的tab状态
            resetProjectsTabs();
            // 确保懒加载已初始化
            if (!projectsObserver) {
                initProjectsLazyLoad();
            } else {
                // 重置懒加载状态并重新加载
                projectsLoadedCount = 0;
                projectsHasMore = true;
                const container = document.getElementById('projectsCardContainer');
                if (container) container.innerHTML = `<div class="loading" style="text-align: center; padding: 40px; color: #999;">${t('common.loading')}</div>`;
                loadProjects(true);
            }
            break;
        case 'annotation-configs':
            loadAnnotationConfigManagement();
            break;
        case 'seed-questions':
            loadSeedQuestionManagement();
            break;
        case 'system-config':
            loadSystemConfigManagement();
            break;
    }
}


function resetProjectsTabs() {
    // 重置项目管理页面到项目列表状态
    const projectsList = document.getElementById('projects-list');
    const detailContainer = document.getElementById('project-detail-container');

    if (projectsList) projectsList.style.display = 'flex';
    if (detailContainer) {
        detailContainer.style.display = 'none';
        detailContainer.innerHTML = ''; // 清空详情页内容
    }

    currentProjectId = null;
}

// ==================== 模态框管理 ====================

function initModals() {
    const modal = document.getElementById('modal');
    const closeBtn = document.getElementById('modalClose');
    const cancelBtn = document.getElementById('modalCancel');

    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
}

function openModal(title, content, onSubmit, hideSubmit = false) {
    const modal = document.getElementById('modal');
    const modalTitle = document.getElementById('modalTitle');
    const modalBody = document.getElementById('modalBody');
    const submitBtn = document.getElementById('modalSubmit');
    const cancelBtn = document.getElementById('modalCancel');

    modalTitle.textContent = title;
    modalBody.innerHTML = content;
    modal.classList.add('active');

    // 控制提交按钮显示/隐藏
    if (hideSubmit) {
        submitBtn.style.display = 'none';
    } else {
        submitBtn.style.display = 'inline-block';
        // 移除旧的事件监听器
        const newSubmitBtn = submitBtn.cloneNode(true);
        submitBtn.parentNode.replaceChild(newSubmitBtn, submitBtn);

        // 添加新的事件监听器
        document.getElementById('modalSubmit').addEventListener('click', async () => {
            if (onSubmit) {
                await onSubmit();
            }
        });
    }
}

function closeModal() {
    const modal = document.getElementById('modal');
    modal.classList.remove('active');
    editingId = null;
}

// ==================== 事件监听器 ====================

function initEventListeners() {
    // 退出登录
    document.getElementById('logoutBtn').addEventListener('click', () => {
        if (confirm(t('actions.confirmLogout'))) {
            clearToken();
            window.location.href = '/auth';
        }
    });

    // 监听从项目管理页面保存数据集的事件
    window.addEventListener('datasetSavedFromProject', (event) => {
        const { projectId } = event.detail;
        // 如果当前在项目管理页面且是同一个项目，刷新数据
        if (currentSection === 'projects' && currentProjectId === projectId) {
            loadProjectDatasets(projectId, true);
        }
    });

    // 项目管理
    document.getElementById('addProjectBtn').addEventListener('click', () => {
        showProjectForm();
    });
    document.getElementById('importProjectBtn').addEventListener('click', () => {
        showImportProjectForm();
    });
    document.getElementById('showProjectUsageBtn').addEventListener('click', () => {
        showProjectUsage();
    });

    // 使用事件委托处理动态加载的详情页按钮
    document.addEventListener('click', (e) => {
        // 处理详情页内的按钮点击
        if (e.target.id === 'addDatasetToProjectBtn' || e.target.closest('#addDatasetToProjectBtn')) {
            if (currentProjectId) {
                showAddDatasetToProjectModal();
            }
        } else if (e.target.id === 'importDatasetToProjectBtn' || e.target.closest('#importDatasetToProjectBtn')) {
            if (currentProjectId) {
                showImportDatasetToProjectForm();
            }
        } else if (e.target.id === 'exportProjectAnnotationsBtn' || e.target.closest('#exportProjectAnnotationsBtn')) {
            if (currentProjectId) {
                exportProjectAnnotations(currentProjectId);
            }
        } else if (e.target.id === 'addConfigToProjectBtn' || e.target.closest('#addConfigToProjectBtn')) {
            if (currentProjectId) {
                showAddConfigToProjectModal();
            }
        }
        // 处理项目详情内的子标签页切换（数据集管理/配置管理）
        else if (e.target.closest('#project-detail-container .project-tabs .tab-btn')) {
            const btn = e.target.closest('.tab-btn');
            if (btn && btn.dataset.tab) {
                switchProjectDetailTab(btn.dataset.tab);
            }
        }
    });
}

// ==================== 用户管理模块加载 ====================

async function loadUserManagement() {
    const container = document.getElementById('user-management-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/user-management.html');
        if (!htmlResponse.ok) {
            throw new Error('加载用户管理HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/user-management.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/user-management.js');

        // 初始化模块
        if (window.UserManagement) {
            window.UserManagement.init(container);
        }
    } catch (error) {
        console.error('加载用户管理模块失败:', error);
        showError('加载用户管理模块失败: ' + (error.message || '未知错误'));
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
    const existingScript = document.getElementById(scriptId);

    if (existingScript) {
        // 如果脚本元素已存在，等待它加载完成
        if (existingScript.complete || existingScript.readyState === 'complete' || existingScript.readyState === 'loaded') {
            return Promise.resolve();
        }
        // 等待现有脚本的onload事件
        return new Promise((resolve) => {
            existingScript.addEventListener('load', resolve);
            existingScript.addEventListener('error', resolve); // 即使失败也继续
            // 如果脚本已经加载完成但事件没触发，设置一个超时
            setTimeout(resolve, 100);
        });
    }

    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.id = scriptId;
        script.src = src;
        script.onload = resolve;
        script.onerror = () => {
            console.error('Failed to load script:', src);
            resolve(); // 即使失败也继续，让后续代码处理错误
        };
        document.head.appendChild(script);
    });
}

// ==================== 数据库管理模块加载 ====================

async function loadDatasetManagement() {
    const container = document.getElementById('dataset-management-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/dataset-management.html');
        if (!htmlResponse.ok) {
            throw new Error('加载数据库管理HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/dataset-management.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/dataset-management.js');

        // 初始化模块
        if (window.DatasetManagement) {
            window.DatasetManagement.init(container);
        }
    } catch (error) {
        console.error('加载数据库管理模块失败:', error);
        showError('加载数据库管理模块失败: ' + (error.message || '未知错误'));
    }
}

// 确保 DatasetManagement 模块已加载（仅加载 JS，不加载 HTML/CSS）
async function ensureDatasetManagementLoaded() {
    // 如果模块已存在，直接返回
    if (window.DatasetManagement) {
        return Promise.resolve();
    }

    try {
        // 只加载 JS 脚本
        await ensureScriptLoaded('/static/js/dataset-management.js');

        // 等待模块初始化
        let retries = 0;
        while (!window.DatasetManagement && retries < 10) {
            await new Promise(resolve => setTimeout(resolve, 100));
            retries++;
        }

        if (!window.DatasetManagement) {
            throw new Error('DatasetManagement 模块加载超时');
        }

        return Promise.resolve();
    } catch (error) {
        console.error('加载 DatasetManagement 模块失败:', error);
        showError('加载数据库管理模块失败: ' + (error.message || '未知错误'));
        throw error;
    }
}

// 从项目管理页面编辑数据库
async function editDatasetFromProject(datasetId) {
    try {
        // 确保模块已加载
        await ensureDatasetManagementLoaded();

        // 保存当前项目ID，用于保存成功后刷新数据
        const projectIdToRefresh = currentProjectId;

        // 设置标志，表示从项目管理页面调用
        window._editingDatasetFromProject = true;
        window._projectIdToRefresh = projectIdToRefresh;

        // 调用编辑方法（不切换标签页）
        if (window.DatasetManagement && window.DatasetManagement.editDataset) {
            await window.DatasetManagement.editDataset(datasetId);
        } else {
            throw new Error('DatasetManagement.editDataset 方法不可用');
        }
    } catch (error) {
        console.error('编辑数据库失败:', error);
        showError('编辑数据库失败: ' + (error.message || '未知错误'));
        // 清除标志
        window._editingDatasetFromProject = false;
        window._projectIdToRefresh = null;
    }
}

// ==================== 标注配置管理模块加载 ====================

async function loadAnnotationConfigManagement() {
    const container = document.getElementById('annotation-config-management-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/annotation-config-management.html');
        if (!htmlResponse.ok) {
            throw new Error('加载标注配置管理HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/annotation-config-management.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/annotation-config-management.js');

        // 初始化模块
        if (window.AnnotationConfigManagement) {
            window.AnnotationConfigManagement.init(container);
        }
    } catch (error) {
        console.error('加载标注配置管理模块失败:', error);
        showError('加载标注配置管理模块失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 种子问题管理模块加载 ====================

async function loadSeedQuestionManagement() {
    const container = document.getElementById('seed-question-management-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/seed-question-management.html');
        if (!htmlResponse.ok) {
            throw new Error('加载种子问题管理HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/seed-question-management.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/seed-question-management.js');

        // 初始化模块
        if (window.SeedQuestionManagement) {
            window.SeedQuestionManagement.init(container);
        }
    } catch (error) {
        console.error('加载种子问题管理模块失败:', error);
        showError('加载种子问题管理模块失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 系统配置管理模块加载 ====================

async function loadSystemConfigManagement() {
    const container = document.getElementById('system-config-management-container');
    if (!container) return;

    // 如果已加载，直接返回
    if (container.innerHTML.trim() !== '') {
        return;
    }

    try {
        // 加载HTML
        const htmlResponse = await fetch('/system-config-management.html');
        if (!htmlResponse.ok) {
            throw new Error('加载系统配置管理HTML失败');
        }
        container.innerHTML = await htmlResponse.text();

        // 立即更新模板中的翻译
        if (window.updateTemplateTranslations) {
            window.updateTemplateTranslations(container);
        }

        // 加载CSS（如果未加载）
        await ensureStylesheetLoaded('/static/css/system-config-management.css');

        // 加载JS（如果未加载）
        await ensureScriptLoaded('/static/js/system-config-management.js');

        // 初始化模块
        if (window.SystemConfigManagement) {
            window.SystemConfigManagement.init(container);
        }
    } catch (error) {
        console.error('加载系统配置管理模块失败:', error);
        showError('加载系统配置管理模块失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 导出项目所有标注 ====================

async function exportProjectAnnotations(projectId) {
    // 显示格式选择对话框
    const title = '导出项目所有标注';
    const content = `
        <form id="exportProjectForm">
            <div class="form-group">
                <label>导出格式 *</label>
                <select id="exportProjectFormat" required>
                    <option value="json">JSON格式（完整数据）</option>
                    <option value="csv">CSV格式（表格数据）</option>
                </select>
                <small style="color: #666; display: block; margin-top: 4px;">
                    JSON格式包含完整的标注结果和QA对信息，适合程序处理。<br>
                    CSV格式是扁平化的表格数据，适合在Excel中查看和分析。<br>
                    将导出项目下所有数据集的标注，每个数据集使用数据集名称命名。
                </small>
            </div>
        </form>
    `;

    openModal(title, content, async () => {
        await handleExportProjectAnnotations(projectId);
    });
}

async function handleExportProjectAnnotations(projectId) {
    const format = document.getElementById('exportProjectFormat').value;

    if (!format) {
        showError('请选择导出格式');
        return;
    }

    try {
        // 获取token
        const token = getToken();
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        // 构建导出URL
        const exportUrl = `${API_BASE_URL}/projects/${projectId}/export-annotations?format=${format}`;

        // 使用fetch下载文件
        const response = await fetch(exportUrl, {
            method: 'GET',
            headers: headers
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: '导出失败' }));
            throw new Error(errorData.detail || errorData.message || `HTTP错误: ${response.status}`);
        }

        // 获取文件名（从Content-Disposition头中提取，或使用默认名称）
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `project_${projectId}_annotations.zip`;
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        // 获取文件内容
        const blob = await response.blob();

        // 创建下载链接
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();

        // 清理
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showSuccess(`项目所有标注已导出为ZIP格式（${format.toUpperCase()}）`);
        closeModal();

    } catch (error) {
        console.error('导出失败:', error);
        // 如果是401未授权错误，清除token并跳转到登录页
        if (error.status === 401 || (error.message && error.message.includes('401'))) {
            clearToken();
            const currentPath = window.location.pathname;
            if (currentPath !== '/auth') {
                const redirectUrl = encodeURIComponent(window.location.href);
                window.location.href = `/auth?redirect=${redirectUrl}`;
            }
        }
        showError('导出失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 显示项目用法说明 ====================

function showProjectUsage() {
    // 构建通用的项目功能说明内容
    const usageContent = `
        <div style="max-width: 800px; line-height: 1.6;">
            <div style="margin-bottom: 20px;">
                <h3 style="color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 8px;">
                    ${t('project.usageGuide')}
                </h3>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin-top: 10px;">
                    <h4 style="margin-top: 0; color: #2196F3;">${t('project.usage.section1.title')}</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>${t('project.usage.section1.item1')}</li>
                        <li>${t('project.usage.section1.item2')}</li>
                        <li>${t('project.usage.section1.item3')}</li>
                        <li>${t('project.usage.section1.item4')}</li>
                        <li>${t('project.usage.section1.item5')}</li>
                        <li>${t('project.usage.section1.item6')}</li>
                    </ul>

                    <h4 style="margin-top: 15px; color: #2196F3;">${t('project.usage.section2.title')}</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>${t('project.usage.section2.item1')}</li>
                        <li>${t('project.usage.section2.item2')}</li>
                        <li>${t('project.usage.section2.item3')}</li>
                        <li>${t('project.usage.section2.item4')}</li>
                    </ul>

                    <h4 style="margin-top: 15px; color: #2196F3;">${t('project.usage.section3.title')}</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>${t('project.usage.section3.item1')}</li>
                        <li>${t('project.usage.section3.item2')}</li>
                        <li>${t('project.usage.section3.item3')}</li>
                        <li>${t('project.usage.section3.item4')}</li>
                    </ul>

                    <h4 style="margin-top: 15px; color: #2196F3;">${t('project.usage.section4.title')}</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>可以将现有数据集添加到项目中</li>
                        <li>支持从JSONL文件导入数据集到项目，支持批量导入多个文件</li>
                        <li>数据集会自动继承项目的标注配置（如果数据集没有自己的配置）</li>
                        <li>可以查看和管理项目下的所有数据集，包括数据集的统计信息</li>
                        <li>支持从项目中移除数据集（移除后，数据集的project_id会被设为NULL）</li>
                    </ul>

                    <h4 style="margin-top: 15px; color: #2196F3;">${t('project.usage.section5.title')}</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>${t('project.usage.section5.item1')}</li>
                        <li>${t('project.usage.section5.item2')}</li>
                        <li>${t('project.usage.section5.item3')}</li>
                        <li>${t('project.usage.section5.item4')}</li>
                        <li>${t('project.usage.section5.item5')}</li>
                    </ul>

                    <h4 style="margin-top: 15px; color: #2196F3;">${t('project.usage.section6.title')}</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>${t('project.usage.section6.item1')}</li>
                        <li>${t('project.usage.section6.item2')}</li>
                        <li>${t('project.usage.section6.item3')}</li>
                    </ul>

                    <h4 style="margin-top: 15px; color: #2196F3;">${t('project.usage.section7.title')}</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>${t('project.usage.section7.item1')}</li>
                        <li>${t('project.usage.section7.item2')}</li>
                        <li>${t('project.usage.section7.item3')}</li>
                        <li>${t('project.usage.section7.item4')}</li>
                        <li>${t('project.usage.section7.item5')}</li>
                    </ul>
                </div>
            </div>

            <div style="margin-bottom: 20px;">
                <h3 style="color: #333; border-bottom: 2px solid #FF9800; padding-bottom: 8px;">
                    ${t('project.usage.bestPractices.title')}
                </h3>
                <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #FF9800; margin-top: 10px;">
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li><strong>${t('project.usage.bestPractices.configOrder')}:</strong>${t('project.usage.bestPractices.configOrderDesc')}</li>
                        <li><strong>${t('project.usage.bestPractices.inheritance')}:</strong>${t('project.usage.bestPractices.inheritanceDesc')}</li>
                        <li><strong>${t('project.usage.bestPractices.batchImport')}:</strong>${t('project.usage.bestPractices.batchImportDesc')}</li>
                        <li><strong>${t('project.usage.bestPractices.backup')}:</strong>${t('project.usage.bestPractices.backupDesc')}</li>
                        <li><strong>${t('project.usage.bestPractices.management')}:</strong>${t('project.usage.bestPractices.managementDesc')}</li>
                    </ul>
                </div>
            </div>
        </div>
    `;

    // 显示对话框（隐藏提交按钮，只显示关闭按钮）
    openModal(t('project.usageGuide'), usageContent, null, true);
}

// ==================== 工具函数 ====================

function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '-';
    try {
        const date = new Date(dateTimeStr);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (error) {
        return dateTimeStr;
    }
}

function showSuccess(message) {
    showMessage(message, 'success');
}

function showError(message) {
    showMessage(message, 'error');
}

function showMessage(message, type = 'info') {
    // 创建消息元素
    const messageEl = document.createElement('div');
    messageEl.className = `message ${type} show`;
    messageEl.textContent = message;
    messageEl.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 2000;
        padding: 16px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        animation: slideDown 0.3s ease-out;
        max-width: 400px;
    `;

    // 添加样式
    if (type === 'success') {
        messageEl.style.background = '#d4edda';
        messageEl.style.color = '#155724';
        messageEl.style.border = '1px solid #c3e6cb';
    } else if (type === 'error') {
        messageEl.style.background = '#f8d7da';
        messageEl.style.color = '#721c24';
        messageEl.style.border = '1px solid #f5c6cb';
    } else {
        messageEl.style.background = '#d1ecf1';
        messageEl.style.color = '#0c5460';
        messageEl.style.border = '1px solid #bee5eb';
    }

    document.body.appendChild(messageEl);

    // 3秒后自动移除
    setTimeout(() => {
        messageEl.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            if (messageEl.parentNode) {
                messageEl.parentNode.removeChild(messageEl);
            }
        }, 300);
    }, 3000);
}

// ==================== 项目管理 ====================

let projectsObserver = null;

function initProjectsLazyLoad() {
    // 如果已经初始化过，先清理
    if (projectsObserver) {
        const loader = document.getElementById('projectsLoader');
        if (loader) {
            projectsObserver.unobserve(loader);
        }
    }

    // 使用 Intersection Observer 监听滚动到底部
    const container = document.getElementById('projectsCardContainer');
    if (!container) return;

    // 创建或获取加载指示器
    let loader = document.getElementById('projectsLoader');
    if (!loader) {
        loader = document.createElement('div');
        loader.id = 'projectsLoader';
        loader.className = 'projects-loader';
        loader.style.display = 'none';
        loader.innerHTML = `<div class="loading" style="text-align: center; padding: 20px; color: #999;">${t('common.loading')}</div>`;

        const projectsList = document.getElementById('projects-list');
        if (projectsList) {
            projectsList.appendChild(loader);
        }
    }

    // 创建 Intersection Observer
    projectsObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && projectsHasMore && !projectsLoading) {
                loadProjects(false);
            }
        });
    }, {
        root: null,
        rootMargin: '100px', // 提前100px开始加载
        threshold: 0.1
    });

    // 观察加载指示器
    projectsObserver.observe(loader);

    // 初始加载（如果还没有加载过）
    if (projectsLoadedCount === 0) {
        loadProjects(true);
    }
}

async function loadProjects(reset = false) {
    if (projectsLoading || (!projectsHasMore && !reset)) return;

    projectsLoading = true;
    const loader = document.getElementById('projectsLoader');
    if (loader) loader.style.display = 'block';

    try {
        const skip = reset ? 0 : projectsLoadedCount;
        const limit = PROJECTS_LOAD_SIZE;
        const projects = await getProjects(skip, limit);

        if (reset) {
            projectsLoadedCount = 0;
            const container = document.getElementById('projectsCardContainer');
            if (container) container.innerHTML = '';
        }

        if (projects.length === 0) {
            projectsHasMore = false;
            if (loader) loader.style.display = 'none';
            const container = document.getElementById('projectsCardContainer');
            if (container && container.children.length === 0) {
                container.innerHTML = `<div class="loading" style="text-align: center; padding: 40px; color: #999;">${t('project.noProjects')}</div>`;
            }
            projectsLoading = false;
            return;
        }

        // 判断是否还有更多数据
        if (projects.length < limit) {
            projectsHasMore = false;
        } else {
            // 尝试获取下一页来判断是否还有更多数据
            try {
                const nextPage = await getProjects(skip + limit, 1);
                projectsHasMore = nextPage.length > 0;
            } catch (error) {
                projectsHasMore = true; // 出错时假设还有更多
            }
        }

        projectsLoadedCount += projects.length;
        await renderProjectsTable(projects, reset);

        // 如果没有更多数据，隐藏加载指示器
        if (!projectsHasMore && loader) {
            loader.style.display = 'none';
        }
    } catch (error) {
        console.error('加载项目失败:', error);
        showError('加载项目失败: ' + (error.message || '未知错误'));
        if (loader) loader.style.display = 'none';
    } finally {
        projectsLoading = false;
    }
}

async function renderProjectsTable(projects, reset = false) {
    const container = document.getElementById('projectsCardContainer');
    if (!container) return;

    // 获取每个项目的统计信息
    const projectsWithStats = await Promise.all(projects.map(async (project) => {
        try {
            const stats = await getProjectStats(project.id);
            return { ...project, datasets_count: stats.datasets_count || 0, configs_count: stats.configs_count || 0 };
        } catch (error) {
            return { ...project, datasets_count: 0, configs_count: 0 };
        }
    }));

    const cardsHTML = projectsWithStats.map(project => `
        <div class="project-card">
            <div class="project-card-header">
                <div class="project-card-title-section">
                    <h3 class="project-card-title">${escapeHtml(project.name)}</h3>
                    <span class="project-card-id">ID: ${project.id}</span>
                </div>
                <span class="status-badge ${project.status === 'active' ? 'active' : 'inactive'}">
                    ${project.status || 'active'}
                </span>
            </div>
            <div class="project-card-body">
                <div class="project-card-description">
                    ${escapeHtml(project.description || t('common.description') || '-')}
                </div>
                <div class="project-card-meta">
                    <div class="project-card-meta-item">
                        <span class="project-card-meta-label">${t('project.version')}</span>
                        <span class="project-card-meta-value">${escapeHtml(project.version || '-')}</span>
                    </div>
                    <div class="project-card-meta-item">
                        <span class="project-card-meta-label">${t('project.category')}</span>
                        <span class="project-card-meta-value">${escapeHtml(project.category || '-')}</span>
                    </div>
                    <div class="project-card-meta-item">
                        <span class="project-card-meta-label">${t('common.createdAt')}</span>
                        <span class="project-card-meta-value">${formatDateTime(project.created_at)}</span>
                    </div>
                </div>
                <div class="project-card-stats">
                    <div class="project-card-stat-item">
                        <div class="project-card-stat-icon">📊</div>
                        <div class="project-card-stat-content">
                            <div class="project-card-stat-value">${project.datasets_count || 0}</div>
                            <div class="project-card-stat-label">${t('project.datasets')}</div>
                        </div>
                    </div>
                    <div class="project-card-stat-item">
                        <div class="project-card-stat-icon">⚙️</div>
                        <div class="project-card-stat-content">
                            <div class="project-card-stat-value">${project.configs_count || 0}</div>
                            <div class="project-card-stat-label">${t('project.configs')}</div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="project-card-footer">
                <button class="btn btn-sm btn-primary" onclick="viewProjectDetail(${project.id})">${t('project.viewDetail')}</button>
                <button class="btn btn-sm btn-secondary" onclick="editProject(${project.id})">${t('actions.edit')}</button>
                <button class="btn btn-sm btn-danger" onclick="deleteProjectHandler(${project.id})">${t('actions.delete')}</button>
            </div>
        </div>
    `).join('');

    if (reset) {
        container.innerHTML = cardsHTML;
    } else {
        container.insertAdjacentHTML('beforeend', cardsHTML);
    }
}

function showProjectForm(project = null) {
    editingId = project ? project.id : null;
    const title = project ? t('project.editProject') : t('project.addProject');
    const content = `
        <form id="projectForm">
            <div class="form-group">
                <label>${t('project.projectNameRequired')}</label>
                <input type="text" id="projectName" value="${project ? escapeHtml(project.name) : ''}"
                       required minlength="1" maxlength="200">
            </div>
            <div class="form-group">
                <label>${t('project.descriptionRequired')}</label>
                <textarea id="projectDescription" rows="3" maxlength="1000" required>${project ? escapeHtml(project.description || '') : ''}</textarea>
            </div>
            <div class="form-group">
                <label>${t('project.version')}</label>
                <input type="text" id="projectVersion" value="${project ? escapeHtml(project.version || '') : ''}"
                       maxlength="50">
            </div>
            <div class="form-group">
                <label>${t('common.status')}</label>
                <select id="projectStatus">
                    <option value="active" ${project && project.status === 'active' ? 'selected' : ''}>${t('status.active')}</option>
                    <option value="inactive" ${project && project.status === 'inactive' ? 'selected' : ''}>${t('status.inactive')}</option>
                    <option value="archived" ${project && project.status === 'archived' ? 'selected' : ''}>${t('status.archived')}</option>
                </select>
            </div>
            <div class="form-group">
                <label>${t('project.category')}</label>
                <input type="text" id="projectCategory" value="${project ? escapeHtml(project.category || '') : ''}"
                       maxlength="100">
            </div>
            <div class="form-group">
                <label>${t('project.tagsComma')}</label>
                <input type="text" id="projectTags" value="${project && project.tags ? project.tags.join(', ') : ''}"
                       placeholder="${t('project.tagsPlaceholder')}">
            </div>
            <div class="form-group">
                <label>数据来源</label>
                <input type="text" id="projectSource" value="${project ? escapeHtml(project.source || '') : ''}"
                       maxlength="200">
            </div>
            <div class="form-group">
                <label>数据来源URL</label>
                <input type="url" id="projectSourceUrl" value="${project ? escapeHtml(project.source_url || '') : ''}"
                       maxlength="500">
            </div>
            <div class="form-group">
                <label>要显示的extra字段（用逗号分隔）</label>
                <input type="text" id="projectDisplayExtraFields"
                       value="${project && project.display_extra_fields ? project.display_extra_fields.join(', ') : ''}"
                       placeholder="例如: field1, field2">
            </div>
            <div class="form-group">
                <label>评估目的 <span style="color: red;">*</span></label>
                <textarea id="projectEvaluationPurpose" rows="2" maxlength="500" required
                          placeholder="请输入项目的评估目的">${project && project.metadata && project.metadata.evaluation_purpose ? escapeHtml(project.metadata.evaluation_purpose) : ''}</textarea>
            </div>
            <div class="form-group">
                <label>完成时间 <span style="color: red;">*</span></label>
                <input type="datetime-local" id="projectDeadline" required
                       value="${project && project.metadata && project.metadata.deadline ? (() => {
                           const deadline = project.metadata.deadline;
                           // 将 ISO 8601 格式 (YYYY-MM-DDTHH:mm) 转换为 datetime-local 格式
                           // datetime-local 需要 YYYY-MM-DDTHH:mm 格式，但可能需要处理时区
                           if (deadline.includes('T')) {
                               return deadline.substring(0, 16); // 取前16个字符 (YYYY-MM-DDTHH:mm)
                           } else if (deadline.includes(' ')) {
                               return deadline.replace(' ', 'T').substring(0, 16);
                           }
                           return deadline;
                       })() : ''}">
                <small style="color: #666; display: block; margin-top: 4px;">
                    请填写到具体几点（例如：2024-12-31 18:00）
                </small>
            </div>
        </form>
    `;

    openModal(title, content, async () => {
        await saveProject();
    });
}

async function saveProject() {
    const name = document.getElementById('projectName').value.trim();
    const description = document.getElementById('projectDescription').value.trim();
    const version = document.getElementById('projectVersion').value.trim();
    const status = document.getElementById('projectStatus').value;
    const category = document.getElementById('projectCategory').value.trim();
    const tagsStr = document.getElementById('projectTags').value.trim();
    const source = document.getElementById('projectSource').value.trim();
    const sourceUrl = document.getElementById('projectSourceUrl').value.trim();
    const displayExtraFieldsStr = document.getElementById('projectDisplayExtraFields').value.trim();
    const evaluationPurpose = document.getElementById('projectEvaluationPurpose').value.trim();
    const deadline = document.getElementById('projectDeadline').value.trim();

    // 验证必填字段
    if (!description) {
        showError('任务描述不能为空');
        return;
    }
    if (!evaluationPurpose) {
        showError('评估目的不能为空');
        return;
    }
    if (!deadline) {
        showError('要求完成时间不能为空');
        return;
    }

    try {
        const data = {
            name,
            description: description || null,
            version: version || null,
            status: status || 'active',
            category: category || null,
            source: source || null,
            source_url: sourceUrl || null
        };

        // 处理标签
        if (tagsStr) {
            data.tags = tagsStr.split(',').map(t => t.trim()).filter(t => t);
        }

        // 处理display_extra_fields
        if (displayExtraFieldsStr) {
            data.display_extra_fields = displayExtraFieldsStr.split(',').map(f => f.trim()).filter(f => f);
        }

        // 处理元数据（评估目的和完成时间）
        const metadata = {};
        metadata.evaluation_purpose = evaluationPurpose;
        // datetime-local 格式是 YYYY-MM-DDTHH:mm，需要转换为 ISO 8601 格式
        // 如果已经是正确的格式，直接使用；否则转换
        if (deadline.includes('T')) {
            metadata.deadline = deadline.substring(0, 16); // 确保格式为 YYYY-MM-DDTHH:mm
        } else {
            metadata.deadline = deadline.replace(' ', 'T').substring(0, 16);
        }
        data.metadata = metadata;

        if (editingId) {
            await updateProject(editingId, data);
            showSuccess('项目更新成功');
        } else {
            await createProject(data);
            showSuccess('项目创建成功');
        }

        closeModal();
        if (!editingId) {
            // 重置并重新加载项目列表
            projectsLoadedCount = 0;
            projectsHasMore = true;
            const container = document.getElementById('projectsCardContainer');
            if (container) container.innerHTML = '<div class="loading" style="text-align: center; padding: 40px; color: #999;">加载中...</div>';
            loadProjects(true);
        } else {
            // 编辑项目后，刷新当前显示的项目卡片
            loadProjects(true);
        }

        // 如果正在查看项目详情，刷新详情视图
        if (editingId && currentProjectId === editingId) {
            await viewProjectDetail(editingId);
        }
    } catch (error) {
        showError('保存失败: ' + (error.message || '未知错误'));
    }
}

async function editProject(projectId) {
    try {
        const project = await getProject(projectId);
        showProjectForm(project);
    } catch (error) {
        showError('加载项目失败: ' + (error.message || '未知错误'));
    }
}

async function deleteProjectHandler(projectId) {
    try {
        // 获取项目信息和数据集列表
        const project = await getProject(projectId, true, false);
        const datasets = await getProjectDatasets(projectId, 0, 1000);
        const datasetsCount = datasets.length;

        // 显示选择对话框
        const title = t('project.deleteProject');
        const projectName = project.name || `${t('project.project')} ${projectId}`;

        let datasetsInfo = '';
        if (datasetsCount > 0) {
            const datasetsList = datasets.slice(0, 5).map(d => escapeHtml(d.name || `${t('dataset.dataset')} ${d.id}`)).join(t('common.comma'));
            const moreText = datasetsCount > 5 ? t('project.totalDatasets', { count: datasetsCount }) : '';
            datasetsInfo = `
                <div style="margin-top: 12px; padding: 12px; background: #f5f5f5; border-radius: 4px;">
                    <div style="font-weight: bold; margin-bottom: 8px;">${t('project.projectContainsDatasets')}:</div>
                    <div style="color: #666; font-size: 13px;">${datasetsList}${moreText}</div>
                </div>
            `;
        }

        const content = `
            <div style="margin-bottom: 16px;">
                <p>${t('project.selectAction')}:</p>
                <p style="color: #666; font-size: 14px; margin-top: 8px;">
                    ${t('project.projectLabel')}: <strong>${escapeHtml(projectName)}</strong> (ID: ${projectId})
                </p>
                ${datasetsInfo}
            </div>
            <form id="deleteProjectForm">
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 12px; border: 2px solid #2196F3; border-radius: 4px; margin-bottom: 12px;">
                        <input type="radio" name="deleteAction" value="remove" checked style="margin: 0; width: auto; height: auto;">
                        <div style="flex: 1;">
                            <div style="font-weight: bold; margin-bottom: 4px;">${t('project.deleteProjectOnly')}</div>
                            <div style="color: #666; font-size: 12px;">${t('project.deleteProjectOnlyDesc')}</div>
                        </div>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 12px; border: 2px solid #d32f2f; border-radius: 4px;">
                        <input type="radio" name="deleteAction" value="delete" style="margin: 0; width: auto; height: auto;">
                        <div style="flex: 1;">
                            <div style="font-weight: bold; margin-bottom: 4px; color: #d32f2f;">${t('project.deleteProjectAndDatasets')}</div>
                            <div style="color: #666; font-size: 12px;">${t('project.deleteProjectAndDatasetsDesc', { count: datasetsCount })}</div>
                        </div>
                    </label>
                </div>
            </form>
        `;

        openModal(title, content, async () => {
            const modalBody = document.getElementById('modalBody');
            const selectedAction = modalBody.querySelector('input[name="deleteAction"]:checked');
            if (!selectedAction) {
                showError(t('project.selectActionRequired'));
                return;
            }
            const action = selectedAction.value;
            await handleDeleteProjectAction(projectId, action, datasets);
        });
    } catch (error) {
        showError(t('project.loadProjectInfoFailed') + ': ' + (error.message || t('common.unknownError')));
    }
}

async function handleDeleteProjectAction(projectId, action, datasets) {
    try {
        if (action === 'delete') {
            // 先删除所有数据集
            if (datasets && datasets.length > 0) {
                // 关闭选择对话框，显示删除进度
                closeModal();
                showMessage(`${t('project.deletingDatasets', { count: datasets.length })}...`, 'info');

                let successCount = 0;
                let failCount = 0;
                const errors = [];

                for (const dataset of datasets) {
                    try {
                        await apiDelete(`/datasets/${dataset.id}`);
                        successCount++;
                    } catch (error) {
                        failCount++;
                        errors.push(`${t('dataset.dataset')} ${dataset.name || dataset.id}: ${error.message || t('actions.delete') + t('common.failed')}`);
                        console.error(`${t('project.deleteDatasetFailed')} ${dataset.id}:`, error);
                    }
                }

                if (failCount > 0) {
                    showError(`${t('project.deleteDatasetError')}: ${t('project.success')} ${successCount} ${t('common.count')}, ${t('common.failed')} ${failCount} ${t('common.count')}. ${t('project.projectDeleteCancelled')}.`);
                    if (errors.length > 0) {
                        console.error(t('project.deleteDatasetErrorDetails'), errors);
                    }
                    return;
                }
            }
        }

        // 删除项目
        await deleteProject(projectId);
        showSuccess(action === 'delete' ? t('project.projectAndDatasetsDeleted') : t('project.projectDeleted'));

        // 如果模态框还在打开状态，关闭它
        if (action === 'remove' || (action === 'delete' && (!datasets || datasets.length === 0))) {
            closeModal();
        }

        // 重置并重新加载项目列表
        projectsLoadedCount = 0;
        projectsHasMore = true;
        const container = document.getElementById('projectsCardContainer');
        if (container) container.innerHTML = `<div class="loading" style="text-align: center; padding: 40px; color: #999;">${t('common.loading')}</div>`;
        loadProjects(true);
    } catch (error) {
        const actionText = action === 'delete' ? t('project.deleteProjectAndDatasets') : t('project.deleteProjectOnly');
        showError(`${actionText}${t('common.failed')}: ` + (error.message || t('common.unknownError')));
    }
}

async function viewProjectDetail(projectId) {
    currentProjectId = projectId;
    try {
        const projectsList = document.getElementById('projects-list');
        const detailContainer = document.getElementById('project-detail-container');

        if (!projectsList || !detailContainer) {
            showError('页面元素未找到');
            return;
        }

        // 隐藏项目列表，显示详情页容器
        projectsList.style.display = 'none';
        detailContainer.style.display = 'block';

        // 如果详情页内容未加载，则动态加载
        if (detailContainer.innerHTML.trim() === '') {
            try {
                const response = await fetch('/project-detail.html');
                if (!response.ok) {
                    throw new Error('加载详情页失败');
                }
                const html = await response.text();
                detailContainer.innerHTML = html;

                // 更新模板中的 i18n 翻译
                updateTemplateTranslations(detailContainer);
            } catch (error) {
                console.error('加载详情页HTML失败:', error);
                showError('加载详情页失败: ' + (error.message || '未知错误'));
                // 恢复显示项目列表
                projectsList.style.display = 'flex';
                detailContainer.style.display = 'none';
                return;
            }
        }

        // 加载项目详情数据
        const project = await getProject(projectId, true, true);
        const stats = await getProjectStats(projectId);

        // 填充项目信息
        const detailContent = detailContainer.querySelector('#projectDetailContent');
        if (detailContent) {
            detailContent.querySelector('#projectDetailId').textContent = project.id;
            detailContent.querySelector('#projectDetailName').textContent = project.name || '-';
            detailContent.querySelector('#projectDetailTitle').textContent = project.name || t('project.projectDetail');
            detailContent.querySelector('#projectDetailVersion').textContent = project.version || '-';

            // 状态显示为带样式的标签
            const statusElement = detailContent.querySelector('#projectDetailStatus');
            const statusValue = project.status || 'active';
            statusElement.textContent = t(`status.${statusValue}`);
            statusElement.className = 'project-info-value status-badge ' + (statusValue === 'active' ? 'active' : 'inactive');

            detailContent.querySelector('#projectDetailCategory').textContent = project.category || '-';
            detailContent.querySelector('#projectDetailCreator').textContent = project.creator || '-';
            detailContent.querySelector('#projectDetailCreatedAt').textContent = formatDateTime(project.created_at);
            detailContent.querySelector('#projectDetailUpdatedAt').textContent = formatDateTime(project.updated_at);
            detailContent.querySelector('#projectDetailDescription').textContent = project.description || t('common.noDescription');

            // 显示评估目的和完成时间（从metadata中读取）
            const evaluationPurpose = project.metadata && project.metadata.evaluation_purpose ? project.metadata.evaluation_purpose : '-';
            const deadline = project.metadata && project.metadata.deadline ? formatDateTime(project.metadata.deadline) : '-';
            detailContent.querySelector('#projectDetailEvaluationPurpose').textContent = evaluationPurpose;
            detailContent.querySelector('#projectDetailDeadline').textContent = deadline;

            detailContent.querySelector('#projectDetailDatasetsCount').textContent = stats.datasets_count || 0;
            detailContent.querySelector('#projectDetailConfigsCount').textContent = stats.configs_count || 0;
        }

        // 重置数据集懒加载状态
        projectDatasetsLoadedCount = 0;
        projectDatasetsHasMore = true;
        projectDatasetsLoading = false;

        // 加载数据集和配置
        loadProjectDatasets(projectId, true);
        loadProjectConfigs(projectId);
    } catch (error) {
        console.error('加载项目详情失败:', error);
        showError('加载项目详情失败: ' + (error.message || '未知错误'));
        // 恢复显示项目列表
        const projectsList = document.getElementById('projects-list');
        const detailContainer = document.getElementById('project-detail-container');
        if (projectsList) projectsList.style.display = 'flex';
        if (detailContainer) detailContainer.style.display = 'none';
    }
}

function switchToProjectsList() {
    resetProjectsTabs();
}

function switchProjectDetailTab(tab) {
    // 切换项目详情内的子标签页（数据集管理/配置管理/标注结果分析）
    const detailContainer = document.getElementById('project-detail-container');
    if (!detailContainer) return;

    detailContainer.querySelectorAll('.project-tabs .tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    detailContainer.querySelectorAll('.project-tabs .tab-content').forEach(content => {
        content.classList.toggle('active', content.id === tab);
    });

    // 如果切换到分析Tab，加载分析数据
    if (tab === 'project-analysis' && currentProjectId) {
        loadAnnotationAnalysis(currentProjectId);
    }
}

// 加载标注结果分析
async function loadAnnotationAnalysis(projectId) {
    try {
        // 确保CSS已加载
        await ensureStylesheetLoaded('/static/css/annotation-analysis.css');

        // 确保JS已加载
        await ensureScriptLoaded('/static/js/annotation-analysis.js');

        // 等待一小段时间确保脚本完全解析
        await new Promise(resolve => setTimeout(resolve, 100));

        // 检查 Chart.js 是否可用（已在 HTML 中预加载）
        if (typeof Chart === 'undefined') {
            console.error('Chart.js 未加载！请检查 manager.html 中的 Chart.js 引入');
            const container = document.getElementById('analysisConfigsContainer');
            if (container) {
                container.innerHTML = `<div style="color: red; text-align: center; padding: 40px;">${t('project.chartLibLoadFailed')}</div>`;
            }
            return;
        }

        // 初始化分析页面
        if (window.AnnotationAnalysis) {
            window.AnnotationAnalysis.init(projectId);
        } else {
            console.error('AnnotationAnalysis未定义！');
            // 显示错误信息
            const container = document.getElementById('analysisConfigsContainer');
            if (container) {
                container.innerHTML = '<div style="color: red; text-align: center; padding: 40px;">加载分析模块失败，请刷新页面重试</div>';
            }
        }
    } catch (error) {
        console.error('加载标注结果分析时出错:', error);
        const container = document.getElementById('analysisConfigsContainer');
        if (container) {
            container.innerHTML = `<div style="color: red; text-align: center; padding: 40px;">${t('project.loadFailed')}: ${error.message}</div>`;
        }
    }
}

// 辅助函数：在详情页容器中查找元素
function getDetailElement(id) {
    const detailContainer = document.getElementById('project-detail-container');
    if (!detailContainer) return null;
    return detailContainer.querySelector(`#${id}`);
}

async function loadProjectDatasets(projectId, reset = false) {
    if (projectDatasetsLoading || (!projectDatasetsHasMore && !reset)) return;

    projectDatasetsLoading = true;
    const loader = getDetailElement('projectDatasetsLoader');
    if (loader) loader.style.display = 'block';

    try {
        const skip = reset ? 0 : projectDatasetsLoadedCount;
        const limit = PROJECT_DATASETS_LOAD_SIZE;
        const datasets = await getProjectDatasets(projectId, skip, limit);

        if (reset) {
            projectDatasetsLoadedCount = 0;
            const container = getDetailElement('projectDatasetsCardContainer');
            if (container) container.innerHTML = '';
        }

        if (datasets.length === 0) {
            projectDatasetsHasMore = false;
            if (loader) loader.style.display = 'none';
            const container = getDetailElement('projectDatasetsCardContainer');
            if (container && container.children.length === 0) {
                container.innerHTML = `<div class="loading" style="text-align: center; padding: 40px; color: #999; grid-column: 1 / -1;">${t('dataset.noDatasets')}</div>`;
            }
            projectDatasetsLoading = false;
            return;
        }

        if (datasets.length < limit) {
            projectDatasetsHasMore = false;
        }

        projectDatasetsLoadedCount += datasets.length;
        renderProjectDatasetsCards(datasets, reset);

        if (loader) loader.style.display = 'none';
        projectDatasetsLoading = false;

        // 初始化懒加载（如果还没有初始化）
        if (reset) {
            initProjectDatasetsLazyLoad(projectId);
        }
    } catch (error) {
        console.error('加载项目数据集失败:', error);
        showError('加载项目数据集失败: ' + (error.message || '未知错误'));
        if (loader) loader.style.display = 'none';
        projectDatasetsLoading = false;
    }
}

function renderProjectDatasetsCards(datasets, reset = false) {
    const detailContainer = document.getElementById('project-detail-container');
    if (!detailContainer) return;

    const container = detailContainer.querySelector('#projectDatasetsCardContainer');
    if (!container) return;

    if (datasets.length === 0 && reset) {
        container.innerHTML = `<div class="loading" style="text-align: center; padding: 40px; color: #999; grid-column: 1 / -1;">${t('dataset.noDatasets')}</div>`;
        return;
    }

    const cardsHTML = datasets.map(dataset => `
        <div class="project-card" data-dataset-id="${dataset.id}">
            <div class="project-card-header">
                <div class="project-card-title-section">
                    <h3 class="project-card-title">${escapeHtml(dataset.name)}</h3>
                    <span class="project-card-id">ID: ${dataset.id}</span>
                </div>
                <span class="status-badge ${dataset.status === 'active' ? 'active' : 'inactive'}">
                    ${dataset.status || 'active'}
                </span>
            </div>
            <div class="project-card-body">
                <div class="project-card-description">
                    ${escapeHtml(dataset.description || t('common.description') || '-')}
                </div>
                <div class="project-card-annotation-progress" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e0e0e0;">
                    <div class="loading" style="text-align: center; padding: 8px; color: #999; font-size: 12px;">${t('common.loading')}</div>
                </div>
                <div class="project-card-meta">
                    <div class="project-card-meta-item">
                        <span class="project-card-meta-label">${t('project.version')}</span>
                        <span class="project-card-meta-value">${escapeHtml(dataset.version || '-')}</span>
                    </div>
                    <div class="project-card-meta-item">
                        <span class="project-card-meta-label">${t('project.annotator')}</span>
                        <span class="project-card-meta-value">${escapeHtml(dataset.annotator_name || '-')}</span>
                    </div>
                </div>
            </div>
            <div class="project-card-footer">
                <button class="btn btn-sm btn-success" onclick="window.location.href='/annotation?dataset_id=${dataset.id}'">${t('dataset.annotate')}</button>
                <button class="btn btn-sm btn-primary" onclick="editDatasetFromProject(${dataset.id})">${t('actions.edit')}</button>
                <button class="btn btn-sm btn-danger" onclick="removeDatasetFromProjectHandler(${currentProjectId}, ${dataset.id})">${t('actions.remove')}</button>
            </div>
        </div>
    `).join('');

    if (reset) {
        container.innerHTML = cardsHTML;
    } else {
        container.insertAdjacentHTML('beforeend', cardsHTML);
    }

    // 异步加载每个数据集的标注进度
    datasets.forEach(async dataset => {
        try {
            // 使用 DatasetManagement 模块的方法
            const progress = window.DatasetManagement
                ? await window.DatasetManagement.getDatasetAnnotationProgress(dataset.id)
                : await apiGet(`/datasets/${dataset.id}/annotation-progress`).catch(() => null);
            const card = container.querySelector(`[data-dataset-id="${dataset.id}"]`);
            if (card) {
                const progressContainer = card.querySelector('.project-card-annotation-progress');
                if (progressContainer) {
                    if (progress) {
                        const progressHtml = window.DatasetManagement
                            ? window.DatasetManagement.renderAnnotationProgress(progress)
                            : (() => {
                                // Fallback 函数，如果模块未加载
                                if (!progress || progress.total_items === 0) {
                                    return `<span style="color: #999;">${t('common.noData')}</span>`;
                                }
                                const overallRate = progress.overall_progress_rate || 0;
                                const progressColor = overallRate >= 80 ? '#2e7d32' : overallRate >= 50 ? '#f57c00' : '#d32f2f';

                                let html = `
                                    <div style="display: flex; flex-direction: column; gap: 4px;">
                                        <div style="display: flex; align-items: center; gap: 8px;">
                                            <div style="flex: 1; height: 8px; background: #e0e0e0; border-radius: 4px; overflow: hidden;">
                                                <div style="height: 100%; width: ${overallRate}%; background: ${progressColor}; transition: width 0.3s;"></div>
                                            </div>
                                            <span style="font-size: 12px; color: ${progressColor}; font-weight: bold; min-width: 50px;">
                                                ${overallRate.toFixed(1)}%
                                            </span>
                                        </div>
                                        <div style="font-size: 11px; color: #666;">
                                            ${progress.annotated_items || 0} / ${progress.total_items}
                                        </div>
                                `;

                                // 显示各个配置的进度条
                                if (progress.config_progress && progress.config_progress.length > 0) {
                                    const configDetails = progress.config_progress.map(cp => {
                                        const cpColor = cp.progress_rate >= 80 ? '#2e7d32' : cp.progress_rate >= 50 ? '#f57c00' : '#d32f2f';
                                        return `
                                            <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                                                <span style="font-size: 11px; color: #666; min-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${cp.config_name}">
                                                    ${cp.config_name}:
                                                </span>
                                                <div style="flex: 1; height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden;">
                                                    <div style="height: 100%; width: ${cp.progress_rate}%; background: ${cpColor};"></div>
                                                </div>
                                                <span style="font-size: 11px; color: ${cpColor}; min-width: 45px;">
                                                    ${cp.progress_rate.toFixed(1)}%
                                                </span>
                                            </div>
                                        `;
                                    }).join('');

                                    html += `
                                        <details style="margin-top: 4px;" open>
                                            <summary style="cursor: pointer; font-size: 11px; color: #1976d2; user-select: none;">
                                                ${t('common.viewDetails')}
                                            </summary>
                                            <div style="margin-top: 8px; padding: 8px; background: #f5f5f5; border-radius: 4px;">
                                                ${configDetails}
                                            </div>
                                        </details>
                                    `;
                                }

                                html += '</div>';
                                return html;
                            })();
                        progressContainer.innerHTML = progressHtml;
                    } else {
                        progressContainer.innerHTML = `<div style="text-align: center; padding: 8px; color: #999; font-size: 12px;">${t('common.noData')}</div>`;
                    }
                }
            }
        } catch (error) {
            console.error(`加载数据集 ${dataset.id} 的标注进度失败:`, error);
            const card = container.querySelector(`[data-dataset-id="${dataset.id}"]`);
            if (card) {
                const progressContainer = card.querySelector('.project-card-annotation-progress');
                if (progressContainer) {
                    progressContainer.innerHTML = `<div style="text-align: center; padding: 8px; color: #999; font-size: 12px;">${t('common.loadFailed')}</div>`;
                }
            }
        }
    });
}

function initProjectDatasetsLazyLoad(projectId) {
    // 如果已经初始化过，先清理
    if (projectDatasetsObserver) {
        const loader = getDetailElement('projectDatasetsLoader');
        if (loader) {
            projectDatasetsObserver.unobserve(loader);
        }
    }

    // 使用 Intersection Observer 监听滚动到底部
    const container = getDetailElement('projectDatasetsCardContainer');
    if (!container) return;

    // 创建或获取加载指示器
    let loader = getDetailElement('projectDatasetsLoader');
    if (!loader) {
        loader = document.createElement('div');
        loader.id = 'projectDatasetsLoader';
        loader.style.display = 'none';
        loader.style.textAlign = 'center';
        loader.style.padding = '20px';
        loader.style.color = '#999';
        loader.innerHTML = '<div class="loading">加载中...</div>';

        const detailContainer = document.getElementById('project-detail-container');
        const datasetsTab = detailContainer?.querySelector('#project-datasets');
        if (datasetsTab) {
            datasetsTab.appendChild(loader);
        }
    }

    // 创建 Intersection Observer
    projectDatasetsObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && projectDatasetsHasMore && !projectDatasetsLoading) {
                loadProjectDatasets(projectId, false);
            }
        });
    }, {
        root: null,
        rootMargin: '100px', // 提前100px开始加载
        threshold: 0.1
    });

    // 观察加载指示器
    projectDatasetsObserver.observe(loader);
}

async function showAddDatasetToProjectModal() {
    try {
        // 获取所有数据集
        const allDatasets = await apiGet('/datasets/?skip=0&limit=1000');
        // 获取项目当前的数据集
        const projectDatasets = await getProjectDatasets(currentProjectId, 0, 1000);
        const projectDatasetIds = new Set(projectDatasets.map(d => d.id));

        // 过滤出未关联的数据集
        const availableDatasets = allDatasets.filter(d => !projectDatasetIds.has(d.id));

        if (availableDatasets.length === 0) {
            showError('没有可添加的数据集');
            return;
        }

        const content = `
            <form id="addDatasetToProjectForm">
                <div class="form-group">
                    <label>选择数据集 *</label>
                    <select id="datasetSelectForProject" required>
                        <option value="">请选择数据集...</option>
                        ${availableDatasets.map(d => `
                            <option value="${d.id}">${escapeHtml(d.name)} (ID: ${d.id})</option>
                        `).join('')}
                    </select>
                </div>
            </form>
        `;

        openModal('添加数据集到项目', content, async () => {
            const datasetId = parseInt(document.getElementById('datasetSelectForProject').value);
            if (!datasetId) {
                showError('请选择数据集');
                return;
            }
            await addDatasetToProjectHandler(currentProjectId, datasetId);
        });
    } catch (error) {
        showError('加载数据集列表失败: ' + (error.message || '未知错误'));
    }
}

async function addDatasetToProjectHandler(projectId, datasetId) {
    try {
        await addDatasetToProject(projectId, datasetId);
        showSuccess('数据集已添加到项目');
        closeModal();
        // 重置懒加载状态并重新加载
        projectDatasetsLoadedCount = 0;
        projectDatasetsHasMore = true;
        loadProjectDatasets(projectId, true);
        // 更新统计信息
        const stats = await getProjectStats(projectId);
        const datasetsCountEl = getDetailElement('projectDetailDatasetsCount');
        if (datasetsCountEl) datasetsCountEl.textContent = stats.datasets_count || 0;
    } catch (error) {
        showError('添加数据集失败: ' + (error.message || '未知错误'));
    }
}

async function removeDatasetFromProjectHandler(projectId, datasetId) {
    try {
        // 获取数据集信息以显示名称
        const dataset = await apiGet(`/datasets/${datasetId}`);
        const datasetName = dataset.name || `数据集 ${datasetId}`;

        // 显示选择对话框
        const title = '移除数据集';
        const content = `
            <div style="margin-bottom: 16px;">
                <p>请选择操作方式：</p>
                <p style="color: #666; font-size: 14px; margin-top: 8px;">
                    数据集：<strong>${escapeHtml(datasetName)}</strong> (ID: ${datasetId})
                </p>
            </div>
            <form id="removeDatasetForm">
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 12px; border: 2px solid #2196F3; border-radius: 4px; margin-bottom: 12px;">
                        <input type="radio" name="removeAction" value="remove" checked style="margin: 0; width: auto; height: auto;">
                        <div style="flex: 1;">
                            <div style="font-weight: bold; margin-bottom: 4px;">仅移出项目</div>
                            <div style="color: #666; font-size: 12px;">数据集将从项目中移除，但不会被删除，仍可在数据集管理中查看</div>
                        </div>
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 12px; border: 2px solid #d32f2f; border-radius: 4px;">
                        <input type="radio" name="removeAction" value="delete" style="margin: 0; width: auto; height: auto;">
                        <div style="flex: 1;">
                            <div style="font-weight: bold; margin-bottom: 4px; color: #d32f2f;">删除数据集</div>
                            <div style="color: #666; font-size: 12px;">数据集将被永久删除，包括所有关联的QA对，此操作不可恢复</div>
                        </div>
                    </label>
                </div>
            </form>
        `;

        openModal(title, content, async () => {
            const modalBody = document.getElementById('modalBody');
            const selectedAction = modalBody.querySelector('input[name="removeAction"]:checked');
            if (!selectedAction) {
                showError('请选择操作方式');
                return;
            }
            const action = selectedAction.value;
            await handleRemoveDatasetAction(projectId, datasetId, action);
        });
    } catch (error) {
        showError('加载数据集信息失败: ' + (error.message || '未知错误'));
    }
}

async function handleRemoveDatasetAction(projectId, datasetId, action) {
    try {
        if (action === 'remove') {
            // 仅移出项目
            await removeDatasetFromProject(projectId, datasetId);
            showSuccess('数据集已从项目移除');
        } else if (action === 'delete') {
            // 删除数据集
            await apiDelete(`/datasets/${datasetId}`);
            showSuccess('数据集已删除');
        }

        closeModal();

        // 重置懒加载状态并重新加载
        projectDatasetsLoadedCount = 0;
        projectDatasetsHasMore = true;
        loadProjectDatasets(projectId, true);

        // 更新统计信息
        const stats = await getProjectStats(projectId);
        const datasetsCountEl = getDetailElement('projectDetailDatasetsCount');
        if (datasetsCountEl) datasetsCountEl.textContent = stats.datasets_count || 0;
    } catch (error) {
        const actionText = action === 'remove' ? '移除' : '删除';
        showError(`${actionText}数据集失败: ` + (error.message || '未知错误'));
    }
}

// ==================== 导入数据集到项目 ====================

// 加载用户列表（用于下拉选择）
async function loadUsersForSelect() {
    if (usersCache) {
        return usersCache;
    }
    try {
        const users = await apiGet('/users/?skip=0&limit=1000');
        usersCache = users;
        return users;
    } catch (error) {
        console.error('加载用户列表失败:', error);
        return [];
    }
}

async function showImportDatasetToProjectForm() {
    if (!currentProjectId) {
        showError('请先选择项目');
        return;
    }

    // 加载用户列表
    const users = await loadUsersForSelect();
    const userOptions = '<option value="">无</option>' + users.map(user =>
        `<option value="${user.id}">${escapeHtml(user.username)}${user.full_name ? ' (' + escapeHtml(user.full_name) + ')' : ''}</option>`
    ).join('');

    const title = '导入数据集到项目';
    const content = `
        <form id="importDatasetToProjectForm">
            <div class="form-group">
                <label>选择JSONL文件 *</label>
                <input type="file" id="importDatasetToProjectFile" accept=".jsonl" multiple required>
                <small style="color: #666; display: block; margin-top: 4px;">
                    可以选择多个.jsonl格式的文件，每个文件将作为一个数据集导入
                </small>
                <div id="importDatasetToProjectFilesList" style="margin-top: 12px; display: none;">
                    <h4 style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold;">已选择的文件：</h4>
                    <div id="importDatasetToProjectFilesPreview" style="max-height: 200px; overflow-y: auto; border: 1px solid #e0e0e0; padding: 8px; border-radius: 4px;"></div>
                </div>
            </div>
            <div style="border-top: 1px solid #e0e0e0; margin: 16px 0; padding-top: 16px;">
                <h4 style="margin: 0 0 12px 0; font-size: 14px; font-weight: bold;">数据集元数据（可选）</h4>
                <small style="color: #666; display: block; margin-bottom: 12px;">
                    如果填写了以下字段，将优先使用这些值，而不是文件中的元数据
                </small>
                <div class="form-group">
                    <label>数据集名称 *</label>
                    <input type="text" id="importDatasetToProjectName" placeholder="如果不填写，将使用文件名">
                </div>
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="importDatasetToProjectDescription" rows="2" placeholder="数据集描述"></textarea>
                </div>
                <div class="form-group">
                    <label>版本</label>
                    <input type="text" id="importDatasetToProjectVersion" placeholder="例如: 1.0">
                </div>
                <div class="form-group">
                    <label>分类</label>
                    <input type="text" id="importDatasetToProjectCategory" placeholder="数据集分类">
                </div>
                <div class="form-group">
                    <label>状态</label>
                    <select id="importDatasetToProjectStatus">
                        <option value="active">激活</option>
                        <option value="inactive">禁用</option>
                        <option value="archived">归档</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>标签（逗号分隔）</label>
                    <input type="text" id="importDatasetToProjectTags" placeholder="例如: 标签1,标签2,标签3">
                </div>
                <div class="form-group">
                    <label>数据来源</label>
                    <input type="text" id="importDatasetToProjectSource" placeholder="数据来源">
                </div>
                <div class="form-group">
                    <label>来源URL</label>
                    <input type="url" id="importDatasetToProjectSourceUrl" placeholder="https://example.com">
                </div>
                <div class="form-group">
                    <label>标注者</label>
                    <select id="importDatasetToProjectAnnotatorId">
                        ${userOptions}
                    </select>
                    <small style="color: #666; display: block; margin-top: 4px;">
                        指定负责标注该数据集的用户（可选）
                    </small>
                </div>
            </div>
            <div class="form-group">
                <div id="importDatasetToProjectProgress" style="display: none;">
                    <p style="color: #666;">正在导入，请稍候...</p>
                </div>
                <div id="importDatasetToProjectResult" style="display: none;"></div>
            </div>
        </form>
    `;

    openModal(title, content, async () => {
        await handleImportDatasetToProject();
    });

    // 设置文件选择监听
    const fileInput = document.getElementById('importDatasetToProjectFile');
    const filesList = document.getElementById('importDatasetToProjectFilesList');
    const filesPreview = document.getElementById('importDatasetToProjectFilesPreview');

    fileInput.addEventListener('change', () => {
        const files = Array.from(fileInput.files);
        if (files.length === 0) {
            filesList.style.display = 'none';
            return;
        }

        filesList.style.display = 'block';
        filesPreview.innerHTML = files.map((file, index) => `
            <div style="padding: 4px 0; border-bottom: 1px solid #f0f0f0;">
                <span style="font-weight: bold;">${index + 1}.</span> ${escapeHtml(file.name)}
            </div>
        `).join('');
    });
}

async function handleImportDatasetToProject() {
    if (!currentProjectId) {
        showError('请先选择项目');
        return;
    }

    const fileInput = document.getElementById('importDatasetToProjectFile');
    const files = Array.from(fileInput.files);

    if (files.length === 0) {
        showError('请至少选择一个文件');
        return;
    }

    // 验证文件格式
    for (const file of files) {
        if (!file.name.endsWith('.jsonl')) {
            showError(`文件 ${file.name} 不是.jsonl格式`);
            return;
        }
    }

    // 收集元数据（这些将应用到所有文件）
    const name = document.getElementById('importDatasetToProjectName').value.trim();
    const description = document.getElementById('importDatasetToProjectDescription').value.trim();
    const version = document.getElementById('importDatasetToProjectVersion').value.trim();
    const category = document.getElementById('importDatasetToProjectCategory').value.trim();
    const status = document.getElementById('importDatasetToProjectStatus').value;
    const tags = document.getElementById('importDatasetToProjectTags').value.trim();
    const source = document.getElementById('importDatasetToProjectSource').value.trim();
    const sourceUrl = document.getElementById('importDatasetToProjectSourceUrl').value.trim();
    const annotatorIdInput = document.getElementById('importDatasetToProjectAnnotatorId').value;
    const annotatorId = annotatorIdInput ? parseInt(annotatorIdInput) : null;

    // 显示进度
    const progressDiv = document.getElementById('importDatasetToProjectProgress');
    const resultDiv = document.getElementById('importDatasetToProjectResult');
    progressDiv.style.display = 'block';
    resultDiv.style.display = 'none';

    try {
        // 使用导入项目的API，但指定project_id
        const formData = new FormData();
        files.forEach(file => {
            formData.append('files', file);
        });

        formData.append('project_id', currentProjectId);
        if (name) formData.append('dataset_name_prefix', name);
        if (description) formData.append('project_description', description);
        if (version) formData.append('project_version', version);
        if (category) formData.append('project_category', category);
        if (status) formData.append('project_status', status);
        if (tags) formData.append('project_tags', tags);
        if (source) formData.append('project_source', source);
        if (sourceUrl) formData.append('project_source_url', sourceUrl);
        if (annotatorId) formData.append('annotator_id', annotatorId);

        // 调用导入项目API
        const result = await importProject(formData);

        // 隐藏进度，显示结果
        progressDiv.style.display = 'none';
        resultDiv.style.display = 'block';

        const successMsg = `导入完成！成功导入 ${result.successful_files}/${result.total_files} 个文件到项目 "${result.project_name}"，共 ${result.total_imported} 条QA对，失败 ${result.total_failed} 条`;

        let resultHtml = `<p style="color: #2e7d32; font-weight: bold;">${successMsg}</p>`;

        if (result.file_results && result.file_results.length > 0) {
            resultHtml += '<details style="margin-top: 12px;"><summary style="cursor: pointer; font-weight: bold;">文件导入详情</summary>';
            resultHtml += '<div style="margin-top: 8px; max-height: 300px; overflow-y: auto;">';
            resultHtml += result.file_results.map(r => {
                if (r.success) {
                    return `<div style="padding: 4px 0; border-bottom: 1px solid #f0f0f0;">
                        <strong>${escapeHtml(r.filename)}</strong>: 成功导入 ${r.imported_count} 条，失败 ${r.failed_count} 条
                        ${r.errors && r.errors.length > 0 ? `<div style="color: #d32f2f; font-size: 12px; margin-left: 20px;">${r.errors.slice(0, 3).map(e => escapeHtml(e)).join('<br>')}</div>` : ''}
                    </div>`;
                } else {
                    return `<div style="padding: 4px 0; border-bottom: 1px solid #f0f0f0; color: #d32f2f;">
                        <strong>${escapeHtml(r.filename)}</strong>: 导入失败 - ${escapeHtml(r.error || '未知错误')}
                    </div>`;
                }
            }).join('');
            resultHtml += '</div></details>';
        }

        if (result.errors && result.errors.length > 0) {
            resultHtml += `<details style="margin-top: 12px;"><summary style="cursor: pointer; color: #d32f2f; font-weight: bold;">错误详情 (显示前${Math.min(result.errors.length, 10)}个)</summary>`;
            resultHtml += `<ul style="margin-top: 8px; padding-left: 20px; max-height: 200px; overflow-y: auto;">`;
            resultHtml += result.errors.slice(0, 10).map(err => `<li style="color: #d32f2f; margin: 4px 0;">${escapeHtml(err)}</li>`).join('');
            resultHtml += '</ul></details>';
        }

        resultDiv.innerHTML = resultHtml;

        // 刷新项目数据集列表
        if (result.total_imported > 0) {
            setTimeout(() => {
                projectDatasetsLoadedCount = 0;
                projectDatasetsHasMore = true;
                loadProjectDatasets(currentProjectId, true);
                // 更新统计信息
                getProjectStats(currentProjectId).then(stats => {
                    const datasetsCountEl = getDetailElement('projectDetailDatasetsCount');
                    if (datasetsCountEl) datasetsCountEl.textContent = stats.datasets_count || 0;
                });
            }, 1000);
        }

        // 3秒后自动关闭模态框
        setTimeout(() => {
            closeModal();
        }, 3000);

    } catch (error) {
        progressDiv.style.display = 'none';
        // 如果是401未授权错误，清除token并跳转到登录页
        if (error.status === 401) {
            clearToken();
            const currentPath = window.location.pathname;
            if (currentPath !== '/auth') {
                const redirectUrl = encodeURIComponent(window.location.href);
                window.location.href = `/auth?redirect=${redirectUrl}`;
            }
        }
        showError('导入失败: ' + (error.message || '未知错误'));
    }
}

async function loadProjectConfigs(projectId) {
    try {
        const configs = await getProjectConfigs(projectId);
        renderProjectConfigsTable(configs);
    } catch (error) {
        console.error('Failed to load project configs:', error);
        showError(t('project.loadConfigsFailed') + ': ' + (error.message || t('common.unknownError')));
    }
}

function renderProjectConfigsTable(configs) {
    const detailContainer = document.getElementById('project-detail-container');
    if (!detailContainer) return;

    const tbody = detailContainer.querySelector('#projectConfigsTableBody');
    if (!tbody) return;

    if (configs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="loading">${t('project.noConfigs')}</td></tr>`;
        return;
    }

    tbody.innerHTML = configs.map((config, index) => `
        <tr data-config-id="${config.id}">
            <td style="text-align: center;">
                <div style="display: flex; flex-direction: column; gap: 4px; align-items: center;">
                    <button
                        class="btn btn-sm btn-secondary"
                        onclick="moveConfigOrder(${currentProjectId}, ${config.id}, 'up')"
                        ${index === 0 ? 'disabled' : ''}
                        style="padding: 2px 6px; font-size: 10px; min-width: auto;"
                        title="${t('actions.moveUp')}"
                    >↑</button>
                    <span style="font-size: 12px; color: #666; min-width: 20px; text-align: center;">${index + 1}</span>
                    <button
                        class="btn btn-sm btn-secondary"
                        onclick="moveConfigOrder(${currentProjectId}, ${config.id}, 'down')"
                        ${index === configs.length - 1 ? 'disabled' : ''}
                        style="padding: 2px 6px; font-size: 10px; min-width: auto;"
                        title="${t('actions.moveDown')}"
                    >↓</button>
                </div>
            </td>
            <td>${config.id}</td>
            <td>${escapeHtml(config.name)}</td>
            <td>${escapeHtml(config.annotation_type || config.type || '-')}</td>
            <td>${escapeHtml(config.description || '-')}</td>
            <td><span class="status-badge ${config.required ? 'active' : 'inactive'}">
                ${config.required ? t('common.yes') : t('common.no')}
            </span></td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="removeConfigFromProjectHandler(${currentProjectId}, ${config.id})">${t('actions.remove')}</button>
            </td>
        </tr>
    `).join('');
}

async function showAddConfigToProjectModal() {
    try {
        // 获取所有标注配置
        const allConfigs = await apiGet('/annotation-configs/?skip=0&limit=1000');
        // 获取项目当前的配置
        const projectConfigs = await getProjectConfigs(currentProjectId);
        const projectConfigIds = new Set(projectConfigs.map(c => c.id));

        // 过滤出未关联的配置
        const availableConfigs = allConfigs.filter(c => !projectConfigIds.has(c.id));

        if (availableConfigs.length === 0) {
            showError(t('project.noAvailableConfigs'));
            return;
        }

        const content = `
            <form id="addConfigToProjectForm">
                <div class="form-group">
                    <label>${t('project.selectConfig')} *</label>
                    <select id="configSelectForProject" required>
                        <option value="">${t('project.selectConfigPlaceholder')}...</option>
                        ${availableConfigs.map(c => `
                            <option value="${c.id}">${escapeHtml(c.name)} (ID: ${c.id}, ${t('config.configType')}: ${c.annotation_type || c.type || '-'})</option>
                        `).join('')}
                    </select>
                </div>
            </form>
        `;

        openModal(t('project.addConfigToProject'), content, async () => {
            const configId = parseInt(document.getElementById('configSelectForProject').value);
            if (!configId) {
                showError(t('project.selectConfigRequired'));
                return;
            }
            await addConfigToProjectHandler(currentProjectId, configId);
        });
    } catch (error) {
        showError(t('project.loadConfigsListFailed') + ': ' + (error.message || t('common.unknownError')));
    }
}

async function addConfigToProjectHandler(projectId, configId) {
    try {
        await addConfigToProject(projectId, configId);
        showSuccess('标注配置已添加到项目');
        closeModal();
        loadProjectConfigs(projectId);
        // 更新统计信息
        const stats = await getProjectStats(projectId);
        const configsCountEl = getDetailElement('projectDetailConfigsCount');
        if (configsCountEl) configsCountEl.textContent = stats.configs_count || 0;
    } catch (error) {
        showError('添加标注配置失败: ' + (error.message || '未知错误'));
    }
}

async function removeConfigFromProjectHandler(projectId, configId) {
    if (!confirm('确定要从项目中移除这个标注配置吗？')) {
        return;
    }

    try {
        await removeConfigFromProject(projectId, configId);
        showSuccess('标注配置已从项目移除');
        loadProjectConfigs(projectId);
        // 更新统计信息
        const stats = await getProjectStats(projectId);
        const configsCountEl = getDetailElement('projectDetailConfigsCount');
        if (configsCountEl) configsCountEl.textContent = stats.configs_count || 0;
    } catch (error) {
        showError('移除标注配置失败: ' + (error.message || '未知错误'));
    }
}

async function moveConfigOrder(projectId, configId, direction) {
    try {
        await apiPost(`/projects/${projectId}/configs/${configId}/move?direction=${direction}`);
        showSuccess('顺序调整成功');
        loadProjectConfigs(projectId);
    } catch (error) {
        showError('调整顺序失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 导入项目 ====================

function showImportProjectForm() {
    const title = '导入项目';
    const content = `
        <form id="importProjectForm">
            <div class="form-group">
                <label>选择JSONL文件 *</label>
                <input type="file" id="importProjectFiles" accept=".jsonl" multiple required>
                <small style="color: #666; display: block; margin-top: 4px;">
                    可以选择多个.jsonl格式的文件，每个文件将作为一个数据集导入
                </small>
                <div id="importProjectFilesList" style="margin-top: 12px; display: none;">
                    <h4 style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold;">已选择的文件：</h4>
                    <div id="importProjectFilesPreview" style="max-height: 200px; overflow-y: auto; border: 1px solid #e0e0e0; padding: 8px; border-radius: 4px;"></div>
                </div>
            </div>

            <div style="border-top: 1px solid #e0e0e0; margin: 16px 0; padding-top: 16px;">
                <h4 style="margin: 0 0 12px 0; font-size: 14px; font-weight: bold;">导入模式</h4>
                <div class="form-group" style="display: flex; gap: 24px; align-items: center; flex-wrap: nowrap;">
                    <label style="display: inline-flex; align-items: center; gap: 6px; cursor: pointer; margin: 0; white-space: nowrap; flex-shrink: 0;">
                        <input type="radio" name="importMode" value="new" checked style="margin: 0; width: auto; height: auto; flex-shrink: 0;">
                        <span>创建新项目</span>
                    </label>
                    <label style="display: inline-flex; align-items: center; gap: 6px; cursor: pointer; margin: 0; white-space: nowrap; flex-shrink: 0;">
                        <input type="radio" name="importMode" value="existing" style="margin: 0; width: auto; height: auto; flex-shrink: 0;">
                        <span>导入到现有项目</span>
                    </label>
                </div>
                <div id="existingProjectSelect" style="display: none; margin-top: 12px;">
                    <label>选择项目 *</label>
                    <select id="importProjectExistingId" class="form-control">
                        <option value="">请选择项目...</option>
                    </select>
                </div>
            </div>

            <div id="newProjectInfoSection" style="border-top: 1px solid #e0e0e0; margin: 16px 0; padding-top: 16px;">
                <h4 style="margin: 0 0 12px 0; font-size: 14px; font-weight: bold;">项目信息（创建新项目时必填）</h4>
                <div class="form-group">
                    <label>项目名称 *</label>
                    <input type="text" id="importProjectName" placeholder="项目名称" required>
                </div>
                <div class="form-group">
                    <label>描述 <span style="color: red;">*</span></label>
                    <textarea id="importProjectDescription" rows="2" placeholder="项目描述" required></textarea>
                </div>
                <div class="form-group">
                    <label>版本</label>
                    <input type="text" id="importProjectVersion" placeholder="例如: 1.0">
                </div>
                <div class="form-group">
                    <label>状态</label>
                    <select id="importProjectStatus">
                        <option value="active">激活</option>
                        <option value="inactive">禁用</option>
                        <option value="archived">归档</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>分类</label>
                    <input type="text" id="importProjectCategory" placeholder="项目分类">
                </div>
                <div class="form-group">
                    <label>标签（逗号分隔）</label>
                    <input type="text" id="importProjectTags" placeholder="例如: 标签1,标签2,标签3">
                </div>
                <div class="form-group">
                    <label>数据来源</label>
                    <input type="text" id="importProjectSource" placeholder="数据来源">
                </div>
                <div class="form-group">
                    <label>来源URL</label>
                    <input type="url" id="importProjectSourceUrl" placeholder="https://example.com">
                </div>
                <div class="form-group">
                    <label>评估目的 <span style="color: red;">*</span></label>
                    <textarea id="importProjectEvaluationPurpose" rows="2" placeholder="请输入项目的评估目的" required></textarea>
                </div>
                <div class="form-group">
                    <label>完成时间 <span style="color: red;">*</span></label>
                    <input type="datetime-local" id="importProjectDeadline" required>
                    <small style="color: #666; display: block; margin-top: 4px;">
                        请填写到具体几点（例如：2024-12-31 18:00）
                    </small>
                </div>
            </div>

            <div style="border-top: 1px solid #e0e0e0; margin: 16px 0; padding-top: 16px;">
                <h4 style="margin: 0 0 12px 0; font-size: 14px; font-weight: bold;">数据集命名配置</h4>
                <div class="form-group">
                    <label>数据集名称前缀</label>
                    <input type="text" id="importProjectDatasetPrefix" placeholder="默认为项目名称">
                    <small style="color: #666; display: block; margin-top: 4px;">
                        数据集名称格式：{前缀}_{文件名}，如果不填写，将使用项目名称作为前缀
                    </small>
                </div>
                <div id="importProjectDatasetNames" style="margin-top: 12px; display: none;">
                    <h5 style="margin: 0 0 8px 0; font-size: 13px; font-weight: bold;">数据集名称预览（可编辑）：</h5>
                    <div id="importProjectDatasetNamesList" style="max-height: 200px; overflow-y: auto; border: 1px solid #e0e0e0; padding: 8px; border-radius: 4px;"></div>
                </div>
            </div>

            <div class="form-group">
                <div id="importProjectProgress" style="display: none;">
                    <p style="color: #666;">正在导入，请稍候...</p>
                </div>
                <div id="importProjectResult" style="display: none;"></div>
            </div>
        </form>
    `;

    openModal(title, content, async () => {
        await handleImportProject();
    });

    // 设置文件选择监听
    const fileInput = document.getElementById('importProjectFiles');
    const filesList = document.getElementById('importProjectFilesList');
    const filesPreview = document.getElementById('importProjectFilesPreview');
    const datasetNamesDiv = document.getElementById('importProjectDatasetNames');
    const datasetNamesList = document.getElementById('importProjectDatasetNamesList');
    const prefixInput = document.getElementById('importProjectDatasetPrefix');
    const projectNameInput = document.getElementById('importProjectName');
    const modeRadios = document.querySelectorAll('input[name="importMode"]');
    const existingProjectSelect = document.getElementById('existingProjectSelect');
    const existingProjectIdSelect = document.getElementById('importProjectExistingId');
    const newProjectInfoSection = document.getElementById('newProjectInfoSection');

    // 文件选择监听
    fileInput.addEventListener('change', () => {
        updateFilesPreview();
        updateDatasetNamesPreview();
    });

    // 导入模式切换
    modeRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            if (radio.value === 'existing') {
                // 导入到现有项目：显示项目选择，隐藏项目信息表单
                existingProjectSelect.style.display = 'block';
                newProjectInfoSection.style.display = 'none';
                document.getElementById('importProjectName').required = false;
                loadProjectsForSelect();
            } else {
                // 创建新项目：隐藏项目选择，显示项目信息表单
                existingProjectSelect.style.display = 'none';
                newProjectInfoSection.style.display = 'block';
                document.getElementById('importProjectName').required = true;
            }
            // 更新数据集名称预览（因为前缀可能会变化）
            updateDatasetNamesPreview();
        });
    });

    // 前缀和项目名称变化时更新数据集名称预览
    prefixInput.addEventListener('input', updateDatasetNamesPreview);
    projectNameInput.addEventListener('input', () => {
        if (!prefixInput.value.trim()) {
            updateDatasetNamesPreview();
        }
    });
    // 现有项目选择变化时也更新预览
    existingProjectIdSelect.addEventListener('change', () => {
        if (!prefixInput.value.trim()) {
            updateDatasetNamesPreview();
        }
    });

    function updateFilesPreview() {
        const files = Array.from(fileInput.files);
        if (files.length === 0) {
            filesList.style.display = 'none';
            return;
        }

        filesList.style.display = 'block';
        filesPreview.innerHTML = files.map((file, index) => `
            <div style="padding: 4px 0; border-bottom: 1px solid #f0f0f0;">
                <span style="font-weight: bold;">${index + 1}.</span> ${escapeHtml(file.name)}
            </div>
        `).join('');
    }

    function updateDatasetNamesPreview() {
        const files = Array.from(fileInput.files);
        if (files.length === 0) {
            datasetNamesDiv.style.display = 'none';
            return;
        }

        datasetNamesDiv.style.display = 'block';

        // 确定前缀：优先使用自定义前缀，否则根据模式使用项目名称
        let prefix = prefixInput.value.trim();
        if (!prefix) {
            const selectedMode = document.querySelector('input[name="importMode"]:checked').value;
            if (selectedMode === 'existing') {
                // 导入到现有项目：从下拉框获取项目名称
                const selectedOption = existingProjectIdSelect.options[existingProjectIdSelect.selectedIndex];
                prefix = selectedOption ? selectedOption.text : '项目名';
            } else {
                // 创建新项目：从输入框获取
                prefix = projectNameInput.value.trim() || '项目名';
            }
        }

        datasetNamesList.innerHTML = files.map((file, index) => {
            const filenameWithoutExt = file.name.replace(/\.(jsonl|json)$/i, '');
            const defaultName = `${prefix}_${filenameWithoutExt}`;
            return `
                <div style="padding: 8px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 8px;">
                    <span style="flex: 0 0 120px; font-size: 12px; color: #666;">${escapeHtml(file.name)}:</span>
                    <input
                        type="text"
                        class="form-control"
                        data-file-index="${index}"
                        data-filename="${escapeHtml(file.name)}"
                        value="${escapeHtml(defaultName)}"
                        style="flex: 1;"
                        placeholder="数据集名称"
                    >
                </div>
            `;
        }).join('');
    }

    async function loadProjectsForSelect() {
        try {
            const projects = await apiGet('/projects?limit=1000');
            existingProjectIdSelect.innerHTML = '<option value="">请选择项目...</option>' +
                projects.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
        } catch (error) {
            console.error('加载项目列表失败:', error);
        }
    }
}

async function handleImportProject() {
    const fileInput = document.getElementById('importProjectFiles');
    const files = Array.from(fileInput.files);

    if (files.length === 0) {
        showError('请至少选择一个文件');
        return;
    }

    // 验证文件格式
    for (const file of files) {
        if (!file.name.endsWith('.jsonl')) {
            showError(`文件 ${file.name} 不是.jsonl格式`);
            return;
        }
    }

    // 获取导入模式
    const importMode = document.querySelector('input[name="importMode"]:checked').value;
    const projectId = importMode === 'existing'
        ? document.getElementById('importProjectExistingId').value
        : null;

    if (importMode === 'existing' && !projectId) {
        showError('请选择要导入的项目');
        return;
    }

    if (importMode === 'new') {
        const projectName = document.getElementById('importProjectName').value.trim();
        if (!projectName) {
            showError('项目名称不能为空');
            return;
        }
    }

    // 收集项目信息
    const projectName = document.getElementById('importProjectName').value.trim();
    const projectDescription = document.getElementById('importProjectDescription').value.trim();
    const projectVersion = document.getElementById('importProjectVersion').value.trim();
    const projectStatus = document.getElementById('importProjectStatus').value;
    const projectCategory = document.getElementById('importProjectCategory').value.trim();
    const projectTags = document.getElementById('importProjectTags').value.trim();
    const projectSource = document.getElementById('importProjectSource').value.trim();
    const projectSourceUrl = document.getElementById('importProjectSourceUrl').value.trim();
    const projectEvaluationPurpose = document.getElementById('importProjectEvaluationPurpose').value.trim();
    const projectDeadline = document.getElementById('importProjectDeadline').value.trim();

    // 如果是创建新项目，验证必填字段
    if (importMode === 'new') {
        if (!projectDescription) {
            showError('任务描述不能为空');
            return;
        }
        if (!projectEvaluationPurpose) {
            showError('评估目的不能为空');
            return;
        }
        if (!projectDeadline) {
            showError('要求完成时间不能为空');
            return;
        }
    }
    const datasetPrefix = document.getElementById('importProjectDatasetPrefix').value.trim();

    // 收集数据集名称映射
    const nameMapping = {};
    const datasetNameInputs = document.querySelectorAll('#importProjectDatasetNamesList input[data-file-index]');
    datasetNameInputs.forEach(input => {
        const filename = input.getAttribute('data-filename');
        const datasetName = input.value.trim();
        if (datasetName) {
            nameMapping[filename] = datasetName;
        }
    });

    // 显示进度
    const progressDiv = document.getElementById('importProjectProgress');
    const resultDiv = document.getElementById('importProjectResult');
    progressDiv.style.display = 'block';
    resultDiv.style.display = 'none';

    try {
        // 构建FormData
        const formData = new FormData();
        files.forEach(file => {
            formData.append('files', file);
        });

        if (projectId) {
            formData.append('project_id', projectId);
        } else {
            if (projectName) formData.append('project_name', projectName);
            // 创建新项目时，这些字段是必填的
            formData.append('project_description', projectDescription);
            if (projectVersion) formData.append('project_version', projectVersion);
            if (projectStatus) formData.append('project_status', projectStatus);
            if (projectCategory) formData.append('project_category', projectCategory);
            if (projectTags) formData.append('project_tags', projectTags);
            if (projectSource) formData.append('project_source', projectSource);
            if (projectSourceUrl) formData.append('project_source_url', projectSourceUrl);
            formData.append('project_evaluation_purpose', projectEvaluationPurpose);
            // datetime-local 格式转换为 ISO 8601 格式
            const deadlineFormatted = projectDeadline.includes('T')
                ? projectDeadline.substring(0, 16)
                : projectDeadline.replace(' ', 'T').substring(0, 16);
            formData.append('project_deadline', deadlineFormatted);
        }

        if (datasetPrefix) {
            formData.append('dataset_name_prefix', datasetPrefix);
        }

        if (Object.keys(nameMapping).length > 0) {
            formData.append('dataset_name_mapping', JSON.stringify(nameMapping));
        }

        // 调用API
        const result = await importProject(formData);

        // 隐藏进度，显示结果
        progressDiv.style.display = 'none';
        resultDiv.style.display = 'block';

        const projectAction = result.created ? '创建' : '更新';
        const successMsg = `导入完成！${projectAction}项目 "${result.project_name}"，成功导入 ${result.successful_files}/${result.total_files} 个文件，共 ${result.total_imported} 条QA对，失败 ${result.total_failed} 条`;

        let resultHtml = `<p style="color: #2e7d32; font-weight: bold;">${successMsg}</p>`;

        if (result.file_results && result.file_results.length > 0) {
            resultHtml += '<details style="margin-top: 12px;"><summary style="cursor: pointer; font-weight: bold;">文件导入详情</summary>';
            resultHtml += '<div style="margin-top: 8px; max-height: 300px; overflow-y: auto;">';
            resultHtml += result.file_results.map(r => {
                if (r.success) {
                    return `<div style="padding: 4px 0; border-bottom: 1px solid #f0f0f0;">
                        <strong>${escapeHtml(r.filename)}</strong>: 成功导入 ${r.imported_count} 条，失败 ${r.failed_count} 条
                        ${r.errors && r.errors.length > 0 ? `<div style="color: #d32f2f; font-size: 12px; margin-left: 20px;">${r.errors.slice(0, 3).map(e => escapeHtml(e)).join('<br>')}</div>` : ''}
                    </div>`;
                } else {
                    return `<div style="padding: 4px 0; border-bottom: 1px solid #f0f0f0; color: #d32f2f;">
                        <strong>${escapeHtml(r.filename)}</strong>: 导入失败 - ${escapeHtml(r.error || '未知错误')}
                    </div>`;
                }
            }).join('');
            resultHtml += '</div></details>';
        }

        if (result.errors && result.errors.length > 0) {
            resultHtml += `<details style="margin-top: 12px;"><summary style="cursor: pointer; color: #d32f2f; font-weight: bold;">错误详情 (显示前${Math.min(result.errors.length, 10)}个)</summary>`;
            resultHtml += `<ul style="margin-top: 8px; padding-left: 20px; max-height: 200px; overflow-y: auto;">`;
            resultHtml += result.errors.slice(0, 10).map(err => `<li style="color: #d32f2f; margin: 4px 0;">${escapeHtml(err)}</li>`).join('');
            resultHtml += '</ul></details>';
        }

        resultDiv.innerHTML = resultHtml;

        // 刷新项目列表
        if (result.project_id) {
            setTimeout(() => {
                loadProjects();
                if (importMode === 'existing') {
                    // 如果导入到现有项目，刷新项目详情
                    if (currentProjectId === parseInt(result.project_id)) {
                        loadProjectDetail(result.project_id);
                    }
                }
            }, 1000);
        }

        // 3秒后自动关闭模态框
        setTimeout(() => {
            closeModal();
        }, 3000);

    } catch (error) {
        progressDiv.style.display = 'none';
        if (error.status === 401) {
            clearToken();
            const currentPath = window.location.pathname;
            if (currentPath !== '/auth') {
                const redirectUrl = encodeURIComponent(window.location.href);
                window.location.href = `/auth?redirect=${redirectUrl}`;
            }
        }
        showError('导入失败: ' + (error.message || '未知错误'));
    }
}
