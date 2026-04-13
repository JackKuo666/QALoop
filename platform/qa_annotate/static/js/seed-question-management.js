/**
 * 种子问题管理模块 JavaScript
 * 提供所有种子问题的查看和导出功能（管理员）
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 模块私有状态
    let adminPaginator = null;
    let container = null;

    // 种子问题管理模块
    const SeedQuestionManagement = {
        init: function(containerElement) {
            container = containerElement;
            this.initPaginators();
            this.initEventListeners();

            // 等待 i18next 初始化完成后再加载数据
            const loadData = () => {
                this.loadAllQuestions();
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
            // 初始化管理员列表分页器
            adminPaginator = createPaginator('admin', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    this.loadAllQuestions();
                },
                onPageSizeChange: (pageSize) => {
                    this.loadAllQuestions();
                }
            });
        },

        initEventListeners: function() {
            // 搜索
            const adminSearchInput = container.querySelector('#adminSearchInput');
            if (adminSearchInput) {
                let searchTimeout;
                adminSearchInput.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        this.loadAllQuestions();
                    }, 500);
                });
            }

            // 管理类型和亚类
            const manageTypesBtn = container.querySelector('#manageTypesBtn');
            if (manageTypesBtn) {
                manageTypesBtn.addEventListener('click', () => {
                    this.showManageTypesModal();
                });
            }

            // 管理员刷新
            const refreshAdminBtn = container.querySelector('#refreshAdminBtn');
            if (refreshAdminBtn) {
                refreshAdminBtn.addEventListener('click', () => {
                    this.loadAllQuestions();
                });
            }

            // 管理员导出
            const exportBtn = container.querySelector('#exportBtn');
            if (exportBtn) {
                exportBtn.addEventListener('click', () => {
                    this.exportQuestions();
                });
            }
        },

        loadAllQuestions: async function() {
            if (!adminPaginator) return;

            const tbody = container.querySelector('#adminTableBody');
            if (!tbody) return;

            try {
                tbody.innerHTML = '<tr><td colspan="10" class="loading">加载中...</td></tr>';

                const skip = adminPaginator.getSkip();
                const limit = adminPaginator.getLimit();

                const search = container.querySelector('#adminSearchInput')?.value.trim() || null;

                const params = new URLSearchParams({
                    skip: skip.toString(),
                    limit: limit.toString()
                });
                if (search) {
                    params.append('search', search);
                }

                const questions = await apiGet(`/seed-questions/admin/all?${params.toString()}`);

                if (questions.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="10" class="empty-state"><div class="empty-state-icon">📝</div><div class="empty-state-text">${t('common.noData')}</div></td></tr>`;
                    const paginationContainer = container.querySelector('#adminPaginationContainer');
                    if (paginationContainer) paginationContainer.classList.add('hidden');
                    return;
                }

                tbody.innerHTML = questions.map(q => `
                    <tr>
                        <td>${q.id}</td>
                        <td>${escapeHtml(q.question)}</td>
                        <td>${escapeHtml(q.type)}</td>
                        <td>${escapeHtml(q.subtype)}</td>
                        <td>${escapeHtml(q.species_or_domain || '-')}</td>
                        <td>${escapeHtml(q.model || '-')}</td>
                        <td>${q.date ? this.formatDate(q.date) : '-'}</td>
                        <td>${q.is_verified ? '✓' : '-'}</td>
                        <td>${escapeHtml(q.creator_full_name || `用户ID:${q.creator_id}`)}</td>
                        <td>${this.formatDateTime(q.created_at)}</td>
                    </tr>
                `).join('');

                // 更新分页信息
                const total = await this.getAllQuestionsCount(search);
                adminPaginator.setTotalCount(total);
                adminPaginator.render();
                const paginationContainer = container.querySelector('#adminPaginationContainer');
                if (paginationContainer) paginationContainer.classList.remove('hidden');

            } catch (error) {
                console.error('加载问题列表失败:', error);
                tbody.innerHTML = '<tr><td colspan="10" class="loading">加载失败，请刷新重试</td></tr>';
            }
        },

        getAllQuestionsCount: async function(search) {
            try {
                const result = await apiGet(`/seed-questions/admin/all?skip=0&limit=1000${search ? '&search=' + encodeURIComponent(search) : ''}`);
                return result.length;
            } catch (error) {
                return 0;
            }
        },

        exportQuestions: async function() {
            try {
                const exportBtn = container.querySelector('#exportBtn');
                const originalText = exportBtn ? exportBtn.textContent : '导出CSV';
                if (exportBtn) {
                    exportBtn.disabled = true;
                    exportBtn.textContent = '导出中...';
                }

                const response = await fetch('/api/seed-questions/admin/export', {
                    method: 'GET',
                    headers: getAuthHeaders()
                });

                if (!response.ok) {
                    throw new Error('导出失败');
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `seed_questions_export_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

                showSuccess('导出成功！');

            } catch (error) {
                console.error('导出失败:', error);
                showError('导出失败，请重试');
            } finally {
                const exportBtn = container.querySelector('#exportBtn');
                if (exportBtn) {
                    exportBtn.disabled = false;
                    exportBtn.textContent = '导出CSV';
                }
            }
        },

        formatDate: function(dateString) {
            if (!dateString) return '-';
            const date = new Date(dateString);
            return date.toLocaleDateString('zh-CN');
        },

        formatDateTime: function(dateString) {
            if (!dateString) return '-';
            const date = new Date(dateString);
            return date.toLocaleString('zh-CN');
        },

        showManageTypesModal: async function() {
            try {
                // 加载所有类型和亚类
                const types = await apiGet('/seed-questions/admin/types?limit=1000');

                // 按类型分组
                const grouped = {};
                types.forEach(t => {
                    if (!grouped[t.type]) {
                        grouped[t.type] = [];
                    }
                    grouped[t.type].push(t);
                });

                // 构建内容
                let content = `
                    <div style="max-height: 60vh; overflow-y: auto;">
                        <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
                            <h4 style="margin: 0;">类型和亚类列表</h4>
                            <button class="btn btn-primary btn-sm" id="addTypeBtn">添加类型/亚类</button>
                        </div>
                        <div id="typesListContainer">
                `;

                // 按类型分组显示
                const sortedTypes = Object.keys(grouped).sort();
                if (sortedTypes.length === 0) {
                    content += '<div style="text-align: center; padding: 40px; color: #999;">暂无类型和亚类</div>';
                } else {
                    sortedTypes.forEach(typeName => {
                        const subtypes = grouped[typeName].sort((a, b) => (a.order || 0) - (b.order || 0));
                        content += `
                            <div style="margin-bottom: 16px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px;">
                                <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px; color: #667eea;">
                                    ${escapeHtml(typeName)}
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 8px;">
                        `;
                        subtypes.forEach(subtype => {
                            content += `
                                <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px; background: #f8f9fa; border-radius: 4px;">
                                    <div>
                                        <span style="font-weight: 500;">${escapeHtml(subtype.subtype)}</span>
                                        <span style="color: #999; font-size: 12px; margin-left: 8px;">(ID: ${subtype.id}, 顺序: ${subtype.order || 0})</span>
                                    </div>
                                    <div style="display: flex; gap: 8px;">
                                        <button class="btn btn-sm btn-secondary" onclick="window.SeedQuestionManagement.editType(${subtype.id})">编辑</button>
                                        <button class="btn btn-sm btn-danger" onclick="window.SeedQuestionManagement.deleteType(${subtype.id})">删除</button>
                                    </div>
                                </div>
                            `;
                        });
                        content += `
                                </div>
                            </div>
                        `;
                    });
                }

                content += `
                        </div>
                    </div>
                `;

                openModal('管理类型和亚类', content, null, true);

                // 添加按钮事件
                const addTypeBtn = document.getElementById('addTypeBtn');
                if (addTypeBtn) {
                    addTypeBtn.addEventListener('click', () => {
                        this.showAddTypeModal();
                    });
                }

            } catch (error) {
                console.error('加载类型列表失败:', error);
                showError('加载类型列表失败: ' + (error.message || '未知错误'));
            }
        },

        showAddTypeModal: function() {
            const title = '添加类型/亚类';
            const content = `
                <form id="addTypeForm">
                    <div class="form-group">
                        <label>类型名称 *</label>
                        <input type="text" id="typeName" required minlength="1" maxlength="100" placeholder="例如: 事实性">
                    </div>
                    <div class="form-group">
                        <label>亚类名称 *</label>
                        <input type="text" id="subtypeName" required minlength="1" maxlength="100" placeholder="例如: 定义">
                    </div>
                    <div class="form-group">
                        <label>显示顺序</label>
                        <input type="number" id="typeOrder" value="0" min="0">
                        <small style="color: #666; display: block; margin-top: 4px;">
                            数字越小越靠前显示
                        </small>
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.saveType();
            });
        },

        saveType: async function() {
            const typeName = document.getElementById('typeName').value.trim();
            const subtypeName = document.getElementById('subtypeName').value.trim();
            const order = parseInt(document.getElementById('typeOrder').value) || 0;

            if (!typeName || !subtypeName) {
                showError('类型名称和亚类名称不能为空');
                return;
            }

            try {
                await apiPost('/seed-questions/admin/types', {
                    type: typeName,
                    subtype: subtypeName,
                    order: order
                });
                showSuccess('类型/亚类添加成功');
                closeModal();
                // 重新打开管理模态框
                this.showManageTypesModal();
            } catch (error) {
                console.error('添加类型失败:', error);
                showError('添加类型失败: ' + (error.message || '未知错误'));
            }
        },

        editType: async function(typeId) {
            try {
                const types = await apiGet('/seed-questions/admin/types?limit=1000');
                const type = types.find(t => t.id === typeId);
                if (!type) {
                    showError('类型不存在');
                    return;
                }

                const title = '编辑类型/亚类';
                const content = `
                    <form id="editTypeForm">
                        <div class="form-group">
                            <label>类型名称 *</label>
                            <input type="text" id="editTypeName" value="${escapeHtml(type.type)}" required minlength="1" maxlength="100">
                        </div>
                        <div class="form-group">
                            <label>亚类名称 *</label>
                            <input type="text" id="editSubtypeName" value="${escapeHtml(type.subtype)}" required minlength="1" maxlength="100">
                        </div>
                        <div class="form-group">
                            <label>显示顺序</label>
                            <input type="number" id="editTypeOrder" value="${type.order || 0}" min="0">
                            <small style="color: #666; display: block; margin-top: 4px;">
                                数字越小越靠前显示
                            </small>
                        </div>
                    </form>
                `;

                openModal(title, content, async () => {
                    await this.updateType(typeId);
                });
            } catch (error) {
                console.error('加载类型信息失败:', error);
                showError('加载类型信息失败: ' + (error.message || '未知错误'));
            }
        },

        updateType: async function(typeId) {
            const typeName = document.getElementById('editTypeName').value.trim();
            const subtypeName = document.getElementById('editSubtypeName').value.trim();
            const order = parseInt(document.getElementById('editTypeOrder').value) || 0;

            if (!typeName || !subtypeName) {
                showError('类型名称和亚类名称不能为空');
                return;
            }

            try {
                await apiPut(`/seed-questions/admin/types/${typeId}`, {
                    type: typeName,
                    subtype: subtypeName,
                    order: order
                });
                showSuccess('类型/亚类更新成功');
                closeModal();
                // 重新打开管理模态框
                this.showManageTypesModal();
            } catch (error) {
                console.error('更新类型失败:', error);
                showError('更新类型失败: ' + (error.message || '未知错误'));
            }
        },

        deleteType: async function(typeId) {
            if (!confirm('确定要删除这个类型/亚类吗？删除后无法恢复。')) {
                return;
            }

            try {
                await apiDelete(`/seed-questions/admin/types/${typeId}`);
                showSuccess('类型/亚类删除成功');
                // 重新打开管理模态框
                this.showManageTypesModal();
            } catch (error) {
                console.error('删除类型失败:', error);
                showError('删除类型失败: ' + (error.message || '未知错误'));
            }
        }
    };

    // 导出到全局
    window.SeedQuestionManagement = SeedQuestionManagement;
})();
