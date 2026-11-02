"""Actual key-free DEM/history/regional-source receipts, no user photographs."""
import argparse
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.geoint.open_geography import OpenGeography
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise SystemExit('Prior receipts preserved')
    args.output.mkdir(parents=True);source=OpenGeography();summary=[]
    for method,name,lat,lon in [('terrain','Medeu',43.157,77.058),('terrain','Dolomites',46.5,11.8),
            ('historical','Rome',41.89,12.49),('regional','Interlaken',46.686,7.86)]:
        start=time.monotonic()
        try:
            value=getattr(source,method)({'latitude':lat,'longitude':lon},deadline=start+45)
            (args.output/(method+'-'+name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            row={key:value.get(key) for key in ('status','source','source_url','valid_points','point_count','center_elevation_m','sampled_relief_m','feature_count','item_count_returned','collection_license','assets_downloaded','receipt','receipts','collection_receipt') if key in value}
            row.update(control=name,method=method,seconds=round(time.monotonic()-start,3),status=value.get('status','complete'))
        except Exception as error:row={'control':name,'method':method,'status':'unavailable','error_code':getattr(error,'code',type(error).__name__),'seconds':round(time.monotonic()-start,3)}
        summary.append(row);(args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({key:row[key] for key in ('control','method','status','seconds')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
