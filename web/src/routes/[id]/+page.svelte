<script>
	import { page } from '$app/state';
	import PdfViewer from '$lib/components/pdf-viewer.svelte';

	const emphasis = 'isolamento social';
</script>

<div>{page.params.id}</div>

<PdfViewer url='pl_example.pdf' highlightTerm={emphasis} />
