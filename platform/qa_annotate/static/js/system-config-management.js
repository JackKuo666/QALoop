/**
 * 系统配置管理模块 JavaScript
 * 提供系统配置的查看和编辑功能
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 模块私有状态
    let container = null;
    let registrationConfig = null;
    let llmConfig = {
        api_key: null,
        base_url: null,
        model_name: null
    };

    // 系统配置管理模块
    const SystemConfigManagement = {
        init: function(containerElement) {
            container = containerElement;
            this.initEventListeners();

            // 等待 i18next 初始化完成后再加载数据
            const loadData = () => {
                this.loadRegistrationSettings();
                this.loadLlmSettings();
            };

            // 检查 i18next 是否已可用（通过测试一个翻译键）
            const checkI18nReady = () => {
                if (window.i18next && window.i18next.t) {
                    try {
                        const test = window.i18next.t('common.loading');
                        // 如果翻译键正常工作（返回值不是键名本身），开始加载数据
                        if (test && test !== 'common.loading') {
                            loadData();
                            return true;
                        }
                    } catch (e) {
                        // i18next 还没准备好
                    }
                }
                return false;
            };

            // 立即检查一次
            if (checkI18nReady()) {
                return;
            }

            // 等待 i18next 初始化
            const checkI18n = setInterval(() => {
                if (checkI18nReady()) {
                    clearInterval(checkI18n);
                }
            }, 100);

            // 超时保护（10秒后强制加载）
            setTimeout(() => {
                clearInterval(checkI18n);
                console.warn('i18next initialization timeout or check failed, loading data anyway');
                loadData();
            }, 10000);
        },

        initEventListeners: function() {
            // 编辑注册设置按钮
            const editRegistrationBtn = container.querySelector('#editRegistrationBtn');
            if (editRegistrationBtn) {
                editRegistrationBtn.addEventListener('click', () => {
                    this.showEditRegistrationModal();
                });
            }

            // 编辑 LLM 配置按钮
            const editLlmConfigBtn = container.querySelector('#editLlmConfigBtn');
            if (editLlmConfigBtn) {
                editLlmConfigBtn.addEventListener('click', () => {
                    this.showEditLlmConfigModal();
                });
            }

            // 测试 LLM 连接按钮
            const testLlmBtn = container.querySelector('#testLlmConnectionBtn');
            if (testLlmBtn) {
                testLlmBtn.addEventListener('click', () => {
                    this.testLlmConnection();
                });
            }
        },

        loadRegistrationSettings: async function() {
            try {
                registrationConfig = await apiGet('/system-configs/allow_registration');
                this.renderRegistrationValue();
            } catch (error) {
                // 如果配置不存在，创建默认配置
                if (error.status === 404) {
                    try {
                        registrationConfig = await apiPut('/system-configs/allow_registration', {
                            value: 'true',
                            description: t('system.allowRegistrationDefaultDesc')
                        });
                        this.renderRegistrationValue();
                    } catch (createError) {
                        console.error('创建默认注册设置失败:', createError);
                        showError(t('system.createDefaultFailed') + ' ' + (createError.message || t('messages.unknownError')));
                    }
                } else {
                    console.error('加载注册设置失败:', error);
                    showError(t('system.loadRegistrationFailed') + ' ' + (error.message || t('messages.unknownError')));
                }
                // 显示默认值
                const valueDisplay = container.querySelector('#registrationValueDisplay');
                if (valueDisplay && !registrationConfig) {
                    valueDisplay.innerHTML = `<span class="value-text" style="color: #999;">${t('common.failed')}</span>`;
                }
            }
        },

        renderRegistrationValue: function() {
            const valueDisplay = container.querySelector('#registrationValueDisplay');
            if (!valueDisplay || !registrationConfig) return;

            const value = registrationConfig.value || 'true';
            const isEnabled = value.toLowerCase() === 'true' || value === '1' || value.toLowerCase() === 'yes';

            valueDisplay.innerHTML = `
                <span class="value-text ${isEnabled ? 'value-enabled' : 'value-disabled'}">
                    ${isEnabled ? t('system.configEnabled') : t('system.configDisabled')}
                </span>
                <span class="value-raw" style="color: #666; font-size: 12px; margin-left: 8px;">
                    (${escapeHtml(value)})
                </span>
            `;
        },

        showEditRegistrationModal: function() {
            const currentValue = registrationConfig ? registrationConfig.value : 'true';
            const isEnabled = currentValue.toLowerCase() === 'true' || currentValue === '1' || currentValue.toLowerCase() === 'yes';

            const title = t('system.editRegistrationTitle');
            const content = `
                <form id="editRegistrationForm">
                    <div class="form-group">
                        <label>${t('system.allowRegistrationLabel')}</label>
                        <select id="registrationValue" required>
                            <option value="true" ${isEnabled ? 'selected' : ''}>${t('system.allowRegistrationYes')}</option>
                            <option value="false" ${!isEnabled ? 'selected' : ''}>${t('system.allowRegistrationNo')}</option>
                        </select>
                        <small style="color: #666; display: block; margin-top: 4px;">
                            ${t('system.allowRegistrationHelp')}
                        </small>
                    </div>
                    <div class="form-group">
                        <label>${t('common.description')}</label>
                        <textarea id="registrationDescription" rows="2" maxlength="500">${registrationConfig ? escapeHtml(registrationConfig.description || '') : t('system.allowRegistrationDefaultDesc')}</textarea>
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.saveRegistrationSettings();
            });
        },

        saveRegistrationSettings: async function() {
            const value = document.getElementById('registrationValue').value;
            const description = document.getElementById('registrationDescription').value.trim();

            if (!value) {
                showError(t('system.selectRegistrationValue'));
                return;
            }

            try {
                const updateData = {
                    value: value,
                    description: description || t('system.allowRegistrationDefaultDesc')
                };

                registrationConfig = await apiPut('/system-configs/allow_registration', updateData);
                showSuccess(t('system.registrationUpdateSuccess'));
                closeModal();
                this.renderRegistrationValue();
            } catch (error) {
                console.error('保存注册设置失败:', error);
                showError(t('system.registrationSaveFailed') + ' ' + (error.message || t('messages.unknownError')));
            }
        },

        // ==================== LLM 配置管理 ====================

        loadLlmSettings: async function() {
            const keys = [
                { field: 'api_key', key: 'llm_api_key', displayId: 'llmApiKeyDisplay' },
                { field: 'base_url', key: 'llm_base_url', displayId: 'llmBaseUrlDisplay' },
                { field: 'model_name', key: 'llm_model_name', displayId: 'llmModelNameDisplay' }
            ];

            for (const { field, key, displayId } of keys) {
                try {
                    const config = await apiGet(`/system-configs/${key}`);
                    llmConfig[field] = config.value;
                } catch (error) {
                    if (error.status === 404) {
                        llmConfig[field] = null;
                    } else {
                        console.error(`加载 LLM 配置 ${key} 失败:`, error);
                    }
                }
                this.renderLlmConfigValue(field, displayId);
            }
        },

        renderLlmConfigValue: function(field, displayId) {
            const valueDisplay = container.querySelector(`#${displayId}`);
            if (!valueDisplay) return;

            const value = llmConfig[field];
            if (!value) {
                valueDisplay.innerHTML = `<span class="value-text" style="color: #999;">${t('system.llmConfigNotSet')}</span>`;
            } else if (field === 'api_key') {
                // API Key 脱敏显示
                const masked = value.length > 8
                    ? value.substring(0, 4) + '****' + value.substring(value.length - 4)
                    : '****';
                valueDisplay.innerHTML = `<span class="value-text">${escapeHtml(masked)}</span>`;
            } else {
                valueDisplay.innerHTML = `<span class="value-text">${escapeHtml(value)}</span>`;
            }
        },

        showEditLlmConfigModal: function() {
            const title = t('system.editLlmConfigTitle');
            const content = `
                <form id="editLlmConfigForm">
                    <div class="form-group">
                        <label>${t('system.llmApiKey')} *</label>
                        <input type="password" id="llmApiKeyInput" class="form-control"
                            placeholder="${t('system.llmApiKeyPlaceholder')}"
                            value="${llmConfig.api_key ? escapeHtml(llmConfig.api_key) : ''}">
                        <small style="color: #666; display: block; margin-top: 4px;">
                            ${llmConfig.api_key ? t('system.llmConfigValue') + ' ' + (llmConfig.api_key.length > 8 ? llmConfig.api_key.substring(0, 4) + '****' + llmConfig.api_key.substring(llmConfig.api_key.length - 4) : '****') : ''}
                        </small>
                    </div>
                    <div class="form-group">
                        <label>${t('system.llmBaseUrl')} *</label>
                        <input type="text" id="llmBaseUrlInput" class="form-control"
                            placeholder="${t('system.llmBaseUrlPlaceholder')}"
                            value="${llmConfig.base_url ? escapeHtml(llmConfig.base_url) : ''}">
                    </div>
                    <div class="form-group">
                        <label>${t('system.llmModelName')} *</label>
                        <input type="text" id="llmModelNameInput" class="form-control"
                            placeholder="${t('system.llmModelNamePlaceholder')}"
                            value="${llmConfig.model_name ? escapeHtml(llmConfig.model_name) : ''}">
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.saveLlmSettings();
            });
        },

        saveLlmSettings: async function() {
            const apiKey = document.getElementById('llmApiKeyInput').value.trim();
            const baseUrl = document.getElementById('llmBaseUrlInput').value.trim();
            const modelName = document.getElementById('llmModelNameInput').value.trim();

            const configs = [
                { field: 'api_key', key: 'llm_api_key', value: apiKey, description: 'LLM API Key' },
                { field: 'base_url', key: 'llm_base_url', value: baseUrl, description: 'LLM API Base URL' },
                { field: 'model_name', key: 'llm_model_name', value: modelName, description: 'LLM Model Name' }
            ];

            try {
                for (const config of configs) {
                    if (config.value) {
                        await apiPut(`/system-configs/${config.key}`, {
                            value: config.value,
                            description: config.description
                        });
                        llmConfig[config.field] = config.value;
                    }
                }

                showSuccess(t('system.llmConfigUpdateSuccess'));
                closeModal();

                // 刷新显示
                this.renderLlmConfigValue('api_key', 'llmApiKeyDisplay');
                this.renderLlmConfigValue('base_url', 'llmBaseUrlDisplay');
                this.renderLlmConfigValue('model_name', 'llmModelNameDisplay');
            } catch (error) {
                console.error('保存 LLM 配置失败:', error);
                showError(t('system.llmConfigSaveFailed') + ' ' + (error.message || t('messages.unknownError')));
            }
        },

        testLlmConnection: async function() {
            const btn = container.querySelector('#testLlmConnectionBtn');
            const resultSpan = container.querySelector('#llmTestResult');
            if (!btn || !resultSpan) return;

            btn.disabled = true;
            btn.querySelector('span').textContent = t('system.testingConnection') || '测试中...';
            resultSpan.textContent = '';
            resultSpan.style.color = '#666';

            try {
                const currentLang = (window.i18next && window.i18next.language) || 'zh';
                const lang = currentLang.startsWith('zh') ? 'zh' : 'en';
                const res = await apiPost(`/analysis/test-llm-connection?lang=${lang}`);
                if (res.success) {
                    resultSpan.style.color = '#2e7d32';
                    resultSpan.textContent = '✓ ' + res.message;
                } else {
                    resultSpan.style.color = '#c62828';
                    resultSpan.textContent = '✗ ' + res.message;
                }
            } catch (error) {
                resultSpan.style.color = '#c62828';
                resultSpan.textContent = '✗ ' + t('system.testConnectionFailed') + ': ' + (error.message || t('messages.unknownError'));
            } finally {
                btn.disabled = false;
                btn.querySelector('span').textContent = t('system.testConnection') || '测试连接';
            }
        }
    };

    // 导出到全局
    window.SystemConfigManagement = SystemConfigManagement;
})();
