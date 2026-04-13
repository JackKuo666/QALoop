/**
 * 可领取任务管理模块 JavaScript
 * 提供可领取任务的查看和领取功能
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 模块私有状态
    let listPaginator = null;
    let container = null;

    // 可领取任务管理模块
    const UserAvailableTasks = {
        init: function(containerElement) {
            container = containerElement;
            this.initPaginators();
            this.initEventListeners();
            this.loadAvailableTasks();
        },

        initPaginators: function() {
            // 初始化可领取任务列表分页器
            listPaginator = createPaginator('availableTasks', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    this.loadAvailableTasks();
                },
                onPageSizeChange: (pageSize) => {
                    this.loadAvailableTasks();
                }
            });
        },

        initEventListeners: function() {
            // 刷新列表
            const refreshBtn = container.querySelector('#refreshAvailableTasksBtn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.loadAvailableTasks();
                });
            }
        },

        loadAvailableTasks: async function() {
            if (!listPaginator) return;

            const tbody = container.querySelector('#availableTasksTableBody');
            if (!tbody) return;

            try {
                tbody.innerHTML = '<tr><td colspan="9" class="loading">加载中...</td></tr>';

                const skip = listPaginator.getSkip();
                const limit = listPaginator.getLimit();

                const tasks = await apiGet(`/datasets/tasks/available?skip=${skip}&limit=${limit}`);

                const emptyState = container.querySelector('#availableTasksEmptyState');
                const paginationContainer = container.querySelector('#availableTasksPaginationContainer');

                if (tasks.length === 0) {
                    tbody.innerHTML = '';
                    if (emptyState) emptyState.classList.remove('hidden');
                    if (paginationContainer) paginationContainer.classList.add('hidden');
                    return;
                }

                if (emptyState) emptyState.classList.add('hidden');
                if (paginationContainer) paginationContainer.classList.remove('hidden');

                tbody.innerHTML = tasks.map(task => {
                    const categoryRequirement = task.category
                        ? `<span class="category-requirement has-category">${t('task.categoryRequirementPrefix')}${escapeHtml(task.category)}</span>`
                        : `<span class="category-requirement no-category">${t('task.noCategoryRestriction')}</span>`;

                    const evaluationDimensions = task.evaluation_dimensions && task.evaluation_dimensions.length > 0
                        ? `<div class="evaluation-dimension-tags">${task.evaluation_dimensions.map(dim =>
                            `<span class="evaluation-dimension-tag" title="${escapeHtml(dim.description || '')}">${escapeHtml(dim.name)}</span>`
                        ).join('')}</div>`
                        : '-';

                    const deadline = task.deadline
                        ? this.formatDateTime(task.deadline)
                        : '-';

                    const taskDescription = task.task_description
                        ? `<div class="task-description" title="${escapeHtml(task.task_description)}">${escapeHtml(task.task_description)}</div>`
                        : '-';

                    const evaluationPurpose = task.evaluation_purpose
                        ? `<div class="evaluation-purpose" title="${escapeHtml(task.evaluation_purpose)}">${escapeHtml(task.evaluation_purpose)}</div>`
                        : '-';

                    return `
                        <tr>
                            <td>${escapeHtml(task.dataset_name)}</td>
                            <td>${taskDescription}</td>
                            <td>${categoryRequirement}</td>
                            <td>${task.target_annotation_count}${t('task.qaUnit')}</td>
                            <td>${escapeHtml(task.project_name || '-')}</td>
                            <td>${evaluationPurpose}</td>
                            <td>${deadline}</td>
                            <td>${evaluationDimensions}</td>
                            <td>
                                <div class="action-buttons">
                                    <button class="btn btn-sm btn-primary" onclick="window.UserAvailableTasks.claimTask(${task.dataset_id})">${t('task.claim')}</button>
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('');

                // 更新分页信息（由于API可能不支持总数，这里使用简单的分页逻辑）
                // 如果返回的数量等于limit，假设还有更多数据
                const hasMore = tasks.length === limit;
                listPaginator.setTotalCount((listPaginator.currentPage - 1) * limit + tasks.length + (hasMore ? 1 : 0));
                listPaginator.render();

            } catch (error) {
                console.error('Failed to load available tasks:', error);
                tbody.innerHTML = `<tr><td colspan="9" class="loading">${t('task.loadFailed') || '加载失败，请刷新重试'}</td></tr>`;
                showError((t('task.loadListFailed') || '加载可领取任务列表失败') + ': ' + (error.message || t('common.unknownError')));
            }
        },

        claimTask: async function(datasetId) {
            if (!confirm(t('task.claimConfirm'))) {
                return;
            }

            try {
                await apiPost(`/datasets/tasks/${datasetId}/claim`, {});
                showSuccess(t('task.claimSuccess'));
                // 刷新列表
                this.loadAvailableTasks();
            } catch (error) {
                console.error('Failed to claim task:', error);
                const errorMessage = error.data?.detail || error.message || t('common.unknownError');
                showError(t('task.claimFailed') + ': ' + errorMessage);
            }
        },

        formatDateTime: function(dateTimeString) {
            if (!dateTimeString) return '-';
            try {
                const date = new Date(dateTimeString);
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                return `${year}-${month}-${day} ${hours}:${minutes}`;
            } catch (e) {
                return dateTimeString;
            }
        }
    };

    // 导出到全局
    window.UserAvailableTasks = UserAvailableTasks;
})();
