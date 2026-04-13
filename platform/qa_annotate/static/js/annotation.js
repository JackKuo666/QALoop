/**
 * 标注页面 JavaScript
 * 提供QA对标注功能
 */

// 获取翻译函数
// 翻译函数由 i18n-helper.js 提供

// 全局状态
let currentDatasetId = null;
let currentDataset = null; // 当前数据集信息
let currentQAPair = null;
let annotationConfigs = [];
let annotationResults = {}; // 存储已标注的结果 {item_id: {config_id: result}}
let qaPairsList = []; // 缓存的QA对列表
let totalQACount = 0; // 数据集中的QA对总数
let loadedQACount = 0; // 已加载的QA对数量
let isLoadingMore = false; // 是否正在加载更多
const PAGE_SIZE = 50; // 每页加载的数量
let isAdmin = false; // 是否为管理员

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    checkAuth();
    checkUserRole();
    // 从URL参数获取dataset_id
    const urlParams = new URLSearchParams(window.location.search);
    const datasetId = urlParams.get('dataset_id');
    if (datasetId) {
        initAnnotation(parseInt(datasetId));
    } else {
        showError(t('error.missingDatasetIdParam'));
        // 3秒后返回用户中心
        setTimeout(() => {
            window.location.href = '/user';
        }, 3000);
    }
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
        // 获取用户列表，非超级用户会返回自己的信息
        const users = await apiGet('/users/?skip=0&limit=1');
        if (users && users.length > 0) {
            const currentUser = users[0];
            isAdmin = currentUser.is_superuser;
        }
    } catch (error) {
        console.error(t('error.checkUserRoleFailed') + ':', error);
    }
}


// ==================== 事件监听 ====================

function initEventListeners() {
    // 退出登录
    const logoutBtn = document.getElementById('logoutBtn');
    logoutBtn.addEventListener('click', () => {
        clearToken();
        window.location.href = '/auth';
    });

    // 返回按钮
    const backBtn = document.getElementById('backBtn');
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            // 根据用户角色跳转到不同页面
            if (isAdmin) {
                window.location.href = '/manager';
            } else {
                window.location.href = '/user';
            }
        });
    }
}

// ==================== 初始化标注页面 ====================

async function initAnnotation(datasetId) {
    try {
        currentDatasetId = datasetId;
        qaPairsList = []; // 清空缓存，准备加载新数据集
        loadedQACount = 0; // 重置已加载数量
        totalQACount = 0; // 重置总数
        await loadDatasetInfo(currentDatasetId); // 加载数据集信息
        await loadAnnotationConfigs(currentDatasetId);
        await loadAnnotationResults(currentDatasetId); // 先加载标注结果
        await loadQAList(currentDatasetId); // 再加载和渲染列表
        setupScrollListener(); // 设置滚动监听
    } catch (error) {
        console.error(t('error.initAnnotationPageFailed') + ':', error);
        const errorMessage = error.data?.detail || error.data?.message || error.message || t('common.unknownError');
        showError(t('error.initAnnotationPageFailed') + ': ' + errorMessage);
        // 3秒后返回用户中心
        setTimeout(() => {
            window.location.href = '/user';
        }, 3000);
    }
}

// ==================== 加载数据集信息 ====================

async function loadDatasetInfo(datasetId) {
    try {
        // 获取数据集详细信息（使用普通用户可访问的端点）
        currentDataset = await apiGet(`/datasets/annotation/${datasetId}/info`);
        console.log(t('error.loadDatasetInfoFailed') + ':', currentDataset);
    } catch (error) {
        console.error(t('error.loadDatasetInfoFailed') + ':', error);
        currentDataset = null;
    }
}

// ==================== 加载标注配置 ====================

async function loadAnnotationConfigs(datasetId) {
    try {
        // 使用普通用户可访问的端点
        annotationConfigs = await apiGet(`/datasets/annotation/${datasetId}/configs`);
        console.log(t('error.loadAnnotationConfigsFailed') + ':', annotationConfigs);
    } catch (error) {
        console.error(t('error.loadAnnotationConfigsFailed') + ':', error);
        annotationConfigs = [];
    }
}

// ==================== 判断QA对是否已标注 ====================

/**
 * 判断一个QA对是否已标注
 * 逻辑：
 * - 如果有必填配置：所有必填配置都已标注，才算已标注
 * - 如果只有选填配置（没有必填配置）：至少一个配置有标注结果，就算已标注
 * @param {number} itemId - QA对的ID
 * @returns {boolean} - 是否已标注
 */
function isItemAnnotated(itemId) {
    if (!annotationConfigs || annotationConfigs.length === 0) {
        return false;
    }

    // 获取当前所有有效配置的ID集合（用于过滤已取消的配置）
    const validConfigIds = new Set(annotationConfigs.map(c => c.id));

    // 获取必填配置
    const requiredConfigs = annotationConfigs.filter(config => config.required);
    const requiredConfigIds = new Set(requiredConfigs.map(c => c.id));

    // 获取当前QA对的标注结果，只保留属于当前有效配置的结果
    const itemResults = annotationResults[itemId] || {};
    const annotatedConfigIds = new Set(
        Object.keys(itemResults)
            .map(Number)
            .filter(id => validConfigIds.has(id))  // 过滤掉已取消配置的标注结果
    );

    // 判断是否已标注
    if (requiredConfigs.length > 0) {
        // 有必填配置：所有必填配置都已标注
        return requiredConfigIds.size > 0 &&
               Array.from(requiredConfigIds).every(id => annotatedConfigIds.has(id));
    } else {
        // 没有必填配置：至少一个配置有标注结果
        return annotatedConfigIds.size > 0;
    }
}

// ==================== 加载QA对列表 ====================

async function loadQAList(datasetId) {
    try {
        // 先获取总数
        const stats = await apiGet(`/datasets/annotation/${datasetId}/stats`).catch(() => null);
        totalQACount = stats?.items_count || 0;

        // 懒加载：只加载第一页
        await loadMoreQAPairs(datasetId, true);
        updateProgressInfo(datasetId);
    } catch (error) {
        console.error(t('error.loadQAPairsListFailed') + ':', error);
        const errorMessage = error.data?.detail || error.data?.message || error.message || t('common.unknownError');
        showError(t('error.loadQAPairsListFailed') + ': ' + errorMessage);
        qaPairsList = []; // 清空缓存
        loadedQACount = 0;
    }
}

// ==================== 加载更多QA对 ====================

async function loadMoreQAPairs(datasetId, isInitial = false) {
    // 如果正在加载或已加载全部，则不加载
    if (isLoadingMore) {
        return;
    }
    if (!isInitial && loadedQACount >= totalQACount && totalQACount > 0) {
        return;
    }

    try {
        isLoadingMore = true;
        showLoadingIndicator(true);

        // 加载下一页数据
        const skip = loadedQACount;
        const limit = PAGE_SIZE;
        const qaPairs = await apiGet(`/datasets/annotation/${datasetId}/items?skip=${skip}&limit=${limit}`);

        if (qaPairs.length === 0) {
            showLoadingIndicator(false);
            isLoadingMore = false;
            return;
        }

        // 追加到缓存列表
        qaPairsList = qaPairsList.concat(qaPairs);
        loadedQACount += qaPairs.length;

        // 渲染新加载的数据
        renderQAList(qaPairs, !isInitial);

        // 如果获取的数据少于请求的数量，说明已经加载完所有数据
        if (qaPairs.length < limit) {
            totalQACount = loadedQACount;
        }

        showLoadingIndicator(false);
        isLoadingMore = false;
    } catch (error) {
        console.error(t('error.loadMoreQAPairsFailed') + ':', error);
        showLoadingIndicator(false);
        isLoadingMore = false;
        const errorMessage = error.data?.detail || error.data?.message || error.message || t('common.unknownError');
        showError(t('error.loadMoreQAPairsFailed') + ': ' + errorMessage);
    }
}

// ==================== 渲染QA对列表 ====================

function renderQAList(qaPairs, append = false) {
    const listContainer = document.getElementById('qaListBody');

    if (!qaPairs || qaPairs.length === 0) {
        if (!append) {
            listContainer.innerHTML = '<li class="qa-list-empty">暂无QA对</li>';
        }
        return;
    }

    // 如果是追加模式，先移除加载指示器
    if (append) {
        const loadingItem = listContainer.querySelector('.qa-list-loading');
        if (loadingItem) {
            loadingItem.remove();
        }
    } else {
        // 清空列表（首次加载）
        listContainer.innerHTML = '';
    }

    // 渲染QA对列表项
    const itemsHtml = qaPairs.map((qa, index) => {
        // 计算全局行号
        const rowNumber = append ? loadedQACount - qaPairs.length + index + 1 : index + 1;

        // 检查是否已标注（使用辅助函数，考虑必填配置）
        const isAnnotated = isItemAnnotated(qa.id);
        const status = isAnnotated ?
            '<span class="status-badge active">已标注</span>' :
            '<span class="status-badge inactive">未标注</span>';

        // 截断问题文本，显示更多内容（根据侧边栏宽度调整）
        const questionText = qa.question.length > 120 ?
            qa.question.substring(0, 120) + '...' : qa.question;

        // 检查是否是当前选中的QA对
        const isActive = currentQAPair && currentQAPair.id === qa.id ? 'active' : '';

        return `
            <li class="qa-list-item ${isActive}" onclick="loadQAPair('${qa.id}')" title="${escapeHtml(qa.question)}">
                <div class="qa-list-item-content">
                    <span class="qa-list-item-number">${rowNumber}.</span>
                    <span class="qa-list-item-question">${escapeHtml(questionText)}</span>
                </div>
                <div class="qa-list-item-status">${status}</div>
            </li>
        `;
    }).join('');

    // 追加或设置HTML
    if (append) {
        listContainer.insertAdjacentHTML('beforeend', itemsHtml);
    } else {
        listContainer.innerHTML = itemsHtml;
    }

    // 如果还有更多数据，添加加载指示器
    if (loadedQACount < totalQACount || totalQACount === 0) {
        const loadingHtml = '<li class="qa-list-loading" id="qaListLoading">加载中...</li>';
        listContainer.insertAdjacentHTML('beforeend', loadingHtml);
    }
}

// ==================== 加载单个QA对 ====================

async function loadQAPair(itemId) {
    try {
        // 使用普通用户可访问的端点
        const qaPair = await apiGet(`/datasets/annotation/${currentDatasetId}/items/${itemId}`);
        currentQAPair = qaPair;
        renderAnnotationForm(qaPair);
        // 更新列表中的选中状态
        updateQAListActiveState(itemId);
    } catch (error) {
        console.error(t('error.loadQAPairFailed') + ':', error);
        const errorMessage = error.data?.detail || error.data?.message || error.message || t('common.unknownError');
        showError(t('error.loadQAPairFailed') + ': ' + errorMessage);
    }
}

// ==================== 更新QA列表选中状态 ====================

function updateQAListActiveState(activeItemId) {
    const listItems = document.querySelectorAll('.qa-list-item');
    listItems.forEach(item => {
        const onclickAttr = item.getAttribute('onclick');
        if (onclickAttr && onclickAttr.includes(`'${activeItemId}'`)) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

// ==================== 保存标注后更新列表状态 ====================

async function updateQAListAfterSave() {
    // 重新加载标注结果以确保状态正确
    if (currentDatasetId) {
        try {
            // 重新加载标注结果
            await loadAnnotationResults(currentDatasetId);
            // 更新列表中当前项的标注状态
            updateQAListItemStatus(currentQAPair?.id);
            // 恢复当前选中状态
            if (currentQAPair) {
                updateQAListActiveState(currentQAPair.id);
            }
        } catch (error) {
            console.error(t('error.updateListFailed') + ':', error);
        }
    }
}

// ==================== 更新单个列表项的状态 ====================

function updateQAListItemStatus(itemId) {
    if (!itemId) return;

    const listItems = document.querySelectorAll('.qa-list-item');
    listItems.forEach(item => {
        const onclickAttr = item.getAttribute('onclick');
        if (onclickAttr && onclickAttr.includes(`'${itemId}'`)) {
            // 找到对应的QA对
            const qa = qaPairsList.find(q => q.id === itemId);
            if (qa) {
                // 检查是否已标注（使用辅助函数，考虑必填配置）
                const isAnnotated = isItemAnnotated(qa.id);
                const status = isAnnotated ?
                    '<span class="status-badge active">已标注</span>' :
                    '<span class="status-badge inactive">未标注</span>';

                // 更新状态
                const statusDiv = item.querySelector('.qa-list-item-status');
                if (statusDiv) {
                    statusDiv.innerHTML = status;
                }
            }
        }
    });
}

// ==================== 加载标注结果 ====================

async function loadAnnotationResults(datasetId) {
    try {
        // 使用新的API端点获取标注结果
        const results = await apiGet(`/annotation-results/datasets/${datasetId}/results?skip=0&limit=10000`).catch(() => {
            // 如果API不存在，返回空数组
            return [];
        });

        // 按item_id组织结果
        annotationResults = {};
        if (Array.isArray(results)) {
            results.forEach(result => {
                if (!annotationResults[result.dataset_item_id]) {
                    annotationResults[result.dataset_item_id] = {};
                }
                annotationResults[result.dataset_item_id][result.annotation_config_id] = result;
            });
        }

        // 更新进度信息
        updateProgressInfo(datasetId);
    } catch (error) {
        console.error(t('error.loadAnnotationResultsFailed') + ':', error);
        annotationResults = {};
    }
}

// ==================== 更新进度信息 ====================

async function updateProgressInfo(datasetId) {
    try {
        // 使用stats端点获取总数
        let total = totalQACount;
        if (total === 0) {
            try {
                const stats = await apiGet(`/datasets/annotation/${datasetId}/stats`);
                total = stats.items_count || 0;
                totalQACount = total;
            } catch (error) {
                console.warn(t('error.loadStatsFailed') + ':', error);
                // 如果获取失败，使用已加载的数量
                total = loadedQACount;
            }
        }

        let annotated = 0;

        // 统计已标注的数量（使用与列表项相同的判断逻辑）
        // 遍历所有已加载的QA对，使用 isItemAnnotated 函数判断是否已标注
        if (qaPairsList.length > 0) {
            qaPairsList.forEach(qa => {
                if (isItemAnnotated(qa.id)) {
                    annotated++;
                }
            });
        }

        const progressInfo = document.getElementById('progressInfo');
        const annotatedCount = document.getElementById('annotatedCount');
        const totalCount = document.getElementById('totalCount');
        const progressBar = document.getElementById('progressBar');

        if (total > 0) {
            progressInfo.style.display = 'block';
            const percentage = Math.round((annotated / total) * 100);
            annotatedCount.textContent = annotated;
            totalCount.textContent = total;
            // 更新进度条
            progressBar.style.width = percentage + '%';
            // 添加百分比显示（如果还没有）
            let percentageSpan = progressInfo.querySelector('.progress-percentage');
            if (!percentageSpan) {
                percentageSpan = document.createElement('span');
                percentageSpan.className = 'progress-percentage';
                percentageSpan.style.marginLeft = '8px';
                percentageSpan.style.fontWeight = '600';
                annotatedCount.parentNode.appendChild(percentageSpan);
            }
            percentageSpan.textContent = `(${percentage}%)`;
        } else {
            progressInfo.style.display = 'none';
        }
    } catch (error) {
        console.error('更新进度信息失败:', error);
    }
}

// ==================== 渲染标注表单 ====================

function renderAnnotationForm(qaPair) {
    const qaDisplay = document.getElementById('qaDisplay');
    const annotationFormPanel = document.getElementById('annotationFormPanel');

    if (!qaPair) {
        qaDisplay.innerHTML = '<div class="empty-state"><div class="empty-state-icon">❌</div><div class="empty-state-text">未找到QA对</div></div>';
        annotationFormPanel.style.display = 'none';
        return;
    }

    if (annotationConfigs.length === 0) {
        qaDisplay.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚙️</div><div class="empty-state-text">该数据集暂无标注配置，请联系管理员</div></div>';
        annotationFormPanel.style.display = 'none';
        return;
    }

    // 获取当前QA对的已标注结果
    const currentResults = annotationResults[qaPair.id] || {};

    const annotationForms = annotationConfigs.map(config => {
        const existingResult = currentResults[config.id];
        return renderAnnotationField(config, existingResult);
    }).join('');

    // 渲染extra字段
    const extraFieldsHtml = renderExtraFields(qaPair);

    // 左侧显示QA对内容
    qaDisplay.innerHTML = `
        <div class="qa-card">
            <div class="qa-card-header">
                <h3>QA对 #${qaPair.id}</h3>
                <div class="qa-card-navigation">
                    <button type="button" class="btn btn-info btn-compact" onclick="loadPreviousQAPair()">上一条</button>
                    <button type="button" class="btn btn-info btn-compact" onclick="loadNextQAPair()">研究领域和该问题不匹配，建议转给其它专家</button>
                </div>
            </div>
            <div class="qa-card-body">
                <div class="qa-item">
                    <div class="qa-label">问题</div>
                    <div class="qa-text">${escapeHtml(qaPair.question)}</div>
                </div>
                <div class="qa-item">
                    <div class="qa-label">答案</div>
                    <div class="qa-text">${escapeHtml(qaPair.answer)}</div>
                </div>
                ${extraFieldsHtml}
                <div class="qa-card-navigation-bottom">
                    <button type="button" class="btn btn-info btn-compact" onclick="loadPreviousQAPair()">上一条</button>
                    <button type="button" class="btn btn-info btn-compact" onclick="loadNextQAPair()">下一条</button>
                </div>
            </div>
        </div>
    `;

    // 右侧显示标注表单
    const annotationFormBody = document.getElementById('annotationFormBody');
    annotationFormBody.innerHTML = `
        <form class="annotation-form" id="annotationForm" onsubmit="submitAnnotation(event)">
            ${annotationForms}
            <div class="annotation-actions">
                <button type="button" class="btn btn-secondary" onclick="clearAnnotationForm()">清空</button>
                <button type="submit" class="btn btn-primary">保存标注</button>
            </div>
        </form>
        <div class="annotation-navigation">
            <button type="button" class="btn btn-info btn-compact" onclick="loadPreviousQAPair()">上一条</button>
            <button type="button" class="btn btn-info btn-compact" onclick="loadNextQAPair()">下一条</button>
        </div>
    `;
    annotationFormPanel.style.display = 'flex';
}

// ==================== 渲染extra字段 ====================

function renderExtraFields(qaPair) {
    if (!currentDataset || !currentDataset.display_extra_fields || !Array.isArray(currentDataset.display_extra_fields)) {
        return '';
    }

    const extraFields = currentDataset.display_extra_fields;
    if (extraFields.length === 0) {
        return '';
    }

    // 获取qaPair中所有非标准字段（排除id, dataset_id, question, answer）
    const standardFields = ['id', 'dataset_id', 'question', 'answer'];
    const extraFieldsHtml = extraFields.map(fieldName => {
        // 检查字段是否存在
        if (qaPair.hasOwnProperty(fieldName)) {
            const fieldValue = qaPair[fieldName];
            // 处理不同类型的值
            let displayValue = '';
            if (fieldValue === null || fieldValue === undefined) {
                displayValue = '';
            } else if (typeof fieldValue === 'object') {
                displayValue = JSON.stringify(fieldValue, null, 2);
            } else {
                displayValue = String(fieldValue);
            }

            return `
                <div class="qa-item">
                    <div class="qa-label">${escapeHtml(fieldName)}</div>
                    <div class="qa-text">${escapeHtml(displayValue)}</div>
                </div>
            `;
        }
        return '';
    }).filter(html => html !== '').join('');

    return extraFieldsHtml;
}

// ==================== 渲染标注字段 ====================

function renderAnnotationField(config, existingResult = null) {
    const fieldId = `annotation_${config.id}`;
    const required = config.required ? '<span class="required">*</span>' : '';
    const description = config.description ? `<div class="annotation-field-description">${escapeHtml(config.description)}</div>` : '';

    let inputHtml = '';
    const existingValue = existingResult ? existingResult.value : null;

    switch (config.annotation_type) {
        case 'score':
            inputHtml = renderScoreField(config, fieldId, existingValue);
            break;
        case 'category':
            inputHtml = renderCategoryField(config, fieldId, existingValue);
            break;
        case 'text':
            inputHtml = renderTextField(config, fieldId, existingValue);
            break;
        case 'single_choice':
            inputHtml = renderSingleChoiceField(config, fieldId, existingValue);
            break;
        case 'multi_choice':
            inputHtml = renderMultiChoiceField(config, fieldId, existingValue);
            break;
        case 'binary':
            inputHtml = renderBinaryField(config, fieldId, existingValue);
            break;
        default:
            inputHtml = `<div class="annotation-input">未知的标注类型: ${config.annotation_type}</div>`;
    }

    // 如果配置启用了 show_reason，添加理由输入框
    let reasonHtml = '';
    if (config.show_reason) {
        const existingReason = existingResult?.notes || '';
        reasonHtml = `
            <div style="margin-top: 8px;">
                <label style="display: block; font-size: 0.85em; color: #666; margin-bottom: 4px; font-weight: normal;">标注理由（可选）</label>
                <textarea id="${fieldId}_reason"
                          class="annotation-input"
                          placeholder="请说明标注的理由或依据">${escapeHtml(existingReason)}</textarea>
            </div>
        `;
    }

    // 如果配置启用了 show_confidence，添加置信度输入框
    let confidenceHtml = '';
    if (config.show_confidence) {
        const existingConfidence = existingResult?.confidence !== undefined && existingResult?.confidence !== null ? existingResult.confidence : '';
        confidenceHtml = `
            <div style="margin-top: 8px;">
                <label style="display: block; font-size: 0.85em; color: #666; margin-bottom: 4px; font-weight: normal;">置信度（0-1）</label>
                <input type="number"
                       id="${fieldId}_confidence"
                       class="annotation-input"
                       min="0"
                       max="1"
                       step="0.01"
                       value="${existingConfidence}"
                       placeholder="0.00 - 1.00">
            </div>
        `;
    }

    return `
        <div class="annotation-field">
            <label class="annotation-field-label">
                ${escapeHtml(config.name)}${required}
            </label>
            ${description}
            ${inputHtml}
            ${reasonHtml}
            ${confidenceHtml}
        </div>
    `;
}

// ==================== 渲染不同类型的标注字段 ====================

function renderScoreField(config, fieldId, existingValue) {
    const scoreConfig = config.config;
    const min = scoreConfig.min_score || 1;
    const max = scoreConfig.max_score || 5;
    const step = scoreConfig.score_step || 1;
    const currentValue = existingValue?.score?.score || '';

    return `
        <div class="score-input-group">
            <input type="number"
                   id="${fieldId}"
                   class="annotation-input score-input"
                   min="${min}"
                   max="${max}"
                   step="${step}"
                   value="${currentValue}"
                   required="${config.required}">
            <span class="score-range">范围: ${min} - ${max}</span>
        </div>
    `;
}

function renderCategoryField(config, fieldId, existingValue) {
    const categories = config.config.categories || [];
    const currentValue = existingValue?.category?.category || '';

    if (categories.length === 0) {
        return `<input type="text" id="${fieldId}" class="annotation-input" value="${escapeHtml(currentValue)}" ${config.required ? 'required' : ''}>`;
    }

    const options = categories.map(cat => {
        const selected = cat === currentValue ? 'selected' : '';
        return `<option value="${escapeHtml(cat)}" ${selected}>${escapeHtml(cat)}</option>`;
    }).join('');

    return `<select id="${fieldId}" class="annotation-input" ${config.required ? 'required' : ''}>${options}</select>`;
}

function renderTextField(config, fieldId, existingValue) {
    const maxLength = config.config.max_length || '';
    const currentValue = existingValue?.text?.text || '';
    const maxLengthAttr = maxLength ? `maxlength="${maxLength}"` : '';

    return `<textarea id="${fieldId}" class="annotation-input" ${maxLengthAttr} ${config.required ? 'required' : ''}>${escapeHtml(currentValue)}</textarea>`;
}

function renderSingleChoiceField(config, fieldId, existingValue) {
    const options = config.config.options || [];
    const currentValue = existingValue?.choice?.selected_options?.[0] || '';

    return `
        <div class="annotation-options">
            ${options.map(opt => {
                const checked = opt.option_id === currentValue ? 'checked' : '';
                return `
                    <label class="annotation-option">
                        <input type="radio"
                               name="${fieldId}"
                               value="${escapeHtml(opt.option_id)}"
                               ${checked}
                               ${config.required ? 'required' : ''}>
                        <div class="annotation-option-label">
                            <div>${escapeHtml(opt.label)}</div>
                            ${opt.description ? `<div class="annotation-option-description">${escapeHtml(opt.description)}</div>` : ''}
                        </div>
                    </label>
                `;
            }).join('')}
        </div>
    `;
}

function renderMultiChoiceField(config, fieldId, existingValue) {
    const options = config.config.options || [];
    const currentValues = existingValue?.choice?.selected_options || [];

    return `
        <div class="annotation-options">
            ${options.map(opt => {
                const checked = currentValues.includes(opt.option_id) ? 'checked' : '';
                return `
                    <label class="annotation-option">
                        <input type="checkbox"
                               name="${fieldId}[]"
                               value="${escapeHtml(opt.option_id)}"
                               ${checked}>
                        <div class="annotation-option-label">
                            <div>${escapeHtml(opt.label)}</div>
                            ${opt.description ? `<div class="annotation-option-description">${escapeHtml(opt.description)}</div>` : ''}
                        </div>
                    </label>
                `;
            }).join('')}
        </div>
    `;
}

function renderBinaryField(config, fieldId, existingValue) {
    const binaryConfig = config.config;
    const trueLabel = binaryConfig.true_label || '是';
    const falseLabel = binaryConfig.false_label || '否';
    const currentValue = existingValue?.binary?.value;

    let checkedTrue = '';
    let checkedFalse = '';
    if (currentValue === true) {
        checkedTrue = 'checked';
    } else if (currentValue === false) {
        checkedFalse = 'checked';
    }

    return `
        <div class="annotation-options">
            <label class="annotation-option">
                <input type="radio"
                       name="${fieldId}"
                       value="true"
                       ${checkedTrue}
                       ${config.required ? 'required' : ''}>
                <div class="annotation-option-label">${escapeHtml(trueLabel)}</div>
            </label>
            <label class="annotation-option">
                <input type="radio"
                       name="${fieldId}"
                       value="false"
                       ${checkedFalse}
                       ${config.required ? 'required' : ''}>
                <div class="annotation-option-label">${escapeHtml(falseLabel)}</div>
            </label>
        </div>
    `;
}

// ==================== 提交标注 ====================

async function submitAnnotation(event) {
    event.preventDefault();

    if (!currentQAPair || !currentDatasetId) {
        showError(t('error.selectQAPairFirst'));
        return;
    }

    try {
        const results = [];

        // 收集所有标注配置的值
        for (const config of annotationConfigs) {
            const fieldId = `annotation_${config.id}`;
            const value = collectAnnotationValue(config, fieldId);

            if (config.required && !value) {
                showError(t('error.fillRequiredField', { name: config.name }));
                return;
            }

            if (value) {
                // 构建标注结果
                const result = {
                    dataset_id: currentDatasetId,
                    dataset_item_id: currentQAPair.id,
                    annotation_config_id: config.id,
                    value: value
                };

                // 如果配置启用了 show_reason，收集该配置的理由并保存到 notes 字段
                if (config.show_reason) {
                    const reasonInput = document.getElementById(`${fieldId}_reason`);
                    const reason = reasonInput?.value?.trim() || null;
                    result.notes = reason;  // reason 可能是 null，这样会清空 notes
                }

                // 如果配置启用了 show_confidence，收集该配置的置信度并保存到 confidence 字段
                if (config.show_confidence) {
                    const confidenceInput = document.getElementById(`${fieldId}_confidence`);
                    const confidenceValue = confidenceInput?.value?.trim();
                    if (confidenceValue) {
                        const confidence = parseFloat(confidenceValue);
                        // 验证置信度范围
                        if (!isNaN(confidence) && confidence >= 0 && confidence <= 1) {
                            result.confidence = confidence;
                        } else {
                            showError(t('error.confidenceRangeError', { name: config.name }));
                            return;
                        }
                    } else {
                        result.confidence = null;  // 清空置信度
                    }
                }

                // 检查是否已存在标注结果
                const existingResult = annotationResults[currentQAPair.id]?.[config.id];
                if (existingResult && existingResult.id) {
                    // 更新现有结果
                    await apiPut(`/annotation-results/${existingResult.id}`, result);
                } else {
                    // 创建新结果
                    await apiPost('/annotation-results/', result);
                }

                results.push(result);
            }
        }

        // 更新本地存储的标注结果
        if (!annotationResults[currentQAPair.id]) {
            annotationResults[currentQAPair.id] = {};
        }
        results.forEach(result => {
            annotationResults[currentQAPair.id][result.annotation_config_id] = result;
        });

        // 更新列表显示（不重新加载，只更新状态）
        await updateQAListAfterSave();
        await updateProgressInfo(currentDatasetId);

        showSuccess(t('error.annotationSaveSuccess'));

        // 自动加载下一个未标注的QA对
        await loadNextUnannotatedQAPair();

    } catch (error) {
        console.error(t('error.saveAnnotationFailed') + ':', error);
        showError(t('error.saveAnnotationFailed') + ': ' + (error.message || t('common.unknownError')));
    }
}

// ==================== 收集标注值 ====================

function collectAnnotationValue(config, fieldId) {
    switch (config.annotation_type) {
        case 'score':
            const scoreInput = document.getElementById(fieldId);
            if (!scoreInput || !scoreInput.value) return null;
            return {
                score: {
                    score: parseFloat(scoreInput.value)
                }
            };

        case 'category':
            const categoryInput = document.getElementById(fieldId);
            if (!categoryInput || !categoryInput.value) return null;
            return {
                category: {
                    category: categoryInput.value
                }
            };

        case 'text':
            const textInput = document.getElementById(fieldId);
            if (!textInput || !textInput.value.trim()) return null;
            return {
                text: {
                    text: textInput.value.trim()
                }
            };

        case 'single_choice':
            const radioInput = document.querySelector(`input[name="${fieldId}"]:checked`);
            if (!radioInput) return null;
            return {
                choice: {
                    selected_options: [radioInput.value]
                }
            };

        case 'multi_choice':
            const checkboxes = document.querySelectorAll(`input[name="${fieldId}[]"]:checked`);
            if (checkboxes.length === 0) return null;
            return {
                choice: {
                    selected_options: Array.from(checkboxes).map(cb => cb.value)
                }
            };

        case 'binary':
            const binaryInput = document.querySelector(`input[name="${fieldId}"]:checked`);
            if (!binaryInput) return null;
            return {
                binary: {
                    value: binaryInput.value === 'true'
                }
            };

        default:
            return null;
    }
}

// ==================== 加载下一个未标注的QA对 ====================

async function loadNextUnannotatedQAPair() {
    try {
        // 先在已加载的列表中查找
        const currentIndex = qaPairsList.findIndex(qa => qa.id === currentQAPair.id);
        for (let i = currentIndex + 1; i < qaPairsList.length; i++) {
            const qa = qaPairsList[i];
            // 使用辅助函数判断是否已标注（考虑必填配置）
            const isAnnotated = isItemAnnotated(qa.id);
            if (!isAnnotated) {
                await loadQAPair(qa.id);
                return;
            }
        }

        // 如果已加载的列表中没有找到，尝试加载更多数据
        if (loadedQACount < totalQACount || totalQACount === 0) {
            await loadMoreQAPairs(currentDatasetId);
            // 加载更多后，再次查找
            const newCurrentIndex = qaPairsList.findIndex(qa => qa.id === currentQAPair.id);
            for (let i = newCurrentIndex + 1; i < qaPairsList.length; i++) {
                const qa = qaPairsList[i];
                // 使用辅助函数判断是否已标注（考虑必填配置）
                const isAnnotated = isItemAnnotated(qa.id);
                if (!isAnnotated) {
                    await loadQAPair(qa.id);
                    return;
                }
            }
        }
    } catch (error) {
        console.error('加载下一个QA对失败:', error);
    }
}

// ==================== 加载上一条QA对 ====================

async function loadPreviousQAPair() {
    if (!currentQAPair || !currentDatasetId) {
        showError('请先选择QA对');
        return;
    }

    try {
        // 查找当前QA对的索引
        const currentIndex = qaPairsList.findIndex(qa => qa.id === currentQAPair.id);

        if (currentIndex === -1) {
            showError('未找到当前QA对');
            return;
        }

        // 如果还有上一条，加载上一条
        if (currentIndex > 0) {
            const previousQAPair = qaPairsList[currentIndex - 1];
            await loadQAPair(previousQAPair.id);
        } else {
            showSuccess('已经是第一条数据了');
        }
    } catch (error) {
        console.error('加载上一条QA对失败:', error);
        showError('加载上一条QA对失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 加载下一条QA对 ====================

async function loadNextQAPair() {
    if (!currentQAPair || !currentDatasetId) {
        showError('请先选择QA对');
        return;
    }

    try {
        // 查找当前QA对的索引
        const currentIndex = qaPairsList.findIndex(qa => qa.id === currentQAPair.id);

        if (currentIndex === -1) {
            showError('未找到当前QA对');
            return;
        }

        // 如果还有下一条，加载下一条
        if (currentIndex < qaPairsList.length - 1) {
            const nextQAPair = qaPairsList[currentIndex + 1];
            await loadQAPair(nextQAPair.id);
        } else {
            // 如果已加载的数据中没有下一条，尝试加载更多
            if (loadedQACount < totalQACount || totalQACount === 0) {
                await loadMoreQAPairs(currentDatasetId);
                // 加载更多后，再次检查
                const newCurrentIndex = qaPairsList.findIndex(qa => qa.id === currentQAPair.id);
                if (newCurrentIndex < qaPairsList.length - 1) {
                    const nextQAPair = qaPairsList[newCurrentIndex + 1];
                    await loadQAPair(nextQAPair.id);
                } else {
                    showSuccess('已经是最后一条数据了');
                }
            } else {
                showSuccess('已经是最后一条数据了');
            }
        }
    } catch (error) {
        console.error('加载下一条QA对失败:', error);
        showError('加载下一条QA对失败: ' + (error.message || '未知错误'));
    }
}

// ==================== 清空标注表单 ====================

function clearAnnotationForm() {
    if (confirm('确定要清空当前标注吗？')) {
        const form = document.getElementById('annotationForm');
        if (form) {
            form.reset();
        }
    }
}

// ==================== 清空标注内容 ====================

function clearAnnotationContent() {
    const qaDisplay = document.getElementById('qaDisplay');
    const annotationFormPanel = document.getElementById('annotationFormPanel');
    qaDisplay.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📝</div><div class="empty-state-text">加载中...</div></div>';
    annotationFormPanel.style.display = 'none';

    const listContainer = document.getElementById('qaListBody');
    listContainer.innerHTML = '<li class="qa-list-empty">加载中...</li>';

    const progressInfo = document.getElementById('progressInfo');
    progressInfo.style.display = 'none';
}

// ==================== 工具函数 ====================

function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

function showError(message) {
    // 尝试解析错误对象
    let errorMsg = message;
    if (typeof message === 'object') {
        errorMsg = message.detail || message.message || JSON.stringify(message);
    }
    showMessage('错误: ' + errorMsg, 'error');
}

function showSuccess(message) {
    showMessage('成功: ' + message, 'success');
}

// ==================== 滚动监听和懒加载 ====================

let scrollListener = null;

function setupScrollListener() {
    // 移除旧的监听器（如果存在）
    removeScrollListener();

    const listContainer = document.querySelector('.qa-list-container');
    if (!listContainer) return;

    scrollListener = () => {
        // 检查是否滚动到底部
        const scrollTop = listContainer.scrollTop;
        const scrollHeight = listContainer.scrollHeight;
        const clientHeight = listContainer.clientHeight;

        // 当滚动到距离底部50px时，触发加载
        if (scrollTop + clientHeight >= scrollHeight - 50) {
            if (currentDatasetId && !isLoadingMore) {
                // 检查是否还有更多数据需要加载
                if (loadedQACount < totalQACount || totalQACount === 0) {
                    loadMoreQAPairs(currentDatasetId);
                }
            }
        }
    };

    listContainer.addEventListener('scroll', scrollListener);
}

function removeScrollListener() {
    if (scrollListener) {
        const listContainer = document.querySelector('.qa-list-container');
        if (listContainer) {
            listContainer.removeEventListener('scroll', scrollListener);
        }
        scrollListener = null;
    }
}

// ==================== 显示/隐藏加载指示器 ====================

function showLoadingIndicator(show) {
    const listContainer = document.getElementById('qaListBody');
    if (!listContainer) return;

    let loadingItem = listContainer.querySelector('.qa-list-loading');

    if (show) {
        if (!loadingItem) {
            loadingItem = document.createElement('li');
            loadingItem.className = 'qa-list-loading';
            loadingItem.id = 'qaListLoading';
            loadingItem.textContent = '加载中...';
            listContainer.appendChild(loadingItem);
        }
    } else {
        if (loadingItem) {
            // 只有在没有更多数据时才移除
            if (loadedQACount >= totalQACount && totalQACount > 0) {
                loadingItem.remove();
            }
        }
    }
}
