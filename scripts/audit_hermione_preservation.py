"""Anonymous, read-only preservation check; never publish profile paths/hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def unchanged(root,expected):
    return sum((root/name).is_file() and hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
        for name,digest in expected.items())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    stage=json.loads(args.baseline.read_text(encoding='utf-8'))
    original=json.loads((ROOT/'output/chibi-reconstruction/baseline.json').read_text(encoding='utf-8'))
    profile=Path(os.environ['APPDATA'])/'GrangerPet'
    groups={'current_stage_profile':(profile,stage['profile']),
        'existing_guest_assets':(ROOT,stage['guest_assets']),'original_character_assets':(ROOT,original['assets'])}
    result={'method':'Read-only SHA-256 counts; no profile values, ciphertexts, names or hashes published',
        'groups':{name:{'files':len(expected),'unchanged':unchanged(root,expected)} for name,(root,expected) in groups.items()},
        'earlier_dialog_anomaly':'One encrypted dialog differed before this stage. User denied editing it. Cause unresolved; preserved without rollback, decryption or publication.'}
    result['passed']=all(row['files']==row['unchanged'] for row in result['groups'].values())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
