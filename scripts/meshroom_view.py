"""Open an owner-built Windows viewing package with the qualified native GUI.

The package builder owns the graph, cache and image paths. This launcher only
maps the historical filesystem root and selects the existing Qt/Meshroom GUI.
Requires Windows, Python >=3.10, full Meshroom 8df9560 and Mesa 26.3.1 x64.
"""
import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


WORK = "root/photo-cad/work"
PROJECT = WORK + "/runs/textures/project.mg"
MESHROOM_PINS = {
    "Meshroom.exe": "03ba1b3af07348ccc6182ed40a68daa0b46b2b82a39c798a83f8743eee6df99d",
    "python/python.exe": "7128399232d839de02837375c41d72bba321a01e635c247cea4be9b7208fa8a1",
    "lib/meshroom/__init__.pyc": "07a05cc4f2bb3b0c600e31236dc57bb588821d9d1103a00d4b8dc66c8995eecb",
    "lib/meshroom/ui/app.pyc": "f9397e4d4946e91da4715989f00090dc27a1f99cab661d216d16d3cc9170d8e7",
    "qtPlugins/qml/meshViewer/meshViewer.dll": "b01027703347b8b617a45d4004f57270215cf88dff7d5ad68da5e3a92cc5e666",
    "qtPlugins/qml/AliceVision/qtAliceVisionPlugin.dll": "514cb66a043b23a9ada4382c0add4278e21dd7494115f82f4f0bfed370d7e4aa",
    "qtPlugins/imageformats/qtAliceVisionImageIOPlugin.dll": "bb515b0936297f3597a7d050598e243e29795ece2b0e9cb0e3a7b5033dfada53",
    "aliceVision/bin/aliceVision_image.dll": "efe6b6af623074665ce0115c4d2371e41c4bba0f801c0d5c23f7421f50245665",
    "aliceVision/bin/OpenImageIO.dll": "8e87961cc9e2b5f170842851af6574b48a0c0ec01de1abda224a1c32084bb538",
}
MESA_PINS = {
    "opengl32.dll": "2ae2472a335b400bbc0d16b99981feacb3a7653eb4add6f694ac0e6d6351bbb3",
    "libgallium_wgl.dll": "8f6a0670aaf73604ea0ad8241af583a4ebc21d8a0c112102fafe2bf7695ef6c4",
}


class ViewError(RuntimeError):
    pass


def kernel32():
    if os.name != "nt":
        raise ViewError("This viewing launcher requires Windows.")
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    dll.QueryDosDeviceW.restype = wintypes.DWORD
    dll.GetLogicalDrives.restype = wintypes.DWORD
    dll.DefineDosDeviceW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR]
    dll.DefineDosDeviceW.restype = wintypes.BOOL
    return dll


def drive_name(value):
    value = value.upper()
    if not re.fullmatch(r"[A-Z]:", value):
        raise ViewError("Use a drive letter such as P: (without a trailing slash).")
    return value


def drive_target(drive):
    buffer = ctypes.create_unicode_buffer(32768)
    if kernel32().QueryDosDeviceW(drive_name(drive), buffer, len(buffer)):
        return buffer.value
    error = ctypes.get_last_error()
    if error == 2:  # ERROR_FILE_NOT_FOUND: no DOS device with that name.
        return None
    raise ViewError(f"Cannot inspect {drive}: {ctypes.WinError(error)}")


def same_target(left, right):
    return ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))


def remove_exact_mapping(drive, target):
    # RAW_TARGET_PATH | REMOVE_DEFINITION | EXACT_MATCH_ON_REMOVE: never remove
    # a different mapping even if another process changes the drive meanwhile.
    if not kernel32().DefineDosDeviceW(0x1 | 0x2 | 0x4, drive, target):
        raise ViewError(f"Cannot release owned drive {drive}: {ctypes.WinError(ctypes.get_last_error())}")


@contextmanager
def mapped_drive(package, drive):
    """Reserve a free DOS drive; preserve foreign mappings on every exit path."""
    drive = drive_name(drive)
    package = Path(package).resolve(strict=True)
    mask = kernel32().GetLogicalDrives()
    if not mask:
        raise ViewError(f"Cannot inspect Windows drives: {ctypes.WinError(ctypes.get_last_error())}")
    if mask & (1 << (ord(drive[0]) - ord("A"))) or drive_target(drive) is not None:
        raise ViewError(f"Drive {drive} is occupied. Choose another unused --drive; existing drives are preserved.")
    expected = "\\??\\" + str(package)
    subst = str(Path(os.environ["SystemRoot"]) / "System32/subst.exe")
    result = subprocess.run([subst, drive, str(package)], capture_output=True, text=True)
    if result.returncode:
        raise ViewError(f"Cannot map {drive}: {result.stdout.strip()} {result.stderr.strip()}")
    target = drive_target(drive)
    if target is None or not same_target(target, expected):
        raise ViewError(f"Drive {drive} did not map to the requested package; unexpected mapping was preserved.")
    try:
        yield drive
    finally:
        current = drive_target(drive)
        if current is not None:
            if not same_target(current, target):
                raise ViewError(f"Drive {drive} changed owner; its current mapping was preserved.")
            remove_exact_mapping(drive, target)
            if drive_target(drive) is not None:
                raise ViewError(f"Owned mapping was removed, but another mapping remains on {drive}; it was preserved.")


def verify_pins(root, pins, label):
    for relative, expected in pins.items():
        path = root / relative
        if not path.is_file():
            raise ViewError(f"{label} is incomplete: missing {relative}")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _sha256(stream)
        if actual != expected:
            raise ViewError(f"{label} pin mismatch: {relative}. Use the qualified complete release.")


def _sha256(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def validate(args):
    kernel32()
    if sys.version_info < (3, 10):
        raise ViewError("Python 3.10 or newer is required for this launcher.")
    for name in ("package", "meshroom", "mesa"):
        value = getattr(args, name).resolve(strict=True)
        if not value.is_dir() or str(value).startswith("\\\\"):
            raise ViewError(f"{name} must be an existing local directory.")
        setattr(args, name, value)
    for relative in (WORK + "/capture/images", WORK + "/runs/standard/cache"):
        if not (args.package / relative).is_dir():
            raise ViewError(f"Viewing package is incomplete: missing {relative}")
    if not (args.package / PROJECT).is_file():
        raise ViewError(f"Viewing package is incomplete: missing {PROJECT}")
    drive_name(args.drive)
    verify_pins(args.meshroom, MESHROOM_PINS, "Meshroom full 8df9560")
    verify_pins(args.mesa, MESA_PINS, "Mesa 26.3.1 x64")


def native_material_default(app, workspace, direct_connection):
    """Choose the qualified native Material mode once per created mesh entry."""
    from PySide6.QtQml import QQmlEngine, QQmlExpression
    attached = None

    def added(_index, entry):
        if not entry.metaObject().className().startswith("MeshEntry_QMLTYPE"):
            raise ViewError("The qualified native MeshEntry is unavailable.")
        # This bundle does not expose a Python converter for the native enum.
        # Keep its write/read in the existing QML owner and return a number.
        expression = QQmlExpression(QQmlEngine.contextForObject(entry), entry,
            "layer && layer.shadingMode !== undefined ? "
            "(layer.shadingMode = 2, Number(layer.shadingMode)) : -1")
        actual, undefined = expression.evaluate()
        if expression.hasError() or undefined or actual != 2:
            raise ViewError("The qualified native Material default is unavailable.")

    def report_failure(error):
        print(f"Meshroom viewing profile: {error}", file=sys.stderr, flush=True)
        app.exit(1)

    def on_added(index, entry):
        try:
            added(index, entry)
        except Exception as error:
            report_failure(error)

    def attach():
        nonlocal attached
        # QJSValue keeps private QML pointer types inside their native engine;
        # toQObject returns the public QObject* instead of a typed QVariant.
        panel_value = app.engine.newQObject(workspace).property("panel3dViewer")
        panel = panel_value.toQObject()
        if panel is None:
            attached = None
            return
        inst = panel_value.property("viewer3D").property("collection").property(
            "meshes").property("instantiator").toQObject()
        if inst is None or not hasattr(inst, "objectAdded"):
            raise ViewError("The qualified native mesh Instantiator is unavailable.")
        if inst is attached:
            return
        entries = [entry for entry in inst.children()
                   if entry.metaObject().className().startswith("MeshEntry_QMLTYPE")]
        if len(entries) != int(inst.property("count")):
            raise ViewError("The qualified native MeshEntry ownership is unavailable.")
        for entry in entries:
            added(-1, entry)
        inst.objectAdded.connect(on_added, direct_connection)
        attached = inst

    def on_panel_changed(*_args):
        try:
            attach()
        except Exception as error:
            report_failure(error)

    workspace.panel3dViewerChanged.connect(on_panel_changed, direct_connection)
    attach()
    # Keep the callbacks alive through app.exec(); no polling or mode forcing.
    return on_added, on_panel_changed


def native_gui(meshroom, mesa, project):
    """Load only the declared binary bundle, then use its native public GUI."""
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(meshroom / "lib"), str(meshroom / "aliceVision/lib/python")]
    dll_dirs = [os.add_dll_directory(str(path)) for path in
                (mesa, meshroom, meshroom / "aliceVision/bin", meshroom / "lib/PySide6")]
    os.environ.update({
        "MESHROOM_INSTALL_DIR": str(meshroom),
        "MESHROOM_USE_8BIT_VIEWER": "1",
        "QT_OPENGL": "software",
        "QT_OPENGL_DLL": str(mesa / "opengl32.dll"),
        "GALLIUM_DRIVER": "llvmpipe",
        "LP_NUM_THREADS": "2",
    })
    os.environ["PATH"] = str(mesa) + os.pathsep + os.environ.get("PATH", "")
    import meshroom as runtime
    runtime.setupEnvironment(runtime.Backend.PYSIDE)
    from meshroom.ui.app import MeshroomApp
    from PySide6.QtCore import QObject, Qt
    from PySide6.QtQml import QQmlEngine
    app = MeshroomApp([str(meshroom / "Meshroom.exe"), project])
    # Use the existing HDR toggle rather than replacing the 2D image reader.
    viewer = next((item for item in app.engine.rootObjects()[0].findChildren(QObject)
                   if item.metaObject().className().startswith("Viewer2D_QMLTYPE")), None)
    if viewer is None:
        raise ViewError("The qualified native 2D viewer is unavailable.")
    toggle = None
    for item in viewer.findChildren(QObject):
        context = QQmlEngine.contextForObject(item)
        toggle = context.objectForName("displayHDR") if context else None
        if toggle is not None:
            break
    if toggle is None:
        raise ViewError("The qualified native HDR/8-bit toggle is unavailable.")
    toggle.setProperty("checked", False)
    if viewer.property("useFloatImageViewer"):
        raise ViewError("Could not select the native 8-bit image viewer.")
    workspace = next((item for item in app.engine.rootObjects()[0].findChildren(QObject)
                      if item.metaObject().className().startswith("WorkspaceView_QMLTYPE")), None)
    if workspace is None:
        raise ViewError("The qualified native workspace is unavailable.")
    material_callbacks = native_material_default(app, workspace, Qt.DirectConnection)
    return app.exec()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--meshroom", required=True, type=Path, help="Qualified full Windows 8df9560 directory")
    parser.add_argument("--mesa", required=True, type=Path, help="Mesa 26.3.1 x64 directory containing both DLLs")
    parser.add_argument("--drive", default="P:", help="Unused temporary drive letter (default P:)")
    parser.add_argument("--gui-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        validate(args)
        if args.gui_child:
            target = drive_target(args.drive)
            if target is None or not same_target(target, "\\??\\" + str(args.package)):
                raise ViewError("GUI child requires the launcher's verified package mapping.")
            os.chdir(f"{args.drive}/{WORK}")
            return native_gui(args.meshroom, args.mesa, f"{args.drive}/{PROJECT}")
        with mapped_drive(args.package, args.drive) as drive:
            with tempfile.TemporaryDirectory(prefix="meshroom-view-thumbnails-") as thumbnails:
                env = os.environ.copy()
                env["MESHROOM_THUMBNAIL_DIR"] = thumbnails
                command = [str(args.meshroom / "python/python.exe"), str(Path(__file__).resolve()),
                           str(args.package), "--meshroom", str(args.meshroom), "--mesa", str(args.mesa),
                           "--drive", drive, "--gui-child"]
                print(f"Opening native Meshroom through {drive}; close the window to release this mapping.", flush=True)
                process = subprocess.Popen(command, cwd=f"{drive}/{WORK}", env=env)
                try:
                    return process.wait()
                except KeyboardInterrupt:
                    process.terminate()
                    process.wait()
                    return 130
    except (ViewError, OSError, subprocess.SubprocessError) as error:
        print(f"meshroom_view: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
