"""Install pinned MIT Florence weights; reuse verified optional CPU dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Download the reviewed pinned model artifacts')
    args = parser.parse_args()
    from grangerpet.visual_models.installation import download
    from grangerpet.visual_models.manager import default_runtime_root
    manifest_path = ROOT/'grangerpet/visual_models/scene_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    runtime = default_runtime_root()
    target = ROOT/'.toolenvs/scene-vision'
    if not args.install:
        print(json.dumps({'download_bytes':manifest['download_bytes'], 'license':manifest['license'],
            'model':manifest['model'], 'revision':manifest['revision'], 'remote_code':False,
            'cpu_dependencies_available':(runtime/'site-packages/transformers/models/florence2').is_dir()}, indent=2))
        return
    if not (runtime/'receipt.json').is_file() or not (runtime/'site-packages/transformers/models/florence2').is_dir():
        raise SystemExit('Install and verify the optional visual CPU runtime first. No environment was changed.')
    if shutil.disk_usage(ROOT).free < manifest['download_bytes']*2+500_000_000:
        raise SystemExit('Insufficient free disk for verified staging and model.')
    target.mkdir(parents=True, exist_ok=True)
    last = [0.0]
    def progress(event):
        if event.get('bytes') == event.get('total_bytes') or time.monotonic()-last[0] > 10:
            last[0] = time.monotonic()
            print(json.dumps(event), flush=True)
    for artifact in manifest['artifacts']:
        download(artifact, target/'model'/artifact['relative_path'], progress=progress)
    receipt = {'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'model':manifest['model'], 'revision':manifest['revision'], 'license':manifest['license'],
        'files_verified':True, 'inference_verified':False, 'runtime_modified':False}
    (target/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print('Pinned files verified. Live CPU inference has not yet been verified.')


if __name__ == '__main__': main()
