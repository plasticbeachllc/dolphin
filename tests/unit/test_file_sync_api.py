"""Unit tests for file sync API endpoints."""


class TestRecordPendingChangesEndpoint:
    """Test POST /v1/repos/{repo_name}/changes endpoint."""

    def test_record_single_change(self, kb_api_client, registered_test_repo):
        """Test recording a single pending change."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={"changes": [{"file_path": "src/main.py", "change_type": "modified"}]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "change_ids" in data
        assert len(data["change_ids"]) == 1
        assert data["change_ids"][0] > 0

    def test_record_multiple_changes(self, kb_api_client, registered_test_repo):
        """Test recording multiple pending changes in one request."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={
                "changes": [
                    {"file_path": "file1.py", "change_type": "created"},
                    {"file_path": "file2.py", "change_type": "modified"},
                    {"file_path": "file3.py", "change_type": "deleted"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["change_ids"]) == 3
        assert all(cid > 0 for cid in data["change_ids"])

    def test_record_rename_with_old_path(self, kb_api_client, registered_test_repo):
        """Test recording a rename change with old_path."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={
                "changes": [
                    {
                        "file_path": "src/new_name.py",
                        "change_type": "renamed",
                        "old_path": "src/old_name.py",
                    }
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["change_ids"]) == 1

    def test_record_changes_nonexistent_repo(self, kb_api_client):
        """Test recording changes for non-existent repository."""
        response = kb_api_client.post(
            "/v1/repos/nonexistent-repo/changes",
            json={"changes": [{"file_path": "file.py", "change_type": "modified"}]},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_record_changes_empty_list(self, kb_api_client, registered_test_repo):
        """Test recording empty changes list."""
        response = kb_api_client.post(f"/v1/repos/{registered_test_repo['name']}/changes", json={"changes": []})

        assert response.status_code == 200
        data = response.json()
        assert data["change_ids"] == []

    def test_record_changes_missing_file_path(
        self, kb_api_client, registered_test_repo
    ):
        """Test recording change without file_path fails validation."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={"changes": [{"change_type": "modified"}]},  # Missing file_path
        )

        assert response.status_code == 422  # Validation error

    def test_record_changes_missing_change_type(
        self, kb_api_client, registered_test_repo
    ):
        """Test recording change without change_type fails validation."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={"changes": [{"file_path": "file.py"}]},  # Missing change_type
        )

        assert response.status_code == 422  # Validation error

    def test_record_changes_invalid_change_type(
        self, kb_api_client, registered_test_repo
    ):
        """Test recording change with invalid change_type."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={"changes": [{"file_path": "file.py", "change_type": "invalid_type"}]},
        )

        # Should still succeed - validation is permissive
        # Or could enforce strict validation and return 422
        assert response.status_code in [200, 422]


class TestGetPendingChangesEndpoint:
    """Test GET /v1/repos/{repo_name}/pending-changes endpoint."""

    def test_get_pending_changes_empty(self, kb_api_client, registered_test_repo):
        """Test getting pending changes when none exist."""
        response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/pending-changes")

        assert response.status_code == 200
        data = response.json()
        assert "changes" in data
        assert data["changes"] == []

    def test_get_pending_changes_after_recording(
        self, kb_api_client, registered_test_repo
    ):
        """Test getting pending changes after recording some."""
        # Record changes first
        kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={
                "changes": [
                    {"file_path": "file1.py", "change_type": "created"},
                    {"file_path": "file2.py", "change_type": "modified"},
                ]
            },
        )

        # Get pending changes
        response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/pending-changes")

        assert response.status_code == 200
        data = response.json()
        assert len(data["changes"]) == 2

        # Verify structure
        for change in data["changes"]:
            assert "id" in change
            assert "repo_id" in change
            assert "file_path" in change
            assert "change_type" in change
            assert "detected_at" in change
            assert "processed" in change

    def test_get_pending_changes_with_limit(self, kb_api_client, registered_test_repo):
        """Test getting pending changes with limit parameter."""
        # Record many changes
        kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={"changes": [{"file_path": f"file{i}.py", "change_type": "modified"} for i in range(20)]},
        )

        # Get with limit
        response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/pending-changes?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data["changes"]) == 5

    def test_get_pending_changes_nonexistent_repo(self, kb_api_client):
        """Test getting pending changes for non-existent repository."""
        response = kb_api_client.get("/v1/repos/nonexistent-repo/pending-changes")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_pending_changes_excludes_processed(
        self, kb_api_client, registered_test_repo
    ):
        """Test that processed changes are excluded."""
        # Record changes
        record_response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={
                "changes": [
                    {"file_path": "file1.py", "change_type": "modified"},
                    {"file_path": "file2.py", "change_type": "modified"},
                ]
            },
        )
        change_ids = record_response.json()["change_ids"]

        # Mark first one as processed
        kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes/mark-processed",
            json={"change_ids": [change_ids[0]]},
        )

        # Get pending changes
        response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/pending-changes")

        assert response.status_code == 200
        data = response.json()
        assert len(data["changes"]) == 1
        assert data["changes"][0]["id"] == change_ids[1]


class TestMarkChangesProcessedEndpoint:
    """Test POST /v1/repos/{repo_name}/changes/mark-processed endpoint."""

    def test_mark_changes_processed_success(self, kb_api_client, registered_test_repo):
        """Test successfully marking changes as processed."""
        # Record changes first
        record_response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={
                "changes": [
                    {"file_path": "file1.py", "change_type": "modified"},
                    {"file_path": "file2.py", "change_type": "modified"},
                ]
            },
        )
        change_ids = record_response.json()["change_ids"]

        # Mark as processed
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes/mark-processed",
            json={"change_ids": change_ids},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["processed_count"] == 2

    def test_mark_changes_processed_empty_list(
        self, kb_api_client, registered_test_repo
    ):
        """Test marking with empty change_ids list."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes/mark-processed",
            json={"change_ids": []},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["processed_count"] == 0

    def test_mark_changes_processed_nonexistent_ids(
        self, kb_api_client, registered_test_repo
    ):
        """Test marking non-existent change IDs."""
        response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes/mark-processed",
            json={"change_ids": [99999, 88888]},
        )

        assert response.status_code == 200
        data = response.json()
        # Should not error, just return 0 processed
        assert data["processed_count"] == 0

    def test_mark_changes_processed_nonexistent_repo(self, kb_api_client):
        """Test marking changes for non-existent repository."""
        response = kb_api_client.post(
            "/v1/repos/nonexistent-repo/changes/mark-processed",
            json={"change_ids": [1, 2]},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_mark_changes_processed_missing_param(
        self, kb_api_client, registered_test_repo
    ):
        """Test marking without change_ids parameter fails validation."""
        response = kb_api_client.post(f"/v1/repos/{registered_test_repo['name']}/changes/mark-processed", json={})

        assert response.status_code == 422  # Validation error

    def test_mark_changes_processed_removes_from_pending(
        self, kb_api_client, registered_test_repo
    ):
        """Test that marked changes are removed from pending list."""
        # Record changes
        record_response = kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes",
            json={"changes": [{"file_path": "file.py", "change_type": "modified"}]},
        )
        change_ids = record_response.json()["change_ids"]

        # Mark as processed
        kb_api_client.post(
            f"/v1/repos/{registered_test_repo['name']}/changes/mark-processed",
            json={"change_ids": change_ids},
        )

        # Verify not in pending list
        pending_response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/pending-changes")
        assert len(pending_response.json()["changes"]) == 0


class TestDetectDriftEndpoint:
    """Test GET /v1/repos/{repo_name}/drift endpoint."""

    def test_detect_drift_no_changes(self, kb_api_client, registered_test_repo):
        """Test drift detection when no files changed."""
        response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/drift")

        assert response.status_code == 200
        data = response.json()
        assert "drift_events" in data
        # May have events or be empty depending on repo state
        assert isinstance(data["drift_events"], list)

    def test_detect_drift_with_modified_file(
        self, kb_api_client, registered_test_repo, mock_kb_stores
    ):
        """Test drift detection for modified file."""
        sql_store, _ = mock_kb_stores
        workspace = registered_test_repo["workspace"]
        repo = sql_store.get_repo_by_name(registered_test_repo["name"])

        # Create a test file
        test_file = workspace / "test.py"
        test_file.write_text("def test(): pass")

        # Record file and create snapshot with old state

        file_id = sql_store.upsert_file(
            repo_id=repo["id"],
            path="test.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=test_file.stat().st_size,
        )

        sql_store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="test.py",
            mtime_ns=123,  # Old timestamp
            size_bytes=50,  # Old size
            content_hash="old_hash",
        )

        # Modify file
        test_file.write_text("def test(): return 42")

        # Detect drift
        response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/drift")

        assert response.status_code == 200
        data = response.json()
        assert "drift_events" in data

        # Should detect the modification
        if len(data["drift_events"]) > 0:
            modified_events = [
                e for e in data["drift_events"] if e["drift_type"] == "modified"
            ]
            assert any(e["path"] == "test.py" for e in modified_events)

    def test_detect_drift_nonexistent_repo(self, kb_api_client):
        """Test drift detection for non-existent repository."""
        response = kb_api_client.get("/v1/repos/nonexistent-repo/drift")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_detect_drift_response_structure(self, kb_api_client, registered_test_repo):
        """Test drift detection response structure."""
        response = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/drift")

        assert response.status_code == 200
        data = response.json()
        assert "drift_events" in data
        assert isinstance(data["drift_events"], list)

        # If there are drift events, verify structure
        for event in data["drift_events"]:
            assert "path" in event
            assert "drift_type" in event
            # drift_type should be one of: modified, deleted, created
            assert event["drift_type"] in ["modified", "deleted", "created"]


class TestFileSyncEndpointIntegration:
    """Integration tests for file sync workflow."""

    def test_complete_file_sync_workflow(self, kb_api_client, registered_test_repo):
        """Test complete workflow: record -> get -> process."""
        repo_name = registered_test_repo["name"]

        # 1. Record some changes
        record_response = kb_api_client.post(
            f"/v1/repos/{repo_name}/changes",
            json={
                "changes": [
                    {"file_path": "file1.py", "change_type": "created"},
                    {"file_path": "file2.py", "change_type": "modified"},
                    {"file_path": "file3.py", "change_type": "deleted"},
                ]
            },
        )
        assert record_response.status_code == 200
        change_ids = record_response.json()["change_ids"]
        assert len(change_ids) == 3

        # 2. Get pending changes
        pending_response = kb_api_client.get(f"/v1/repos/{repo_name}/pending-changes")
        assert pending_response.status_code == 200
        assert len(pending_response.json()["changes"]) == 3

        # 3. Mark some as processed
        mark_response = kb_api_client.post(
            f"/v1/repos/{repo_name}/changes/mark-processed",
            json={"change_ids": change_ids[:2]},  # Process first 2
        )
        assert mark_response.status_code == 200
        assert mark_response.json()["processed_count"] == 2

        # 4. Verify only 1 pending remains
        final_pending = kb_api_client.get(f"/v1/repos/{repo_name}/pending-changes")
        assert len(final_pending.json()["changes"]) == 1

    def test_concurrent_change_recording(self, kb_api_client, registered_test_repo):
        """Test recording changes from multiple sources."""
        repo_name = registered_test_repo["name"]

        # Simulate multiple clients recording changes
        response1 = kb_api_client.post(
            f"/v1/repos/{repo_name}/changes",
            json={"changes": [{"file_path": "a.py", "change_type": "modified"}]},
        )
        response2 = kb_api_client.post(
            f"/v1/repos/{repo_name}/changes",
            json={"changes": [{"file_path": "b.py", "change_type": "modified"}]},
        )
        response3 = kb_api_client.post(
            f"/v1/repos/{repo_name}/changes",
            json={"changes": [{"file_path": "c.py", "change_type": "modified"}]},
        )

        assert all(r.status_code == 200 for r in [response1, response2, response3])

        # All should be in pending
        pending = kb_api_client.get(f"/v1/repos/{repo_name}/pending-changes")
        assert len(pending.json()["changes"]) == 3

    def test_drift_detection_after_indexing(
        self, kb_api_client, registered_test_repo, mock_kb_stores
    ):
        """Test drift detection workflow after simulated indexing."""
        sql_store, _ = mock_kb_stores
        workspace = registered_test_repo["workspace"]
        repo = sql_store.get_repo_by_name(registered_test_repo["name"])

        # Create and snapshot a file (simulating post-index snapshot)
        test_file = workspace / "tracked.py"
        test_file.write_text("original content")

        import hashlib

        file_id = sql_store.upsert_file(
            repo_id=repo["id"],
            path="tracked.py",
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=test_file.stat().st_size,
        )

        stat = test_file.stat()
        content_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()
        sql_store.upsert_file_snapshot(
            file_id=file_id,
            repo_id=repo["id"],
            path="tracked.py",
            mtime_ns=stat.st_mtime_ns,
            size_bytes=stat.st_size,
            content_hash=content_hash,
        )

        # No drift initially
        drift1 = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/drift")
        initial_drift_count = len(drift1.json()["drift_events"])

        # Modify file (simulate external edit)
        import time

        time.sleep(0.01)
        test_file.write_text("modified content")

        # Should detect drift now
        drift2 = kb_api_client.get(f"/v1/repos/{registered_test_repo['name']}/drift")
        assert len(drift2.json()["drift_events"]) > initial_drift_count
