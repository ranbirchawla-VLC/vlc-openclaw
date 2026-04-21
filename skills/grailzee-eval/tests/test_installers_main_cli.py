"""End-to-end CLI tests for the six Phase A installers.

The per-installer ``test_install_*.py`` files exercise the ``install()``
function directly. This suite covers the argparse layer above it:
``--help``, ``--dry-run`` with default target resolution, ``--force``
against missing and existing targets, and unknown-flag error handling.

Every test is parametrized across the six installers via
``INSTALLER_SPECS`` in ``_installer_main_helpers`` so a single TestMain
body provides coverage for all six scripts.
"""

from __future__ import annotations

import json

import pytest

from tests._installer_main_helpers import (
    INSTALLER_SPECS,
    patch_default_root,
    run_main,
)


@pytest.mark.parametrize(
    "spec",
    INSTALLER_SPECS,
    ids=[s["id"] for s in INSTALLER_SPECS],
)
class TestMain:
    def test_help_exits_zero(self, spec, monkeypatch, capsys):
        """``--help`` prints argparse usage and exits 0.

        argparse signals success with SystemExit(0); we catch and
        assert on the code rather than the return value.
        """
        with pytest.raises(SystemExit) as exc:
            run_main(monkeypatch, spec["module"], ["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "--target" in out
        assert "--force" in out
        assert "--dry-run" in out

    def test_dry_run_with_default_target_does_not_write(
        self, spec, monkeypatch, tmp_path
    ):
        """``--dry-run`` without ``--target`` resolves the installer's
        default target path and exits 0 without writing to it.

        We monkey-patch the default-target root (WORKSPACE_STATE_PATH
        for workspace installers, the installer's own STATE_PATH for
        Drive installers) so the resolved default lands inside tmp_path
        rather than the real Drive/state directory.
        """
        default_target = patch_default_root(monkeypatch, spec, tmp_path)
        assert not default_target.exists()

        rc = run_main(monkeypatch, spec["module"], ["--dry-run"])
        assert rc == 0
        assert not default_target.exists()

    def test_force_fresh_install_writes_factory_config(
        self, spec, monkeypatch, tmp_path
    ):
        """``--force`` on a missing target writes the factory config.

        Explicit ``--target`` keeps this test hermetic regardless of
        how default resolution behaves.
        """
        target = tmp_path / spec["default_name"]
        assert not target.exists()

        rc = run_main(
            monkeypatch, spec["module"],
            ["--target", str(target), "--force"],
        )
        assert rc == 0
        assert target.exists()

        parsed = json.loads(target.read_text())
        assert parsed["schema_version"] == 1
        assert parsed["updated_by"] == "phase_a_install"

    def test_force_overwrites_existing_target(
        self, spec, monkeypatch, tmp_path
    ):
        """``--force`` replaces the contents of an existing target.

        Pre-write a sentinel JSON so we can prove overwrite (not merge).
        """
        target = tmp_path / spec["default_name"]
        target.write_text(json.dumps(
            {"schema_version": 1, "sentinel": "pre-overwrite"}
        ))

        rc = run_main(
            monkeypatch, spec["module"],
            ["--target", str(target), "--force"],
        )
        assert rc == 0

        parsed = json.loads(target.read_text())
        assert "sentinel" not in parsed
        assert parsed["updated_by"] == "phase_a_install"

    def test_unknown_flag_raises_argparse_error(
        self, spec, monkeypatch, capsys
    ):
        """A bogus flag surfaces as argparse SystemExit(2).

        None of the installers take required positional args, so an
        unknown flag stands in for the generic 'bad CLI invocation'
        guard the task spec calls for.
        """
        with pytest.raises(SystemExit) as exc:
            run_main(monkeypatch, spec["module"], ["--no-such-flag"])
        assert exc.value.code == 2
