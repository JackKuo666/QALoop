/**
 * 数据库管理模块 JavaScript
 * 提供数据集的查看、创建、编辑、删除、导入功能，以及QA对管理功能
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 模块私有状态
    let datasetsPaginator = null;
    let qaPaginator = null;
    let editingId = null;
    let currentDatasetId = null;
    let container = null;
    let usersCache = null;

    // 数据库管理模块
    const DatasetManagement = {
        init: function(containerElement) {
            container = containerElement;
            this.initPaginators();
            this.initEventListeners();

            // 等待 i18next 初始化完成后再加载数据
            const loadData = () => {
                console.log('Loading datasets with i18next language:', window.i18next?.language);
                this.loadDatasets();
                this.loadDatasetsForSelect();
            };

            // 检查 i18next 是否已可用（通过测试实际翻译）
            const checkI18nReady = () => {
                if (window.i18next && typeof window.i18next.t === 'function') {
                    try {
                        // 测试翻译一个已知存在的键
                        const testResult1 = window.i18next.t('common.loading');
                        const testResult2 = window.i18next.t('dataset.manageConfigs');
                        // 如果返回的值不是键名本身，说明翻译已正常工作
                        const isWorking = testResult1 && testResult1 !== 'common.loading';
                        console.log('Checking i18next ready:', isWorking, 'language:', window.i18next.language);
                        console.log('  Test common.loading:', testResult1);
                        console.log('  Test dataset.manageConfigs:', testResult2);
                        console.log('  Test dataset.manageConfigs === key?:', testResult2 === 'dataset.manageConfigs');
                        return isWorking;
                    } catch (e) {
                        console.log('i18next test failed:', e);
                        return false;
                    }
                }
                console.log('i18next not available');
                return false;
            };

            // 立即检查一次
            if (checkI18nReady()) {
                loadData();
                return;
            }

            console.log('i18next not ready yet, waiting...');

            // 等待 i18next 初始化
            const checkI18n = setInterval(() => {
                if (checkI18nReady()) {
                    clearInterval(checkI18n);
                    loadData();
                }
            }, 100);

            // 超时保护（10秒后强制加载）
            let loadDataTimeout = setTimeout(() => {
                clearInterval(checkI18n);
                console.warn('i18next initialization timeout, loading data anyway. Language:', window.i18next?.language);
                loadData();
            }, 10000);

            // 同时监听 i18next-ready 事件（更可靠的方式）
            window.addEventListener('i18next-ready', function onI18nReady() {
                console.log('Received i18next-ready event, language:', window.i18next?.language);
                clearInterval(checkI18n);
                clearTimeout(loadDataTimeout);
                window.removeEventListener('i18next-ready', onI18nReady);
                loadData();
            });
        },

        initPaginators: function() {
            // 初始化数据集管理分页器
            datasetsPaginator = createPaginator('datasets', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    this.loadDatasets();
                },
                onPageSizeChange: (pageSize) => {
                    this.loadDatasets();
                }
            });

            // 初始化QA对分页器
            qaPaginator = createPaginator('qa', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    if (currentDatasetId) {
                        this.loadQAPairs(currentDatasetId);
                    }
                },
                onPageSizeChange: (pageSize) => {
                    if (currentDatasetId) {
                        this.loadQAPairs(currentDatasetId);
                    }
                }
            });
        },

        initEventListeners: function() {
            // 添加数据集按钮
            const addDatasetBtn = container.querySelector('#addDatasetBtn');
            if (addDatasetBtn) {
                addDatasetBtn.addEventListener('click', () => {
                    this.showDatasetForm();
                });
            }

            // 导入数据集按钮
            const importDatasetBtn = container.querySelector('#importDatasetBtn');
            if (importDatasetBtn) {
                importDatasetBtn.addEventListener('click', () => {
                    this.showImportDatasetForm();
                });
            }

            // 刷新数据集按钮
            const refreshDatasetsBtn = container.querySelector('#refreshDatasetsBtn');
            if (refreshDatasetsBtn) {
                refreshDatasetsBtn.addEventListener('click', () => {
                    this.loadDatasets();
                });
            }

            // 标签页切换
            container.querySelectorAll('.tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const tab = btn.dataset.tab;
                    this.switchTab(tab);
                });
            });

            // 数据集选择
            const datasetSelect = container.querySelector('#datasetSelect');
            if (datasetSelect) {
                datasetSelect.addEventListener('change', (e) => {
                    currentDatasetId = e.target.value ? parseInt(e.target.value) : null;
                    if (currentDatasetId) {
                        if (qaPaginator) qaPaginator.reset();
                        this.loadQAPairs(currentDatasetId);
                    } else {
                        const tbody = container.querySelector('#qaPairsTableBody');
                        if (tbody) {
                            tbody.innerHTML = '<tr><td colspan="4" class="loading">' + t('system.selectDatasetFirst') + '</td></tr>';
                        }
                        const qaPaginationContainer = container.querySelector('#qaPaginationContainer');
                        if (qaPaginationContainer) qaPaginationContainer.style.display = 'none';
                    }
                });
            }

            // 导入数据按钮
            const importDataBtn = container.querySelector('#importDataBtn');
            if (importDataBtn) {
                importDataBtn.addEventListener('click', () => {
                    this.showImportDataForm();
                });
            }
        },

        switchTab: function(tab) {
            // 更新tab按钮状态
            container.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tab);
            });

            // 更新tab内容状态
            container.querySelectorAll('.tab-content').forEach(content => {
                content.classList.toggle('active', content.id === tab);
            });

            if (tab === 'dataset-items' && !currentDatasetId) {
                this.loadDatasetsForSelect();
            }
        },

        loadDatasets: async function() {
            if (!datasetsPaginator) return;

            try {
                const skip = datasetsPaginator.getSkip();
                const limit = datasetsPaginator.getLimit();
                const datasets = await apiGet(`/datasets/?skip=${skip}&limit=${limit}`);

                // 获取总数：如果返回的数据量小于limit，说明这是最后一页
                // 如果等于limit，可能还有更多数据，尝试获取下一页来判断
                let totalCount;
                if (datasets.length < limit) {
                    totalCount = skip + datasets.length;
                } else {
                    // 尝试获取下一页来判断是否还有更多数据
                    try {
                        const nextPage = await apiGet(`/datasets/?skip=${skip + limit}&limit=1`);
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

                datasetsPaginator.setTotalCount(totalCount);
                this.renderDatasetsTable(datasets);
                this.loadDatasetsForSelect();
            } catch (error) {
                console.error('Failed to load datasets:', error);
                showError(t('messages.loadFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        renderDatasetsTable: async function(datasets) {
            const tbody = container.querySelector('#datasetsTableBody');
            const paginationContainer = container.querySelector('#datasetsPaginationContainer');

            if (datasets.length === 0) {
                tbody.innerHTML = '<tr><td colspan="10" class="loading">' + t('dataset.noDatasets') + '</td></tr>';
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            // 先渲染基础信息
            tbody.innerHTML = datasets.map(dataset => `
                <tr data-dataset-id="${dataset.id}">
                    <td>${dataset.id}</td>
                    <td>${escapeHtml(dataset.name)}</td>
                    <td>${escapeHtml(dataset.description || '-')}</td>
                    <td>${escapeHtml(dataset.version || '-')}</td>
                    <td><span class="status-badge ${dataset.status === 'active' ? 'active' : 'inactive'}">
                        ${t(`status.${dataset.status || 'active'}`)}
                    </span></td>
                    <td class="items-count">${t('common.loading')}</td>
                    <td class="annotation-progress">${t('common.loading')}</td>
                    <td>${escapeHtml(dataset.annotator_name || '-')}</td>
                    <td>${formatDateTime(dataset.created_at)}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="window.DatasetManagement.editDataset(${dataset.id})">${t('actions.edit')}</button>
                        <button class="btn btn-sm btn-secondary" onclick="window.DatasetManagement.manageDatasetConfigs(${dataset.id})">${t('dataset.manageConfigs')}</button>
                        <button class="btn btn-sm btn-success" onclick="window.DatasetManagement.exportAnnotations(${dataset.id})">${t('system.exportAnnotations')}</button>
                        <button class="btn btn-sm btn-danger" onclick="window.DatasetManagement.deleteDataset(${dataset.id})">${t('actions.delete')}</button>
                    </td>
                </tr>
            `).join('');

            // 异步加载统计数据和标注进展
            datasets.forEach(async dataset => {
                try {
                    const [stats, progress] = await Promise.all([
                        this.getDatasetStats(dataset.id),
                        this.getDatasetAnnotationProgress(dataset.id).catch(() => null)
                    ]);
                    const row = tbody.querySelector(`tr[data-dataset-id="${dataset.id}"]`);
                    if (row) {
                        const countCell = row.querySelector('.items-count');
                        if (countCell) {
                            countCell.textContent = stats.items_count || 0;
                        }

                        const progressCell = row.querySelector('.annotation-progress');
                        if (progressCell && progress) {
                            progressCell.innerHTML = this.renderAnnotationProgress(progress);
                        } else if (progressCell) {
                            progressCell.textContent = '-';
                        }
                    }
                } catch (error) {
                    console.error('Failed to load statistics:', error);
                    const row = tbody.querySelector(`tr[data-dataset-id="${dataset.id}"]`);
                    if (row) {
                        const countCell = row.querySelector('.items-count');
                        if (countCell) {
                            countCell.textContent = '0';
                        }
                        const progressCell = row.querySelector('.annotation-progress');
                        if (progressCell) {
                            progressCell.textContent = '-';
                        }
                    }
                }
            });

            // 显示分页器
            if (paginationContainer && datasetsPaginator) {
                paginationContainer.style.display = 'block';
                datasetsPaginator.render();
            }
        },

        getDatasetStats: async function(datasetId) {
            try {
                return await apiGet(`/datasets/${datasetId}/stats`);
            } catch (error) {
                return { items_count: 0, configs_count: 0 };
            }
        },

        getDatasetAnnotationProgress: async function(datasetId) {
            try {
                return await apiGet(`/datasets/${datasetId}/annotation-progress`);
            } catch (error) {
                console.error('Failed to get annotation progress:', error);
                return null;
            }
        },

        renderAnnotationProgress: function(progress) {
            if (!progress || progress.total_items === 0) {
                return '<span style="color: #999;">' + t('common.noData') + '</span>';
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

            // 如果有配置进展，显示详细信息（可展开）
            if (progress.config_progress && progress.config_progress.length > 0) {
                const configDetails = progress.config_progress.map(cp => {
                    const cpColor = cp.progress_rate >= 80 ? '#2e7d32' : cp.progress_rate >= 50 ? '#f57c00' : '#d32f2f';
                    return `
                        <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                            <span style="font-size: 11px; color: #666; min-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(cp.config_name)}">
                                ${escapeHtml(cp.config_name)}:
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
                    <details style="margin-top: 4px;">
                        <summary style="cursor: pointer; font-size: 11px; color: #1976d2; user-select: none;">
                            ${t('system.viewDetails')}
                        </summary>
                        <div style="margin-top: 8px; padding: 8px; background: #f5f5f5; border-radius: 4px;">
                            ${configDetails}
                        </div>
                    </details>
                `;
            }

            html += '</div>';
            return html;
        },

        loadDatasetsForSelect: function() {
            apiGet('/datasets/').then(datasets => {
                const select = container.querySelector('#datasetSelect');
                if (select) {
                    select.innerHTML = '<option value="">' + t('system.selectDataset') + '</option>' +
                        datasets.map(ds => `<option value="${ds.id}">${escapeHtml(ds.name)}</option>`).join('');
                    if (currentDatasetId) {
                        select.value = currentDatasetId;
                    }
                }
            }).catch(error => {
                console.error('Failed to load dataset list:', error);
            });
        },

        loadUsersForSelect: async function() {
            if (usersCache) {
                return usersCache;
            }
            try {
                const users = await apiGet('/users/?skip=0&limit=1000');
                usersCache = users;
                return users;
            } catch (error) {
                console.error('Failed to load user list:', error);
                return [];
            }
        },

        showDatasetForm: async function(dataset = null) {
            editingId = dataset ? dataset.id : null;
            const title = dataset ? t('dataset.editDataset') : t('dataset.addDataset');

            // 加载用户列表
            const users = await this.loadUsersForSelect();
            const userOptions = '<option value="">' + t('common.none') + '</option>' + users.map(user =>
                `<option value="${user.id}" ${dataset && dataset.annotator_id === user.id ? 'selected' : ''}>${escapeHtml(user.username)}${user.full_name ? ' (' + escapeHtml(user.full_name) + ')' : ''}</option>`
            ).join('');

            const content = `
                <form id="datasetForm">
                    <div class="form-group">
                        <label>${t('dataset.name')} *</label>
                        <input type="text" id="name" value="${dataset ? escapeHtml(dataset.name) : ''}" required>
                    </div>
                    <div class="form-group">
                        <label>${t('dataset.description')}</label>
                        <textarea id="description">${dataset ? escapeHtml(dataset.description || '') : ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label>${t('dataset.version')}</label>
                        <input type="text" id="version" value="${dataset ? escapeHtml(dataset.version || '') : ''}">
                    </div>
                    <div class="form-group">
                        <label>${t('dataset.status')}</label>
                        <select id="status">
                            <option value="active" ${dataset && dataset.status === 'active' ? 'selected' : ''}>${t('status.active')}</option>
                            <option value="inactive" ${dataset && dataset.status === 'inactive' ? 'selected' : ''}>${t('status.inactive')}</option>
                            <option value="archived" ${dataset && dataset.status === 'archived' ? 'selected' : ''}>${t('status.archived')}</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>${t('dataset.category')}</label>
                        <input type="text" id="category" value="${dataset ? escapeHtml(dataset.category || '') : ''}">
                    </div>
                    <div class="form-group">
                        <label>${t('dataset.annotator')}</label>
                        <select id="annotator_id">
                            ${userOptions}
                        </select>
                        <small style="color: #666; display: block; margin-top: 4px;">
                            ${t('dataset.annotatorHelp')}
                        </small>
                    </div>
                    <div class="form-group">
                        <label>${t('dataset.displayExtraFields')}</label>
                        <input type="text" id="display_extra_fields"
                               value="${dataset && dataset.display_extra_fields ? dataset.display_extra_fields.join(', ') : ''}"
                               placeholder="${t('dataset.extraFieldsPlaceholder')}">
                        <small style="color: #666; display: block; margin-top: 4px;">
                            ${t('dataset.extraFieldsHelp')}
                        </small>
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.saveDataset();
            });
        },

        saveDataset: async function() {
            const displayExtraFieldsInput = document.getElementById('display_extra_fields').value.trim();
            const displayExtraFields = displayExtraFieldsInput
                ? displayExtraFieldsInput.split(',').map(f => f.trim()).filter(f => f)
                : null;

            const annotatorIdInput = document.getElementById('annotator_id').value;
            const annotatorId = annotatorIdInput ? parseInt(annotatorIdInput) : null;

            // 获取标注者名称
            let annotatorName = null;
            if (annotatorId) {
                const users = await this.loadUsersForSelect();
                const annotator = users.find(u => u.id === annotatorId);
                if (annotator) {
                    annotatorName = annotator.username;
                }
            }

            const data = {
                name: document.getElementById('name').value,
                description: document.getElementById('description').value || null,
                version: document.getElementById('version').value || null,
                status: document.getElementById('status').value || 'active',
                category: document.getElementById('category').value || null,
                annotator_id: annotatorId,
                annotator_name: annotatorName,
                display_extra_fields: displayExtraFields
            };

            try {
                if (editingId) {
                    data.id = editingId;
                    await apiPut(`/datasets/${editingId}`, data);
                    showSuccess(t('messages.updateSuccess'));
                } else {
                    await apiPost('/datasets/', data);
                    showSuccess(t('messages.createSuccess'));
                }

                // 保存 editingId，因为 closeModal 可能会重置它
                const savedEditingId = editingId;

                closeModal();
                // 如果是新建数据集，重置到第一页
                if (!savedEditingId && datasetsPaginator) {
                    datasetsPaginator.reset();
                }
                this.loadDatasets();

                // 如果是从项目管理页面调用的，刷新项目管理页面的数据
                if (window._editingDatasetFromProject && window._projectIdToRefresh) {
                    const projectId = window._projectIdToRefresh;
                    // 清除标志
                    window._editingDatasetFromProject = false;
                    window._projectIdToRefresh = null;
                    // 触发自定义事件，通知 manager.js 刷新数据
                    window.dispatchEvent(new CustomEvent('datasetSavedFromProject', {
                        detail: { projectId: projectId, datasetId: savedEditingId }
                    }));
                }
            } catch (error) {
                showError(t('messages.saveFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        editDataset: async function(datasetId) {
            try {
                const dataset = await apiGet(`/datasets/${datasetId}`);
                this.showDatasetForm(dataset);
            } catch (error) {
                showError(t('messages.loadFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        deleteDataset: async function(datasetId) {
            if (!confirm(t('dataset.deleteConfirm'))) {
                return;
            }

            try {
                await apiDelete(`/datasets/${datasetId}`);
                showSuccess(t('messages.deleteSuccess'));
                // 如果当前页没有数据了，回到上一页
                if (datasetsPaginator) {
                    datasetsPaginator.adjustPageAfterDelete();
                }
                this.loadDatasets();
                if (currentDatasetId === datasetId) {
                    currentDatasetId = null;
                    const datasetSelect = container.querySelector('#datasetSelect');
                    if (datasetSelect) datasetSelect.value = '';
                    const tbody = container.querySelector('#qaPairsTableBody');
                    if (tbody) {
                        tbody.innerHTML = '<tr><td colspan="4" class="loading">' + t('system.selectDatasetFirst') + '</td></tr>';
                    }
                }
            } catch (error) {
                showError(t('messages.deleteFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        manageDatasetConfigs: async function(datasetId) {
            try {
                // 获取数据集信息
                const dataset = await apiGet(`/datasets/${datasetId}`);

                // 获取已关联的标注配置
                const associatedConfigs = await apiGet(`/datasets/${datasetId}/configs`);

                // 获取所有可用的标注配置
                const allConfigs = await apiGet('/annotation-configs/?skip=0&limit=1000');

                // 找出未关联的配置
                const associatedIds = new Set(associatedConfigs.map(c => c.id));
                const unassociatedConfigs = allConfigs.filter(c => !associatedIds.has(c.id));

                // 显示管理模态框
                this.showDatasetConfigsModal(dataset, associatedConfigs, unassociatedConfigs);
            } catch (error) {
                showError(t('dataset.loadConfigsFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        showDatasetConfigsModal: function(dataset, associatedConfigs, unassociatedConfigs) {
            const title = `${t('dataset.manageConfigs')} - ${escapeHtml(dataset.name)}`;

            // 构建已关联配置列表
            const associatedList = associatedConfigs.length > 0
                ? associatedConfigs.map(config => `
                    <div class="config-item" data-config-id="${config.id}">
                        <div class="config-info">
                            <strong>${escapeHtml(config.name)}</strong>
                            <span class="config-type">${escapeHtml(config.annotation_type)}</span>
                            ${config.description ? `<div class="config-desc">${escapeHtml(config.description)}</div>` : ''}
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="window.DatasetManagement.removeDatasetConfig(${dataset.id}, ${config.id})">${t('actions.remove')}</button>
                    </div>
                `).join('')
                : '<div class="empty-state">' + t('dataset.noAssociatedConfigs') + '</div>';

            // 构建未关联配置选择器
            const unassociatedOptions = unassociatedConfigs.length > 0
                ? unassociatedConfigs.map(config =>
                    `<option value="${config.id}">${escapeHtml(config.name)} (${escapeHtml(config.annotation_type)})</option>`
                ).join('')
                : '<option value="">' + t('dataset.noAvailableConfigs') + '</option>';

            const content = `
                <div class="dataset-configs-manager">
                    <div class="configs-section">
                        <h4>${t('dataset.associatedConfigs')}</h4>
                        <div class="configs-list" id="associatedConfigsList">
                            ${associatedList}
                        </div>
                    </div>
                    <div class="configs-section" style="margin-top: 24px; padding-top: 24px; border-top: 1px solid #e0e0e0;">
                        <h4>${t('dataset.addConfig')}</h4>
                        <div class="form-group">
                            <label>${t('dataset.selectConfig')}</label>
                            <select id="configSelect" class="form-control">
                                <option value="">${t('common.select')}</option>
                                ${unassociatedOptions}
                            </select>
                        </div>
                        <button class="btn btn-primary" onclick="window.DatasetManagement.addDatasetConfig(${dataset.id})" style="margin-top: 12px;">${t('actions.add')}</button>
                    </div>
                </div>
                <style>
                    .dataset-configs-manager {
                        max-height: 60vh;
                        overflow-y: auto;
                    }
                    .configs-section h4 {
                        margin: 0 0 12px 0;
                        font-size: 14px;
                        font-weight: bold;
                        color: #333;
                    }
                    .configs-list {
                        display: flex;
                        flex-direction: column;
                        gap: 12px;
                    }
                    .config-item {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        padding: 12px;
                        background: #f5f5f5;
                        border-radius: 6px;
                        border: 1px solid #e0e0e0;
                    }
                    .config-info {
                        flex: 1;
                    }
                    .config-info strong {
                        display: block;
                        margin-bottom: 4px;
                        color: #333;
                    }
                    .config-type {
                        display: inline-block;
                        padding: 2px 8px;
                        background: #e3f2fd;
                        color: #1976d2;
                        border-radius: 4px;
                        font-size: 12px;
                        margin-left: 8px;
                    }
                    .config-desc {
                        margin-top: 4px;
                        font-size: 12px;
                        color: #666;
                    }
                    .empty-state {
                        padding: 24px;
                        text-align: center;
                        color: #999;
                        font-size: 14px;
                    }
                </style>
            `;

            openModal(title, content, null, true); // 第四个参数表示不需要提交按钮
        },

        addDatasetConfig: async function(datasetId) {
            const configSelect = document.getElementById('configSelect');
            const configId = configSelect.value;

            if (!configId) {
                showError(t('dataset.selectConfigToAdd'));
                return;
            }

            try {
                await apiPost(`/annotation-configs/${configId}/associate/${datasetId}`);
                showSuccess(t('dataset.configAddSuccess'));
                // 重新加载管理界面
                this.manageDatasetConfigs(datasetId);
            } catch (error) {
                showError(t('dataset.configAddFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        removeDatasetConfig: async function(datasetId, configId) {
            if (!confirm(t('dataset.configRemoveConfirm'))) {
                return;
            }

            try {
                await apiDelete(`/annotation-configs/${configId}/associate/${datasetId}`);
                showSuccess(t('dataset.configRemoveSuccess'));
                // 重新加载管理界面
                this.manageDatasetConfigs(datasetId);
            } catch (error) {
                showError(t('dataset.configRemoveFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        showImportDatasetForm: async function() {
            const title = t('dataset.importDataset');

            // 加载用户列表
            const users = await this.loadUsersForSelect();
            const userOptions = '<option value="">' + t('common.none') + '</option>' + users.map(user =>
                `<option value="${user.id}">${escapeHtml(user.username)}${user.full_name ? ' (' + escapeHtml(user.full_name) + ')' : ''}</option>`
            ).join('');

            const content = `
                <form id="importDatasetForm">
                    <div class="form-group">
                        <label>${t('dataset.selectJsonlFile')} *</label>
                        <input type="file" id="importDatasetFile" accept=".jsonl" required>
                        <small style="color: #666; display: block; margin-top: 4px;">
                            ${t('dataset.jsonlFileHelp')}
                        </small>
                    </div>
                    <div style="border-top: 1px solid #e0e0e0; margin: 16px 0; padding-top: 16px;">
                        <h4 style="margin: 0 0 12px 0; font-size: 14px; font-weight: bold;">${t('dataset.metadataOptional')}</h4>
                        <small style="color: #666; display: block; margin-bottom: 12px;">
                            ${t('dataset.metadataHelp')}
                        </small>
                        <div class="form-group">
                            <label>${t('dataset.name')} *</label>
                            <input type="text" id="importDatasetName" placeholder="${t('dataset.namePlaceholder')}">
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.description')}</label>
                            <textarea id="importDatasetDescription" rows="2" placeholder="${t('dataset.descriptionPlaceholder')}"></textarea>
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.version')}</label>
                            <input type="text" id="importDatasetVersion" placeholder="${t('dataset.versionPlaceholder')}">
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.category')}</label>
                            <input type="text" id="importDatasetCategory" placeholder="${t('dataset.categoryPlaceholder')}">
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.status')}</label>
                            <select id="importDatasetStatus">
                                <option value="active">${t('status.active')}</option>
                                <option value="inactive">${t('status.inactive')}</option>
                                <option value="archived">${t('status.archived')}</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.tags')}</label>
                            <input type="text" id="importDatasetTags" placeholder="${t('dataset.tagsPlaceholder')}">
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.source')}</label>
                            <input type="text" id="importDatasetSource" placeholder="${t('dataset.sourcePlaceholder')}">
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.sourceUrl')}</label>
                            <input type="url" id="importDatasetSourceUrl" placeholder="${t('dataset.sourceUrlPlaceholder')}">
                        </div>
                        <div class="form-group">
                            <label>${t('dataset.annotator')}</label>
                            <select id="importDatasetAnnotatorId">
                                ${userOptions}
                            </select>
                            <small style="color: #666; display: block; margin-top: 4px;">
                                ${t('dataset.annotatorHelp')}
                            </small>
                        </div>
                    </div>
                    <div class="form-group">
                        <div id="importDatasetProgress" style="display: none;">
                            <p style="color: #666;">${t('dataset.importing')}</p>
                        </div>
                        <div id="importDatasetResult" style="display: none;"></div>
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.handleImportDataset();
            });
        },

        handleImportDataset: async function() {
            const fileInput = document.getElementById('importDatasetFile');
            const file = fileInput.files[0];

            if (!file) {
                showError(t('dataset.selectFileError'));
                return;
            }

            if (!file.name.endsWith('.jsonl')) {
                showError(t('dataset.fileFormatError'));
                return;
            }

            // 收集元数据
            const name = document.getElementById('importDatasetName').value.trim();
            const description = document.getElementById('importDatasetDescription').value.trim();
            const version = document.getElementById('importDatasetVersion').value.trim();
            const category = document.getElementById('importDatasetCategory').value.trim();
            const status = document.getElementById('importDatasetStatus').value;
            const tags = document.getElementById('importDatasetTags').value.trim();
            const source = document.getElementById('importDatasetSource').value.trim();
            const sourceUrl = document.getElementById('importDatasetSourceUrl').value.trim();
            const annotatorIdInput = document.getElementById('importDatasetAnnotatorId').value;
            const annotatorId = annotatorIdInput ? parseInt(annotatorIdInput) : null;

            // 显示进度
            const progressDiv = document.getElementById('importDatasetProgress');
            const resultDiv = document.getElementById('importDatasetResult');
            progressDiv.style.display = 'block';
            resultDiv.style.display = 'none';

            try {
                // 构建FormData，包含文件和元数据
                const formData = new FormData();
                formData.append('file', file);
                if (name) formData.append('name', name);
                if (description) formData.append('description', description);
                if (version) formData.append('version', version);
                if (category) formData.append('category', category);
                if (status) formData.append('status', status);
                if (tags) formData.append('tags', tags);
                if (source) formData.append('source', source);
                if (sourceUrl) formData.append('source_url', sourceUrl);
                if (annotatorId) formData.append('annotator_id', annotatorId);

                // 获取token
                const token = getToken();
                const headers = {};
                if (token) {
                    headers['Authorization'] = `Bearer ${token}`;
                }

                // 发送请求
                const response = await fetch(`${API_BASE_URL}/datasets/import`, {
                    method: 'POST',
                    headers: headers,
                    body: formData
                });

                // 处理响应
                let result;
                const contentType = response.headers.get('content-type');

                if (contentType && contentType.includes('application/json')) {
                    try {
                        result = await response.json();
                    } catch (error) {
                        result = {};
                    }
                } else {
                    result = await response.text();
                }

                // 如果响应不成功，抛出错误
                if (!response.ok) {
                    const error = new Error(result.detail || result.message || `${t('messages.httpError')}: ${response.status}`);
                    error.status = response.status;
                    error.data = result;
                    throw error;
                }

                // 隐藏进度，显示结果
                progressDiv.style.display = 'none';
                resultDiv.style.display = 'block';

                const datasetAction = result.created ? t('dataset.created') : t('dataset.updated');
                const successMsg = `${t('dataset.importComplete')} ${datasetAction} ${t('dataset.dataset')} "${result.dataset_name}", ${t('dataset.importedCount', { imported: result.imported_count, failed: result.failed_count, total: result.total_lines })}`;

                if (result.failed_count > 0 && result.errors && result.errors.length > 0) {
                    const errorsHtml = result.errors.map(err => `<li style="color: #d32f2f; margin: 4px 0;">${escapeHtml(err)}</li>`).join('');
                    resultDiv.innerHTML = `
                        <div style="margin-top: 12px;">
                            <p style="color: #2e7d32; font-weight: bold;">${successMsg}</p>
                            ${result.errors.length > 0 ? `
                                <details style="margin-top: 12px;">
                                    <summary style="cursor: pointer; color: #d32f2f; font-weight: bold;">
                                        ${t('dataset.errorDetails', { count: result.errors.length })}
                                    </summary>
                                    <ul style="margin-top: 8px; padding-left: 20px; max-height: 200px; overflow-y: auto;">
                                        ${errorsHtml}
                                    </ul>
                                </details>
                            ` : ''}
                        </div>
                    `;
                } else {
                    resultDiv.innerHTML = `<p style="color: #2e7d32; font-weight: bold;">${successMsg}</p>`;
                }

                // 如果导入成功，刷新数据集列表
                if (result.imported_count > 0 || result.created) {
                    setTimeout(() => {
                        this.loadDatasets();
                    }, 1000);
                }

                showSuccess(successMsg);

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
                showError(t('dataset.importFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        loadQAPairs: async function(datasetId) {
            if (!datasetId || !qaPaginator) {
                return;
            }

            try {
                const skip = qaPaginator.getSkip();
                const limit = qaPaginator.getLimit();

                // 同时获取数据集信息和QA对
                const [dataset, qaPairs] = await Promise.all([
                    apiGet(`/datasets/${datasetId}`),
                    apiGet(`/datasets/${datasetId}/items/?skip=${skip}&limit=${limit}`)
                ]);

                // 获取总数（通过获取数据集统计信息）
                let totalCount;
                try {
                    const stats = await apiGet(`/datasets/${datasetId}/stats`);
                    totalCount = stats.items_count || 0;
                } catch (error) {
                    // 如果获取统计失败，根据返回的数据量估算
                    const currentPage = qaPaginator.currentPage;
                    totalCount = qaPairs.length === limit ? (currentPage * limit + 1) : ((currentPage - 1) * limit + qaPairs.length);
                }

                qaPaginator.setTotalCount(totalCount);
                this.renderQAPairsTable(qaPairs, dataset);
            } catch (error) {
                console.error('Failed to load QA pairs:', error);
                showError(t('dataset.loadQAPairsFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        renderQAPairsTable: function(qaPairs, dataset = null) {
            const tbody = container.querySelector('#qaPairsTableBody');
            const thead = tbody ? tbody.closest('table').querySelector('thead tr') : null;
            const paginationContainer = container.querySelector('#qaPaginationContainer');

            if (!tbody || !thead) return;

            // 获取要显示的extra字段列表
            const displayExtraFields = dataset && dataset.display_extra_fields ? dataset.display_extra_fields : [];

            // 动态更新表头
            const baseHeaders = [t('dataset.serialNumber'), t('dataset.question'), t('dataset.answer')];
            const extraHeaders = displayExtraFields.map(field => escapeHtml(field));
            const allHeaders = [...baseHeaders, ...extraHeaders, t('common.actions')];

            thead.innerHTML = allHeaders.map(header => `<th>${header}</th>`).join('');

            // 计算总列数（用于colspan）
            const totalCols = allHeaders.length;

            if (qaPairs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="${totalCols}" class="loading">${t('dataset.noQAPairs')}</td></tr>`;
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            // 计算当前页的起始序号
            const startIndex = qaPaginator ? qaPaginator.getSkip() : 0;

            // 渲染表格内容
            tbody.innerHTML = qaPairs.map((qa, index) => {
                // 基础列
                let row = `
                    <td>${startIndex + index + 1}</td>
                    <td>${escapeHtml(qa.question).substring(0, 100)}${qa.question.length > 100 ? '...' : ''}</td>
                    <td>${escapeHtml(qa.answer).substring(0, 100)}${qa.answer.length > 100 ? '...' : ''}</td>
                `;

                // 添加extra字段列
                displayExtraFields.forEach(field => {
                    const value = qa[field];
                    if (value !== undefined && value !== null) {
                        const displayValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
                        row += `<td>${escapeHtml(displayValue).substring(0, 50)}${displayValue.length > 50 ? '...' : ''}</td>`;
                    } else {
                        row += '<td>-</td>';
                    }
                });

                // 操作列
                row += '<td>-</td>';

                return `<tr>${row}</tr>`;
            }).join('');

            // 显示分页器
            if (paginationContainer && qaPaginator) {
                paginationContainer.style.display = 'block';
                qaPaginator.render();
            }
        },

        showImportDataForm: function() {
            if (!currentDatasetId) {
                showError(t('system.selectDatasetFirst'));
                return;
            }

            const title = t('dataset.importData');
            const content = `
                <form id="importForm">
                    <div class="form-group">
                        <label>${t('dataset.selectJsonlFile')} *</label>
                        <input type="file" id="importFile" accept=".jsonl" required>
                        <small style="color: #666; display: block; margin-top: 4px;">
                            ${t('dataset.jsonlFileHelp')}
                        </small>
                    </div>
                    <div class="form-group">
                        <div id="importProgress" style="display: none;">
                            <p style="color: #666;">${t('dataset.importing')}</p>
                        </div>
                        <div id="importResult" style="display: none;"></div>
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.handleImportData();
            });
        },

        handleImportData: async function() {
            const fileInput = document.getElementById('importFile');
            const file = fileInput.files[0];

            if (!file) {
                showError(t('dataset.selectFileError'));
                return;
            }

            if (!file.name.endsWith('.jsonl')) {
                showError(t('dataset.fileFormatError'));
                return;
            }

            // 显示进度
            const progressDiv = document.getElementById('importProgress');
            const resultDiv = document.getElementById('importResult');
            progressDiv.style.display = 'block';
            resultDiv.style.display = 'none';

            try {
                const result = await apiUploadFile(`/datasets/${currentDatasetId}/import`, file);

                // 隐藏进度，显示结果
                progressDiv.style.display = 'none';
                resultDiv.style.display = 'block';

                const successMsg = `${t('dataset.importComplete')} ${t('dataset.importedCount', { imported: result.imported_count, failed: result.failed_count, total: result.total_lines })}`;

                if (result.failed_count > 0 && result.errors && result.errors.length > 0) {
                    const errorsHtml = result.errors.map(err => `<li style="color: #d32f2f; margin: 4px 0;">${escapeHtml(err)}</li>`).join('');
                    resultDiv.innerHTML = `
                        <div style="margin-top: 12px;">
                            <p style="color: #2e7d32; font-weight: bold;">${successMsg}</p>
                            ${result.errors.length > 0 ? `
                                <details style="margin-top: 12px;">
                                    <summary style="cursor: pointer; color: #d32f2f; font-weight: bold;">
                                        ${t('dataset.errorDetails', { count: result.errors.length })}
                                    </summary>
                                    <ul style="margin-top: 8px; padding-left: 20px; max-height: 200px; overflow-y: auto;">
                                        ${errorsHtml}
                                    </ul>
                                </details>
                            ` : ''}
                        </div>
                    `;
                } else {
                    resultDiv.innerHTML = `<p style="color: #2e7d32; font-weight: bold;">${successMsg}</p>`;
                }

                // 如果导入成功，刷新QA对列表
                if (result.imported_count > 0) {
                    setTimeout(() => {
                        if (qaPaginator) qaPaginator.reset();
                        this.loadQAPairs(currentDatasetId);
                        this.loadDatasets(); // 刷新数据集列表以更新统计
                    }, 1000);
                }

                showSuccess(successMsg);

                // 3秒后自动关闭模态框
                setTimeout(() => {
                    closeModal();
                }, 3000);

            } catch (error) {
                progressDiv.style.display = 'none';
                showError(t('dataset.importFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        exportAnnotations: function(datasetId) {
            // 显示格式选择对话框
            const title = t('dataset.exportAnnotations');
            const content = `
                <form id="exportForm">
                    <div class="form-group">
                        <label>${t('dataset.exportFormat')} *</label>
                        <select id="exportFormat" required>
                            <option value="json">${t('dataset.jsonFormat')}</option>
                            <option value="csv">${t('dataset.csvFormat')}</option>
                        </select>
                        <small style="color: #666; display: block; margin-top: 4px;">
                            ${t('dataset.exportFormatHelp')}
                        </small>
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.handleExportAnnotations(datasetId);
            });
        },

        handleExportAnnotations: async function(datasetId) {
            const format = document.getElementById('exportFormat').value;

            if (!format) {
                showError(t('dataset.selectExportFormat'));
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
                const exportUrl = `${API_BASE_URL}/annotation-results/datasets/${datasetId}/export?format=${format}`;

                // 使用fetch下载文件
                const response = await fetch(exportUrl, {
                    method: 'GET',
                    headers: headers
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: t('dataset.exportFailed') }));
                    throw new Error(errorData.detail || errorData.message || `${t('messages.httpError')}: ${response.status}`);
                }

                // 获取文件名（从Content-Disposition头中提取，或使用默认名称）
                const contentDisposition = response.headers.get('Content-Disposition');
                let filename = `dataset_${datasetId}_annotations.${format}`;
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

                showSuccess(`${t('dataset.exportSuccess')} ${format.toUpperCase()}`);
                closeModal();

            } catch (error) {
                console.error('Export failed:', error);
                // 如果是401未授权错误，清除token并跳转到登录页
                if (error.status === 401 || (error.message && error.message.includes('401'))) {
                    clearToken();
                    const currentPath = window.location.pathname;
                    if (currentPath !== '/auth') {
                        const redirectUrl = encodeURIComponent(window.location.href);
                        window.location.href = `/auth?redirect=${redirectUrl}`;
                    }
                }
                showError(t('dataset.exportFailed') + ': ' + (error.message || t('messages.unknownError')));
            }
        },

        destroy: function() {
            // 清理资源
            datasetsPaginator = null;
            qaPaginator = null;
            editingId = null;
            currentDatasetId = null;
            container = null;
            usersCache = null;
        }
    };

    // 暴露到全局
    window.DatasetManagement = DatasetManagement;
})();
