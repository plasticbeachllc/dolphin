"""Unit tests for Svelte chunker.

Tests cover:
- Basic Svelte component structure
- Script, style, and template sections
- Component imports and usage
- Props and stores
- Graph extraction (nodes and edges)
"""

from kb.chunkers.svelte_chunker import chunk_source, extract_graph_data


class TestBasicSvelteChunking:
    """Test chunking of basic Svelte components."""

    def test_chunk_simple_component(self):
        """Test chunking basic Svelte component."""
        source = """
        <script>
            export let name;
            let count = 0;

            function increment() {
                count += 1;
            }
        </script>

        <button on:click={increment}>
            Clicks: {count}
        </button>

        <style>
            button { color: blue; }
        </style>
        """
        chunks = chunk_source(source)
        assert len(chunks) >= 2  # At least script + template (+ maybe style)

        # Check for script chunks
        script_chunks = [c for c in chunks if "script" in str(c.symbol_kind)]
        assert len(script_chunks) > 0

    def test_chunk_with_module_script(self):
        """Test component with module context script."""
        source = """
        <script context="module">
            export const API_URL = "/api";
        </script>

        <script>
            export let userId;
            let user = null;
        </script>

        <div>{user?.name}</div>
        """
        chunks = chunk_source(source)

        # Should have both module and instance script chunks
        module_chunks = [c for c in chunks if "module" in str(c.symbol_kind)]
        assert len(module_chunks) > 0

    def test_chunk_script_section(self):
        """Test extraction of script section."""
        source = """
        <script>
            import Component from './Component.svelte';

            export let title = "Default";
            let items = [];

            async function loadItems() {
                items = await fetch('/api/items').then(r => r.json());
            }
        </script>
        """
        chunks = chunk_source(source)

        # Should extract script chunks
        assert len(chunks) > 0
        script_chunks = [c for c in chunks if "script" in str(c.symbol_kind)]
        assert len(script_chunks) > 0

    def test_chunk_style_section(self):
        """Test extraction of style section."""
        source = """
        <script>
            export let color = "blue";
        </script>

        <div>Styled content</div>

        <style>
            div {
                color: var(--color);
                padding: 1rem;
            }
        </style>
        """
        chunks = chunk_source(source)

        # Should have style chunk
        style_chunks = [c for c in chunks if "style" in str(c.symbol_kind)]
        assert len(style_chunks) == 1

    def test_chunk_template_section(self):
        """Test extraction of template section."""
        source = """
        <script>
            let items = [1, 2, 3];
        </script>

        <div>
            {#each items as item}
                <p>{item}</p>
            {/each}
        </div>
        """
        chunks = chunk_source(source)

        # Should have template chunk
        template_chunks = [c for c in chunks if "template" in str(c.symbol_kind)]
        assert len(template_chunks) > 0


class TestSvelteFeatures:
    """Test Svelte-specific features."""

    def test_chunk_with_props(self):
        """Test component with exported props."""
        source = """
        <script>
            export let name;
            export let age = 0;
            export let email;
        </script>

        <div>
            <p>Name: {name}</p>
            <p>Age: {age}</p>
            <p>Email: {email}</p>
        </div>
        """
        chunks = chunk_source(source)
        assert len(chunks) > 0

        # Script should contain prop declarations
        script_text = "".join(c.text for c in chunks if "script" in str(c.symbol_kind))
        assert "export let name" in script_text

    def test_chunk_with_stores(self):
        """Test component using stores."""
        source = """
        <script>
            import { writable } from 'svelte/store';
            import { userStore } from './stores';

            const count = writable(0);

            function increment() {
                $count += 1;
            }
        </script>

        <div>Count: {$count}</div>
        <div>User: {$userStore.name}</div>
        """
        chunks = chunk_source(source)
        assert len(chunks) > 0

    def test_chunk_with_reactive_statements(self):
        """Test component with reactive statements."""
        source = """
        <script>
            let count = 0;
            $: doubled = count * 2;
            $: {
                console.log('count changed:', count);
            }
        </script>

        <div>
            <p>Count: {count}</p>
            <p>Doubled: {doubled}</p>
        </div>
        """
        chunks = chunk_source(source)
        assert len(chunks) > 0

    def test_chunk_with_events(self):
        """Test component with event dispatching."""
        source = """
        <script>
            import { createEventDispatcher } from 'svelte';

            const dispatch = createEventDispatcher();

            function handleClick() {
                dispatch('message', { text: 'Hello' });
            }
        </script>

        <button on:click={handleClick}>Send</button>
        """
        chunks = chunk_source(source)
        assert len(chunks) > 0


class TestGraphExtraction:
    """Test graph data extraction from Svelte components."""

    def test_extract_component_node(self):
        """Test extracting component node."""
        source = """
        <script>
            export let name;
        </script>
        <div>Hello {name}</div>
        """
        nodes, edges = extract_graph_data(source, "MyComponent")

        # Should have component node
        assert len(nodes) >= 1
        assert nodes[0].node_type == "svelte_component"
        assert nodes[0].name == "MyComponent"

    def test_extract_imports(self):
        """Test extracting import edges."""
        source = """
        <script>
            import Button from './Button.svelte';
            import { Modal } from './Modal.svelte';
            import * as utils from './utils';
        </script>
        """
        nodes, edges = extract_graph_data(source, "MyComponent")

        # Should have import edges
        import_edges = [e for e in edges if e.edge_type == "imports"]
        assert len(import_edges) >= 2

        edge_targets = [e.target_name for e in import_edges]
        assert "Button" in edge_targets
        assert "Modal" in edge_targets

    def test_extract_component_usage(self):
        """Test extracting component usage edges."""
        source = """
        <script>
            import Button from './Button.svelte';
            import Card from './Card.svelte';
        </script>

        <Card>
            <Button>Click me</Button>
            <Button variant="secondary">Cancel</Button>
        </Card>
        """
        nodes, edges = extract_graph_data(source, "MyComponent")

        # Should have component usage edges
        usage_edges = [e for e in edges if e.edge_type == "uses_component"]
        assert len(usage_edges) >= 2

        edge_targets = [e.target_name for e in usage_edges]
        assert "Button" in edge_targets
        assert "Card" in edge_targets

    def test_extract_props(self):
        """Test extracting prop nodes and edges."""
        source = """
        <script>
            export let title;
            export let subtitle = "";
            export let count = 0;
        </script>

        <div>
            <h1>{title}</h1>
            <h2>{subtitle}</h2>
        </div>
        """
        nodes, edges = extract_graph_data(source, "MyComponent")

        # Should have prop nodes
        prop_nodes = [n for n in nodes if n.node_type == "prop"]
        assert len(prop_nodes) >= 3

        prop_names = [n.name for n in prop_nodes]
        assert "title" in prop_names
        assert "subtitle" in prop_names
        assert "count" in prop_names

        # Should have accepts_prop edges
        prop_edges = [e for e in edges if e.edge_type == "accepts_prop"]
        assert len(prop_edges) >= 3

    def test_extract_store_subscriptions(self):
        """Test extracting store subscription edges."""
        source = """
        <script>
            import { userStore, settingsStore } from './stores';

            let userName = $userStore.name;
        </script>

        <div>
            User: {$userStore.name}
            Theme: {$settingsStore.theme}
        </div>
        """
        nodes, edges = extract_graph_data(source, "MyComponent")

        # Should have store subscription edges
        sub_edges = [e for e in edges if e.edge_type == "subscribes_to"]
        assert len(sub_edges) >= 2

        edge_targets = [e.target_name for e in sub_edges]
        assert "userStore" in edge_targets
        assert "settingsStore" in edge_targets

    def test_extract_event_dispatches(self):
        """Test extracting event dispatch edges."""
        source = """
        <script>
            import { createEventDispatcher } from 'svelte';
            const dispatch = createEventDispatcher();

            function handleSubmit() {
                dispatch('submit', { data });
            }

            function handleCancel() {
                dispatch('cancel');
            }
        </script>
        """
        nodes, edges = extract_graph_data(source, "MyComponent")

        # Should have event dispatch edges
        event_edges = [e for e in edges if e.edge_type == "dispatches_event"]
        assert len(event_edges) >= 2

        edge_targets = [e.target_name for e in event_edges]
        assert "submit" in edge_targets
        assert "cancel" in edge_targets


class TestComplexComponents:
    """Test chunking of complex Svelte components."""

    def test_chunk_large_component(self):
        """Test chunking large component with many functions."""
        # Create a large script section
        functions = [f"function func{i}() {{ return {i}; }}" for i in range(20)]
        source = f"""
        <script>
            export let data;

            {chr(10).join(functions)}
        </script>

        <div>Content</div>
        """

        chunks = chunk_source(source, token_target=200)
        assert len(chunks) >= 1

    def test_chunk_with_multiple_sections(self):
        """Test component with multiple script/style sections."""
        source = """
        <script context="module">
            export const preload = async () => {
                return { data: await fetchData() };
            };
        </script>

        <script>
            export let data;
            let processed = processData(data);
        </script>

        <div>{processed}</div>

        <style>
            div { padding: 1rem; }
        </style>
        """

        chunks = chunk_source(source)

        # Should have chunks from both scripts
        module_chunks = [c for c in chunks if "module" in str(c.symbol_kind)]
        script_chunks = [
            c
            for c in chunks
            if "script" in str(c.symbol_kind) and "module" not in str(c.symbol_kind)
        ]

        assert len(module_chunks) > 0
        assert len(script_chunks) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_component(self):
        """Test chunking empty component."""
        assert chunk_source("") == []
        assert chunk_source("   \n  \n  ") == []

    def test_component_with_only_template(self):
        """Test component with no script or style."""
        source = """
        <div>
            <h1>Static Content</h1>
            <p>No JavaScript needed</p>
        </div>
        """
        chunks = chunk_source(source)
        assert len(chunks) >= 1

        # Should have template chunks
        template_chunks = [c for c in chunks if "template" in str(c.symbol_kind)]
        assert len(template_chunks) > 0

    def test_component_with_only_script(self):
        """Test component with no template."""
        source = """
        <script>
            export const API_URL = "/api";
            export function helper() {
                return "helper";
            }
        </script>
        """
        chunks = chunk_source(source)
        assert len(chunks) >= 1

    def test_malformed_component(self):
        """Test handling of malformed component (fallback)."""
        source = """
        <script
            // Unclosed script tag
            export let broken;

        <div>Content</div>
        """
        # Should fall back to simple chunking
        chunks = chunk_source(source)
        assert len(chunks) >= 1

    def test_line_number_tracking(self):
        """Test accurate line number tracking."""
        source = """<script>
export let name;
let count = 0;
</script>

<div>
    <p>Name: {name}</p>
    <p>Count: {count}</p>
</div>

<style>
div { padding: 1rem; }
</style>
"""
        chunks = chunk_source(source)

        # Chunks should have reasonable line numbers
        for chunk in chunks:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
            assert chunk.start_line <= source.count("\n") + 1
