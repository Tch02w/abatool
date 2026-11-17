from pathlib import Path

root = Path(SPECPATH).parent
post = root / "modules" / "postprocessor"
analysis = Analysis(
    [str(root / "packaging" / "control_plane_entry.py")],
    pathex=[str(root)],
    datas=[(str(post / "defaults.json"), "modules/postprocessor"),
           (str(post / "abaqus_scripts" / "*.py"), "modules/postprocessor/abaqus_scripts")],
    hiddenimports=["openpyxl", "xlsxwriter"],
    excludes=["PySide6", "shiboken6", "PyQt5", "PyQt6", "tkinter", "pytest"],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True,
          name="AbaqusTools.ControlPlane", console=True, upx=False)
COLLECT(exe, analysis.binaries, analysis.datas, name="control-plane", upx=False)
