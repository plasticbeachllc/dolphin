import './app.css';
import { mount } from 'svelte';
import App from './App.svelte';

let app: ReturnType<typeof mount>;

// Ensure DOM is ready before mounting
if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', () => {
		app = mount(App, {
			target: document.getElementById('app')!
		});
	});
} else {
	app = mount(App, {
		target: document.getElementById('app')!
	});
}

export default app;