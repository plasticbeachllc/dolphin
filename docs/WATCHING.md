MEMORANDUM

TO: Code Architect FROM: Gemini DATE: January 24, 2026 SUBJECT: Implementation Strategy for watchfiles Integration in Dolphin kb/ Module

1. Executive Summary
To satisfy the requirement for a resilient, uv pip install-compatible distribution model without external binary dependencies (such as watchexec or watchman), we recommend integrating the watchfiles library into the Dolphin kb module.

watchfiles provides high-performance file watching backed by the Rust notify crate, packaged as a standard Python wheel. This approach allows us to decouple change detection from the current Git-based polling mechanism found in kb/ingest/pipeline.py while maintaining zero external system dependencies.

2. Technical Overview: What is watchfiles?
watchfiles is a Python binding for the Rust notify crate. It utilizes low-level OS file system APIs (e.g., inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows) to detect changes efficiently.

Key Advantages for Dolphin:

Zero External Dependencies: It installs as a standard Python library via uv or pip, eliminating the need for users to manually install tools like watchexec or watchman.

Async Native: It exposes an asynchronous iterator (awatch) that integrates naturally with Python's asyncio loop, effectively acting as a non-blocking queue.

Built-in Debouncing: It natively handles "noisy" file system events (e.g., rapid-fire touch, write, close sequences) by grouping them into batches, preventing redundant indexing cycles.

3. Integration Plan
The integration requires modifications across dependency management, the CLI, and the ingestion pipeline to support an event-driven workflow alongside the existing Git-based workflow.

A. Dependency Management
We must add watchfiles to the project dependencies to ensure it is installed alongside the application.

Target File: plasticbeachllc/dolphin/dolphin-develop/pyproject.toml

Action: Append "watchfiles>=0.21.0" to the dependencies list.

B. Pipeline Refactoring (Crucial)
Currently, IngestionPipeline.index is tightly coupled to Git for change detection via git_changed_files_modified_added and git_changed_files_deleted. We must extract the core processing logic into a reusable method that accepts an explicit list of file paths.

Target File: plasticbeachllc/dolphin/dolphin-develop/kb/ingest/pipeline.py

Action: Refactor the processing loop inside index() into a new public method, e.g., process_batch(self, files: list[Path]).

Current State: index() determines changed_files via internal _git calls.

New State: index() will still call _git for the CLI command, but the new process_batch method will allow the watcher to inject files directly.

Benefit: This ensures that both dolphin kb index (Git-based) and dolphin kb watch (Real-time) use the exact same logic for chunking, deduplication, and vector upsertion.

C. New Watcher Module
We require a new module to host the persistent watcher loop. This module will serve as the bridge between the OS file system events and the Dolphin pipeline.

Proposed File: kb/ingest/watcher.py

Responsibility:

Initialize the IngestionPipeline.

Load ignore patterns using kb.config.KBConfig.ignore to prevent the watcher from triggering on irrelevant files (e.g., .git, __pycache__, node_modules).

Execute the awatch loop to consume events and pass them to the pipeline.

Implementation Sketch:

Python

import asyncio
from pathlib import Path
from watchfiles import awatch, Change
from kb.ingest.pipeline import IngestionPipeline
from kb.config import KBConfig

async def watch_repo(repo_name: str, pipeline: IngestionPipeline, config: KBConfig):
    repo = pipeline.metadata.get_repo_by_name(repo_name)
    root_path = Path(repo["root_path"])
    
    # Use micro-sessions per batch for data safety
    print(f"🐬 Dolphin Watcher started for {repo_name} at {root_path}")
    
    # awatch handles the queueing and debouncing (default 1.6s)
    async for changes in awatch(root_path, debounce=1600, step=500):
        files_to_process = []
        files_to_delete = []

        for change_type, path_str in changes:
            path = Path(path_str)
            # Filter based on ignore patterns (simplified)
            if any(part.startswith('.') for part in path.parts):
                 continue

            if change_type in {Change.added, Change.modified}:
                files_to_process.append(path)
            elif change_type == Change.deleted:
                files_to_delete.append(path)
        
        if files_to_process or files_to_delete:
            print(f"Detected changes: {len(files_to_process)} modified, {len(files_to_delete)} deleted")
            
            # Call the refactored pipeline methods
            if files_to_process:
                pipeline.process_batch(files_to_process, repo_id=repo['id'])
            if files_to_delete:
                pipeline.process_deletions(files_to_delete, repo_id=repo['id'])
D. CLI Entry Point
We must expose the watcher functionality to the user via the CLI.

Target File: plasticbeachllc/dolphin/dolphin-develop/kb/cli.py

Action: Add a watch command to the kb_app Typer group.

Proposed Signature:

Python

@kb_app.command()
def watch(
    name: str = typer.Argument(..., help="Repository name to watch."),
) -> None:
    """Start a persistent file watcher for real-time indexing."""
    import asyncio
    from kb.ingest.watcher import watch_repo
    
    # ... resolve config and pipeline ...
    # This mirrors the setup in kb_index but enters a persistent loop
    
    try:
        asyncio.run(watch_repo(name, pipeline, config))
    except KeyboardInterrupt:
        print("Watcher stopped.")
4. Handling Queueing and Concurrency
The requirement explicitly requested "queueing changes." watchfiles handles the raw OS event queue, but we must manage the application-level processing to ensure data consistency.

Implicit Queueing: The async for loop in awatch acts as the primary queue consumer. It yields a batch of changes that occurred during the debounce window.

Session Management:

The IngestionPipeline manages sessions via metadata.begin_session.

Recommendation: Wrap each batch processing cycle in a short-lived "incremental" session. This ensures that if the watcher crashes or is interrupted, we have a distinct record of which files were successfully indexed in that specific batch, without leaving a long-running "zombie" session open.

5. Next Steps
Refactor: Extract the file processing logic from IngestionPipeline.index in kb/ingest/pipeline.py.

Install: Add watchfiles to pyproject.toml.

Implement: Create kb/ingest/watcher.py utilizing the IncrementalIndexer logic to verify file hashes before aggressive processing.

Expose: Add the watch command to kb/cli.py.
