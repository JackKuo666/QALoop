/**
 * 用户管理模块 JavaScript
 * 提供用户的查看、创建、编辑、删除功能
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 密码哈希工具函数（使用crypto-js库）
    function sha256(message) {
        if (typeof CryptoJS !== 'undefined' && CryptoJS.SHA256) {
            return CryptoJS.SHA256(message).toString();
        } else {
            console.error(t('error.cryptoJsNotLoaded'));
            throw new Error(t('error.encryptionLibraryNotLoaded'));
        }
    }

    // 模块私有状态
    let usersPaginator = null;
    let editingId = null;
    let container = null;

    // 用户管理模块
    const UserManagement = {
        init: function(containerElement) {
            container = containerElement;
            this.initPaginators();
            this.initEventListeners();

            // 等待 i18next 初始化完成后再加载数据
            const loadData = () => {
                this.loadUsers();
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
            // 初始化用户管理分页器
            usersPaginator = createPaginator('users', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    this.loadUsers();
                },
                onPageSizeChange: (pageSize) => {
                    this.loadUsers();
                }
            });
        },

        initEventListeners: function() {
            // 添加用户按钮
            const addUserBtn = container.querySelector('#addUserBtn');
            if (addUserBtn) {
                addUserBtn.addEventListener('click', () => {
                    this.showUserForm();
                });
            }
        },

        loadUsers: async function() {
            if (!usersPaginator) return;

            try {
                const skip = usersPaginator.getSkip();
                const limit = usersPaginator.getLimit();
                const users = await apiGet(`/users/?skip=${skip}&limit=${limit}`);

                // 获取总数：如果返回的数据量小于limit，说明这是最后一页
                // 如果等于limit，可能还有更多数据，尝试获取下一页来判断
                let totalCount;
                if (users.length < limit) {
                    totalCount = skip + users.length;
                } else {
                    // 尝试获取下一页来判断是否还有更多数据
                    try {
                        const nextPage = await apiGet(`/users/?skip=${skip + limit}&limit=1`);
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

                usersPaginator.setTotalCount(totalCount);
                this.renderUsersTable(users);
            } catch (error) {
                console.error('加载用户失败:', error);
                showError(`${t('user.loadFailed')}: ${error.message || t('error.unknownError')}`);
            }
        },

        renderUsersTable: function(users) {
            const tbody = container.querySelector('#usersTableBody');
            const paginationContainer = container.querySelector('#usersPaginationContainer');

            // 如果元素不存在，说明容器已被清空，需要重新初始化
            if (!tbody) {
                console.warn('Users table body not found, container may have been cleared');
                return;
            }

            if (users.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10" class="loading">${t('user.noUsers')}</td></tr>`;
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            tbody.innerHTML = users.map(user => `
                <tr>
                    <td>${user.id}</td>
                    <td>${escapeHtml(user.username)}</td>
                    <td>${escapeHtml(user.full_name || '-')}</td>
                    <td>${escapeHtml(user.organization || '-')}</td>
                    <td>${escapeHtml(user.team || '-')}</td>
                    <td>${escapeHtml(user.species || '-')}</td>
                    <td><span class="status-badge ${user.is_active ? 'active' : 'inactive'}">
                        ${user.is_active ? t('status.active') : t('status.inactive')}
                    </span></td>
                    <td><span class="status-badge ${user.is_superuser ? 'superuser' : 'user'}">
                        ${user.is_superuser ? t('user.isSuperuser') : t('user.isUser')}
                    </span></td>
                    <td>${formatDateTime(user.created_at)}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="window.UserManagement.editUser(${user.id})">${t('actions.edit')}</button>
                        <button class="btn btn-sm btn-danger" onclick="window.UserManagement.deleteUser(${user.id})">${t('actions.delete')}</button>
                    </td>
                </tr>
            `).join('');

            // 显示分页器
            if (paginationContainer && usersPaginator) {
                paginationContainer.style.display = 'block';
                usersPaginator.render();
            }
        },

        showUserForm: function(user = null) {
            editingId = user ? user.id : null;
            const title = user ? t('user.editUser') : t('user.addUser');
            const content = `
                <form id="userForm">
                    <div class="form-group">
                        <label>${t('user.username')} *</label>
                        <input type="text" id="username" value="${user ? escapeHtml(user.username) : ''}"
                               required minlength="3" maxlength="50">
                    </div>
                    <div class="form-group">
                        <label>${t('user.fullName')}</label>
                        <input type="text" id="full_name" value="${user ? escapeHtml(user.full_name || '') : ''}"
                               maxlength="100">
                    </div>
                    <div class="form-group">
                        <label>${t('user.organization')}</label>
                        <input type="text" id="organization" value="${user ? escapeHtml(user.organization || '') : ''}"
                               maxlength="100">
                    </div>
                    <div class="form-group">
                        <label>${t('user.team')}</label>
                        <input type="text" id="team" value="${user ? escapeHtml(user.team || '') : ''}"
                               maxlength="100">
                    </div>
                    <div class="form-group">
                        <label>${t('user.species')}</label>
                        <input type="text" id="species" value="${user ? escapeHtml(user.species || '') : ''}"
                               maxlength="100">
                    </div>
                    <div class="form-group">
                        <label>${t('user.password')} ${user ? `(${t('user.leaveEmptyToKeep')})` : '*'}</label>
                        <input type="password" id="password" ${user ? '' : 'required'} minlength="6">
                    </div>
                    <div class="form-group">
                        <div class="form-check">
                            <input type="checkbox" id="is_active" ${user && user.is_active ? 'checked' : ''}>
                            <label for="is_active">${t('status.active')}</label>
                        </div>
                    </div>
                    <div class="form-group">
                        <div class="form-check">
                            <input type="checkbox" id="is_superuser" ${user && user.is_superuser ? 'checked' : ''}>
                            <label for="is_superuser">${t('user.isSuperuser')}</label>
                        </div>
                    </div>
                </form>
            `;

            openModal(title, content, async () => {
                await this.saveUser();
            });
        },

        saveUser: async function() {
            const username = document.getElementById('username').value;
            const full_name = document.getElementById('full_name').value;
            const organization = document.getElementById('organization').value;
            const team = document.getElementById('team').value;
            const species = document.getElementById('species').value;
            const password = document.getElementById('password').value;
            const is_active = document.getElementById('is_active').checked;
            const is_superuser = document.getElementById('is_superuser').checked;

            try {
                const data = {
                    username,
                    full_name: full_name || null,
                    organization: organization || null,
                    team: team || null,
                    species: species || null,
                    is_active,
                    is_superuser
                };

                if (password) {
                    // 对密码进行SHA-256哈希（用于创建/更新用户，不需要时间戳）
                    const passwordHash = sha256(password);
                    data.password = passwordHash;
                }

                if (editingId) {
                    await apiPut(`/users/${editingId}`, data);
                    showSuccess(t('user.updateSuccess'));
                } else {
                    if (!password) {
                        alert(t('user.passwordRequired'));
                        return;
                    }
                    await apiPost('/users/', data);
                    showSuccess(t('user.createSuccess'));
                }

                closeModal();
                // 如果是新建用户，重置到第一页
                if (!editingId && usersPaginator) {
                    usersPaginator.reset();
                }
                this.loadUsers();
            } catch (error) {
                showError(`${t('user.saveFailed')}: ${error.message || t('error.unknownError')}`);
            }
        },

        editUser: async function(userId) {
            try {
                const user = await apiGet(`/users/${userId}`);
                this.showUserForm(user);
            } catch (error) {
                showError(`${t('user.loadFailed')}: ${error.message || t('error.unknownError')}`);
            }
        },

        deleteUser: async function(userId) {
            if (!confirm(t('user.deleteConfirm'))) {
                return;
            }

            try {
                await apiDelete(`/users/${userId}`);
                showSuccess(t('user.deleteSuccess'));
                // 如果当前页没有数据了，回到上一页
                if (usersPaginator) {
                    usersPaginator.adjustPageAfterDelete();
                }
                this.loadUsers();
            } catch (error) {
                showError(`${t('user.deleteFailed')}: ${error.message || t('error.unknownError')}`);
            }
        },

        destroy: function() {
            // 清理资源
            usersPaginator = null;
            editingId = null;
            container = null;
        }
    };

    // 暴露到全局
    window.UserManagement = UserManagement;
})();
