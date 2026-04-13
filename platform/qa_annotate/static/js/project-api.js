/**
 * 项目相关的API函数
 * 提供项目管理的所有API调用接口
 */

/**
 * 获取项目列表
 * @param {number} skip - 跳过的记录数
 * @param {number} limit - 返回的记录数
 * @param {string} name_search - 名称搜索关键词（可选）
 * @param {string} category - 分类筛选（可选）
 * @param {string} status - 状态筛选（可选）
 * @param {string} order_by - 排序字段（可选，默认为 'created_at'）
 * @param {string} order - 排序方向（可选，默认为 'desc'）
 * @returns {Promise<Array>} 项目列表
 */
async function getProjects(skip = 0, limit = 100, name_search = null, category = null, status = null, order_by = 'created_at', order = 'desc') {
    const params = new URLSearchParams();
    params.append('skip', skip);
    params.append('limit', limit);
    if (name_search) params.append('name_search', name_search);
    if (category) params.append('category', category);
    if (status) params.append('status', status);
    if (order_by) params.append('order_by', order_by);
    if (order) params.append('order', order);

    return await apiGet(`/projects/?${params.toString()}`);
}

/**
 * 获取项目详情
 * @param {number} projectId - 项目ID
 * @param {boolean} include_datasets - 是否包含数据集列表
 * @param {boolean} include_configs - 是否包含标注配置列表
 * @returns {Promise<Object>} 项目详情
 */
async function getProject(projectId, include_datasets = false, include_configs = false) {
    const params = new URLSearchParams();
    if (include_datasets) params.append('include_datasets', 'true');
    if (include_configs) params.append('include_configs', 'true');

    const queryString = params.toString();
    const url = queryString ? `/projects/${projectId}?${queryString}` : `/projects/${projectId}`;
    return await apiGet(url);
}

/**
 * 创建项目
 * @param {Object} projectData - 项目数据
 * @returns {Promise<Object>} 创建的项目
 */
async function createProject(projectData) {
    return await apiPost('/projects/', projectData);
}

/**
 * 更新项目
 * @param {number} projectId - 项目ID
 * @param {Object} projectData - 项目数据
 * @returns {Promise<Object>} 更新后的项目
 */
async function updateProject(projectId, projectData) {
    return await apiPut(`/projects/${projectId}`, projectData);
}

/**
 * 删除项目
 * @param {number} projectId - 项目ID
 * @returns {Promise<void>}
 */
async function deleteProject(projectId) {
    return await apiDelete(`/projects/${projectId}`);
}

/**
 * 获取项目下的数据集列表
 * @param {number} projectId - 项目ID
 * @param {number} skip - 跳过的记录数
 * @param {number} limit - 返回的记录数
 * @returns {Promise<Array>} 数据集列表
 */
async function getProjectDatasets(projectId, skip = 0, limit = 100) {
    const params = new URLSearchParams();
    params.append('skip', skip);
    params.append('limit', limit);

    return await apiGet(`/projects/${projectId}/datasets?${params.toString()}`);
}

/**
 * 添加数据集到项目
 * @param {number} projectId - 项目ID
 * @param {number} datasetId - 数据集ID
 * @returns {Promise<Object>} 操作结果
 */
async function addDatasetToProject(projectId, datasetId) {
    return await apiPost(`/projects/${projectId}/datasets/${datasetId}`);
}

/**
 * 从项目移除数据集
 * @param {number} projectId - 项目ID
 * @param {number} datasetId - 数据集ID
 * @returns {Promise<Object>} 操作结果
 */
async function removeDatasetFromProject(projectId, datasetId) {
    return await apiDelete(`/projects/${projectId}/datasets/${datasetId}`);
}

/**
 * 获取项目下的标注配置列表
 * @param {number} projectId - 项目ID
 * @returns {Promise<Array>} 标注配置列表
 */
async function getProjectConfigs(projectId) {
    return await apiGet(`/projects/${projectId}/configs`);
}

/**
 * 添加标注配置到项目
 * @param {number} projectId - 项目ID
 * @param {number} configId - 标注配置ID
 * @returns {Promise<Object>} 操作结果
 */
async function addConfigToProject(projectId, configId) {
    return await apiPost(`/projects/${projectId}/configs/${configId}`);
}

/**
 * 从项目移除标注配置
 * @param {number} projectId - 项目ID
 * @param {number} configId - 标注配置ID
 * @returns {Promise<Object>} 操作结果
 */
async function removeConfigFromProject(projectId, configId) {
    return await apiDelete(`/projects/${projectId}/configs/${configId}`);
}

/**
 * 获取项目统计信息
 * @param {number} projectId - 项目ID
 * @returns {Promise<Object>} 统计信息
 */
async function getProjectStats(projectId) {
    return await apiGet(`/projects/${projectId}/stats`);
}

/**
 * 导入项目（从多个JSONL文件）
 * @param {FormData} formData - 包含文件和项目信息的FormData
 * @returns {Promise<Object>} 导入结果
 */
async function importProject(formData) {
    const url = `${API_BASE_URL}/projects/import`;

    // 构建请求配置
    const headers = {};
    const token = getToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        method: 'POST',
        headers: headers,
        body: formData
    };

    try {
        const response = await fetch(url, config);
        return await handleResponse(response);
    } catch (error) {
        // 如果是401未授权错误，清除token并跳转到登录页
        if (error.status === 401) {
            clearToken();
            const currentPath = window.location.pathname;
            if (currentPath !== '/auth') {
                const redirectUrl = encodeURIComponent(window.location.href);
                window.location.href = `/auth?redirect=${redirectUrl}`;
            }
        }
        throw error;
    }
}

/**
 * 获取项目标注分析数据
 * @param {number} projectId - 项目ID
 * @returns {Promise<Object>} 标注分析数据
 */
async function getProjectAnnotationAnalysis(projectId) {
    return await apiGet(`/analysis/projects/${projectId}/annotation-stats`);
}
