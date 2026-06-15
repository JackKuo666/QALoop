/**
 * i18n 国际化辅助函数
 */

/**
 * 获取翻译文本
 * @param {string} key - 翻译键，如 'app.title'
 * @param {Object} options - i18next 选项
 * @returns {string} 翻译后的文本
 */
function t(key, options) {
    if (window.i18next && typeof window.i18next.t === 'function') {
        try {
            const result = window.i18next.t(key, options);
            // 如果返回的值等于键名，说明翻译失败，使用后备
            if (result === key) {
                console.warn(`[t] Translation failed for key: ${key}, using fallback`);
                return getFallbackText(key);
            }
            return result;
        } catch (e) {
            console.warn(`[t] Translation error for key ${key}:`, e);
            return getFallbackText(key);
        }
    }
    // 如果 i18next 未初始化，使用后备文本
    console.warn(`[t] i18next not ready for key: ${key}, using fallback`);
    return getFallbackText(key);
}

/**
 * 获取后备文本
 * @param {string} key - 翻译键
 * @returns {string} 后备文本
 */
function getFallbackText(key) {
    const fallbacks = {
        'common.loading': '加载中...',
        'actions.edit': '编辑',
        'actions.delete': '删除',
        'actions.add': '添加',
        'actions.save': '保存',
        'actions.cancel': '取消',
        'actions.confirm': '确定',
        'actions.close': '关闭',
        'actions.submit': '提交',
        'actions.refresh': '刷新',
        'actions.remove': '移除',
        'annotation.annotate': '标注',
        'annotation.score': '评分',
        'annotation.category': '分类',
        'annotation.text': '文本',
        'annotation.single_choice': '单选',
        'annotation.multi_choice': '多选',
        'annotation.binary': '二元',
        'dataset.manageConfigs': '管理标注配置',
        'dataset.addDataset': '添加数据集',
        'dataset.importDataset': '导入数据集',
        'dataset.editDataset': '编辑数据集',
        'dataset.noDatasets': '暂无数据集',
        'system.exportAnnotations': '导出标注结果',
        'common.selectDatasetFirst': '请先选择数据集',
        'status.active': '激活',
        'status.inactive': '禁用'
    };
    return fallbacks[key] || '';
}

/**
 * 更新元素的翻译内容
 * @param {string|HTMLElement} selector - CSS 选择器或 DOM 元素
 * @param {string} key - 翻译键
 * @param {Object} options - i18next 选项
 */
function updateElementTranslation(selector, key, options) {
    const element = typeof selector === 'string'
        ? document.querySelector(selector)
        : selector;

    if (element) {
        element.textContent = t(key, options);
    }
}

/**
 * 批量更新带有 data-i18n 属性的元素
 */
function updateAllTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(element => {
        const key = element.getAttribute('data-i18n');
        element.textContent = t(key);
    });
}

/**
 * 获取当前语言
 * @returns {string} 当前语言代码，如 'zh-CN' 或 'en-US'
 */
function getCurrentLanguage() {
    return window.i18next ? window.i18next.language : 'en-US';
}

/**
 * 切换语言
 * @param {string} lang - 目标语言代码，如 'en-US'
 * @param {Function} callback - 语言切换完成后的回调函数
 */
function changeLanguage(lang, callback) {
    if (window.i18next) {
        window.i18next.changeLanguage(lang, () => {
            localStorage.setItem('appLanguage', lang);
            updateAllTranslations();
            if (callback) callback();
        });
    }
}

/**
 * 切换中英文
 */
function toggleLanguage() {
    const currentLang = getCurrentLanguage();
    const newLang = currentLang === 'zh-CN' ? 'en-US' : 'zh-CN';
    changeLanguage(newLang);
}

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
