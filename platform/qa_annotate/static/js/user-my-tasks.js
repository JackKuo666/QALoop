/**
 * 我的任务管理模块 JavaScript
 * 提供已领取任务的查看和跳转标注功能
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 模块私有状态
    let listPaginator = null;
    let container = null;

    // 我的任务管理模块
    const UserMyTasks = {
        init: function(containerElement) {
            container = containerElement;
            this.initPaginators();
            this.initEventListeners();
            this.loadMyTasks();
        },

        initPaginators: function() {
            // 初始化我的任务列表分页器
            listPaginator = createPaginator('myTasks', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    this.loadMyTasks();
                },
                onPageSizeChange: (pageSize) => {
                    this.loadMyTasks();
                }
            });
        },

        initEventListeners: function() {
            // 刷新列表
            const refreshBtn = container.querySelector('#refreshMyTasksBtn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.loadMyTasks();
                });
            }
            // 使用说明按钮
            const showUsageBtn = container.querySelector('#showMyTasksUsageBtn');
            if (showUsageBtn) {
                showUsageBtn.addEventListener('click', () => {
                    this.showMyTasksUsage();
                });
            }
        },

        loadMyTasks: async function() {
            if (!listPaginator) return;

            const tbody = container.querySelector('#myTasksTableBody');
            if (!tbody) return;

            try {
                tbody.innerHTML = '<tr><td colspan="10" class="loading">加载中...</td></tr>';

                const skip = listPaginator.getSkip();
                const limit = listPaginator.getLimit();

                const tasks = await apiGet(`/datasets/tasks/my?skip=${skip}&limit=${limit}`);

                const emptyState = container.querySelector('#myTasksEmptyState');
                const paginationContainer = container.querySelector('#myTasksPaginationContainer');

                if (tasks.length === 0) {
                    tbody.innerHTML = '';
                    if (emptyState) emptyState.classList.remove('hidden');
                    if (paginationContainer) paginationContainer.classList.add('hidden');
                    return;
                }

                if (emptyState) emptyState.classList.add('hidden');
                if (paginationContainer) paginationContainer.classList.remove('hidden');

                tbody.innerHTML = tasks.map(task => {
                    const category = task.category
                        ? `<span class="category-requirement has-category">${escapeHtml(task.category)}</span>`
                        : '-';

                    const evaluationDimensions = task.evaluation_dimensions && task.evaluation_dimensions.length > 0
                        ? `<div class="evaluation-dimension-tags">${task.evaluation_dimensions.map(dim =>
                            `<span class="evaluation-dimension-tag" title="${escapeHtml(dim.description || '')}">${escapeHtml(dim.name)}</span>`
                        ).join('')}</div>`
                        : '-';

                    const deadlineInfo = this.formatDeadline(task.deadline);

                    const taskDescription = task.task_description
                        ? `<div class="task-description" title="${escapeHtml(task.task_description)}">${escapeHtml(task.task_description)}</div>`
                        : '-';

                    const evaluationPurpose = task.evaluation_purpose
                        ? `<div class="evaluation-purpose" title="${escapeHtml(task.evaluation_purpose)}">${escapeHtml(task.evaluation_purpose)}</div>`
                        : '-';

                    // 渲染进度
                    const progressHtml = this.renderProgress(task);

                    return `
                        <tr>
                            <td>${escapeHtml(task.dataset_name)}</td>
                            <td>${taskDescription}</td>
                            <td>${category}</td>
                            <td>${task.target_annotation_count}${t('task.qaUnit')}</td>
                            <td>${progressHtml}</td>
                            <td>${escapeHtml(task.project_name || '-')}</td>
                            <td>${evaluationPurpose}</td>
                            <td>${deadlineInfo}</td>
                            <td>${evaluationDimensions}</td>
                            <td>
                                <div class="action-buttons">
                                    <button class="btn btn-sm btn-primary" onclick="window.UserMyTasks.startAnnotation(${task.dataset_id})">${t('common.startAnnotate')}</button>
                                    <button class="btn btn-sm btn-secondary" onclick="window.UserMyTasks.releaseTask(${task.dataset_id})">${t('task.release')}</button>
                                </div>
                            </td>
                        </tr>
                    `;
                }).join('');

                // 更新分页信息
                const hasMore = tasks.length === limit;
                listPaginator.setTotalCount((listPaginator.currentPage - 1) * limit + tasks.length + (hasMore ? 1 : 0));
                listPaginator.render();

            } catch (error) {
                console.error('加载我的任务列表失败:', error);
                tbody.innerHTML = '<tr><td colspan="10" class="loading">加载失败，请刷新重试</td></tr>';
                showError('加载我的任务列表失败: ' + (error.message || '未知错误'));
            }
        },

        startAnnotation: function(datasetId) {
            // 跳转到标注工作台
            window.location.href = `/annotation?dataset_id=${datasetId}`;
        },

        releaseTask: async function(datasetId) {
            // 确认退回任务
            if (!confirm(t('task.releaseConfirm'))) {
                return;
            }

            try {
                // 调用退回任务API
                await apiPost(`/datasets/tasks/${datasetId}/release`, {});

                // 显示成功消息
                showSuccess(t('task.taskReleased'));

                // 刷新任务列表
                this.loadMyTasks();
            } catch (error) {
                console.error(t('task.releaseFailed') + ':', error);
                showError(t('task.releaseFailed') + ': ' + (error.message || t('common.unknownError')));
            }
        },

        formatDeadline: function(deadlineString) {
            if (!deadlineString) return '-';

            try {
                const deadline = new Date(deadlineString);
                const now = new Date();
                const diff = deadline - now;

                const formattedDate = this.formatDateTime(deadlineString);

                if (diff < 0) {
                    // 已过期
                    return `<span class="deadline-countdown expired">${formattedDate} (${t('task.expired')})</span>`;
                } else if (diff < 24 * 60 * 60 * 1000) {
                    // 少于24小时
                    const hours = Math.floor(diff / (60 * 60 * 1000));
                    const minutes = Math.floor((diff % (60 * 60 * 1000)) / (60 * 1000));
                    const timeLeft = t('task.expiresInMinutes', { hours: hours, minutes: minutes });
                    return `<span class="deadline-countdown danger">${formattedDate}<br><small>${timeLeft}</small></span>`;
                } else if (diff < 3 * 24 * 60 * 60 * 1000) {
                    // 少于3天
                    const days = Math.floor(diff / (24 * 60 * 60 * 1000));
                    const hours = Math.floor((diff % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
                    const timeLeft = t('task.expiresInHours', { days: days, hours: hours });
                    return `<span class="deadline-countdown warning">${formattedDate}<br><small>${timeLeft}</small></span>`;
                } else {
                    // 还有充足时间
                    return formattedDate;
                }
            } catch (e) {
                return deadlineString;
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
        },

        renderProgress: function(task) {
            if (task.annotated_count === undefined || task.annotated_count === null) {
                return '-';
            }

            const total = task.target_annotation_count || 0;
            const annotated = task.annotated_count || 0;
            const rate = task.progress_rate || 0;

            if (total === 0) {
                return '-';
            }

            const percentage = Math.round(rate);
            const progressBarClass = percentage === 100 ? 'progress-bar-complete' :
                                    percentage >= 80 ? 'progress-bar-high' :
                                    percentage >= 50 ? 'progress-bar-medium' :
                                    'progress-bar-low';

            return `
                <div class="task-progress">
                    <div class="task-progress-text">
                        ${annotated} / ${total} (${percentage}%)
                    </div>
                    <div class="task-progress-bar-container">
                        <div class="task-progress-bar ${progressBarClass}" style="width: ${percentage}%"></div>
                    </div>
                </div>
            `;
        },

        showMyTasksUsage: function() {
            // 构建t('task.usageGuideTitle')内容
            const usageContent = `
                <div style="max-width: 800px; line-height: 1.6;">
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 8px;">
                            t('task.usageGuideTitle')
                        </h3>
                        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin-top: 10px;">
                            <h4 style="margin-top: 0; color: #2196F3;">1. 任务查看</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>显示您已领取的所有标注任务</li>
                                <li>可以查看任务的详细信息，包括数据集名称、任务描述、分类、目标标注数量等</li>
                                <li>显示任务所属的项目名称、评估目的、要求完成时间等元数据</li>
                                <li>显示任务的评估维度，帮助您了解标注要求</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">2. 任务进度</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>实时显示每个任务的标注进度（已标注数量/目标数量）</li>
                                <li>进度条颜色表示完成情况：绿色（完成）、蓝色（高进度）、黄色（中等进度）、红色（低进度）</li>
                                <li>进度计算基于必填标注配置，只有完成所有必填配置才算完成一个QA对的标注</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">3. 任务分类</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>任务可能包含分类标签，表示该任务需要特定领域的专业知识</li>
                                <li>只有匹配您账户物种标签的任务才会显示在可领取任务列表中</li>
                                <li>没有分类标签的任务，所有用户都可以领取</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">4. 开始标注</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>点击"开始标注"按钮可以跳转到标注工作台</li>
                                <li>在标注工作台中，您可以看到该数据集的所有QA对和标注配置</li>
                                <li>根据评估维度和标注配置完成标注工作</li>
                                <li>标注完成后，进度会自动更新</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">5. 完成时间</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>如果任务设置了完成时间，会显示在任务列表中</li>
                                <li>接近或超过完成时间的任务会有颜色提示（红色表示已过期或即将过期）</li>
                                <li>请合理安排时间，按时完成标注任务</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">6. 任务刷新</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>点击"刷新"按钮可以更新任务列表和进度信息</li>
                                <li>建议在完成标注后刷新页面，查看最新的进度</li>
                            </ul>
                        </div>
                    </div>

                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; border-bottom: 2px solid #FF9800; padding-bottom: 8px;">
                            使用建议
                        </h3>
                        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #FF9800; margin-top: 10px;">
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li><strong>任务优先级：</strong>根据完成时间合理安排任务优先级，优先处理即将到期的任务</li>
                                <li><strong>进度跟踪：</strong>定期查看任务进度，确保按时完成标注工作</li>
                                <li><strong>标注质量：</strong>仔细阅读任务描述和评估维度，确保标注质量符合要求</li>
                                <li><strong>必填配置：</strong>注意必填标注配置，必须完成所有必填配置才能算完成一个QA对的标注</li>
                                <li><strong>任务理解：</strong>在开始标注前，仔细阅读任务描述、评估目的和评估维度，充分理解标注要求</li>
                            </ul>
                        </div>
                    </div>
                </div>
            `;

            // 显示对话框（隐藏提交按钮，只显示关闭按钮）
            openModal(t('task.usageGuideTitle'), usageContent, null, true);
        }
    };

    // 导出到全局
    window.UserMyTasks = UserMyTasks;
})();
