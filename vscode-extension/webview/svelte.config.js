import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		// Use static adapter for VS Code webview
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: 'index.html',
			precompress: false,
			strict: false
		}),
		// Set base path for VS Code webview
		paths: {
			base: '',
			relative: true
		},
		// Path aliases - moved from tsconfig.json per SvelteKit recommendations
		alias: {
			'@shared': '../../shared'
		}
	}
};

export default config;
