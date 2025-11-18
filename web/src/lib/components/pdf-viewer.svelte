<script lang="ts">
    import { browser } from '$app/environment';
    import { createEventDispatcher, onDestroy, onMount } from 'svelte';

    import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist/types/src/display/api';

    type PdfCoreModule = typeof import('pdfjs-dist');
    type PdfViewerModule = typeof import('pdfjs-dist/web/pdf_viewer');

    const PDFJS_VERSION = '4.6.82';
    const PDFJS_CDN_BASE = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;
    const PDFJS_SCRIPT = `${PDFJS_CDN_BASE}/pdf.mjs`;
    const PDFJS_VIEWER_SCRIPT = `${PDFJS_CDN_BASE}/pdf_viewer.mjs`;
    const PDFJS_WORKER_SCRIPT = `${PDFJS_CDN_BASE}/pdf.worker.mjs`;
    const PDFJS_VIEWER_CSS = `${PDFJS_CDN_BASE}/pdf_viewer.min.css`;

    export type PdfHighlight = {
        id?: string | number;
        term: string;
        color?: string;
        caseSensitive?: boolean;
        exact?: boolean;
    };

    const props = $props<{
        url: string;
        highlights?: PdfHighlight[];
        highlightTerm?: string;
        scale?: number;
        withCredentials?: boolean;
    }>();

    let { url, highlights = [], highlightTerm = '', scale = 1, withCredentials = false } = props;

    const dispatch = createEventDispatcher<{
        select: { text: string; pageNumber?: number; rects: Array<{ x: number; y: number; width: number; height: number }> };
    }>();

    let container: HTMLDivElement | null = null;
    let viewerHost: HTMLDivElement | null = null;
    let loading = $state(false);
    let errorMessage = $state('');

    let pdfTask: PDFDocumentLoadingTask | null = null;
    let pdfDocument: PDFDocumentProxy | null = null;
    let eventBus: InstanceType<PdfViewerModule['EventBus']> | null = null;
    let linkService: InstanceType<PdfViewerModule['PDFLinkService']> | null = null;
    let pdfViewer: InstanceType<PdfViewerModule['PDFViewer']> | null = null;
    let highlightFrame: number | null = null;
    const pendingHighlightPages = new Set<number>();
    let lastSourceKey: string | null = null;
    let detachMouseup: (() => void) | null = null;

    const handleTextLayerRendered = (...args: unknown[]) => {
        const event = args[0] as { pageNumber?: number } | undefined;
        if (typeof event?.pageNumber === 'number') {
            scheduleHighlightRefresh(event.pageNumber);
        }
    };

    onMount(() => {
        if (!browser || !container || !viewerHost) {
            return undefined;
        }

        let destroyed = false;

        const init = async () => {
            try {
                const runtime = await ensurePdfRuntime();
                if (!runtime || destroyed || !container || !viewerHost) {
                    return;
                }

                const { viewer } = runtime;

                eventBus = new viewer.EventBus();
                eventBus.on('textlayerrendered', handleTextLayerRendered);

                linkService = new viewer.PDFLinkService({ eventBus });
                const normalizedEventBus =
                    eventBus as unknown as import('pdfjs-dist/types/web/event_utils').EventBus;
                pdfViewer = new viewer.PDFViewer({
                    container,
                    viewer: viewerHost,
                    eventBus: normalizedEventBus,
                    textLayerMode: 1,
                    removePageBorders: true
                });

                linkService.setViewer(pdfViewer);

                const mouseupListener = () => handleMouseUp();
                window.addEventListener('mouseup', mouseupListener);
                detachMouseup = () => window.removeEventListener('mouseup', mouseupListener);

                if (url) {
                    lastSourceKey = sourceKey(url, withCredentials);
                    await loadPdf(url);
                }
            } catch (error) {
                errorMessage =
                    error instanceof Error
                        ? error.message
                        : 'Não foi possível inicializar o visualizador de PDF.';
            }
        };

        void init();

        return () => {
            destroyed = true;
            detachMouseup?.();
            detachMouseup = null;
            destroyPdf();
        };
    });

    onDestroy(() => {
        destroyPdf();
    });

    $effect(() => {
        if (!browser || !pdfViewer || !url) {
            return;
        }
        const key = sourceKey(url, withCredentials);
        if (key === lastSourceKey) {
            return;
        }
        lastSourceKey = key;
        void loadPdf(url);
    });

    $effect(() => {
        if (!browser || !pdfViewer) {
            return;
        }
        pdfViewer.currentScale = scale;
    });

    $effect(() => {
        if (!browser || !pdfViewer) {
            return;
        }
        void highlights;
        void highlightTerm;
        scheduleHighlightRefresh();
    });

    async function loadPdf(targetUrl: string) {
        if (!pdfViewer || !linkService || !browser) {
            return;
        }

        const runtime = await ensurePdfRuntime();
        if (!runtime) {
            return;
        }

        loading = true;
        errorMessage = '';

        try {
            await cleanupDocument();
            const { core } = runtime;
            pdfTask = core.getDocument({ url: targetUrl, withCredentials, enableHWA: true });
            pdfDocument = await pdfTask.promise;
            pdfViewer.setDocument(pdfDocument);
            linkService.setDocument(pdfDocument);
            pdfViewer.currentScale = scale;
            scheduleHighlightRefresh();
        } catch (error) {
            errorMessage = error instanceof Error ? error.message : 'Não foi possível carregar o PDF.';
        } finally {
            loading = false;
        }
    }

    async function cleanupDocument() {
        await pdfTask?.destroy();
        pdfTask = null;
        await pdfDocument?.destroy();
        pdfDocument = null;
    }

    function destroyPdf() {
        detachMouseup?.();
        detachMouseup = null;
        if (highlightFrame) {
            cancelAnimationFrame(highlightFrame);
            highlightFrame = null;
        }
        pendingHighlightPages.clear();
        if (eventBus) {
            eventBus.off('textlayerrendered', handleTextLayerRendered);
        }
        pdfViewer?.cleanup();
        pdfViewer = null;
        linkService = null;
        void cleanupDocument();
    }

    function sourceKey(targetUrl: string, credentials: boolean) {
        return `${targetUrl}::${credentials ? 'with-credentials' : 'anon'}`;
    }

    function scheduleHighlightRefresh(pageNumber?: number) {
        if (!browser) {
            return;
        }
        if (typeof pageNumber === 'number') {
            pendingHighlightPages.add(pageNumber);
        }
        if (highlightFrame) {
            return;
        }
        highlightFrame = requestAnimationFrame(() => {
            highlightFrame = null;
            const pages = pendingHighlightPages.size ? [...pendingHighlightPages] : undefined;
            pendingHighlightPages.clear();
            applyHighlights(pages);
        });
    }

    function applyHighlights(targetPages?: number[]) {
        if (!container) {
            return;
        }
        const selector = targetPages?.length
            ? targetPages
                    .map((page) => `.page[data-page-number="${page}"] .textLayer span`)
                    .join(', ')
            : '.page .textLayer span';
        const spans = container.querySelectorAll<HTMLSpanElement>(selector);
        spans.forEach((span) => {
            const baseText = span.dataset.originalText ?? span.textContent ?? '';
            if (!span.dataset.originalText) {
                span.dataset.originalText = baseText;
            }
            let content = baseText;
            for (const highlight of getActiveHighlights()) {
                const updated = applyHighlightToText(content, highlight);
                if (updated !== null) {
                    content = updated;
                }
            }
            span.innerHTML = content;
        });
    }

    function applyHighlightToText(content: string, highlight: PdfHighlight) {
        const term = highlight.term?.trim();
        if (!term) {
            return null;
        }
        const flags = highlight.caseSensitive ? 'g' : 'gi';
        const escaped = escapeRegExp(term);
        const pattern = highlight.exact ? `\\b${escaped}\\b` : escaped;
        const regex = new RegExp(pattern, flags);
        let didMatch = false;
        const color = highlight.color ?? 'var(--pdf-highlight-color, rgba(255, 244, 0, 0.65))';
        const nextContent = content.replace(regex, (match) => {
            didMatch = true;
            return `<mark data-highlight-id="${highlight.id ?? term}" style="background-color:${color};">${match}</mark>`;
        });
        return didMatch ? nextContent : null;
    }

    function escapeRegExp(value: string) {
        return value.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&');
    }

    function handleMouseUp() {
        if (!browser) {
            return;
        }
        const selection = window.getSelection();
        if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
            return;
        }
        const text = selection.toString().trim();
        if (!text) {
            return;
        }
        const range = selection.getRangeAt(0);
        const anchorElement =
            range.startContainer instanceof Element
                ? range.startContainer
                : range.startContainer.parentElement;
        const pageElement = anchorElement?.closest<HTMLElement>('.page');
        if (!pageElement) {
            return;
        }
        const rects = Array.from(range.getClientRects()).map((rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height
        }));
        dispatch('select', { text, pageNumber: Number(pageElement.dataset.pageNumber), rects });
    }

    function getActiveHighlights() {
        const merged: PdfHighlight[] = Array.isArray(highlights) ? [...highlights] : [];
        const term = highlightTerm?.trim();
        if (term) {
            merged.unshift({ id: `single-${term}`, term });
        }
        return merged;
    }

    let pdfRuntimePromise: Promise<{ core: PdfCoreModule; viewer: PdfViewerModule }> | null = null;

    async function ensurePdfRuntime() {
        if (!browser) {
            return null;
        }
        if (!pdfRuntimePromise) {
            pdfRuntimePromise = (async () => {
                const coreModule = await import(/* @vite-ignore */ PDFJS_SCRIPT);
                const core = coreModule as PdfCoreModule;
                core.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_SCRIPT;
                if (typeof globalThis !== 'undefined') {
                    (globalThis as typeof globalThis & { pdfjsLib?: PdfCoreModule }).pdfjsLib = core;
                }
                const viewerModule = await import(/* @vite-ignore */ PDFJS_VIEWER_SCRIPT);
                const viewer = viewerModule as PdfViewerModule;
                return { core, viewer };
            })();
        }
        return pdfRuntimePromise;
    }
</script>

<svelte:head>
	<link rel="stylesheet" href={PDFJS_VIEWER_CSS} crossorigin="anonymous" />
</svelte:head>

<div class="viewer-shell" bind:this={container} aria-live="polite" role="region" aria-label="Visualizador de PDF">
    {#if loading || errorMessage}
        <div class="status-layer" data-variant={errorMessage ? 'error' : 'info'}>
            <p>
                {#if errorMessage}
                    {errorMessage}
                {:else}
                    Carregando PDF…
                {/if}
            </p>
        </div>
    {/if}
    <div class="pdfViewer" bind:this={viewerHost}>
        {#if !browser}
            <p class="status-layer" data-variant="info">Visualização disponível somente no navegador.</p>
        {/if}
    </div>
</div>

<style>
    .viewer-shell {
        position: absolute;
        top: 0;
        right: 0;
        bottom: 0;
        left: 0;
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        min-height: 480px;
        border-radius: 0.75rem;
        border: 1px solid color-mix(in srgb, currentColor 8%, transparent);
        background: var(--pdf-viewer-bg, #f7f7f9);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
        overflow: auto;
        isolation: isolate;
    }

    .viewer-shell :global(.pdfViewer) {
        padding: 1.5rem 0;
        margin: 0 auto;
        width: min(100%, 960px);
    }

    .viewer-shell :global(.page) {
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
        margin: 0 auto 1.5rem;
    }

    .viewer-shell :global(.textLayer) {
        pointer-events: auto;
        user-select: text;
        mix-blend-mode: normal;
    }

    .viewer-shell :global(.textLayer span) {
        cursor: text;
    }

    .viewer-shell :global(canvas) {
        border-radius: 0.25rem;
    }

    :global(.viewer-shell mark) {
        background-color: var(--pdf-highlight-color, rgba(255, 244, 0, 0.65));
        padding: 0 0.08em;
        border-radius: 0.15rem;
    }

    .status-layer {
        position: absolute;
        top: 1rem;
        right: 1rem;
        left: 1rem;
        padding: 0.75rem 1rem;
        background: color-mix(in srgb, var(--pdf-viewer-bg, #f7f7f9) 70%, white);
        border-radius: 0.5rem;
        border: 1px solid color-mix(in srgb, currentColor 12%, transparent);
        font-size: 0.95rem;
        box-shadow: 0 6px 24px rgba(15, 23, 42, 0.1);
        z-index: 2;
    }

    .status-layer[data-variant='error'] {
        color: #b91c1c;
        background: color-mix(in srgb, #fee2e2 60%, white);
        border-color: color-mix(in srgb, #b91c1c 35%, transparent);
    }

    .status-layer[data-variant='info'] {
        color: #1f2937;
    }

    .status-layer p {
        margin: 0;
    }
</style>