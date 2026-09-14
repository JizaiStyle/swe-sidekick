from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sidekick-install-test-")
        self.home = (Path(self.tmp.name) / "home with spaces").resolve()
        self.home.mkdir()

    def tearDown(self):
        install.MUTATION_HOOK = None
        os.environ.pop("SWE_SIDEKICK_INSTALL_FAIL_AFTER", None)
        self.tmp.cleanup()

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = install.main(["--home", str(self.home), *args])
        return code, out.getvalue(), err.getvalue()

    def apply(self, *args):
        code, out, err = self.invoke("--apply", *args)
        self.assertEqual(code, 0, out + err)
        return out

    @staticmethod
    def mode(path):
        return stat.S_IMODE(path.lstat().st_mode)

    def manifest_path(self):
        return self.home / install.MANIFEST_RELATIVE

    def read_manifest(self):
        return json.loads(self.manifest_path().read_text(encoding="utf-8"))

    def test_plan_no_changes(self):
        code, _, err = self.invoke()
        self.assertEqual(code, 0, err)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_fresh_install_and_uninstall_keeps_state(self):
        global_codex_config = self.home / ".codex/config.toml"
        global_codex_config.parent.mkdir(parents=True)
        global_codex_config.write_text("keep = true\n", encoding="utf-8")
        self.apply()
        manifest = self.read_manifest()
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertEqual(manifest["app_version"], "0.2.0")
        self.assertTrue(manifest["created"])
        self.assertTrue(all("mode" in record for record in manifest["created"]))

        app = self.home / ".local/share/codex-swe-sidekick/0.2.0"
        cli = self.home / ".local/bin/swe-sidekick"
        codex_skill = self.home / ".codex/skills/swe-sidekick/SKILL.md"
        devin_skill = self.home / ".config/devin/skills/swe-sidekick/SKILL.md"
        codex_openai = self.home / ".codex/skills/swe-sidekick/agents/openai.yaml"
        self.assertTrue((app / "README.md").is_file())
        self.assertTrue((app / "TEST_REPORT.md").is_file())
        self.assertTrue((app / "docs/HOSTS.md").is_file())
        self.assertTrue(codex_openai.is_file())
        self.assertTrue(cli.is_file())
        self.assertEqual(self.mode(cli), 0o755)
        self.assertNotIn("__SIDEKICK", codex_skill.read_text(encoding="utf-8"))
        self.assertNotIn("triggers:", codex_skill.read_text(encoding="utf-8"))
        self.assertIn("triggers: [user]", devin_skill.read_text(encoding="utf-8"))
        self.assertNotIn("model:", codex_openai.read_text())
        self.assertEqual(global_codex_config.read_text(encoding="utf-8"), "keep = true\n")

        code, _, err = self.invoke("--apply")
        self.assertEqual(code, 0, err)

        state = self.home / ".local/state/codex-swe-sidekick"
        state.mkdir(parents=True)
        (state / "config.json").write_text('{"keep": true}\n', encoding="utf-8")
        task = state / "tasks/fixture"
        task.mkdir(parents=True)
        (task / "task.json").write_text('{"keep": true}\n', encoding="utf-8")

        code, _, err = self.invoke("--uninstall")
        self.assertEqual(code, 0, err)
        self.assertTrue(cli.exists())
        self.assertTrue(self.manifest_path().exists())
        code, _, err = self.invoke("--uninstall", "--apply")
        self.assertEqual(code, 0, err)
        self.assertFalse(cli.exists())
        self.assertFalse(codex_skill.exists())
        self.assertFalse(devin_skill.exists())
        self.assertFalse(self.manifest_path().exists())
        self.assertEqual((state / "config.json").read_text(encoding="utf-8"), '{"keep": true}\n')
        self.assertEqual((task / "task.json").read_text(encoding="utf-8"), '{"keep": true}\n')
        self.assertEqual(global_codex_config.read_text(encoding="utf-8"), "keep = true\n")

    def test_existing_skill_is_an_unowned_conflict(self):
        skill = self.home / ".codex/skills/swe-sidekick/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("my skill", encoding="utf-8")
        code, _, _ = self.invoke("--apply")
        self.assertEqual(code, 1)
        self.assertEqual(skill.read_text(encoding="utf-8"), "my skill")
        self.assertFalse(self.manifest_path().exists())

    def test_modified_managed_file_refuses_upgrade_and_uninstall(self):
        self.apply()
        skill = self.home / ".codex/skills/swe-sidekick/SKILL.md"
        original_manifest = self.manifest_path().read_bytes()
        skill.write_text("edited", encoding="utf-8")
        code, _, _ = self.invoke("--upgrade", "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(skill.read_text(encoding="utf-8"), "edited")
        self.assertEqual(self.manifest_path().read_bytes(), original_manifest)
        code, _, _ = self.invoke("--uninstall", "--apply")
        self.assertEqual(code, 1)
        self.assertTrue(skill.exists())

    def test_same_version_upgrade_refreshes_changed_source_with_backup(self):
        self.apply()
        desired = install.payloads(self.home)
        target = self.home / ".local/share/codex-swe-sidekick/0.2.0/README.md"
        desired[target] = (b"updated release report\n", 0o644)
        old_bytes = target.read_bytes()
        with patch.object(install, "payloads", return_value=desired):
            code, _, err = self.invoke("--upgrade", "--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(target.read_bytes(), b"updated release report\n")
        self.assertNotEqual(self.manifest_path().read_bytes(), b"")
        backups = list((self.home / install.STATE_BASE / "install-backups").iterdir())
        self.assertEqual(len(backups), 1)
        metadata = json.loads((backups[0] / "backup.json").read_text(encoding="utf-8"))
        record = next(item for item in metadata["files"] if item["path"] == str(target))
        self.assertEqual((backups[0] / record["backup"]).read_bytes(), old_bytes)

    def test_unowned_target_refuses_upgrade(self):
        self._make_legacy_install()
        target = self.home / ".local/share/codex-swe-sidekick/0.2.0/README.md"
        target.parent.mkdir(parents=True)
        target.write_text("unowned", encoding="utf-8")
        old_manifest = self.manifest_path().read_bytes()
        code, _, _ = self.invoke("--upgrade", "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "unowned")
        self.assertEqual(self.manifest_path().read_bytes(), old_manifest)
        self.assertFalse((self.home / ".local/state/codex-swe-sidekick/install-backups").exists())

    def _make_legacy_install(self):
        old_app = self.home / ".local/share/codex-swe-sidekick" / install.LEGACY_VERSION
        records = []
        for relative in install.LEGACY_PAYLOADS:
            source = ROOT / relative
            data = source.read_bytes() if source.is_file() else ("legacy:" + relative).encode()
            path = old_app / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            os.chmod(path, 0o644)
            records.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest()})

        canonical = install._skill_text(self.home, old_app)
        codex_skill = self.home / install.LEGACY_CODEX_SKILL_BASE
        (codex_skill / "agents").mkdir(parents=True, exist_ok=True)
        (codex_skill / "SKILL.md").write_text(canonical, encoding="utf-8")
        (codex_skill / "agents/openai.yaml").write_bytes((ROOT / "skill/agents/openai.yaml").read_bytes())
        for path in (codex_skill / "SKILL.md", codex_skill / "agents/openai.yaml"):
            os.chmod(path, 0o644)
            records.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

        # An unknown entry below the old skill directory must survive the
        # migration; only files explicitly owned by the legacy manifest may be
        # removed.
        self.legacy_unowned = codex_skill / "keep.txt"
        self.legacy_unowned.write_text("keep", encoding="utf-8")

        cli = self.home / install.CLI_RELATIVE
        cli.parent.mkdir(parents=True, exist_ok=True)
        wrapper = (
            "#!/bin/sh\nexec " + repr(sys.executable) + " " + repr(str(old_app / "swe_sidekick.py")) + ' "$@"\n'
        ).replace("'", "")
        # The legacy installer used shell quoting; its exact wrapper text is
        # irrelevant to the compatibility manifest, so preserve its bytes.
        cli.write_text(wrapper, encoding="utf-8")
        os.chmod(cli, 0o755)
        records.append({"path": str(cli), "sha256": hashlib.sha256(cli.read_bytes()).hexdigest()})

        manifest = self.manifest_path()
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"version": install.LEGACY_VERSION, "created": records}, indent=2) + "\n", encoding="utf-8")
        os.chmod(manifest, 0o600)

    def test_managed_upgrade_from_original_manifest_and_backup(self):
        self._make_legacy_install()
        old_app = self.home / ".local/share/codex-swe-sidekick" / install.LEGACY_VERSION
        old_manifest = self.manifest_path().read_bytes()
        old_skill = self.home / ".agents/skills/swe-sidekick/SKILL.md"
        old_openai = self.home / ".agents/skills/swe-sidekick/agents/openai.yaml"
        old_skill_bytes = old_skill.read_bytes()
        old_skill_mode = self.mode(old_skill)

        code, _, err = self.invoke("--upgrade")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.manifest_path().read_bytes(), old_manifest)
        self.assertFalse((self.home / ".local/share/codex-swe-sidekick/0.2.0").exists())
        self.assertFalse((self.home / ".local/state/codex-swe-sidekick/install-backups").exists())

        self.apply("--upgrade")
        manifest = self.read_manifest()
        self.assertEqual(manifest["version"], install.VERSION)
        self.assertEqual(manifest["previous_app_version"], install.LEGACY_VERSION)
        self.assertTrue(old_app.exists(), "the prior app version is retained")
        self.assertTrue((self.home / ".codex/skills/swe-sidekick/SKILL.md").is_file())
        self.assertTrue((self.home / ".codex/skills/swe-sidekick/agents/openai.yaml").is_file())
        self.assertFalse(old_skill.exists())
        self.assertFalse(old_openai.exists())
        self.assertTrue(self.legacy_unowned.is_file())
        self.assertTrue((self.home / ".config/devin/skills/swe-sidekick/SKILL.md").is_file())
        self.assertIn("triggers: [user]", (self.home / ".config/devin/skills/swe-sidekick/SKILL.md").read_text())

        backups = list((self.home / install.STATE_BASE / "install-backups").iterdir())
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        self.assertEqual((backup / "install-manifest.json").read_bytes(), old_manifest)
        self.assertEqual(self.mode(backup), 0o700)
        self.assertEqual(self.mode(backup / "install-manifest.json"), 0o600)
        metadata = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata["files"])
        self.assertTrue(all("mode" in item for item in metadata["files"]))
        self.assertTrue(any(item["path"] == str(old_skill) for item in metadata["files"]))
        backed_skill = backup / next(item["backup"] for item in metadata["files"] if item["path"] == str(old_skill))
        self.assertEqual(backed_skill.read_bytes(), old_skill_bytes)
        self.assertEqual(self.mode(backed_skill), old_skill_mode)

    def test_injected_failure_rolls_back_upgrade(self):
        self._make_legacy_install()
        old_manifest = self.manifest_path().read_bytes()
        old_skill = self.home / ".agents/skills/swe-sidekick/SKILL.md"
        old_openai = self.home / ".agents/skills/swe-sidekick/agents/openai.yaml"
        old_skill_bytes = old_skill.read_bytes()
        old_openai_bytes = old_openai.read_bytes()
        state = self.home / install.STATE_BASE
        state.mkdir(parents=True)
        (state / "config.json").write_text('{"keep": true}\n', encoding="utf-8")

        # Fail after both legacy files have been removed and before the new
        # manifest is committed, exercising migration restoration too.
        os.environ["SWE_SIDEKICK_INSTALL_FAIL_AFTER"] = "20"
        code, _, _ = self.invoke("--upgrade", "--apply")
        self.assertEqual(code, 1)
        self.assertEqual(self.manifest_path().read_bytes(), old_manifest)
        self.assertEqual(old_skill.read_bytes(), old_skill_bytes)
        self.assertEqual(old_openai.read_bytes(), old_openai_bytes)
        self.assertTrue(self.legacy_unowned.is_file())
        self.assertFalse((self.home / ".codex/skills/swe-sidekick/SKILL.md").exists())
        self.assertFalse((self.home / ".config/devin/skills/swe-sidekick/SKILL.md").exists())
        self.assertFalse((self.home / ".local/share/codex-swe-sidekick/0.2.0").exists())
        self.assertEqual((state / "config.json").read_text(encoding="utf-8"), '{"keep": true}\n')
        backups = list((state / "install-backups").iterdir())
        self.assertEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()
