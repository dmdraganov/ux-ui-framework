import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import install_framework


class InstallerTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(self.enterContext(TemporaryDirectory()))
        self.site = workspace / "site with spaces"
        self.site.mkdir()
        self.bin = workspace / "bin"
        self.bin.mkdir()
        cli = self.bin / "npx"
        cli.write_text("""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
assert args[:2] == ["--prefer-offline", "--yes"]
if args[2] == "skills@1.9.0":
    assert args[3:] == ["install", "--frozen-lockfile", "--agent", "codex"]
    names = json.loads(Path("skills-lock.json").read_text())["skills"]
else:
    assert args[2:] == ["ui-ux-pro-max-cli@2.15.0", "init", "--ai", "codex"]
    if os.environ.get("FAIL_UIPRO"):
        sys.exit(12)
    names = ["ui-ux-pro-max"]
for name in names:
    directory = Path(".agents/skills") / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(name)
""")
        cli.chmod(0o755)

    def install(self, success=True, **env):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/install-skills.sh"), "--target", str(self.site)],
            capture_output=True, text=True, check=False,
            env={**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", **env},
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def test_install_and_replace_only_managed_paths(self):
        self.install()
        manifest = json.loads((self.site / install_framework.MANIFEST).read_text())
        self.assertEqual(len(manifest["paths"]), 13)
        for role in install_framework.ROLES:
            path = self.site / install_framework.AGENTS / f"{role}.toml"
            self.assertEqual(tomllib.loads(path.read_text())["name"], role)
        workflow = self.site / install_framework.WORKFLOW / "workflow.md"
        pinned_rules = self.site / install_framework.SKILLS / "web-design-guidelines" / "SKILL.md"
        self.assertIn(".agents/skills/web-design-guidelines/SKILL.md", workflow.read_text())
        self.assertTrue(pinned_rules.is_file())
        status = subprocess.check_output(
            [sys.executable, str(workflow.with_name("workflow-state.py")), "status"], cwd=self.site,
        )
        self.assertEqual(json.loads(status), {"stage": "discovery", "status": "pending"})
        foreign = self.site / install_framework.AGENTS / "other.toml"
        foreign.write_text("preserve")
        stale = self.site / install_framework.SKILLS / "ui-ux-pro-max" / "stale.txt"
        stale.write_text("retired")
        self.install()
        self.assertFalse(stale.exists())
        self.assertEqual(foreign.read_text(), "preserve")

    def test_unmanaged_conflict_and_failed_prepare_preserve_site(self):
        role = self.site / install_framework.AGENTS / "design-qa.toml"
        role.parent.mkdir(parents=True)
        role.write_text("custom role")
        result = self.install(success=False)
        self.assertIn("design-qa.toml", result.stderr)
        self.assertEqual(list(path for path in self.site.rglob("*") if path.is_file()), [role])
        self.assertEqual(role.read_text(), "custom role")
        role.unlink()
        self.install()
        stale = self.site / install_framework.SKILLS / "ui-ux-pro-max" / "stale.txt"
        stale.write_text("old installation")
        old_manifest = (self.site / install_framework.MANIFEST).read_bytes()
        self.install(success=False, FAIL_UIPRO="true")
        self.assertEqual(stale.read_text(), "old installation")
        self.assertEqual((self.site / install_framework.MANIFEST).read_bytes(), old_manifest)

    def test_publish_failure_restores_previous_paths(self):
        one, two = Path("existing"), Path("new/failing")
        (self.site / one).write_text("previous")
        staging = Path(self.enterContext(TemporaryDirectory()))
        (staging / one).write_text("replacement")
        (staging / two).parent.mkdir()
        (staging / two).write_text("unpublished")
        original = Path.replace

        def interrupt_publish(source, destination):
            if destination == self.site / two:
                raise OSError("simulated rename failure")
            return original(source, destination)

        with patch.object(Path, "replace", interrupt_publish):
            with self.assertRaisesRegex(OSError, "simulated rename failure"):
                install_framework.install(staging, self.site, [one, two])
        self.assertEqual((self.site / one).read_text(), "previous")
        self.assertEqual(list(self.site.iterdir()), [self.site / one])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.site = Path(self.enterContext(TemporaryDirectory()))
        self.write("brief-source.md", "The site must expose its contact form.")
        self.write("docs/design/brief.md", "R1. A visitor can open the contact form.")
        self.write("docs/design/research.md", "Keep the form reachable from the home page.")
        self.write("docs/design/ux-spec.md", "R1. The Contact link opens the form.")
        self.write("docs/design/design-system.md", "Use the primary link style.")
        self.write("src/index.html", '<a href="contact.html">Contact</a>')
        self.record_ui = (
            "record", "ui", "--source", "src", "--launch-command", "python3 -m http.server",
            "--url", "http://localhost:8000",
        )

    def write(self, name, content):
        file = self.site / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def state(self, *args, success=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/workflow-state.py"), *args],
            cwd=self.site, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return json.loads(result.stdout) if success else result.stderr

    def accept_through_ui(self):
        self.state("record", "discovery", "--input", "brief-source.md")
        self.state("record", "research")
        self.state("record", "ux")
        self.assertEqual(self.state(*self.record_ui)["stage"], "qa")

    def test_resume_detects_changed_source_and_brief(self):
        self.assertEqual(self.state("status")["stage"], "discovery")
        self.accept_through_ui()
        self.write("docs/design/qa-report.md", "R1 passed.")
        self.state("record", "qa", "--outcome", "passed")
        self.assertEqual(self.state("status")["status"], "complete")
        self.write("src/contact.html", "<form></form>")
        self.assertEqual(self.state("status"), {"stage": "ui", "status": "stale", "path": "src"})
        self.state("record", "qa", "--outcome", "passed", success=False)
        self.assertEqual(self.state(*self.record_ui)["status"], "pending")
        self.write("brief-source.md", "The site must collect contact form messages.")
        self.assertEqual(self.state("status")["stage"], "discovery")
        self.state("record", "discovery", "--input", "brief-source.md")
        self.assertEqual(self.state("status"), {"stage": "research", "status": "pending"})
        self.assertTrue((self.site / "docs/design/qa-report.md").is_file())

    def test_blocked_qa_recheck_and_acceptance(self):
        self.accept_through_ui()
        self.write("docs/design/qa-report.md", "R1 unverified. Launch: port already in use.")
        self.assertEqual(self.state("record", "qa", "--outcome", "blocked")["status"], "blocked")
        self.assertEqual(self.state("status")["prototype"]["url"], "http://localhost:8000")
        self.write("docs/design/qa-report.md", "R1 failed. The Contact link opens a missing page.")
        self.state("record", "qa", "--outcome", "blocked")
        self.write("src/contact.html", "<form></form>")
        self.state(*self.record_ui)
        self.write("docs/design/qa-report.md", "R1 passed on repeat. The Contact link opens the form.")
        self.assertEqual(self.state("record", "qa", "--outcome", "passed")["status"], "complete")


if __name__ == "__main__":
    unittest.main()
