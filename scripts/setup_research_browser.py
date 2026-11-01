"""Prepare only a separate official Playwright runtime; use installed Edge."""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    runtime=ROOT/'.toolenvs/research-browser'
    python=runtime/'Scripts/python.exe'
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    if not python.is_file():subprocess.run([sys.executable,'-m','venv',str(runtime)],check=True,creationflags=flags)
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--only-binary=:all:',
        '--index-url','https://pypi.org/simple','-r',str(ROOT/'resources/browser-runtime-requirements.txt')],
        check=True,creationflags=flags)
    print('Separate runtime ready. No Chromium download;installed Edge is required. Main Qt environment unchanged.')


if __name__=='__main__':main()
