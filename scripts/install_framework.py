"""Prepare and install the framework in a Codex project."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parent.parent
SKILLS = Path(".agents/skills")
AGENTS = Path(".codex/agents")
WORKFLOW = Path(".codex/ux-ui-framework")
MANIFEST = Path(".codex/ux-ui-framework-install.json")
ROLES = ("discovery-specialist", "design-researcher", "ux-designer", "ui-designer", "design-qa")


def installation_paths(skill_names, local_only):
    paths = [SKILLS / name for name in (*skill_names, "ui-ux-pro-max")]
    if not local_only:
        paths.extend(AGENTS / f"{name}.toml" for name in ROLES)
        paths.extend((WORKFLOW, MANIFEST))
    return paths


def prepare(staging, skill_names, paths, local_only):
    lock = ROOT / "skills-lock.json"
    shutil.copy2(lock, staging / lock.name)
    if local_only:
        # Preserve frozen-lockfile validation of already-installed local skills.
        for name in skill_names:
            installed = ROOT / SKILLS / name
            if installed.is_dir():
                shutil.copytree(installed, staging / SKILLS / name)
    subprocess.run(
        ["npx", "--prefer-offline", "--yes", "skills@1.9.0",
         "install", "--frozen-lockfile", "--agent", "codex"],
        cwd=staging, check=True,
    )
    uipro = staging / "uipro"
    uipro.mkdir()
    subprocess.run(
        ["npx", "--prefer-offline", "--yes", "ui-ux-pro-max-cli@2.15.0", "init", "--ai", "codex"],
        cwd=uipro, check=True,
    )
    shutil.move(uipro / SKILLS / "ui-ux-pro-max", staging / SKILLS / "ui-ux-pro-max")

    for path in (path for path in paths if path.parent == SKILLS):
        if not (staging / path / "SKILL.md").is_file():
            raise ValueError(f"Missing skill manifest: {path / 'SKILL.md'}")
    if local_only:
        return

    (staging / AGENTS).mkdir(parents=True, exist_ok=True)
    for name in ROLES:
        path = AGENTS / f"{name}.toml"
        with (ROOT / path).open("rb") as file:
            role = tomllib.load(file)
        if role.get("name") != name or not all(
            isinstance(role.get(key), str) and role[key].strip()
            for key in ("description", "developer_instructions")
        ):
            raise ValueError(f"Invalid Codex role: {path}")
        shutil.copy2(ROOT / path, staging / path)

    (staging / WORKFLOW).mkdir(parents=True)
    shutil.copy2(ROOT / "workflows/uxui-code-first.md", staging / WORKFLOW / "workflow.md")
    shutil.copy2(ROOT / "scripts/workflow-state.py", staging / WORKFLOW / "workflow-state.py")
    (staging / MANIFEST).write_text(
        json.dumps({"version": 1, "paths": [path.as_posix() for path in paths if path != MANIFEST]}, indent=2)
        + "\n"
    )


def validate_destination(target, paths, local_only):
    for path in paths:
        for parent in path.parents:
            directory = target / parent
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                raise ValueError(f"Installation path requires a regular directory: {directory}")
        if (target / path).is_symlink():
            raise ValueError(f"Installation path is a symlink: {target / path}")

    if local_only:
        return
    managed = []
    manifest = target / MANIFEST
    if manifest.exists():
        data = json.loads(manifest.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"Invalid installation manifest: {manifest}")
        managed = data.get("paths")
        valid_paths = {path.as_posix() for path in paths if path != MANIFEST}
        if data.get("version") != 1 or not isinstance(managed, list) or any(
            not isinstance(path, str) or path not in valid_paths for path in managed
        ):
            raise ValueError(f"Invalid installation manifest: {manifest}")
    for path in paths:
        if path != MANIFEST and (target / path).exists() and path.as_posix() not in managed:
            raise ValueError(f"Path already exists and is outside this installation: {target / path}")


def make_parents(directory, target, created):
    if directory != target and not directory.exists():
        make_parents(directory.parent, target, created)
        directory.mkdir()
        created.append(directory)


def install(staging, target, paths):
    # Backups and replacements live on the target filesystem for atomic renames.
    transaction = Path(tempfile.mkdtemp(prefix=".ux-ui-install-", dir=target))
    prepared = transaction / "prepared"
    backup = transaction / "backup"
    prepared.mkdir()
    backup.mkdir()
    replaced = []
    created = []
    try:
        for index, path in enumerate(paths):
            source = staging / path
            destination = prepared / str(index)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        for index, path in enumerate(paths):
            destination = target / path
            saved = backup / str(index)
            make_parents(destination.parent, target, created)
            if destination.exists():
                destination.replace(saved)
            replaced.append((destination, saved))
            (prepared / str(index)).replace(destination)
    except BaseException:
        try:
            for index, (destination, saved) in reversed(list(enumerate(replaced))):
                if destination.exists():
                    destination.replace(transaction / f"discard-{index}")
                if saved.exists():
                    saved.replace(destination)
            for directory in reversed(created):
                directory.rmdir()
        except OSError as rollback_error:
            raise RuntimeError(f"Rollback incomplete. Backups are in {backup}: {rollback_error}") from rollback_error
        shutil.rmtree(transaction)
        raise
    shutil.rmtree(transaction)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, help="Existing website project directory")
    args = parser.parse_args()
    local_only = args.target is None
    target = ROOT if local_only else args.target.resolve()
    if not target.is_dir():
        parser.error(f"Website project directory does not exist: {target}")
    try:
        skill_names = tuple(json.loads((ROOT / "skills-lock.json").read_text())["skills"])
        paths = installation_paths(skill_names, local_only)
        # Lock the directory itself so concurrent installs share the same lock.
        descriptor = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            validate_destination(target, paths, local_only)
            with tempfile.TemporaryDirectory(prefix="ux-ui-skills-") as temp:
                staging = Path(temp)
                prepare(staging, skill_names, paths, local_only)
                validate_destination(target, paths, local_only)
                install(staging, target, paths)
        finally:
            os.close(descriptor)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Installation failed: {error}\n")
    print(f"Installed UX/UI {'skills' if local_only else 'Framework'} in {target}")


if __name__ == "__main__":
    main()
