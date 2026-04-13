/**
 * 标注结果分析页面逻辑
 */

window.AnnotationAnalysis = {
    currentProjectId: null,
    currentStats: null,

    /**
     * 初始化分析页面
     */
    init: async function(projectId) {
        this.currentProjectId = projectId;
        this.initLlmAnalysisButton();
        await this.loadAnalysisData();
        await this.loadCachedAnalysis();
    },

    /**
     * 加载分析数据
     */
    loadAnalysisData: async function() {
        try {
            const stats = await apiGet(`/analysis/projects/${this.currentProjectId}/annotation-stats`);
            this.currentStats = stats;
            this.renderOverview(stats);
            this.renderConfigsStats(stats.configs_stats);
            this.renderNotesSummary(stats.notes_summary);
        } catch (error) {
            console.error('加载分析数据失败:', error);
            this.showError('加载分析数据失败');
        }
    },

    /**
     * 加载缓存的 LLM 分析报告
     */
    loadCachedAnalysis: async function() {
        try {
            const response = await apiGet(`/analysis/projects/${this.currentProjectId}/cached-analysis`);
            if (response) {
                this.renderLlmAnalysisResult(response);
                const btn = document.getElementById('generateLlmAnalysisBtn');
                if (btn) {
                    btn.textContent = t('analysis.regenerateAnalysis') || '重新生成分析';
                }
            }
        } catch (error) {
            // 404 means no cached analysis, which is normal
            if (error.status !== 404) {
                console.warn('加载缓存分析报告失败:', error);
            }
        }
    },

    /**
     * 渲染概览卡片
     */
    renderOverview: function(stats) {
        document.getElementById('analysisTotalDatasets').textContent = stats.total_datasets;
        document.getElementById('analysisTotalItems').textContent = stats.total_items;
        // 已标注的QA对：至少标注了1个配置的QA对数量
        document.getElementById('analysisAnnotatedItems').textContent = stats.annotated_items_count;
        // 已完整标注的QA对：完成所有配置标注的QA对数量
        document.getElementById('analysisFullyAnnotatedItems').textContent = stats.fully_annotated_count;
        // 完整标注率：完成所有配置标注的QA对占比
        document.getElementById('analysisCompletionRate').textContent =
            (stats.completion_rate * 100).toFixed(1) + '%';
    },

    /**
     * 渲染配置统计
     */
    renderConfigsStats: function(configsStats) {
        const container = document.getElementById('analysisConfigsContainer');
        container.innerHTML = '';

        if (!configsStats || configsStats.length === 0) {
            container.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">' + t('project.noAnnotationData') + '</div>';
            return;
        }

        configsStats.forEach(configStat => {
            const card = this.createConfigStatCard(configStat);
            container.appendChild(card);
        });
    },

    /**
     * 创建配置统计卡片
     */
    createConfigStatCard: function(configStat) {
        const card = document.createElement('div');
        card.className = 'config-stat-card';

        const header = document.createElement('div');
        header.className = 'config-stat-header';
        header.innerHTML = `
            <h4>${this.escapeHtml(configStat.config_name)}</h4>
            <span class="config-type-badge">${this.getTypeLabel(configStat.annotation_type)}</span>
        `;
        card.appendChild(header);

        const info = document.createElement('div');
        info.className = 'config-stat-info';
        info.innerHTML = `
            <span>${t('project.annotationCount')}: <strong>${configStat.total_annotations}</strong></span>
            <span>${t('project.coverage')}: <strong>${(configStat.coverage * 100).toFixed(1)}%</strong></span>
        `;
        card.appendChild(info);

        // 渲染图表容器
        const chartContainer = document.createElement('div');
        chartContainer.className = 'config-chart-container';
        chartContainer.id = `chart-${configStat.config_id}`;
        card.appendChild(chartContainer);

        // 根据类型渲染不同的图表
        this.renderChart(chartContainer, configStat);

        return card;
    },

    /**
     * 渲染图表
     */
    renderChart: function(container, configStat) {
        const stats = configStat.stats;

        switch (configStat.annotation_type) {
            case 'score':
                this.renderScoreChart(container, stats);
                break;
            case 'single_choice':
            case 'multi_choice':
                this.renderChoiceChart(container, stats);
                break;
            case 'category':
                this.renderCategoryChart(container, stats);
                break;
            case 'binary':
                this.renderBinaryChart(container, stats);
                break;
            case 'text':
                this.renderTextStats(container, stats);
                break;
        }
    },

    /**
     * 渲染评分图表
     */
    renderScoreChart: function(container, stats) {
        try {
            const canvas = document.createElement('canvas');
            // 获取容器的实际宽度
            const containerWidth = container.offsetWidth || 600;
            const width = Math.min(containerWidth, 600);
            canvas.width = width;
            canvas.height = 300;
            canvas.style.width = width + 'px';
            canvas.style.height = '300px';
            canvas.style.display = 'block';
            canvas.style.maxWidth = '100%';
            container.appendChild(canvas);

            const labels = Object.keys(stats.distribution).sort();
            const data = labels.map(key => stats.distribution[key]);

            if (typeof Chart === 'undefined') {
                container.innerHTML += '<div style="color: red; text-align: center; margin-top: 20px;">' + t('messages.chartLibLoadFailed') + '</div>';
                return;
            }

            new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: labels.map(l => l + t('config.scoreUnit') || '分'),
                    datasets: [{
                        label: t('common.count') || '数量',
                        data: data,
                        backgroundColor: 'rgba(54, 162, 235, 0.6)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: `${t('project.averageScore') || '平均分'}: ${stats.average.toFixed(2)} (${t('project.scoreRange') || '范围'}: ${stats.min}-${stats.max})`
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        } catch (error) {
            console.error('renderScoreChart error:', error);
            container.innerHTML += `<div style="color: red; text-align: center; margin-top: 20px;">${t('project.chartRenderFailed')}: ${error.message}</div>`;
        }
    },

    /**
     * 渲染选择题图表
     */
    renderChoiceChart: function(container, stats) {
        const canvas = document.createElement('canvas');
        // 获取容器的实际宽度
        const containerWidth = container.offsetWidth || 600;
        const width = Math.min(containerWidth, 600);
        canvas.width = width;
        canvas.height = 300;
        canvas.style.width = width + 'px';
        canvas.style.height = '300px';
        canvas.style.display = 'block';
        canvas.style.maxWidth = '100%';
        container.appendChild(canvas);

        const labels = Object.keys(stats.option_distribution).map(key =>
            stats.option_labels[key] || key
        );
        const data = Object.values(stats.option_distribution);

        try {
            new Chart(canvas, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{
                        data: data,
                        backgroundColor: [
                            'rgba(255, 99, 132, 0.6)',
                            'rgba(54, 162, 235, 0.6)',
                            'rgba(255, 206, 86, 0.6)',
                            'rgba(75, 192, 192, 0.6)',
                            'rgba(153, 102, 255, 0.6)',
                            'rgba(255, 159, 64, 0.6)'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: `${t('project.totalAnnotations') || '总标注数'}: ${stats.count}`
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Chart创建失败:', error);
        }
    },

    /**
     * 渲染分类图表
     */
    renderCategoryChart: function(container, stats) {
        const canvas = document.createElement('canvas');
        const containerWidth = container.offsetWidth || 600;
        const width = Math.min(containerWidth, 600);
        canvas.width = width;
        canvas.height = 300;
        canvas.style.width = width + 'px';
        canvas.style.height = '300px';
        canvas.style.display = 'block';
        canvas.style.maxWidth = '100%';
        container.appendChild(canvas);

        const labels = Object.keys(stats.category_distribution);
        const data = Object.values(stats.category_distribution);

        new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.6)',
                        'rgba(54, 162, 235, 0.6)',
                        'rgba(255, 206, 86, 0.6)',
                        'rgba(75, 192, 192, 0.6)',
                        'rgba(153, 102, 255, 0.6)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: `${t('project.totalAnnotations') || '总标注数'}: ${stats.count}`
                    }
                }
            }
        });
    },

    /**
     * 渲染二元标注图表
     */
    renderBinaryChart: function(container, stats) {
        const canvas = document.createElement('canvas');
        const containerWidth = container.offsetWidth || 600;
        const width = Math.min(containerWidth, 600);
        canvas.width = width;
        canvas.height = 300;
        canvas.style.width = width + 'px';
        canvas.style.height = '300px';
        canvas.style.display = 'block';
        canvas.style.maxWidth = '100%';
        container.appendChild(canvas);

        new Chart(canvas, {
            type: 'pie',
            data: {
                labels: [t('common.yes'), t('common.no')],
                datasets: [{
                    data: [stats.true_count, stats.false_count],
                    backgroundColor: [
                        'rgba(75, 192, 192, 0.6)',
                        'rgba(255, 99, 132, 0.6)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: `${t('project.yesRatio') || `'是'占比`}: ${(stats.true_ratio * 100).toFixed(1)}%`
                    }
                }
            }
        });
    },

    /**
     * 渲染文本统计
     */
    renderTextStats: function(container, stats) {
        const statsDiv = document.createElement('div');
        statsDiv.className = 'text-stats-container';
        statsDiv.innerHTML = `
            <div class="text-stat-item">
                <span class="text-stat-label">${t('project.avgLength') || '平均长度'}</span>
                <span class="text-stat-value">${stats.avg_length.toFixed(0)} ${t('project.characters') || '字符'}</span>
            </div>
            <div class="text-stat-item">
                <span class="text-stat-label">${t('project.avgWords') || '平均词数'}</span>
                <span class="text-stat-value">${stats.avg_words.toFixed(0)} ${t('project.words') || '词'}</span>
            </div>
            <div class="text-stat-item">
                <span class="text-stat-label">${t('project.maxLength') || '最长'}</span>
                <span class="text-stat-value">${stats.max_length} ${t('project.characters') || '字符'}</span>
            </div>
            <div class="text-stat-item">
                <span class="text-stat-label">${t('project.minLength') || '最短'}</span>
                <span class="text-stat-value">${stats.min_length} ${t('project.characters') || '字符'}</span>
            </div>
        `;
        container.appendChild(statsDiv);
    },

    /**
     * 渲染Notes汇总
     */
    renderNotesSummary: function(notesSummary) {
        const container = document.getElementById('analysisNotesContainer');
        container.innerHTML = '';

        if (!notesSummary || notesSummary.length === 0) {
            container.innerHTML = '<div style="color: #999;">' + t('project.noNotes') + '</div>';
            return;
        }

        notesSummary.forEach(item => {
            const section = document.createElement('div');
            section.className = 'notes-summary-section';

            const header = document.createElement('h4');
            header.textContent = `${item.config_name} (${item.count}${t('common.items') || '条'})`;
            section.appendChild(header);

            // 简单的关键词提取
            const keywords = this.extractKeywords(item.notes);
            if (keywords.length > 0) {
                const keywordDiv = document.createElement('div');
                keywordDiv.className = 'notes-keywords';
                keywordDiv.innerHTML = `<strong>${t('project.keywords') || '关键词'}:</strong> ` + keywords.map(k =>
                    `<span class="keyword-tag">${k.word}</span>`
                ).join('');
                section.appendChild(keywordDiv);
            }

            // 显示前10条notes
            const notesList = document.createElement('div');
            notesList.className = 'notes-list';
            item.notes.slice(0, 10).forEach(note => {
                const noteItem = document.createElement('div');
                noteItem.className = 'note-item';
                noteItem.textContent = note;
                notesList.appendChild(noteItem);
            });

            if (item.notes.length > 10) {
                const more = document.createElement('div');
                more.className = 'notes-more';
                more.textContent = `还有 ${item.notes.length - 10} 条...`;
                notesList.appendChild(more);
            }

            section.appendChild(notesList);
            container.appendChild(section);
        });
    },

    /**
     * 提取关键词（简单的词频统计）
     */
    extractKeywords: function(notes) {
        const wordCount = {};
        const stopWords = ['的', '了', '是', '在', '有', '和', '与', '或', '等', '很', '也', '都', '这', '那'];

        notes.forEach(note => {
            // 简单的分词（按空格和常见标点）
            const words = note.split(/[\s，。！？、；：""''（）]+/);
            words.forEach(word => {
                if (word.length >= 2 && !stopWords.includes(word)) {
                    wordCount[word] = (wordCount[word] || 0) + 1;
                }
            });
        });

        // 排序并取前5个
        return Object.entries(wordCount)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([word, count]) => ({ word, count }));
    },

    /**
     * 获取类型标签
     */
    getTypeLabel: function(type) {
        const labels = {
            'score': t('annotation.score'),
            'category': t('annotation.category'),
            'text': t('annotation.text'),
            'single_choice': t('annotation.singleChoice'),
            'multi_choice': t('annotation.multiChoice'),
            'binary': t('annotation.binary')
        };
        return labels[type] || type;
    },

    /**
     * 显示错误
     */
    showError: function(message) {
        const container = document.getElementById('analysisConfigsContainer');
        container.innerHTML = `<div style="color: red; text-align: center; padding: 40px;">${message}</div>`;
    },

    /**
     * 转义HTML
     */
    escapeHtml: function(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // ==================== LLM 分析功能 ====================

    /**
     * 初始化 LLM 分析按钮
     */
    initLlmAnalysisButton: function() {
        const btn = document.getElementById('generateLlmAnalysisBtn');
        if (btn) {
            btn.addEventListener('click', () => {
                this.generateLlmAnalysis();
            });
        }
    },

    /**
     * 生成 LLM 分析
     */
    generateLlmAnalysis: async function() {
        const btn = document.getElementById('generateLlmAnalysisBtn');
        const resultContainer = document.getElementById('llmAnalysisResult');

        if (!btn || !resultContainer) return;

        // 显示加载状态
        btn.disabled = true;
        btn.textContent = t('analysis.generatingAnalysis') || '正在生成分析...';
        resultContainer.innerHTML = `<div class="llm-loading-spinner">${t('analysis.generatingAnalysis') || '正在生成分析...'}</div>`;

        try {
            // 获取当前界面语言
            const currentLang = (window.i18next && window.i18next.language) || 'zh';
            const lang = currentLang.startsWith('zh') ? 'zh' : 'en';
            const response = await apiPost(`/analysis/projects/${this.currentProjectId}/analyze-notes?lang=${lang}`);
            this.renderLlmAnalysisResult(response);
        } catch (error) {
            console.error('LLM 分析失败:', error);
            let errorMessage = t('analysis.analysisFailed') || '分析生成失败';
            if (error.data && error.data.detail) {
                errorMessage += ': ' + error.data.detail;
            } else if (error.message) {
                errorMessage += ': ' + error.message;
            }
            resultContainer.innerHTML = `<div class="llm-error-message"><span class="error-icon">!</span> ${escapeHtml(errorMessage)}</div>`;
        } finally {
            btn.disabled = false;
            // 恢复按钮文字：如果有缓存报告则显示"重新生成分析"，否则显示"一键生成分析"
            const resultContainer = document.getElementById('llmAnalysisResult');
            if (resultContainer && resultContainer.querySelector('.llm-analysis-result')) {
                btn.textContent = t('analysis.regenerateAnalysis') || '重新生成分析';
            } else {
                btn.textContent = t('analysis.generateLlmAnalysis') || '一键生成分析';
            }
        }
    },

    /**
     * 渲染 LLM 分析结果
     */
    renderLlmAnalysisResult: function(response) {
        const resultContainer = document.getElementById('llmAnalysisResult');
        if (!resultContainer) return;

        const htmlContent = this.simpleMarkdownToHtml(response.analysis);

        // 保存原始 markdown 供下载用
        this._lastAnalysisMarkdown = response.analysis;
        this._lastAnalysisModel = response.model_name;

        resultContainer.innerHTML = `
            <div class="llm-analysis-result">
                <div class="llm-analysis-header">
                    <h4>${t('analysis.analysisResult') || 'LLM 分析报告'}</h4>
                    <div class="llm-analysis-meta">
                        <span>${t('analysis.analysisModel') || '使用模型'}: ${this.escapeHtml(response.model_name)}</span>
                        <span>${t('analysis.analysisNotesCount') || '分析备注数'}: ${response.notes_count}</span>
                        <button class="btn btn-secondary" id="downloadAnalysisMdBtn" style="font-size: 12px; padding: 4px 12px;">${t('analysis.downloadMd') || '下载 MD'}</button>
                    </div>
                </div>
                <div class="llm-analysis-content">
                    ${htmlContent}
                </div>
            </div>
        `;

        // 绑定下载按钮
        const downloadBtn = document.getElementById('downloadAnalysisMdBtn');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => {
                this.downloadAnalysisMd();
            });
        }
    },

    /**
     * 下载分析结果为 Markdown 文件
     */
    downloadAnalysisMd: function() {
        if (!this._lastAnalysisMarkdown) return;

        const blob = new Blob([this._lastAnalysisMarkdown], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        const timestamp = new Date().toISOString().slice(0, 10);
        a.href = url;
        a.download = `llm-analysis-${timestamp}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    },

    /**
     * 轻量 Markdown 转 HTML 转换
     */
    simpleMarkdownToHtml: function(md) {
        if (!md) return '';

        let html = this.escapeHtml(md);

        // 代码块 (```...```)
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function(match, lang, code) {
            return '<pre><code>' + code + '</code></pre>';
        });

        // 行内代码 (`...`)
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // 标题 (h1-h6)
        html = html.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>');
        html = html.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>');
        html = html.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>');

        // 粗体 (**...** 或 __...__)
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');

        // 斜体 (*...* 或 _..._)
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        html = html.replace(/_(.+?)_/g, '<em>$1</em>');

        // 引用 (> ...)
        html = html.replace(/^&gt;\s+(.+)$/gm, '<blockquote>$1</blockquote>');

        // 无序列表 (- ... 或 * ...)
        html = html.replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

        // 有序列表 (1. ...)
        html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');

        // 段落：双换行转为段落分隔
        html = html.replace(/\n\n+/g, '</p><p>');

        // 单换行转为 <br>（在非标签内容中）
        html = html.replace(/\n/g, '<br>');

        // 包裹在段落中
        html = '<p>' + html + '</p>';

        // 清理空段落
        html = html.replace(/<p>\s*<\/p>/g, '');
        html = html.replace(/<p>\s*(<h[1-6]>)/g, '$1');
        html = html.replace(/(<\/h[1-6]>)\s*<\/p>/g, '$1');
        html = html.replace(/<p>\s*(<ul>)/g, '$1');
        html = html.replace(/(<\/ul>)\s*<\/p>/g, '$1');
        html = html.replace(/<p>\s*(<pre>)/g, '$1');
        html = html.replace(/(<\/pre>)\s*<\/p>/g, '$1');
        html = html.replace(/<p>\s*(<blockquote>)/g, '$1');
        html = html.replace(/(<\/blockquote>)\s*<\/p>/g, '$1');

        return html;
    }
};
