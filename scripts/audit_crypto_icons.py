"""Inventory the optional local pack without distributing its artwork."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def audit(pack,output):
    from PySide6.QtWidgets import QApplication
    from grangerpet.crypto_icons import FILES,load_icons
    app=QApplication.instance() or QApplication([])
    manifest=json.loads((pack/'manifest.json').read_text(encoding='utf-8'))
    metadata={value['file']:value for value in manifest.get('assets',{}).values()}
    loaded=load_icons(str(pack.parent))
    inventory=[]
    for path in sorted(pack.iterdir()):
        if not path.is_file():continue
        raw=path.read_bytes();entry={'file':path.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'redistribution':'excluded; local-only pack'}
        if path.name in metadata:
            expected=metadata[path.name].get('sha256')
            entry.update(manifest_present=True,manifest_hash_matches=expected==entry['sha256'] if expected else None)
        if path.suffix.lower() in ('.svg','.png'):
            key=next((key for key,name in FILES.items() if name==path.name),None)
            entry.update(registry_key=key,rasterization_passed=key in loaded['icons'])
        inventory.append(entry)
    report={'policy':'Local-only. The application source and EXE ship no supplied artwork. Typed fallback glyphs remain available.',
            'files':inventory,'missing_or_rejected':loaded['unavailable'],'loaded_count':len(loaded['icons']),
            'nominal_sizes_css_px':[16,20,24,32,48],'raster_size_px':128,
            'svg_checks':['viewBox','byte bound','element allowlist','event attributes','external references','active CSS','DOCTYPE/entities'],
            'classification':'Networks, assets, wallet applications, sourced services, generic types are separate. Labels never imply attribution.'}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'loaded':report['loaded_count'],'missing_or_rejected':report['missing_or_rejected']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pack',type=Path,default=ROOT/'crypto_icon');p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.pack,a.output)
