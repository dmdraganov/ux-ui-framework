"""Track accepted Code First artifacts from the website project root."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from urllib.parse import urlsplit


DESIGN = Path("docs/design")
STATE = DESIGN / ".workflow-state.json"
STAGES = {
    "discovery": ("brief.md", ()),
    "research": ("research.md", ("brief.md",)),
    "ux": ("ux-spec.md", ("brief.md", "research.md")),
    "ui": ("design-system.md", ("ux-spec.md",)),
    "qa": ("qa-report.md", ("brief.md", "ux-spec.md", "design-system.md")),
}


def digest(root, path):
    absolute = root / path
    mode = absolute.lstat().st_mode
    if stat.S_ISREG(mode):
        with absolute.open("rb") as file:
            return "file:" + hashlib.file_digest(file, "sha256").hexdigest()
    if not stat.S_ISDIR(mode):
        raise ValueError(f"Expected a regular file or directory: {path}")
    entries = [(child.name, digest(root, child.relative_to(root))) for child in sorted(absolute.iterdir())]
    return "directory:" + hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def checked_path(root, path, project_only=False):
    absolute = (root / path).resolve(strict=True)
    if project_only and not absolute.is_relative_to(root):
        raise ValueError(f"Prototype source must be inside the project: {path}")
    return Path(os.path.relpath(absolute, root))


def read_state(root):
    path = root / STATE
    if not path.exists():
        return {}
    state = json.loads(path.read_text())
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("stages"), dict):
        raise ValueError(f"Invalid workflow state: {path}")
    return state["stages"]


def write_state(root, records):
    state = root / STATE
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=state.parent, delete=False) as file:
        pending = Path(file.name)
        try:
            json.dump({"version": 1, "stages": records}, file, indent=2)
            file.write("\n")
            file.close()
            pending.replace(state)
        finally:
            pending.unlink(missing_ok=True)


def stage_problem(root, records, stage):
    record = records.get(stage)
    if record is None:
        return {"stage": stage, "status": "pending"}
    for group in ("inputs", "outputs"):
        for name, expected in record[group].items():
            path = Path(name)
            # A retargeted symlink is a change even when both files have the same bytes.
            try:
                current = checked_path(root, path)
                changed = current != path or digest(root, path) != expected
            except (FileNotFoundError, NotADirectoryError, ValueError, RuntimeError):
                changed = True
            if changed:
                return {"stage": stage, "status": "stale", "path": name}
    if record.get("outcome") == "blocked":
        return {"stage": stage, "status": "blocked"}
    return None


def status(root, records):
    for stage in STAGES:
        problem = stage_problem(root, records, stage)
        if problem:
            if stage == "qa":
                problem["prototype"] = records["ui"]["prototype"]
            return problem
    return {"stage": None, "status": "complete", "prototype": records["ui"]["prototype"]}


def snapshots(root, paths):
    return {path.as_posix(): digest(root, path) for path in sorted(set(paths))}


def record_stage(root, records, args):
    stage = args.stage
    for prior in STAGES:
        if prior == stage:
            break
        if stage_problem(root, records, prior):
            raise ValueError(f"Accept the current {prior} stage before recording {stage}")
    if stage == "discovery" and not args.input:
        raise ValueError("Discovery needs at least one --input with the source brief or notes")
    if stage != "ui" and (args.source or args.launch_command is not None or args.url is not None):
        raise ValueError("--source, --launch-command and --url belong to the UI stage")
    if (stage == "qa") != (args.outcome is not None):
        raise ValueError("--outcome is required for QA and applies only to QA")

    output, required_inputs = STAGES[stage]
    document = DESIGN / output
    if not (root / document).is_file() or (root / document).stat().st_size == 0:
        raise ValueError(f"Expected a nonempty deliverable: {document}")
    if checked_path(root, document, project_only=True) != document:
        raise ValueError(f"Expected a deliverable at its designated path: {document}")
    inputs = [DESIGN / name for name in required_inputs]
    inputs.extend(checked_path(root, path) for path in args.input)
    # Markdown artifacts have fixed paths. Supplementary inputs are specific
    # files so workflow state and regenerated documents never hash themselves.
    for path in inputs:
        if not (root / path).is_file() or path in (document, STATE):
            raise ValueError(f"Expected a source file distinct from stage output and state: {path}")
    outputs = [document]
    record = {}
    if stage == "ui":
        if not args.source or not args.launch_command or not args.launch_command.strip() or not args.url:
            raise ValueError("UI needs --source, --launch-command and --url")
        url = urlsplit(args.url)
        if url.scheme not in ("http", "https") or url.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("UI needs a local HTTP(S) URL")
        sources = [checked_path(root, path, project_only=True) for path in args.source]
        for path in sources:
            if DESIGN.is_relative_to(path) or path.is_relative_to(DESIGN):
                raise ValueError(f"Select prototype paths outside the design artifacts directory: {path}")
        outputs.extend(sources)
        record["prototype"] = {
            "sources": sorted({path.as_posix() for path in sources}),
            "launch_command": args.launch_command,
            "url": args.url,
        }
    if stage == "qa":
        inputs.extend(Path(path) for path in records["ui"]["prototype"]["sources"])
        record["outcome"] = args.outcome
    record.update(inputs=snapshots(root, inputs), outputs=snapshots(root, outputs))
    if records.get(stage) != record:
        current = list(STAGES).index(stage)
        records = {prior: records[prior] for prior in list(STAGES)[:current]}
        records[stage] = record
        write_state(root, records)
    return status(root, records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("status", help="Show the first stage that needs attention")
    record = actions.add_parser("record", help="Save the snapshot of a reviewed stage")
    record.add_argument("stage", choices=STAGES)
    record.add_argument("--input", type=Path, action="append", default=[])
    record.add_argument("--source", type=Path, action="append", default=[])
    record.add_argument("--launch-command")
    record.add_argument("--url")
    record.add_argument("--outcome", choices=("passed", "blocked"))
    args = parser.parse_args()
    root = Path.cwd()
    try:
        if args.action == "status":
            result = status(root, read_state(root))
        else:
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                result = record_stage(root, read_state(root), args)
            finally:
                os.close(descriptor)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Workflow state error: {error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
