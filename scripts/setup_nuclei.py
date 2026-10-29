r"""Install only the pinned official optional Windows CLI; no shell installer.

Usage: .venv\Scripts\python scripts\setup_nuclei.py [--archive PATH]
The runtime stays outside the main EXE in .toolenvs/nuclei/3.11.1.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from grangerpet.integrations19.nuclei import VERSION,ZIP_SHA256,EXE_SHA256,RELEASE


def install(archive=None):
    target=ROOT/'.toolenvs'/'nuclei'/VERSION;target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='granger-nuclei-install-') as temp:
        path=Path(archive) if archive else Path(temp)/'release.zip'
        if archive is None:
            request=urllib.request.Request(RELEASE+'nuclei_'+VERSION+'_windows_amd64.zip',headers={'User-Agent':'Granger-OSINT optional-runtime-setup'})
            with urllib.request.urlopen(request,timeout=30) as response,path.open('wb') as output:
                total=0
                while chunk:=response.read(1024*1024):
                    total+=len(chunk)
                    if total>60*1024*1024:raise ValueError('Release exceeds pinned size budget')
                    output.write(chunk)
        with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        if digest!=ZIP_SHA256:raise ValueError('Official archive checksum mismatch')
        with zipfile.ZipFile(path) as source:
            binary=source.read('nuclei.exe');license_text=source.read('LICENSE.md')
        if hashlib.sha256(binary).hexdigest()!=EXE_SHA256:raise ValueError('Pinned binary checksum mismatch')
        stage=target/'nuclei.exe.installing';stage.write_bytes(binary);os.replace(stage,target/'nuclei.exe')
        (target/'LICENSE.md').write_bytes(license_text)
        (target/'manifest.json').write_text(json.dumps({'version':VERSION,'platform':'windows_amd64','archive_sha256':ZIP_SHA256,
            'binary_sha256':EXE_SHA256,'source':RELEASE,'license':'MIT','optional':True},indent=2)+'\n',encoding='utf-8')
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive',type=Path)
    args=parser.parse_args();print(install(args.archive))
