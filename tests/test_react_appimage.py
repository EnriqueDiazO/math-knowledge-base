"""Verify package boundaries without touching installed services or user profiles."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import build_react_appimage as build


def test_tool_is_verified_before_execution_and_existing_destination_is_preserved(tmp_path):
    """Reject unverified tools and preserve an existing AppDir."""
    tool = tmp_path / "tool"
    tool.write_bytes(b"untrusted")
    with pytest.raises(ValueError, match="huella"):
        build.verified_tool(tool, build.TOOL_SHA256)
    with pytest.raises(ValueError, match="no se sobrescribió"):
        build.prepare_appdir(tmp_path, tmp_path)
    assert tool.read_bytes() == b"untrusted"


def test_only_tracked_application_resources_enter_bundle(tmp_path, monkeypatch):
    """Include declared application resources while keeping private files out."""
    tracked = [
        "mathmongo/config.py",
        "templates_latex/miestilo.sty",
        "assets/icons/mathmongo-256.png",
        "mathkb_config.py",
        ".env",
        "evidence/private.json",
        "tests/private.zip",
        "mathmongo/private.pdf",
    ]
    for name in tracked:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(
        build.subprocess, "check_output", lambda *a, **k: ("\0".join(tracked) + "\0").encode()
    )
    destination = tmp_path / "app"
    included = build.copy_application(destination)
    assert set(included) == set(tracked[:4])
    assert {
        str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()
    } == set(tracked[:4])
    (tmp_path / tracked[0]).unlink()
    (tmp_path / tracked[0]).symlink_to(tmp_path / ".env")
    with pytest.raises(ValueError, match="archivo regular"):
        build.copy_application(tmp_path / "second")


def test_vendor_keeps_license_and_code_but_rejects_hooks_and_parent_paths(tmp_path, monkeypatch):
    """Keep dependency code and licenses without executable import hooks."""
    source = tmp_path / "source"
    source.mkdir()
    for name in ("library.py", "LICENSE", "hook.pth"):
        (source / name).write_text(name)
    package = SimpleNamespace(
        version="1",
        files=[
            Path(name)
            for name in ("library.py", "LICENSE", "hook.pth", "../private", "/etc/passwd")
        ],
        locate_file=lambda name: source / name,
    )
    monkeypatch.setattr(build, "distribution", lambda name: package)
    destination = tmp_path / "vendor"
    build.copy_vendor(destination, {"library": "1"})
    assert {path.name for path in destination.iterdir()} == {"library.py", "LICENSE"}
    with pytest.raises(ValueError, match="Versión incompatible"):
        build.copy_vendor(tmp_path / "other", {"library": "2"})
    assert not (tmp_path / "other").exists()


def test_runtime_rejects_venv_and_external_symlinks_before_staging(tmp_path):
    """Reject nonportable runtimes before creating any output."""
    runtime = tmp_path / "python"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin/python3.13").touch()
    (runtime / "pyvenv.cfg").touch()
    output = tmp_path / "appdir"
    with pytest.raises(ValueError, match="no un entorno virtual"):
        build.prepare_appdir(output, runtime)
    (runtime / "pyvenv.cfg").unlink()
    (runtime / "bin/external").symlink_to("/bin/sh")
    with pytest.raises(ValueError, match="fuera de su directorio"):
        build.prepare_appdir(output, runtime)
    assert not output.exists()


def test_build_publishes_a_real_digest_and_refuses_to_replace_an_existing_package(
    tmp_path, monkeypatch, capsys
):
    """The packaging process receives bounded inputs and an existing artifact is never replaced."""
    import hashlib
    import json

    output = tmp_path / "MathMongo.AppImage"
    tool = tmp_path / "tool"
    tool.touch()
    runtime = tmp_path / "runtime"
    runtime.touch()
    calls = []
    monkeypatch.setattr(build, "verified_tool", lambda path, expected: Path(path))
    monkeypatch.setattr(build, "prepare_appdir", lambda target, python: target.mkdir())

    def compile_bundle(command, **options):
        calls.append((command, options))
        assert "--runtime-file" in command and str(runtime) in command
        assert options["check"] is True and options["timeout"] == 300
        Path(command[-1]).write_bytes(b"verified generated package")

    monkeypatch.setattr(build.subprocess, "run", compile_bundle)
    monkeypatch.setattr(
        build.sys,
        "argv",
        [
            "build",
            "--python-runtime",
            str(tmp_path),
            "--appimagetool",
            str(tool),
            "--runtime-file",
            str(runtime),
            "--output",
            str(output),
        ],
    )
    assert build.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert len(calls) == 1
    with pytest.raises(ValueError, match="no se sobrescribió"):
        build.main()
    assert output.read_bytes() == b"verified generated package" and len(calls) == 1
