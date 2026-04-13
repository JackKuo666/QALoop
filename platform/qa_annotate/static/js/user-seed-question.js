/**
 * 用户种子问题管理模块 JavaScript
 * 提供用户自己的种子问题的查看、编辑、删除功能
 */

(function() {
    'use strict';

    // 引用全局的翻译函数
    // 翻译函数由 i18n-helper.js 提供

    // 模块私有状态
    let listPaginator = null;
    let editingQuestionId = null;
    let container = null;
    let questionTypes = {}; // 类型/亚类选项 {type: [subtypes]}

    // 用户种子问题管理模块
    const UserSeedQuestion = {
        init: function(containerElement) {
            container = containerElement;
            this.initPaginators();
            this.initEventListeners();
            this.loadQuestionTypes();
            this.loadMyQuestions();
        },

        initPaginators: function() {
            // 初始化我的问题列表分页器
            listPaginator = createPaginator('list', {
                initialPage: 1,
                initialPageSize: 20,
                onPageChange: (page, pageSize) => {
                    this.loadMyQuestions();
                },
                onPageSizeChange: (pageSize) => {
                    this.loadMyQuestions();
                }
            });
        },

        initEventListeners: function() {
            // 搜索
            const searchInput = container.querySelector('#searchInput');
            if (searchInput) {
                let searchTimeout;
                searchInput.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        this.loadMyQuestions();
                    }, 500);
                });
            }

            // 刷新列表
            const refreshListBtn = container.querySelector('#refreshListBtn');
            if (refreshListBtn) {
                refreshListBtn.addEventListener('click', () => {
                    this.loadMyQuestions();
                });
            }

            // 使用说明按钮
            const showUsageBtn = container.querySelector('#showSeedQuestionUsageBtn');
            if (showUsageBtn) {
                showUsageBtn.addEventListener('click', () => {
                    this.showSeedQuestionUsage();
                });
            }

            // 添加问题按钮
            const addQuestionBtn = container.querySelector('#addQuestionBtn');
            if (addQuestionBtn) {
                addQuestionBtn.addEventListener('click', () => {
                    this.showAddModal();
                });
            }

            // 导入CSV按钮
            const importCsvBtn = container.querySelector('#importCsvBtn');
            if (importCsvBtn) {
                importCsvBtn.addEventListener('click', () => {
                    this.showImportCsvModal();
                });
            }

            // 编辑模态框
            this.initEditModal();
            // 添加模态框
            this.initAddModal();
            // 导入CSV模态框
            this.initImportCsvModal();
        },

        loadQuestionTypes: async function() {
            try {
                const types = await apiGet('/seed-questions/options/types');
                questionTypes = types;
                this.populateTypeSelects();
            } catch (error) {
                console.error('加载类型选项失败:', error);
                showError(t('error.loadTypeOptionsFailedRetry'));
            }
        },

        populateTypeSelects: function() {
            const typeSelects = ['editType', 'addType'];

            typeSelects.forEach(selectId => {
                const select = container.querySelector('#' + selectId);
                if (!select) return;

                // 清空现有选项（保留第一个提示选项）
                select.innerHTML = '<option value="">请选择类型...</option>';

                // 添加类型选项
                Object.keys(questionTypes).sort().forEach(type => {
                    const option = document.createElement('option');
                    option.value = type;
                    option.textContent = type;
                    select.appendChild(option);
                });
            });
        },

        updateSubtypes: function(event) {
            const typeSelect = event ? event.target : null;
            if (!typeSelect) return;

            const isAdd = typeSelect.id === 'addType';
            const subtypeSelectId = isAdd ? 'addSubtype' : 'editSubtype';
            const subtypeSelect = container.querySelector('#' + subtypeSelectId);

            if (!subtypeSelect) return;

            // 清空现有选项
            subtypeSelect.innerHTML = '';

            const selectedType = typeSelect.value;
            if (!selectedType || !questionTypes[selectedType]) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = t('error.selectTypeFirst');
                subtypeSelect.appendChild(option);
                return;
            }

            // 添加亚类选项
            const defaultOption = document.createElement('option');
            defaultOption.value = '';
            defaultOption.textContent = t('error.selectSubtype');
            subtypeSelect.appendChild(defaultOption);

            questionTypes[selectedType].sort().forEach(subtype => {
                const option = document.createElement('option');
                option.value = subtype;
                option.textContent = subtype;
                subtypeSelect.appendChild(option);
            });
        },

        loadMyQuestions: async function() {
            if (!listPaginator) return;

            const tbody = container.querySelector('#questionsTableBody');
            if (!tbody) return;

            try {
                tbody.innerHTML = '<tr><td colspan="10" class="loading">加载中...</td></tr>';

                const skip = listPaginator.getSkip();
                const limit = listPaginator.getLimit();

                const search = container.querySelector('#searchInput')?.value.trim() || null;

                const params = new URLSearchParams({
                    skip: skip.toString(),
                    limit: limit.toString()
                });
                if (search) {
                    params.append('search', search);
                }

                const questions = await apiGet(`/seed-questions/?${params.toString()}`);

                if (questions.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="10" class="empty-state"><div class="empty-state-icon">📝</div><div class="empty-state-text">${t('common.noData')}</div></td></tr>`;
                    const paginationContainer = container.querySelector('#listPaginationContainer');
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
                        <td>${this.formatDateTime(q.created_at)}</td>
                        <td>
                            <div class="action-buttons">
                                <button class="btn btn-sm btn-primary" onclick="window.UserSeedQuestion.editQuestion(${q.id})">编辑</button>
                                <button class="btn btn-sm btn-danger" onclick="window.UserSeedQuestion.deleteQuestion(${q.id})">删除</button>
                            </div>
                        </td>
                    </tr>
                `).join('');

                // 更新分页信息（需要获取总数）
                const total = await this.getMyQuestionsCount(search);
                listPaginator.setTotalCount(total);
                listPaginator.render();
                const paginationContainer = container.querySelector('#listPaginationContainer');
                if (paginationContainer) paginationContainer.classList.remove('hidden');

            } catch (error) {
                console.error('加载问题列表失败:', error);
                tbody.innerHTML = '<tr><td colspan="10" class="loading">加载失败，请刷新重试</td></tr>';
            }
        },

        getMyQuestionsCount: async function(search) {
            try {
                const result = await apiGet(`/seed-questions/?skip=0&limit=1000${search ? '&search=' + encodeURIComponent(search) : ''}`);
                return result.length;
            } catch (error) {
                return 0;
            }
        },

        editQuestion: async function(id) {
            try {
                const question = await apiGet(`/seed-questions/${id}`);
                editingQuestionId = id;

                // 填充表单
                const editQuestionId = container.querySelector('#editQuestionId');
                const editQuestion = container.querySelector('#editQuestion');
                const editType = container.querySelector('#editType');
                const editSubtype = container.querySelector('#editSubtype');
                const editSpeciesOrDomain = container.querySelector('#editSpeciesOrDomain');
                const editModel = container.querySelector('#editModel');
                const editDate = container.querySelector('#editDate');
                const editIsVerified = container.querySelector('#editIsVerified');

                if (editQuestionId) editQuestionId.value = id;
                if (editQuestion) editQuestion.value = question.question;
                if (editType) editType.value = question.type;
                if (editSpeciesOrDomain) editSpeciesOrDomain.value = question.species_or_domain || '';
                if (editModel) editModel.value = question.model || '';
                if (editDate) editDate.value = question.date ? question.date.split('T')[0] : '';
                if (editIsVerified) editIsVerified.checked = question.is_verified;

                // 更新亚类选项
                this.updateSubtypes({ target: editType });

                // 等待亚类选项更新后再设置值
                setTimeout(() => {
                    if (editSubtype) editSubtype.value = question.subtype;
                }, 100);

                // 显示模态框
                const modal = container.querySelector('#editModal');
                if (modal) modal.classList.add('active');
            } catch (error) {
                console.error('加载问题失败:', error);
                showError(t('error.loadQuestionFailedRetry'));
            }
        },

        initEditModal: function() {
            const modal = container.querySelector('#editModal');
            if (!modal) return;

            const closeBtn = container.querySelector('#editModalClose');
            const cancelBtn = container.querySelector('#editModalCancel');
            const submitBtn = container.querySelector('#editModalSubmit');
            const editTypeSelect = container.querySelector('#editType');

            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    modal.classList.remove('active');
                    editingQuestionId = null;
                });
            }

            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    modal.classList.remove('active');
                    editingQuestionId = null;
                });
            }

            if (editTypeSelect) {
                editTypeSelect.addEventListener('change', (e) => {
                    this.updateSubtypes(e);
                });
            }

            if (submitBtn) {
                submitBtn.addEventListener('click', () => {
                    this.handleEditSubmit();
                });
            }
        },

        handleEditSubmit: async function() {
            if (!editingQuestionId) return;

            const submitBtn = container.querySelector('#editModalSubmit');
            const originalText = submitBtn ? submitBtn.textContent : t('common.save');

            try {
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = t('common.saving');
                }

                const formData = {
                    question: container.querySelector('#editQuestion')?.value.trim() || '',
                    type: container.querySelector('#editType')?.value || '',
                    subtype: container.querySelector('#editSubtype')?.value || '',
                    species_or_domain: container.querySelector('#editSpeciesOrDomain')?.value.trim() || '',
                    model: container.querySelector('#editModel')?.value.trim() || '',
                    date: container.querySelector('#editDate')?.value || '',
                    is_verified: container.querySelector('#editIsVerified')?.checked
                };

                // 验证必填字段
                if (!formData.question || !formData.type || !formData.subtype ||
                    !formData.species_or_domain || !formData.model || !formData.date) {
                    showError(t('common.pleaseFillRequiredFields'));
                    return;
                }

                await apiPut(`/seed-questions/${editingQuestionId}`, formData);

                showSuccess(t('error.updateSuccess'));
                const modal = container.querySelector('#editModal');
                if (modal) modal.classList.remove('active');
                editingQuestionId = null;

                // 刷新列表
                this.loadMyQuestions();

            } catch (error) {
                console.error(t('error.updateFailed') + ':', error);
                showError(error.message || t('error.updateFailedRetry'));
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            }
        },

        deleteQuestion: async function(id) {
            if (!confirm(t('common.deleteConfirmMessage'))) {
                return;
            }

            try {
                await apiDelete(`/seed-questions/${id}`);
                showSuccess(t('error.deleteSuccess'));
                this.loadMyQuestions();
            } catch (error) {
                console.error(t('error.deleteFailed') + ':', error);
                showError(error.message || t('error.deleteFailedRetry'));
            }
        },

        showAddModal: function() {
            const modal = container.querySelector('#addModal');
            if (modal) {
                this.resetAddForm();
                modal.classList.add('active');
            }
        },

        initAddModal: function() {
            const modal = container.querySelector('#addModal');
            if (!modal) return;

            const closeBtn = container.querySelector('#addModalClose');
            const cancelBtn = container.querySelector('#addModalCancel');
            const resetBtn = container.querySelector('#addModalReset');
            const submitBtn = container.querySelector('#addModalSubmit');
            const addTypeSelect = container.querySelector('#addType');

            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    modal.classList.remove('active');
                    this.resetAddForm();
                });
            }

            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    modal.classList.remove('active');
                    this.resetAddForm();
                });
            }

            if (resetBtn) {
                resetBtn.addEventListener('click', () => {
                    this.resetAddForm();
                });
            }

            if (addTypeSelect) {
                addTypeSelect.addEventListener('change', (e) => {
                    this.updateSubtypes(e);
                });
            }

            if (submitBtn) {
                submitBtn.addEventListener('click', () => {
                    this.handleAddSubmit();
                });
            }
        },

        resetAddForm: function() {
            const form = container.querySelector('#addQuestionForm');
            if (form) {
                form.reset();
            }
            const addSubtype = container.querySelector('#addSubtype');
            if (addSubtype) {
                addSubtype.innerHTML = '<option value="">' + t('error.selectTypeFirst') + '</option>';
            }
        },

        handleAddSubmit: async function() {
            const submitBtn = container.querySelector('#addModalSubmit');
            const originalText = submitBtn ? submitBtn.textContent : t('common.submit');

            try {
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = t('common.submitting');
                }

                const formData = {
                    question: container.querySelector('#addQuestion')?.value.trim() || '',
                    type: container.querySelector('#addType')?.value || '',
                    subtype: container.querySelector('#addSubtype')?.value || '',
                    species_or_domain: container.querySelector('#addSpeciesOrDomain')?.value.trim() || '',
                    model: container.querySelector('#addModel')?.value.trim() || '',
                    date: container.querySelector('#addDate')?.value || '',
                    is_verified: container.querySelector('#addIsVerified')?.checked
                };

                // 验证必填字段
                if (!formData.question || !formData.type || !formData.subtype ||
                    !formData.species_or_domain || !formData.model || !formData.date) {
                    showError(t('common.pleaseFillRequiredFields'));
                    return;
                }

                await apiPost('/seed-questions/', formData);

                showSuccess(t('error.submitSuccess'));
                const modal = container.querySelector('#addModal');
                if (modal) modal.classList.remove('active');
                this.resetAddForm();

                // 刷新列表
                this.loadMyQuestions();

            } catch (error) {
                console.error(t('error.submitFailed') + ':', error);
                showError(error.message || t('error.submitFailedRetry'));
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
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

        showImportCsvModal: function() {
            const modal = container.querySelector('#importCsvModal');
            if (modal) {
                this.resetImportCsvForm();
                modal.classList.add('active');
            }
        },

        initImportCsvModal: function() {
            const modal = container.querySelector('#importCsvModal');
            if (!modal) return;

            const closeBtn = container.querySelector('#importCsvModalClose');
            const cancelBtn = container.querySelector('#importCsvModalCancel');
            const submitBtn = container.querySelector('#importCsvModalSubmit');

            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    modal.classList.remove('active');
                    this.resetImportCsvForm();
                });
            }

            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    modal.classList.remove('active');
                    this.resetImportCsvForm();
                });
            }

            if (submitBtn) {
                submitBtn.addEventListener('click', () => {
                    this.handleImportCsvSubmit();
                });
            }
        },

        resetImportCsvForm: function() {
            const fileInput = container.querySelector('#csvFileInput');
            const resultDiv = container.querySelector('#importResult');
            if (fileInput) {
                fileInput.value = '';
            }
            if (resultDiv) {
                resultDiv.classList.add('hidden');
                resultDiv.innerHTML = '';
            }
        },

        handleImportCsvSubmit: async function() {
            const fileInput = container.querySelector('#csvFileInput');
            const submitBtn = container.querySelector('#importCsvModalSubmit');
            const resultDiv = container.querySelector('#importResult');
            const modal = container.querySelector('#importCsvModal');

            if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
                showError(t('error.selectCsvFile'));
                return;
            }

            const file = fileInput.files[0];
            if (!file.name.endsWith('.csv')) {
                showError(t('error.onlyCsvFormat'));
                return;
            }

            const originalText = submitBtn ? submitBtn.textContent : t('error.importRecords');

            try {
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = t('error.importing');
                }

                // 显示结果区域
                if (resultDiv) {
                    resultDiv.classList.remove('hidden');
                    resultDiv.innerHTML = '<div class="loading">' + t('common.loading') + '</div>';
                }

                // 上传文件
                const result = await apiUploadFile('/seed-questions/import', file);

                // 显示导入结果
                if (resultDiv) {
                    const successCount = result.imported_count || 0;
                    const failedCount = result.failed_count || 0;
                    const totalRows = result.total_rows || 0;
                    const errors = result.errors || [];

                    let resultHtml = `
                        <div class="import-result-content">
                            <h4>导入完成</h4>
                            <div class="import-stats">
                                <div class="stat-item">
                                    <span class="stat-label">总行数：</span>
                                    <span class="stat-value">${totalRows}</span>
                                </div>
                                <div class="stat-item stat-success">
                                    <span class="stat-label">成功导入：</span>
                                    <span class="stat-value">${successCount}</span>
                                </div>
                                <div class="stat-item stat-error">
                                    <span class="stat-label">失败：</span>
                                    <span class="stat-value">${failedCount}</span>
                                </div>
                            </div>
                    `;

                    if (errors.length > 0) {
                        resultHtml += `
                            <div class="import-errors">
                                <h5>错误信息：</h5>
                                <ul class="error-list">
                                    ${errors.map(error => `<li>${escapeHtml(error)}</li>`).join('')}
                                </ul>
                            </div>
                        `;
                    }

                    resultHtml += '</div>';

                    resultDiv.innerHTML = resultHtml;

                    // 如果导入成功，延迟关闭模态框并刷新列表
                    if (successCount > 0) {
                        setTimeout(() => {
                            if (modal) modal.classList.remove('active');
                            this.resetImportCsvForm();
                            this.loadMyQuestions();
                            showSuccess(t('error.importSuccess', { count: successCount }));
                        }, 2000);
                    } else {
                        showError(t('error.importFailedNoRecords'));
                    }
                }

            } catch (error) {
                console.error(t('error.importFailedRetry') + ':', error);
                if (resultDiv) {
                    resultDiv.classList.remove('hidden');
                    resultDiv.innerHTML = `
                        <div class="import-result-content">
                            <h4 class="text-error">导入失败</h4>
                            <p class="error-message">${escapeHtml(error.message || t('error.importFailedRetry'))}</p>
                        </div>
                    `;
                }
                showError(error.message || t('error.importFailedRetry'));
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            }
        },

        showSeedQuestionUsage: function() {
            // 构建种子问题功能说明内容
            const usageContent = `
                <div style="max-width: 800px; line-height: 1.6;">
                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 8px;">
                            种子问题功能说明
                        </h3>
                        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin-top: 10px;">
                            <h4 style="margin-top: 0; color: #2196F3;">1. 种子问题管理</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>种子问题是用于生成数据集的基础问题，可以创建、编辑和删除自己的种子问题</li>
                                <li>每个用户只能查看和管理自己创建的种子问题</li>
                                <li>支持搜索功能，可以快速查找特定的种子问题</li>
                                <li>支持分页浏览，方便管理大量种子问题</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">2. 添加种子问题</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>点击"添加问题"按钮可以创建新的种子问题</li>
                                <li><strong>必填字段：</strong>种子问题内容、类型、亚类</li>
                                <li><strong>可选字段：</strong>物种/领域、使用的模型、日期、是否人工核验</li>
                                <li>种子问题内容应尽量详细和具体，便于后续生成高质量的QA对</li>
                                <li>类型和亚类用于分类管理，请选择合适的分类</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">3. 编辑种子问题</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>点击"编辑"按钮可以修改已创建的种子问题</li>
                                <li>可以更新问题的所有字段，包括内容、分类、附加信息等</li>
                                <li>编辑后保存即可更新问题信息</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">4. 批量导入</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>支持从CSV文件批量导入种子问题</li>
                                <li>CSV文件必须包含以下列：种子问题、类型、亚类（必填）</li>
                                <li>可选列：物种/领域、模型、日期（YYYYMMDD或YYYY-MM-DD格式）、是否核验（是/否）</li>
                                <li>导入时会显示成功和失败的数量，以及错误信息</li>
                                <li>批量导入适合一次性添加大量种子问题的场景</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">5. 分类信息</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li><strong>类型：</strong>种子问题的主要分类，用于大类别管理</li>
                                <li><strong>亚类：</strong>在类型下的细分分类，选择类型后才会显示对应的亚类选项</li>
                                <li>类型和亚类的选项由系统预定义，请从下拉列表中选择</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">6. 附加信息</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li><strong>物种/领域：</strong>用于标识问题所属的特定领域或物种（如：水稻、玉米、小麦等）</li>
                                <li><strong>使用的模型：</strong>记录生成该问题时使用的AI模型（如：GPT-4、Claude等）</li>
                                <li><strong>日期：</strong>记录问题的创建或使用日期</li>
                                <li><strong>是否人工核验：</strong>标记该问题是否经过人工审核和验证</li>
                            </ul>

                            <h4 style="margin-top: 15px; color: #2196F3;">7. 搜索功能</h4>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>在搜索框中输入关键词可以快速查找种子问题</li>
                                <li>搜索支持实时匹配，输入后会自动过滤结果</li>
                                <li>清空搜索框可以显示所有问题</li>
                            </ul>
                        </div>
                    </div>

                    <div style="margin-bottom: 20px;">
                        <h3 style="color: #333; border-bottom: 2px solid #FF9800; padding-bottom: 8px;">
                            使用建议
                        </h3>
                        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #FF9800; margin-top: 10px;">
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li><strong>问题质量：</strong>种子问题应尽量详细和具体，避免过于宽泛或模糊的问题</li>
                                <li><strong>分类准确：</strong>正确选择类型和亚类，便于后续的分类管理和检索</li>
                                <li><strong>信息完整：</strong>尽量填写附加信息，有助于问题的管理和追溯</li>
                                <li><strong>批量导入：</strong>对于大量种子问题，建议使用CSV批量导入功能，提高效率</li>
                                <li><strong>定期整理：</strong>定期检查和整理种子问题，删除重复或不再使用的问题</li>
                                <li><strong>核验标记：</strong>对于经过人工审核的问题，建议标记"是否人工核验"，提高问题质量的可信度</li>
                            </ul>
                        </div>
                    </div>
                </div>
            `;

            // 显示对话框（隐藏提交按钮，只显示关闭按钮）
            openModal('种子问题功能说明', usageContent, null, true);
        }
    };

    // 导出到全局
    window.UserSeedQuestion = UserSeedQuestion;
})();
