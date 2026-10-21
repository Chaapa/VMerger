"""Download pinned portable dependencies. Requires Visual Studio C++ Build Tools for pgvector."""
import hashlib
from pathlib import Path
import subprocess
import urllib.request
import zipfile

root = Path(__file__).resolve().parents[1]
tools = root / ".local/tools"
tools.mkdir(parents=True, exist_ok=True)
packages = [
    ("postgres", "https://get.enterprisedb.com/postgresql/postgresql-18.6-1-windows-x64-binaries.zip",
     "fbe23da234ee31547bf8a36d29dfd81e82b849df2d2b78d2eecb43d360252f8c"),
    ("weed", "https://github.com/seaweedfs/seaweedfs/releases/download/4.49/windows_amd64.zip",
     "34f722f32399293721ba5d87f59a2ee9d108f09267f8a6a6bc8b8c84d72ab171"),
    ("ffmpeg", "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip",
     "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"),
    ("pgvector", "https://github.com/pgvector/pgvector/archive/refs/tags/v0.8.7.zip",
     "7b3b8188a5cc0aa96db3c8f3fca1e78a8a612c46545065490c76448705c6b29e"),
]
for name, url, expected in packages:
    archive = tools / (name + ".zip")
    if not archive.exists():
        print("Downloading", name, flush=True)
        urllib.request.urlretrieve(url, archive)
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {name}")
    destination = tools / name
    if not destination.exists():
        with zipfile.ZipFile(archive) as zipped:
            for item in zipped.infolist():
                if not (destination / item.filename).resolve().is_relative_to(destination.resolve()):
                    raise ValueError("Unsafe archive path")
            zipped.extractall(destination)
    print("Verified", name, flush=True)
vswhere = Path("C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe")
vs = subprocess.check_output([str(vswhere), "-latest", "-products", "*", "-requires",
    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
if not vs:
    raise RuntimeError("Install Visual Studio Build Tools with C++ desktop development, or use Docker")
pgroot = tools / "postgres/pgsql"
batch = root / ".local/build-vector.cmd"
batch.write_text(f'@echo off\ncall "{vs}\\VC\\Auxiliary\\Build\\vcvars64.bat"\n'
                 f'set "PGROOT={pgroot}"\nnmake /F Makefile.win\nif errorlevel 1 exit /b 1\nnmake /F Makefile.win install\n')
subprocess.run(["cmd.exe", "/c", str(batch)], cwd=tools / "pgvector/pgvector-0.8.7", check=True)
print("Portable dependencies are ready. Run scripts/start_native.py next.")
