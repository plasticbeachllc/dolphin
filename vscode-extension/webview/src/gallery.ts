import './app.css';
import { mount } from 'svelte';
import ThemeGallery from './ThemeGallery.svelte';

let app: ReturnType<typeof mount>;

// Ensure DOM is ready before mounting
if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', () => {
		app = mount(ThemeGallery, {
			target: document.getElementById('app')!
		});
	});
} else {
	app = mount(ThemeGallery, {
		target: document.getElementById('app')!
	});
}

export default app;