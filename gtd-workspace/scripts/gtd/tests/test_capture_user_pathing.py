"""Characterization test: capture.py paths writes to per-user directories.

AGENT_ARCHITECTURE.md Pattern 7 proof point: two humans in the same group chat
write to separate per-user directories; the chat ID (OPENCLAW_CHANNEL_PEER_ID)
never appears as a directory component.

Path structure under test:
    <storage_root>/gtd-agent/users/<OPENCLAW_USER_ID>/parking-lot.jsonl
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_CAPTURE_SCRIPT = Path(__file__).parent.parent / "capture.py"
_PARKING_LOT_FILE = "parking-lot.jsonl"


def _args_json(user_id: str, content: str) -> str:
    return json.dumps({"record": {"record_type": "parking_lot", "content": content}, "user_id": user_id})


def _invoke(
    user_id: str, chat_id: str, content: str, storage_root: Path
) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GTD_STORAGE_ROOT": str(storage_root),
    }
    return subprocess.run(
        [sys.executable, str(_CAPTURE_SCRIPT), _args_json(user_id, content)],
        capture_output=True,
        text=True,
        env=env,
    )


def _user_dir(storage_root: Path, user_id: str) -> Path:
    return storage_root / "gtd-agent" / "users" / user_id


def _jsonl(storage_root: Path, user_id: str) -> Path:
    return _user_dir(storage_root, user_id) / _PARKING_LOT_FILE


def _tree(storage_root: Path) -> str:
    root = storage_root / "gtd-agent"
    if not root.exists():
        return "gtd-agent/ absent"
    return str(sorted(str(p.relative_to(storage_root)) for p in root.rglob("*")))


@pytest.fixture(scope="class")
def shared_storage(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("capture_pathing")


class TestCaptureUserPathing:
    """Two users, one chat — writes must key on OPENCLAW_USER_ID, not OPENCLAW_CHANNEL_PEER_ID."""

    def test_a_alpha_writes_to_alpha_dir(self, shared_storage: Path) -> None:
        result = _invoke("alpha", "group-123", "parking lot item alpha", shared_storage)

        assert result.returncode == 0, (
            f"capture.py exited {result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

        alpha_jsonl = _jsonl(shared_storage, "alpha")
        assert alpha_jsonl.exists(), (
            f"Expected {alpha_jsonl} — not found.\n"
            f"Actual tree: {_tree(shared_storage)}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

        lines = alpha_jsonl.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["content"] == "parking lot item alpha"
        assert record["source"] == "telegram"
        assert record["telegram_chat_id"] == "alpha"

        assert not _user_dir(shared_storage, "group-123").exists(), (
            f"group-123 directory must not exist; actual tree: {_tree(shared_storage)}"
        )

    def test_b_beta_writes_to_beta_dir_alpha_unchanged(self, shared_storage: Path) -> None:
        result = _invoke("beta", "group-123", "parking lot item beta", shared_storage)

        assert result.returncode == 0, (
            f"capture.py exited {result.returncode}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )

        beta_jsonl = _jsonl(shared_storage, "beta")
        assert beta_jsonl.exists(), (
            f"Expected {beta_jsonl} — not found.\n"
            f"Actual tree: {_tree(shared_storage)}\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        beta_lines = beta_jsonl.read_text().splitlines()
        assert len(beta_lines) == 1
        beta_record = json.loads(beta_lines[0])
        assert beta_record["content"] == "parking lot item beta"

        alpha_jsonl = _jsonl(shared_storage, "alpha")
        assert alpha_jsonl.exists(), "Alpha's file absent — shared_storage not shared correctly"
        alpha_lines = alpha_jsonl.read_text().splitlines()
        assert len(alpha_lines) == 1, (
            f"Alpha line count changed after beta's write: "
            f"expected 1, got {len(alpha_lines)}"
        )

        assert not _user_dir(shared_storage, "group-123").exists(), (
            f"group-123 directory must not exist after beta's write; "
            f"actual tree: {_tree(shared_storage)}"
        )
