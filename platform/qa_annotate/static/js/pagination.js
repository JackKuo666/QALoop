/**
 * 通用分页模块
 * 提供分页状态管理和UI渲染功能
 */

class Paginator {
    /**
     * 创建分页器实例
     * @param {string} prefix - 分页控件的前缀ID (例如: 'users', 'datasets')
     * @param {Object} options - 配置选项
     * @param {number} options.initialPage - 初始页码，默认1
     * @param {number} options.initialPageSize - 初始每页数量，默认20
     * @param {Function} options.onPageChange - 页码改变时的回调函数
     * @param {Function} options.onPageSizeChange - 每页数量改变时的回调函数
     */
    constructor(prefix, options = {}) {
        this.prefix = prefix;
        this.currentPage = options.initialPage || 1;
        this.pageSize = options.initialPageSize || 20;
        this.totalCount = 0;
        this.onPageChange = options.onPageChange || (() => {});
        this.onPageSizeChange = options.onPageSizeChange || (() => {});

        // 绑定DOM元素
        this.container = document.getElementById(`${prefix}PaginationContainer`);
        this.info = document.getElementById(`${prefix}PaginationInfo`);
        this.pageNumbers = document.getElementById(`${prefix}PageNumbers`);
        this.prevBtn = document.getElementById(`${prefix}PrevPage`);
        this.nextBtn = document.getElementById(`${prefix}NextPage`);
        this.pageSizeSelect = document.getElementById(`${prefix}PageSize`);

        // 初始化事件监听
        this.initEventListeners();
    }

    /**
     * 初始化事件监听器
     */
    initEventListeners() {
        if (this.prevBtn) {
            this.prevBtn.addEventListener('click', () => {
                this.goToPreviousPage();
            });
        }

        if (this.nextBtn) {
            this.nextBtn.addEventListener('click', () => {
                this.goToNextPage();
            });
        }

        if (this.pageSizeSelect) {
            this.pageSizeSelect.addEventListener('change', (e) => {
                this.setPageSize(parseInt(e.target.value));
            });
        }
    }

    /**
     * 设置当前页码
     * @param {number} page - 页码
     */
    setPage(page) {
        const totalPages = this.getTotalPages();
        if (page >= 1 && page <= totalPages) {
            this.currentPage = page;
            this.render();
            this.onPageChange(this.currentPage, this.pageSize);
        }
    }

    /**
     * 设置每页数量
     * @param {number} pageSize - 每页数量
     */
    setPageSize(pageSize) {
        this.pageSize = pageSize;
        this.currentPage = 1; // 重置到第一页
        this.render();
        this.onPageSizeChange(this.pageSize);
    }

    /**
     * 设置总数
     * @param {number} totalCount - 总记录数
     */
    setTotalCount(totalCount) {
        this.totalCount = totalCount;
        this.render();
    }

    /**
     * 获取总页数
     * @returns {number}
     */
    getTotalPages() {
        return Math.ceil(this.totalCount / this.pageSize);
    }

    /**
     * 获取跳过的记录数 (用于API请求的skip参数)
     * @returns {number}
     */
    getSkip() {
        return (this.currentPage - 1) * this.pageSize;
    }

    /**
     * 获取限制数量 (用于API请求的limit参数)
     * @returns {number}
     */
    getLimit() {
        return this.pageSize;
    }

    /**
     * 重置到第一页
     */
    reset() {
        this.currentPage = 1;
        this.render();
    }

    /**
     * 跳转到上一页
     */
    goToPreviousPage() {
        if (this.currentPage > 1) {
            this.setPage(this.currentPage - 1);
        }
    }

    /**
     * 跳转到下一页
     */
    goToNextPage() {
        const totalPages = this.getTotalPages();
        if (this.currentPage < totalPages) {
            this.setPage(this.currentPage + 1);
        }
    }

    /**
     * 跳转到指定页
     * @param {number} page - 页码
     */
    goToPage(page) {
        this.setPage(page);
    }

    /**
     * 渲染分页UI
     */
    render() {
        if (!this.container || !this.info) {
            return;
        }

        if (this.totalCount === 0) {
            this.container.style.display = 'none';
            return;
        }

        this.container.style.display = 'flex';
        this.container.style.flexDirection = 'row';

        const totalPages = this.getTotalPages();
        const startIndex = (this.currentPage - 1) * this.pageSize + 1;
        const endIndex = Math.min(this.currentPage * this.pageSize, this.totalCount);

        // 更新信息
        if (this.info) {
            const text = window.t ? window.t('pagination.info', {
                total: this.totalCount,
                start: startIndex,
                end: endIndex
            }) : `共 ${this.totalCount} 条，显示第 ${startIndex}-${endIndex} 条`;
            this.info.textContent = text;
        }

        // 更新按钮状态
        if (this.prevBtn) {
            this.prevBtn.disabled = this.currentPage <= 1;
            if (this.prevBtn.disabled) {
                this.prevBtn.style.opacity = '0.5';
                this.prevBtn.style.cursor = 'not-allowed';
            } else {
                this.prevBtn.style.opacity = '1';
                this.prevBtn.style.cursor = 'pointer';
            }
        }

        if (this.nextBtn) {
            this.nextBtn.disabled = this.currentPage >= totalPages;
            if (this.nextBtn.disabled) {
                this.nextBtn.style.opacity = '0.5';
                this.nextBtn.style.cursor = 'not-allowed';
            } else {
                this.nextBtn.style.opacity = '1';
                this.nextBtn.style.cursor = 'pointer';
            }
        }

        // 生成页码按钮
        if (this.pageNumbers) {
            this.renderPageNumbers(totalPages);
        }
    }

    /**
     * 渲染页码按钮
     * @param {number} totalPages - 总页数
     */
    renderPageNumbers(totalPages) {
        this.pageNumbers.innerHTML = '';
        const maxVisiblePages = 7;
        let startPage = Math.max(1, this.currentPage - Math.floor(maxVisiblePages / 2));
        let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

        if (endPage - startPage < maxVisiblePages - 1) {
            startPage = Math.max(1, endPage - maxVisiblePages + 1);
        }

        // 第一页
        if (startPage > 1) {
            const btn = this.createPageButton(1);
            this.pageNumbers.appendChild(btn);

            if (startPage > 2) {
                const ellipsis = document.createElement('span');
                ellipsis.textContent = '...';
                ellipsis.style.cssText = 'padding: 6px 4px; color: #666;';
                this.pageNumbers.appendChild(ellipsis);
            }
        }

        // 页码按钮
        for (let i = startPage; i <= endPage; i++) {
            const btn = this.createPageButton(i, i === this.currentPage);
            this.pageNumbers.appendChild(btn);
        }

        // 最后一页
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const ellipsis = document.createElement('span');
                ellipsis.textContent = '...';
                ellipsis.style.cssText = 'padding: 6px 4px; color: #666;';
                this.pageNumbers.appendChild(ellipsis);
            }

            const btn = this.createPageButton(totalPages);
            this.pageNumbers.appendChild(btn);
        }
    }

    /**
     * 创建页码按钮
     * @param {number} page - 页码
     * @param {boolean} isActive - 是否为当前页
     * @returns {HTMLElement}
     */
    createPageButton(page, isActive = false) {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm';
        btn.style.cssText = 'padding: 6px 12px; min-width: 36px;';
        btn.textContent = page.toString();

        if (isActive) {
            btn.classList.add('btn-primary');
        } else {
            btn.classList.add('btn-secondary');
            btn.addEventListener('click', () => {
                this.goToPage(page);
            });
        }

        return btn;
    }

    /**
     * 检查删除后是否需要调整页码
     * 如果当前页没有数据了，自动回到上一页
     * @param {number} deletedCount - 删除的项目数量，默认为1
     */
    adjustPageAfterDelete(deletedCount = 1) {
        // 更新总数（减去删除的数量）
        this.totalCount = Math.max(0, this.totalCount - deletedCount);

        // 如果当前页没有数据了，回到上一页
        if (this.currentPage > 1 && (this.currentPage - 1) * this.pageSize >= this.totalCount) {
            this.currentPage--;
        }

        this.render();
    }
}

/**
 * 创建分页器实例的便捷函数
 * @param {string} prefix - 分页控件的前缀ID
 * @param {Object} options - 配置选项
 * @returns {Paginator}
 */
function createPaginator(prefix, options = {}) {
    return new Paginator(prefix, options);
}
