"""Small test doubles for generation components exercised independently."""

from collections.abc import Iterator
from contextlib import contextmanager

from kb.generation import VerifiedVectorCommit


class AcceptingVectorCommitVerifier:
    """Treat structurally valid commits as present for SQLite-only unit tests."""

    def verify_commit(self, commit: VerifiedVectorCommit) -> None:
        assert isinstance(commit, VerifiedVectorCommit)

    def require_unchanged(self, commit: VerifiedVectorCommit) -> None:
        assert isinstance(commit, VerifiedVectorCommit)

    @contextmanager
    def hold_commit(self, commit: VerifiedVectorCommit) -> Iterator[None]:
        self.require_unchanged(commit)
        yield
