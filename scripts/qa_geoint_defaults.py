"""One bounded real no-key request per configured public mapping service."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from grangerpet.geoint.mapping import MappingClient
from grangerpet.geoint.images import GeointError

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'output/autonomous-qa/geoint-defaults-live.json');args=parser.parse_args()
 if args.output.exists():raise SystemExit('Preserve previous live evidence; choose a new output')
 client=MappingClient();rows=[]
 for tool,query in [('map_geocode','London Bridge'),('map_overpass','51.5007,-0.1246')]:
  try:result=client.execute(tool,query);rows.append({'tool':tool,'mock':False,'key_used':False,'endpoint_override':False,'result':result})
  except GeointError as error:rows.append({'tool':tool,'mock':False,'key_used':False,'endpoint_override':False,'error_code':error.code,'error':str(error)})
 report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Two individual public landmark lookups; no real user profile, key or picture read','executions':rows}
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps([{'tool':row['tool'],'status':row.get('result',{}).get('status'),'error_code':row.get('error_code'),'rows':len(row.get('result',{}).get('places',row.get('result',{}).get('objects',[])))} for row in rows]))
if __name__=='__main__':main()
