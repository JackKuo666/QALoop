/**
 * 标注配置管理模块 JavaScript
 * 提供标注配置的查看、创建、编辑、删除功能
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 模块私有状态
    let configsPaginator = null;
    let editingId = null;
    let container = null;

    // 标注配置管理模块
    const AnnotationConfigManagement = {
        init: function(containerElement) {
            container = containerElement;
            this.initPaginators();
            this.initEventListeners();

            // 等待 i18next 初始化完成后再加载数据
            const loadData = () => {
                this.loadAnnotationConfigs();
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

        initPaginators: function() {
            // 初始化标注配置管理分页器
            configsPaginator = createPaginator('configs', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    this.loadAnnotationConfigs();
                },
                onPageSizeChange: (pageSize) => {
                    this.loadAnnotationConfigs();
                }
            });
        },

        initEventListeners: function() {
            // 添加配置按钮
            const addConfigBtn = container.querySelector('#addConfigBtn');
            if (addConfigBtn) {
                addConfigBtn.addEventListener('click', () => {
                    this.showAnnotationConfigForm();
                });
            }
            // 使用说明按钮
            const showConfigUsageBtn = container.querySelector('#showConfigUsageBtn');
            if (showConfigUsageBtn) {
                showConfigUsageBtn.addEventListener('click', () => {
                    this.showConfigUsage();
                });
            }
        },

        loadAnnotationConfigs: async function() {
            if (!configsPaginator) return;

            try {
                const skip = configsPaginator.getSkip();
                const limit = configsPaginator.getLimit();
                const configs = await apiGet(`/annotation-configs/?skip=${skip}&limit=${limit}`);

                // 获取总数：如果返回的数据量小于limit，说明这是最后一页
                // 如果等于limit，可能还有更多数据，尝试获取下一页来判断
                let totalCount;
                if (configs.length < limit) {
                    totalCount = skip + configs.length;
                } else {
                    // 尝试获取下一页来判断是否还有更多数据
                    try {
                        const nextPage = await apiGet(`/annotation-configs/?skip=${skip + limit}&limit=1`);
                        if (nextPage.length > 0) {
                            // 还有更多数据，但不知道总数，使用估算值（当前页数 * 每页数量 + 1）
                            totalCount = (skip + limit) + 1;
                        } else {
                            // 没有更多数据了
                            totalCount = skip + limit;
                        }
                    } catch (error) {
                        // 如果获取失败，假设还有更多数据
                        totalCount = (skip + limit) + 1;
                    }
                }

                configsPaginator.setTotalCount(totalCount);
                this.renderAnnotationConfigsTable(configs);
            } catch (error) {
                console.error('加载标注配置失败:', error);
                showError(t('config.loadFailed') + ': ' + (error.message || t('common.unknownError')));
            }
        },

        renderAnnotationConfigsTable: async function(configs) {
            const tbody = container.querySelector('#configsTableBody');
            const paginationContainer = container.querySelector('#configsPaginationContainer');

            if (configs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" class="loading">${t('config.noConfigs')}</td></tr>`;
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            // 先渲染基础信息
            tbody.innerHTML = configs.map(config => `
                <tr data-config-id="${config.id}">
                    <td>${config.id}</td>
                    <td>${escapeHtml(config.name)}</td>
                    <td><span class="status-badge">${this.getAnnotationTypeLabel(config.annotation_type)}</span></td>
                    <td>${escapeHtml(config.description || '-')}</td>
                    <td><span class="status-badge ${config.required ? 'active' : 'inactive'}">
                        ${config.required ? t('status.active') : t('status.inactive')}
                    </span></td>
                    <td class="datasets-count">${t('common.loading')}</td>
                    <td>${formatDateTime(config.created_at)}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="window.AnnotationConfigManagement.editAnnotationConfig(${config.id})">${t('actions.edit')}</button>
                        <button class="btn btn-sm btn-warning" onclick="window.AnnotationConfigManagement.clearConfigResults(${config.id})">${t('config.clearResults')}</button>
                        <button class="btn btn-sm btn-danger" onclick="window.AnnotationConfigManagement.deleteAnnotationConfig(${config.id})">${t('actions.delete')}</button>
                    </td>
                </tr>
            `).join('');

            // 异步加载关联数据集数量
            configs.forEach(async config => {
                try {
                    const datasets = await apiGet(`/annotation-configs/${config.id}/datasets`);
                    const row = tbody.querySelector(`tr[data-config-id="${config.id}"]`);
                    if (row) {
                        const countCell = row.querySelector('.datasets-count');
                        if (countCell) {
                            countCell.textContent = datasets.length || 0;
                        }
                    }
                } catch (error) {
                    console.error('加载关联数据集失败:', error);
                    const row = tbody.querySelector(`tr[data-config-id="${config.id}"]`);
                    if (row) {
                        const countCell = row.querySelector('.datasets-count');
                        if (countCell) {
                            countCell.textContent = '0';
                        }
                    }
                }
            });

            // 显示分页器
            if (paginationContainer && configsPaginator) {
                paginationContainer.style.display = 'block';
                configsPaginator.render();
            }
        },

        getAnnotationTypeLabel: function(type) {
            // 如果 window.t 可用，使用 i18next 翻译
            if (window.t && window.i18next) {
                const translated = t(`annotation.${type}`);
                // 如果翻译成功（返回的不是键名本身），使用翻译结果
                if (translated && translated !== `annotation.${type}`) {
                    return translated;
                }
            }

            // 回退到类型名称
            return type;
        },

        showAnnotationConfigForm: function(config = null) {
            editingId = config ? config.id : null;
            const title = config ? t('config.editConfigTitle') : t('config.addConfigTitle');

            // 获取标注类型选项
            apiGet('/annotation-configs/types').then(types => {
                const selectedType = config ? config.annotation_type : '';
                const typeOptions = types.map(t =>
                    `<option value="${t}" ${selectedType === t ? 'selected' : ''}>${this.getAnnotationTypeLabel(t)}</option>`
                ).join('');

                const content = `
                    <form id="configForm">
                        <div class="form-group">
                            <label>${t('config.nameRequired')}</label>
                            <input type="text" id="name" value="${config ? escapeHtml(config.name) : ''}" required>
                        </div>
                        <div class="form-group">
                            <label>${t('config.description')}</label>
                            <textarea id="description">${config ? escapeHtml(config.description || '') : ''}</textarea>
                        </div>
                        <div class="form-group">
                            <label>${t('config.annotationTypeRequired')}</label>
                            <select id="annotation_type" required>
                                <option value="">${t('common.select')}</option>
                                ${typeOptions}
                            </select>
                        </div>
                        <div class="form-group">
                            <div class="form-check">
                                <input type="checkbox" id="required" ${config && config.required ? 'checked' : ''}>
                                <label for="required">${t('config.required')}</label>
                            </div>
                        </div>
                        <div class="form-group">
                            <div class="form-check">
                                <input type="checkbox" id="show_reason" ${config && config.show_reason ? 'checked' : ''}>
                                <label for="show_reason">${t('config.showReasonInput')}</label>
                            </div>
                        </div>
                        <div class="form-group">
                            <div class="form-check">
                                <input type="checkbox" id="show_confidence" ${config && config.show_confidence ? 'checked' : ''}>
                                <label for="show_confidence">${t('config.showConfidenceInput')}</label>
                            </div>
                        </div>
                        <div id="configFieldsContainer">
                            ${this.renderConfigFields(selectedType, config ? config.config : null)}
                        </div>
                    </form>
                `;

                openModal(title, content, async () => {
                    await this.saveAnnotationConfig();
                });

                // 添加标注类型改变事件监听
                const typeSelect = document.getElementById('annotation_type');
                typeSelect.addEventListener('change', (e) => {
                    const container = document.getElementById('configFieldsContainer');
                    container.innerHTML = this.renderConfigFields(e.target.value, null);
                });
            }).catch(error => {
                showError(t('config.loadTypesFailed') + ': ' + (error.message || t('common.unknownError')));
            });
        },

        renderConfigFields: function(annotationType, existingConfig) {
            if (!annotationType) {
                return `<div class="form-group"><p style="color: #999; font-style: italic;">${t('config.selectTypeFirst')}</p></div>`;
            }

            switch(annotationType) {
                case 'score':
                    return this.renderScoreConfig(existingConfig);
                case 'category':
                    return this.renderCategoryConfig(existingConfig);
                case 'text':
                    return this.renderTextConfig(existingConfig);
                case 'single_choice':
                case 'multi_choice':
                    return this.renderChoiceConfig(existingConfig);
                case 'binary':
                    return this.renderBinaryConfig(existingConfig);
                default:
                    return `<div class="form-group"><p style="color: #999;">${t('config.unknownType')}</p></div>`;
            }
        },

        renderScoreConfig: function(config) {
            const minScore = config ? config.min_score : 1;
            const maxScore = config ? config.max_score : 5;
            const scoreStep = config ? config.score_step : 1.0;

            return `
                <div class="form-group">
                    <label>${t('config.minScoreRequired')}</label>
                    <input type="number" id="min_score" value="${minScore}" required min="0">
                </div>
                <div class="form-group">
                    <label>${t('config.maxScoreRequired')}</label>
                    <input type="number" id="max_score" value="${maxScore}" required min="1">
                </div>
                <div class="form-group">
                    <label>${t('config.scoreStep')}</label>
                    <input type="number" id="score_step" value="${scoreStep}" step="0.1" min="0.1">
                </div>
            `;
        },

        renderCategoryConfig: function(config) {
            const categories = config && config.categories ? config.categories.join('\n') : '';

            return `
                <div class="form-group">
                    <label>${t('config.categoriesListHint')}</label>
                    <textarea id="categories" rows="6" placeholder="${t('config.categoriesExample')}">${escapeHtml(categories)}</textarea>
                    <small style="color: #666; display: block; margin-top: 4px;">${t('config.categoriesHelp')}</small>
                </div>
            `;
        },

        renderTextConfig: function(config) {
            const maxLength = config ? config.max_length || '' : '';

            return `
                <div class="form-group">
                    <label>${t('config.maxLengthOptional')}</label>
                    <input type="number" id="max_length" value="${maxLength}" min="1" placeholder="${t('config.maxLengthPlaceholder')}">
                </div>
            `;
        },

        renderChoiceConfig: function(config) {
            const options = config && config.options ? config.options : [];
            const optionsHtml = options.map((opt, index) => `
                <div class="option-item" style="border: 1px solid #e0e0e0; padding: 12px; margin-bottom: 12px; border-radius: 6px; background: #f9f9f9;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <strong>${t('config.option')} ${index + 1}</strong>
                        <button type="button" class="btn btn-sm btn-danger" onclick="window.AnnotationConfigManagement.removeOption(this)" style="padding: 4px 8px; font-size: 12px;">${t('actions.delete')}</button>
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionIdRequired')}</label>
                        <input type="text" class="option-id" value="${escapeHtml(opt.option_id)}" required placeholder="${t('config.optionIdPlaceholder')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionLabelRequired')}</label>
                        <input type="text" class="option-label" value="${escapeHtml(opt.label)}" required placeholder="${t('config.optionLabelPlaceholder')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionDescription')}</label>
                        <input type="text" class="option-description" value="${escapeHtml(opt.description || '')}" placeholder="${t('config.optional')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionValueRequired')}</label>
                        <input type="text" class="option-value" value="${escapeHtml(String(opt.value))}" required placeholder="${t('config.optionValuePlaceholder')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 0;">
                        <label>${t('config.optionOrder')}</label>
                        <input type="number" class="option-order" value="${opt.order || 0}" min="0">
                    </div>
                    <div class="form-group" style="margin-bottom: 0;">
                        <div class="form-check">
                            <input type="checkbox" class="option-enabled" ${opt.enabled !== false ? 'checked' : ''}>
                            <label>${t('config.optionEnabled')}</label>
                        </div>
                    </div>
                </div>
            `).join('');

            return `
                <div class="form-group">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <label>${t('config.optionListRequired')}</label>
                        <button type="button" class="btn btn-sm btn-primary" onclick="window.AnnotationConfigManagement.addOption()" style="padding: 6px 12px; font-size: 12px;">${t('config.addOption')}</button>
                    </div>
                    <div id="optionsContainer">
                        ${optionsHtml || `<p style="color: #999; font-style: italic; margin-bottom: 12px;">${t('config.noOptionsHint')}</p>`}
                    </div>
                </div>
            `;
        },

        renderBinaryConfig: function(config) {
            const trueLabel = config ? config.true_label || t('common.yes') : t('common.yes');
            const falseLabel = config ? config.false_label || t('common.no') : t('common.no');

            return `
                <div class="form-group">
                    <label>${t('config.trueLabel')}</label>
                    <input type="text" id="true_label" value="${escapeHtml(trueLabel)}" placeholder="${t('common.yes')}">
                </div>
                <div class="form-group">
                    <label>${t('config.falseLabel')}</label>
                    <input type="text" id="false_label" value="${escapeHtml(falseLabel)}" placeholder="${t('common.no')}">
                </div>
            `;
        },

        addOption: function() {
            const container = document.getElementById('optionsContainer');
            const emptyMsg = container.querySelector('p');
            if (emptyMsg) {
                emptyMsg.remove();
            }

            const optionHtml = `
                <div class="option-item" style="border: 1px solid #e0e0e0; padding: 12px; margin-bottom: 12px; border-radius: 6px; background: #f9f9f9;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <strong>${t('config.newOption')}</strong>
                        <button type="button" class="btn btn-sm btn-danger" onclick="window.AnnotationConfigManagement.removeOption(this)" style="padding: 4px 8px; font-size: 12px;">${t('actions.delete')}</button>
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionIdRequired')}</label>
                        <input type="text" class="option-id" required placeholder="${t('config.optionIdPlaceholder')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionLabelRequired')}</label>
                        <input type="text" class="option-label" required placeholder="${t('config.optionLabelPlaceholder')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionDescription')}</label>
                        <input type="text" class="option-description" placeholder="${t('config.optional')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 8px;">
                        <label>${t('config.optionValueRequired')}</label>
                        <input type="text" class="option-value" required placeholder="${t('config.optionValuePlaceholder')}">
                    </div>
                    <div class="form-group" style="margin-bottom: 0;">
                        <label>${t('config.optionOrder')}</label>
                        <input type="number" class="option-order" value="0" min="0">
                    </div>
                    <div class="form-group" style="margin-bottom: 0;">
                        <div class="form-check">
                            <input type="checkbox" class="option-enabled" checked>
                            <label>${t('config.optionEnabled')}</label>
                        </div>
                    </div>
                </div>
            `;

            container.insertAdjacentHTML('beforeend', optionHtml);
        },

        removeOption: function(btn) {
            const container = document.getElementById('optionsContainer');
            btn.closest('.option-item').remove();

            // 如果没有选项了，显示提示
            if (container.querySelectorAll('.option-item').length === 0) {
                container.innerHTML = `<p style="color: #999; font-style: italic; margin-bottom: 12px;">${t('config.noOptionsHint')}</p>`;
            }
        },

        saveAnnotationConfig: async function() {
            const name = document.getElementById('name').value;
            const description = document.getElementById('description').value;
            const annotation_type = document.getElementById('annotation_type').value;
            const required = document.getElementById('required').checked;
            const show_reason = document.getElementById('show_reason').checked;
            const show_confidence = document.getElementById('show_confidence').checked;

            if (!annotation_type) {
                showError(t('config.selectTypeFirst'));
                return;
            }

            // 根据标注类型收集配置数据
            let config_obj;
            try {
                config_obj = this.collectConfigData(annotation_type);
            } catch (error) {
                showError(t('config.configDataError') + ': ' + error.message);
                return;
            }

            const data = {
                name,
                description: description || null,
                annotation_type,
                required,
                show_reason,
                show_confidence,
                config: config_obj
            };

            try {
                if (editingId) {
                    data.id = editingId;
                    await apiPut(`/annotation-configs/${editingId}`, data);
                    showSuccess(t('config.updateSuccess'));
                } else {
                    await apiPost('/annotation-configs/', data);
                    showSuccess(t('config.createSuccess'));
                }

                closeModal();
                // 如果是新建配置，重置到第一页
                if (!editingId && configsPaginator) {
                    configsPaginator.reset();
                }
                this.loadAnnotationConfigs();
            } catch (error) {
                showError(t('config.saveFailed') + ': ' + (error.message || t('common.unknownError')));
            }
        },

        collectConfigData: function(annotationType) {
            switch(annotationType) {
                case 'score':
                    const minScore = parseInt(document.getElementById('min_score').value);
                    const maxScore = parseInt(document.getElementById('max_score').value);
                    const scoreStep = parseFloat(document.getElementById('score_step').value) || 1.0;

                    if (isNaN(minScore) || isNaN(maxScore)) {
                        throw new Error(t('config.scoreMustBeNumber'));
                    }
                    if (minScore >= maxScore) {
                        throw new Error(t('config.maxScoreMustBeGreaterThanMin'));
                    }

                    return {
                        min_score: minScore,
                        max_score: maxScore,
                        score_step: scoreStep
                    };

                case 'category':
                    const categoriesText = document.getElementById('categories').value;
                    const categories = categoriesText
                        .split('\n')
                        .map(c => c.trim())
                        .filter(c => c.length > 0);

                    return {
                        categories: categories.length > 0 ? categories : null
                    };

                case 'text':
                    const maxLength = document.getElementById('max_length').value;
                    return {
                        max_length: maxLength ? parseInt(maxLength) : null
                    };

                case 'single_choice':
                case 'multi_choice':
                    const optionItems = document.querySelectorAll('.option-item');
                    if (optionItems.length === 0) {
                        throw new Error(t('config.atLeastOneOption'));
                    }

                    const options = Array.from(optionItems).map((item, index) => {
                        const optionId = item.querySelector('.option-id').value.trim();
                        const label = item.querySelector('.option-label').value.trim();
                        const description = item.querySelector('.option-description').value.trim();
                        const value = item.querySelector('.option-value').value.trim();
                        const order = parseInt(item.querySelector('.option-order').value) || index;
                        const enabled = item.querySelector('.option-enabled').checked;

                        if (!optionId || !label || !value) {
                            throw new Error(`${t('config.option')} ${index + 1} ${t('config.optionFieldsRequired')}`);
                        }

                        // 尝试将值转换为合适的类型
                        let parsedValue = value;
                        if (!isNaN(value) && value.trim() !== '') {
                            if (value.includes('.')) {
                                parsedValue = parseFloat(value);
                            } else {
                                parsedValue = parseInt(value);
                            }
                        } else if (value.toLowerCase() === 'true') {
                            parsedValue = true;
                        } else if (value.toLowerCase() === 'false') {
                            parsedValue = false;
                        }

                        return {
                            option_id: optionId,
                            label: label,
                            description: description || null,
                            value: parsedValue,
                            order: order,
                            enabled: enabled
                        };
                    });

                    return { options };

                case 'binary':
                    const trueLabel = document.getElementById('true_label').value.trim() || t('common.yes');
                    const falseLabel = document.getElementById('false_label').value.trim() || t('common.no');

                    return {
                        true_label: trueLabel,
                        false_label: falseLabel
                    };

                default:
                    throw new Error(t('config.unknownType'));
            }
        },

        editAnnotationConfig: async function(configId) {
            try {
                // 先检查是否有标注结果
                const stats = await apiGet(`/annotation-configs/${configId}/results-count`);
                if (stats.count > 0) {
                    const datasetsInfo = stats.datasets.length > 0
                        ? `${t('config.relatedDatasets')}${stats.datasets.map(d => d.name).join('、')}`
                        : '';
                    const message = `${t('config.editBlocked.results', {count: stats.count, datasetCount: stats.dataset_count})}\n${datasetsInfo}\n\n${t('config.editBlocked.instruction')}`;
                    showError(message);
                    return;
                }

                // 如果没有标注结果，继续加载配置并显示编辑表单
                const config = await apiGet(`/annotation-configs/${configId}`);
                this.showAnnotationConfigForm(config);
            } catch (error) {
                // 如果统计接口返回404，说明配置不存在
                if (error.status === 404) {
                    showError(t('config.configNotFound') + ': ' + (error.message || t('common.unknownError')));
                } else if (error.status === 400) {
                    // 如果统计接口返回400错误，说明有标注结果，错误信息已经包含详细信息
                    showError(error.message || t('config.editBlocked.defaultMessage'));
                } else {
                    showError(t('config.loadFailed') + ': ' + (error.message || t('common.unknownError')));
                }
            }
        },

        clearConfigResults: async function(configId) {
            try {
                // 先检查是否有标注结果
                const stats = await apiGet(`/annotation-configs/${configId}/results-count`);
                if (stats.count === 0) {
                    showError(t('config.noResultsToClear'));
                    return;
                }

                // 显示确认对话框，包含详细信息
                const datasetsInfo = stats.datasets.length > 0
                    ? `${t('config.relatedDatasets')}${stats.datasets.map(d => d.name).join('、')}\n`
                    : '';
                const message = `${t('config.clearResultsConfirm')}\n\n${t('config.resultsCount')}${stats.count} ${t('config.items')}\n${t('config.datasetCount')}${stats.dataset_count} ${t('config.units')}\n${datasetsInfo}\n${t('config.irreversibleOperation')}`;

                if (!confirm(message)) {
                    return;
                }

                // 调用清除接口
                const result = await apiDelete(`/annotation-configs/${configId}/results`);
                showSuccess(result.message || `${t('config.clearedResults')} ${result.deleted_count || 0} ${t('config.items')}`);

                // 刷新配置列表
                this.loadAnnotationConfigs();
            } catch (error) {
                // 如果统计接口返回404，说明配置不存在
                if (error.status === 404) {
                    showError(t('config.configNotFound') + ': ' + (error.message || t('common.unknownError')));
                } else {
                    showError(t('config.clearResultsFailed') + ': ' + (error.message || t('common.unknownError')));
                }
            }
        },

        deleteAnnotationConfig: async function(configId) {
            try {
                // 先检查是否有标注结果
                const stats = await apiGet(`/annotation-configs/${configId}/results-count`);
                if (stats.count > 0) {
                    const datasetsInfo = stats.datasets.length > 0
                        ? `${t('config.relatedDatasets')}${stats.datasets.map(d => d.name).join('、')}`
                        : '';
                    const message = `${t('config.deleteBlocked.results', {count: stats.count, datasetCount: stats.dataset_count})}\n${datasetsInfo}\n\n${t('config.deleteBlocked.instruction')}`;
                    showError(message);
                    return;
                }

                // 如果没有标注结果，显示确认对话框
                if (!confirm(t('config.deleteConfirm'))) {
                    return;
                }

                await apiDelete(`/annotation-configs/${configId}`);
                showSuccess(t('config.deleteSuccess'));
                // 如果当前页没有数据了，回到上一页
                if (configsPaginator) {
                    configsPaginator.adjustPageAfterDelete();
                }
                this.loadAnnotationConfigs();
            } catch (error) {
                // 如果统计接口返回404，说明配置不存在
                if (error.status === 404) {
                    showError(t('config.configNotFound') + ': ' + (error.message || t('common.unknownError')));
                } else if (error.status === 400) {
                    // 如果统计接口或删除接口返回400错误，说明有标注结果，错误信息已经包含详细信息
                    showError(error.message || t('config.deleteBlocked.defaultMessage'));
                } else {
                    showError(t('config.deleteFailed') + ': ' + (error.message || t('common.unknownError')));
                }
            }
        },

        showConfigUsage: function() {
            // 构建标注配置功能说明内容
            const usageContent = `
                <div style="max-width: 800px; line-height: 1.6;">
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 8px;">
                            ${t('config.usage.title')}
                        </h3>
                        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin-top: 10px;">
                            <h4 style="margin-top: 0; color: #2196F3;">${t('config.usage.section1.title')}</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>${t('config.usage.section1.item1')}</li>
                                <li>${t('config.usage.section1.item2')}</li>
                                <li>${t('config.usage.section1.item3')}</li>
                                <li>${t('config.usage.section1.item4')}</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">${t('config.usage.section2.title')}</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li><strong>${t('config.usage.section2.score')}：</strong>${t('config.usage.section2.scoreDesc')}</li>
                                <li><strong>${t('config.usage.section2.category')}：</strong>${t('config.usage.section2.categoryDesc')}</li>
                                <li><strong>${t('config.usage.section2.text')}：</strong>${t('config.usage.section2.textDesc')}</li>
                                <li><strong>${t('config.usage.section2.singleChoice')}：</strong>${t('config.usage.section2.singleChoiceDesc')}</li>
                                <li><strong>${t('config.usage.section2.multiChoice')}：</strong>${t('config.usage.section2.multiChoiceDesc')}</li>
                                <li><strong>${t('config.usage.section2.binary')}：</strong>${t('config.usage.section2.binaryDesc')}</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">${t('config.usage.section3.title')}</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>${t('config.usage.section3.item1')}</li>
                                <li>${t('config.usage.section3.item2')}</li>
                                <li>${t('config.usage.section3.item3')}</li>
                                <li>${t('config.usage.section3.item4')}</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">${t('config.usage.section4.title')}</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>${t('config.usage.section4.item1')}</li>
                                <li>${t('config.usage.section4.item2')}</li>
                                <li>${t('config.usage.section4.item3')}</li>
                                <li>${t('config.usage.section4.item4')}</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">${t('config.usage.section5.title')}</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>${t('config.usage.section5.item1')}</li>
                                <li>${t('config.usage.section5.item2')}</li>
                                <li>${t('config.usage.section5.item3')}</li>
                                <li>${t('config.usage.section5.item4')}</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">${t('config.usage.section6.title')}</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>${t('config.usage.section6.item1')}</li>
                                <li>${t('config.usage.section6.item2')}</li>
                                <li>${t('config.usage.section6.item3')}</li>
                                <li>${t('config.usage.section6.item4')}</li>
                            </ul>
                        </div>
                    </div>

                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; border-bottom: 2px solid #FF9800; padding-bottom: 8px;">
                            ${t('config.usage.bestPractices.title')}
                        </h3>
                        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #FF9800; margin-top: 10px;">
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li><strong>${t('config.usage.bestPractices.naming')}：</strong>${t('config.usage.bestPractices.namingDesc')}</li>
                                <li><strong>${t('config.usage.bestPractices.description')}：</strong>${t('config.usage.bestPractices.descriptionDesc')}</li>
                                <li><strong>${t('config.usage.bestPractices.required')}：</strong>${t('config.usage.bestPractices.requiredDesc')}</li>
                                <li><strong>${t('config.usage.bestPractices.projectLevel')}：</strong>${t('config.usage.bestPractices.projectLevelDesc')}</li>
                                <li><strong>${t('config.usage.bestPractices.datasetLevel')}：</strong>${t('config.usage.bestPractices.datasetLevelDesc')}</li>
                                <li><strong>${t('config.usage.bestPractices.reuse')}：</strong>${t('config.usage.bestPractices.reuseDesc')}</li>
                                <li><strong>${t('config.usage.bestPractices.modification')}：</strong>${t('config.usage.bestPractices.modificationDesc')}</li>
                            </ul>
                        </div>
                    </div>
                </div>
            `;

            // 显示对话框（隐藏提交按钮，只显示关闭按钮）
            openModal(t('config.usage.modalTitle'), usageContent, null, true);
        },

        destroy: function() {
            // 清理资源
            configsPaginator = null;
            editingId = null;
            container = null;
        }
    };

    // 暴露到全局
    window.AnnotationConfigManagement = AnnotationConfigManagement;
})();
