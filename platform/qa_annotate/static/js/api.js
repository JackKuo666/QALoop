/**
 * 通用API请求函数
 * 提供统一的API调用接口，自动处理认证、错误处理等
 */

// API 基础 URL
const API_BASE_URL = '/api';

/**
 * 从localStorage获取访问令牌
 * @returns {string|null} 访问令牌
 */
function getToken() {
    return localStorage.getItem('access_token');
}

/**
 * 保存访问令牌到localStorage
 * @param {string} token 访问令牌
 */
function saveToken(token) {
    localStorage.setItem('access_token', token);
}

/**
 * 清除访问令牌
 */
function clearToken() {
    localStorage.removeItem('access_token');
}

/**
 * 检查是否已登录
 * @returns {boolean} 是否已登录
 */
function isLoggedIn() {
    return !!getToken();
}

/**
 * 获取认证请求头
 * @param {Object} customHeaders 自定义请求头
 * @returns {Object} 请求头对象
 */
function getAuthHeaders(customHeaders = {}) {
    const token = getToken();
    return {
        'Content-Type': 'application/json',
        ...(token && { 'Authorization': `Bearer ${token}` }),
        ...customHeaders
    };
}

/**
 * 处理API响应
 * @param {Response} response Fetch响应对象
 * @returns {Promise} 解析后的数据
 */
async function handleResponse(response) {
    // 尝试解析JSON响应
    let data;
    const contentType = response.headers.get('content-type');

    if (contentType && contentType.includes('application/json')) {
        try {
            data = await response.json();
        } catch (error) {
            // 如果JSON解析失败，返回空对象
            data = {};
        }
    } else {
        // 非JSON响应，返回文本
        data = await response.text();
    }

    // 如果响应不成功，抛出错误
    if (!response.ok) {
        const error = new Error(data.detail || data.message || `HTTP错误: ${response.status}`);
        error.status = response.status;
        error.data = data;
        throw error;
    }

    return data;
}

/**
 * 通用API请求函数
 * @param {string} endpoint API端点（不需要包含/api前缀）
 * @param {Object} options 请求选项
 * @param {string} options.method HTTP方法，默认为'GET'
 * @param {Object} options.body 请求体（会自动转换为JSON）
 * @param {Object} options.headers 自定义请求头
 * @param {boolean} options.requireAuth 是否需要认证，默认为true
 * @returns {Promise} API响应数据
 */
async function apiRequest(endpoint, options = {}) {
    const {
        method = 'GET',
        body = null,
        headers = {},
        requireAuth = true
    } = options;

    // 构建完整URL
    const url = `${API_BASE_URL}${endpoint}`;

    // 构建请求配置
    const config = {
        method: method.toUpperCase(),
        headers: requireAuth ? getAuthHeaders(headers) : {
            'Content-Type': 'application/json',
            ...headers
        }
    };

    // 添加请求体
    if (body && (method.toUpperCase() === 'POST' || method.toUpperCase() === 'PUT' || method.toUpperCase() === 'PATCH')) {
        config.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(url, config);
        return await handleResponse(response);
    } catch (error) {
        // 如果是401未授权错误，清除token并跳转到登录页
        if (error.status === 401) {
            clearToken();
            // 如果不在登录页面，则跳转，并带上当前URL作为redirect参数
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
 * GET请求
 * @param {string} endpoint API端点
 * @param {Object} options 请求选项
 * @returns {Promise} API响应数据
 */
function apiGet(endpoint, options = {}) {
    return apiRequest(endpoint, { ...options, method: 'GET' });
}

/**
 * POST请求
 * @param {string} endpoint API端点
 * @param {Object} body 请求体
 * @param {Object} options 请求选项
 * @returns {Promise} API响应数据
 */
function apiPost(endpoint, body, options = {}) {
    return apiRequest(endpoint, { ...options, method: 'POST', body });
}

/**
 * PUT请求
 * @param {string} endpoint API端点
 * @param {Object} body 请求体
 * @param {Object} options 请求选项
 * @returns {Promise} API响应数据
 */
function apiPut(endpoint, body, options = {}) {
    return apiRequest(endpoint, { ...options, method: 'PUT', body });
}

/**
 * PATCH请求
 * @param {string} endpoint API端点
 * @param {Object} body 请求体
 * @param {Object} options 请求选项
 * @returns {Promise} API响应数据
 */
function apiPatch(endpoint, body, options = {}) {
    return apiRequest(endpoint, { ...options, method: 'PATCH', body });
}

/**
 * DELETE请求
 * @param {string} endpoint API端点
 * @param {Object} options 请求选项
 * @returns {Promise} API响应数据
 */
function apiDelete(endpoint, options = {}) {
    return apiRequest(endpoint, { ...options, method: 'DELETE' });
}

/**
 * 上传文件
 * @param {string} endpoint API端点
 * @param {File} file 要上传的文件
 * @param {Object} options 请求选项
 * @returns {Promise} API响应数据
 */
async function apiUploadFile(endpoint, file, options = {}) {
    const { requireAuth = true } = options;

    // 构建完整URL
    const url = `${API_BASE_URL}${endpoint}`;

    // 创建FormData
    const formData = new FormData();
    formData.append('file', file);

    // 构建请求配置
    const headers = {};
    if (requireAuth) {
        const token = getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
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

// 导出函数（如果在模块环境中使用）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        apiRequest,
        apiGet,
        apiPost,
        apiPut,
        apiPatch,
        apiDelete,
        apiUploadFile,
        getToken,
        saveToken,
        clearToken,
        isLoggedIn,
        getAuthHeaders
    };
}
