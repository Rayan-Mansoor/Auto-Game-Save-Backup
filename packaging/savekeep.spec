# PyInstaller spec: builds saveix.exe (command line) and saveix-tray.exe (tray app,
# no console window) into one folder that the installer then packages.
# Build with: uv run --group build pyinstaller packaging/saveix.spec --noconfirm
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hidden = collect_submodules("saveix.integrations") + collect_submodules("saveix.ui")
# Entry point metadata is how saveix finds its provider plugins.
datas = collect_data_files("saveix") + copy_metadata("saveix")


def analysis(script):
    return Analysis(
        [script],
        pathex=[os.path.join(SPECPATH, "..", "src")],
        hiddenimports=hidden,
        datas=datas,
        excludes=["tkinter"],
    )


cli = analysis(os.path.join(SPECPATH, "cli_entry.py"))
tray = analysis(os.path.join(SPECPATH, "tray_entry.py"))

cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="saveix",
    console=True,
)
tray_exe = EXE(
    PYZ(tray.pure),
    tray.scripts,
    [],
    exclude_binaries=True,
    name="saveix-tray",
    console=False,
)
COLLECT(
    cli_exe,
    cli.binaries,
    cli.datas,
    tray_exe,
    tray.binaries,
    tray.datas,
    name="saveix",
)
