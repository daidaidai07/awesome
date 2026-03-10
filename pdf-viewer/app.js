/**
 * LightPDF Viewer - A lightweight PDF viewer
 */
(function () {
    'use strict';

    // --- State ---
    let pdfDoc = null;
    let currentPage = 1;
    let totalPages = 0;
    let currentScale = 1.0;
    let scaleMode = 'fixed'; // 'fixed', 'fit-width', 'fit-page'
    let rotation = 0;
    let renderedPages = new Map();
    let searchMatches = [];
    let currentSearchIndex = -1;
    let searchDebounceTimer = null;

    // --- DOM Elements ---
    const el = {
        fileInput: document.getElementById('file-input'),
        btnOpen: document.getElementById('btn-open'),
        btnPrint: document.getElementById('btn-print'),
        btnPrev: document.getElementById('btn-prev'),
        btnNext: document.getElementById('btn-next'),
        pageInput: document.getElementById('page-input'),
        pageCount: document.getElementById('page-count'),
        btnZoomOut: document.getElementById('btn-zoom-out'),
        btnZoomIn: document.getElementById('btn-zoom-in'),
        zoomSelect: document.getElementById('zoom-select'),
        btnRotateLeft: document.getElementById('btn-rotate-left'),
        btnRotateRight: document.getElementById('btn-rotate-right'),
        searchInput: document.getElementById('search-input'),
        searchResultCount: document.getElementById('search-result-count'),
        btnSearchPrev: document.getElementById('btn-search-prev'),
        btnSearchNext: document.getElementById('btn-search-next'),
        btnSidebar: document.getElementById('btn-sidebar'),
        btnDarkMode: document.getElementById('btn-dark-mode'),
        btnFullscreen: document.getElementById('btn-fullscreen'),
        sidebar: document.getElementById('sidebar'),
        thumbnailContainer: document.getElementById('thumbnail-container'),
        outlineContainer: document.getElementById('outline-container'),
        viewerContainer: document.getElementById('viewer-container'),
        viewer: document.getElementById('viewer'),
        dropZone: document.getElementById('drop-zone'),
        loading: document.getElementById('loading'),
    };

    // --- Initialization ---
    function init() {
        bindEvents();
        loadDarkModePreference();
    }

    function bindEvents() {
        el.btnOpen.addEventListener('click', () => el.fileInput.click());
        el.fileInput.addEventListener('change', handleFileSelect);
        el.btnPrint.addEventListener('click', printPDF);

        el.btnPrev.addEventListener('click', () => goToPage(currentPage - 1));
        el.btnNext.addEventListener('click', () => goToPage(currentPage + 1));
        el.pageInput.addEventListener('change', () => goToPage(parseInt(el.pageInput.value)));
        el.pageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') goToPage(parseInt(el.pageInput.value));
        });

        el.btnZoomOut.addEventListener('click', () => zoomBy(-0.25));
        el.btnZoomIn.addEventListener('click', () => zoomBy(0.25));
        el.zoomSelect.addEventListener('change', handleZoomSelect);

        el.btnRotateLeft.addEventListener('click', () => rotate(-90));
        el.btnRotateRight.addEventListener('click', () => rotate(90));

        el.searchInput.addEventListener('input', debounceSearch);
        el.searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.shiftKey ? searchPrev() : searchNext();
            }
        });
        el.btnSearchPrev.addEventListener('click', searchPrev);
        el.btnSearchNext.addEventListener('click', searchNext);

        el.btnSidebar.addEventListener('click', toggleSidebar);
        el.btnDarkMode.addEventListener('click', toggleDarkMode);
        el.btnFullscreen.addEventListener('click', toggleFullscreen);

        // Sidebar tabs
        document.querySelectorAll('.sidebar-tab').forEach(tab => {
            tab.addEventListener('click', () => switchSidebarTab(tab.dataset.tab));
        });

        // Drag and drop
        const body = document.body;
        body.addEventListener('dragover', (e) => {
            e.preventDefault();
            el.dropZone.classList.add('dragging');
        });
        body.addEventListener('dragleave', (e) => {
            if (!body.contains(e.relatedTarget)) {
                el.dropZone.classList.remove('dragging');
            }
        });
        body.addEventListener('drop', handleDrop);

        // Keyboard shortcuts
        document.addEventListener('keydown', handleKeyboard);

        // Track scroll for current page
        el.viewerContainer.addEventListener('scroll', handleScroll);

        // Resize handler for fit modes
        window.addEventListener('resize', handleResize);
    }

    // --- File Loading ---
    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (file && file.type === 'application/pdf') {
            loadFile(file);
        }
        e.target.value = '';
    }

    function handleDrop(e) {
        e.preventDefault();
        el.dropZone.classList.remove('dragging');
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            loadFile(file);
        }
    }

    function loadFile(file) {
        showLoading(true);
        const reader = new FileReader();
        reader.onload = function (e) {
            loadPDF(new Uint8Array(e.target.result), file.name);
        };
        reader.readAsArrayBuffer(file);
    }

    async function loadPDF(data, filename) {
        try {
            if (pdfDoc) {
                pdfDoc.destroy();
            }
            pdfDoc = await pdfjsLib.getDocument({ data }).promise;
            totalPages = pdfDoc.numPages;
            currentPage = 1;
            rotation = 0;
            searchMatches = [];
            currentSearchIndex = -1;
            renderedPages.clear();

            document.title = filename ? `${filename} - LightPDF Viewer` : 'LightPDF Viewer';

            enableControls(true);
            updatePageInfo();

            el.dropZone.classList.remove('active');
            el.viewer.innerHTML = '';
            el.viewer.appendChild(el.dropZone);

            renderAllPages();
            renderThumbnails();
            loadOutline();

            showLoading(false);
        } catch (err) {
            showLoading(false);
            alert('PDFの読み込みに失敗しました: ' + err.message);
        }
    }

    // --- Rendering ---
    async function renderAllPages() {
        const fragment = document.createDocumentFragment();

        for (let i = 1; i <= totalPages; i++) {
            const wrapper = document.createElement('div');
            wrapper.className = 'page-wrapper';
            wrapper.id = `page-${i}`;
            wrapper.dataset.pageNumber = i;

            const canvas = document.createElement('canvas');
            canvas.className = 'page-canvas';
            wrapper.appendChild(canvas);

            fragment.appendChild(wrapper);
        }

        // Keep drop zone but hide it, add pages
        el.viewer.innerHTML = '';
        el.viewer.appendChild(fragment);

        await renderVisiblePages();
    }

    async function renderVisiblePages() {
        const container = el.viewerContainer;
        const scrollTop = container.scrollTop;
        const viewHeight = container.clientHeight;
        const buffer = viewHeight; // render one screen above and below

        for (let i = 1; i <= totalPages; i++) {
            const wrapper = document.getElementById(`page-${i}`);
            if (!wrapper) continue;

            const rect = wrapper.getBoundingClientRect();
            const containerRect = container.getBoundingClientRect();
            const relativeTop = rect.top - containerRect.top;
            const relativeBottom = rect.bottom - containerRect.top;

            const isVisible = relativeBottom > -buffer && relativeTop < viewHeight + buffer;

            if (isVisible && !renderedPages.has(i)) {
                renderedPages.set(i, true);
                await renderPage(i);
            }
        }
    }

    async function renderPage(pageNum) {
        const page = await pdfDoc.getPage(pageNum);
        const viewport = page.getViewport({ scale: getEffectiveScale(page), rotation });

        const wrapper = document.getElementById(`page-${pageNum}`);
        if (!wrapper) return;

        const canvas = wrapper.querySelector('canvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const pixelRatio = window.devicePixelRatio || 1;

        canvas.width = viewport.width * pixelRatio;
        canvas.height = viewport.height * pixelRatio;
        canvas.style.width = viewport.width + 'px';
        canvas.style.height = viewport.height + 'px';

        ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);

        await page.render({
            canvasContext: ctx,
            viewport: viewport,
        }).promise;

        // Add text layer for selection
        const existingTextLayer = wrapper.querySelector('.text-layer');
        if (existingTextLayer) existingTextLayer.remove();

        const textContent = await page.getTextContent();
        const textLayer = document.createElement('div');
        textLayer.className = 'text-layer';
        textLayer.style.width = viewport.width + 'px';
        textLayer.style.height = viewport.height + 'px';

        textContent.items.forEach(item => {
            const span = document.createElement('span');
            const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
            const fontSize = Math.sqrt(tx[0] * tx[0] + tx[1] * tx[1]);

            span.textContent = item.str;
            span.style.left = tx[4] + 'px';
            span.style.top = (tx[5] - fontSize) + 'px';
            span.style.fontSize = fontSize + 'px';
            span.style.fontFamily = item.fontName || 'sans-serif';

            const scaleX = item.width / (span.offsetWidth || item.str.length * fontSize * 0.5) || 1;
            span.style.transform = `scaleX(${scaleX})`;

            textLayer.appendChild(span);
        });

        wrapper.appendChild(textLayer);
    }

    function getEffectiveScale(page) {
        if (scaleMode === 'fixed') return currentScale;

        const viewport = page.getViewport({ scale: 1, rotation });
        const containerWidth = el.viewerContainer.clientWidth - 60;
        const containerHeight = el.viewerContainer.clientHeight - 40;

        if (scaleMode === 'fit-width') {
            return containerWidth / viewport.width;
        } else if (scaleMode === 'fit-page') {
            const scaleW = containerWidth / viewport.width;
            const scaleH = containerHeight / viewport.height;
            return Math.min(scaleW, scaleH);
        }
        return currentScale;
    }

    async function reRenderAll() {
        renderedPages.clear();
        for (let i = 1; i <= totalPages; i++) {
            const wrapper = document.getElementById(`page-${i}`);
            if (wrapper) {
                const canvas = wrapper.querySelector('canvas');
                if (canvas) {
                    // Reset canvas to trigger re-render
                    canvas.width = 0;
                    canvas.height = 0;
                }
                const textLayer = wrapper.querySelector('.text-layer');
                if (textLayer) textLayer.remove();
            }
        }
        await renderVisiblePages();
    }

    // --- Thumbnails ---
    async function renderThumbnails() {
        el.thumbnailContainer.innerHTML = '';

        for (let i = 1; i <= totalPages; i++) {
            const page = await pdfDoc.getPage(i);
            const viewport = page.getViewport({ scale: 0.2 });

            const item = document.createElement('div');
            item.className = 'thumbnail-item' + (i === currentPage ? ' active' : '');
            item.dataset.page = i;

            const canvas = document.createElement('canvas');
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            canvas.style.width = viewport.width + 'px';
            canvas.style.height = viewport.height + 'px';

            const ctx = canvas.getContext('2d');
            await page.render({ canvasContext: ctx, viewport }).promise;

            const label = document.createElement('div');
            label.className = 'thumbnail-label';
            label.textContent = i;

            item.appendChild(canvas);
            item.appendChild(label);
            item.addEventListener('click', () => goToPage(i));

            el.thumbnailContainer.appendChild(item);
        }
    }

    function updateThumbnailHighlight() {
        document.querySelectorAll('.thumbnail-item').forEach(item => {
            item.classList.toggle('active', parseInt(item.dataset.page) === currentPage);
        });
    }

    // --- Outline ---
    async function loadOutline() {
        el.outlineContainer.innerHTML = '';
        try {
            const outline = await pdfDoc.getOutline();
            if (outline && outline.length > 0) {
                buildOutlineTree(outline, el.outlineContainer);
            } else {
                el.outlineContainer.innerHTML = '<p style="padding:12px;color:var(--text-secondary);font-size:13px;">目次はありません</p>';
            }
        } catch {
            el.outlineContainer.innerHTML = '<p style="padding:12px;color:var(--text-secondary);font-size:13px;">目次の読み込みに失敗しました</p>';
        }
    }

    function buildOutlineTree(items, container) {
        items.forEach(item => {
            const link = document.createElement('a');
            link.className = 'outline-item';
            link.textContent = item.title;
            link.href = '#';
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                if (item.dest) {
                    try {
                        let dest = item.dest;
                        if (typeof dest === 'string') {
                            dest = await pdfDoc.getDestination(dest);
                        }
                        const pageIndex = await pdfDoc.getPageIndex(dest[0]);
                        goToPage(pageIndex + 1);
                    } catch {
                        // ignore navigation errors
                    }
                }
            });
            container.appendChild(link);

            if (item.items && item.items.length > 0) {
                const children = document.createElement('div');
                children.className = 'outline-children';
                buildOutlineTree(item.items, children);
                container.appendChild(children);
            }
        });
    }

    // --- Navigation ---
    function goToPage(num) {
        num = Math.max(1, Math.min(num, totalPages));
        currentPage = num;
        updatePageInfo();

        const wrapper = document.getElementById(`page-${num}`);
        if (wrapper) {
            wrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        updateThumbnailHighlight();
        renderVisiblePages();
    }

    function updatePageInfo() {
        el.pageInput.value = currentPage;
        el.pageInput.max = totalPages;
        el.pageCount.textContent = totalPages;
        el.btnPrev.disabled = currentPage <= 1;
        el.btnNext.disabled = currentPage >= totalPages;
    }

    function handleScroll() {
        if (!pdfDoc) return;

        // Determine current visible page
        const container = el.viewerContainer;
        const containerTop = container.scrollTop + container.clientHeight / 3;

        for (let i = 1; i <= totalPages; i++) {
            const wrapper = document.getElementById(`page-${i}`);
            if (!wrapper) continue;

            const top = wrapper.offsetTop - el.viewer.offsetTop;
            const bottom = top + wrapper.offsetHeight;

            if (containerTop >= top && containerTop < bottom) {
                if (currentPage !== i) {
                    currentPage = i;
                    updatePageInfo();
                    updateThumbnailHighlight();
                }
                break;
            }
        }

        renderVisiblePages();
    }

    // --- Zoom ---
    function zoomBy(delta) {
        scaleMode = 'fixed';
        currentScale = Math.max(0.25, Math.min(5, currentScale + delta));
        updateZoomSelect();
        reRenderAll();
    }

    function handleZoomSelect() {
        const value = el.zoomSelect.value;
        if (value === 'fit-width') {
            scaleMode = 'fit-width';
        } else if (value === 'fit-page') {
            scaleMode = 'fit-page';
        } else {
            scaleMode = 'fixed';
            currentScale = parseFloat(value);
        }
        reRenderAll();
    }

    function updateZoomSelect() {
        const options = el.zoomSelect.options;
        let matched = false;
        for (let i = 0; i < options.length; i++) {
            if (parseFloat(options[i].value) === currentScale) {
                el.zoomSelect.selectedIndex = i;
                matched = true;
                break;
            }
        }
        if (!matched) {
            // Set to closest or keep current
            el.zoomSelect.value = currentScale.toString();
        }
    }

    function handleResize() {
        if (!pdfDoc) return;
        if (scaleMode !== 'fixed') {
            reRenderAll();
        }
    }

    // --- Rotation ---
    function rotate(degrees) {
        rotation = (rotation + degrees + 360) % 360;
        reRenderAll();
        renderThumbnails();
    }

    // --- Search ---
    function debounceSearch() {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(performSearch, 300);
    }

    async function performSearch() {
        const query = el.searchInput.value.trim();
        clearSearchHighlights();
        searchMatches = [];
        currentSearchIndex = -1;

        if (!query || !pdfDoc) {
            el.searchResultCount.textContent = '';
            el.btnSearchPrev.disabled = true;
            el.btnSearchNext.disabled = true;
            return;
        }

        const lowerQuery = query.toLowerCase();

        for (let i = 1; i <= totalPages; i++) {
            const page = await pdfDoc.getPage(i);
            const textContent = await page.getTextContent();

            textContent.items.forEach((item, idx) => {
                const text = item.str.toLowerCase();
                let startPos = 0;
                while ((startPos = text.indexOf(lowerQuery, startPos)) !== -1) {
                    searchMatches.push({ pageNum: i, itemIndex: idx, startPos, length: query.length });
                    startPos += query.length;
                }
            });
        }

        if (searchMatches.length > 0) {
            el.searchResultCount.textContent = `${searchMatches.length}件`;
            el.btnSearchPrev.disabled = false;
            el.btnSearchNext.disabled = false;
            currentSearchIndex = 0;
            highlightCurrentMatch();
        } else {
            el.searchResultCount.textContent = '0件';
            el.btnSearchPrev.disabled = true;
            el.btnSearchNext.disabled = true;
        }
    }

    function searchNext() {
        if (searchMatches.length === 0) return;
        currentSearchIndex = (currentSearchIndex + 1) % searchMatches.length;
        highlightCurrentMatch();
    }

    function searchPrev() {
        if (searchMatches.length === 0) return;
        currentSearchIndex = (currentSearchIndex - 1 + searchMatches.length) % searchMatches.length;
        highlightCurrentMatch();
    }

    function highlightCurrentMatch() {
        if (currentSearchIndex < 0 || currentSearchIndex >= searchMatches.length) return;

        const match = searchMatches[currentSearchIndex];
        el.searchResultCount.textContent = `${currentSearchIndex + 1}/${searchMatches.length}`;

        // Navigate to the page
        goToPage(match.pageNum);

        // Visual feedback: briefly highlight the page wrapper
        const wrapper = document.getElementById(`page-${match.pageNum}`);
        if (wrapper) {
            wrapper.style.outline = '3px solid var(--accent-color)';
            setTimeout(() => {
                wrapper.style.outline = '';
            }, 1500);
        }
    }

    function clearSearchHighlights() {
        document.querySelectorAll('.page-wrapper').forEach(w => {
            w.style.outline = '';
        });
    }

    // --- Print ---
    function printPDF() {
        if (!pdfDoc) return;
        window.print();
    }

    // --- Sidebar ---
    function toggleSidebar() {
        el.sidebar.classList.toggle('hidden');
    }

    function switchSidebarTab(tab) {
        document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        document.querySelectorAll('.sidebar-content').forEach(c => c.classList.remove('active'));
        document.getElementById(tab === 'thumbnails' ? 'thumbnail-container' : 'outline-container').classList.add('active');
    }

    // --- Dark Mode ---
    function toggleDarkMode() {
        document.body.classList.toggle('dark-mode');
        localStorage.setItem('lightpdf-dark-mode', document.body.classList.contains('dark-mode'));
    }

    function loadDarkModePreference() {
        if (localStorage.getItem('lightpdf-dark-mode') === 'true') {
            document.body.classList.add('dark-mode');
        }
    }

    // --- Fullscreen ---
    function toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }

    // --- Controls ---
    function enableControls(enabled) {
        const controls = [
            el.btnPrint, el.btnPrev, el.btnNext, el.pageInput,
            el.btnZoomOut, el.btnZoomIn, el.zoomSelect,
            el.btnRotateLeft, el.btnRotateRight,
            el.searchInput, el.btnSearchPrev, el.btnSearchNext,
        ];
        controls.forEach(c => c.disabled = !enabled);
        if (enabled) updatePageInfo();
    }

    // --- Keyboard ---
    function handleKeyboard(e) {
        // Don't handle if typing in an input
        if (e.target.tagName === 'INPUT' && e.target.type !== 'number') return;

        if (e.ctrlKey || e.metaKey) {
            switch (e.key) {
                case 'o':
                    e.preventDefault();
                    el.fileInput.click();
                    break;
                case 'f':
                    e.preventDefault();
                    el.searchInput.focus();
                    el.searchInput.select();
                    break;
                case 'p':
                    e.preventDefault();
                    printPDF();
                    break;
                case '=':
                case '+':
                    e.preventDefault();
                    zoomBy(0.25);
                    break;
                case '-':
                    e.preventDefault();
                    zoomBy(-0.25);
                    break;
                case '0':
                    e.preventDefault();
                    scaleMode = 'fixed';
                    currentScale = 1.0;
                    updateZoomSelect();
                    reRenderAll();
                    break;
            }
            return;
        }

        switch (e.key) {
            case 'ArrowLeft':
            case 'PageUp':
                if (e.target.tagName !== 'INPUT') {
                    e.preventDefault();
                    goToPage(currentPage - 1);
                }
                break;
            case 'ArrowRight':
            case 'PageDown':
                if (e.target.tagName !== 'INPUT') {
                    e.preventDefault();
                    goToPage(currentPage + 1);
                }
                break;
            case 'Home':
                if (e.target.tagName !== 'INPUT') {
                    e.preventDefault();
                    goToPage(1);
                }
                break;
            case 'End':
                if (e.target.tagName !== 'INPUT') {
                    e.preventDefault();
                    goToPage(totalPages);
                }
                break;
            case 'F11':
                e.preventDefault();
                toggleFullscreen();
                break;
        }
    }

    // --- Utility ---
    function showLoading(show) {
        el.loading.classList.toggle('hidden', !show);
    }

    // --- Start ---
    init();
})();
