"""Run bounded public production-registry probes, at most two source workers."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
TON='UQCMUP3GW7s5i0dYOKgDc0b-mr6X0JhwopbQ30YUbzTdZKPd'
EVM='0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045'
CASES=[(chain,address,'profile')for chain,address in [
    ('btc','1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'),('doge','DH5yaieqoZN36fDVciNyRueRGvGLR3mr7L'),
    *[(chain,EVM)for chain in ('eth','bsc','polygon','arbitrum','optimism','avalanche')],
    ('tron','TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'),('ton',TON),('solana','So11111111111111111111111111111111111111112')]]
CASES += [('ton',TON,'nft'),('auto','vitalik.eth','identity'),('auto','foundation.ton','nft'),('auto','invalid-address','profile')]

def main():
    out=ROOT/'output/masterfix/live-matrix-01';out.mkdir(parents=True,exist_ok=False)
    def run(case):
        chain,address,operation=case;label=chain+'-'+operation+('-'+address if address.endswith(('.eth','.ton')) else '')
        target=out/label
        result=subprocess.run([sys.executable,str(ROOT/'scripts/qa_masterfix_blockchain_live.py'),'--output',str(target),
            '--chain',chain,'--address',address,'--operation',operation],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
        report=json.loads((target/'report.json').read_text(encoding='utf-8')) if (target/'report.json').exists() else {'status':'harness_error','returncode':result.returncode}
        return label,report
    results={}
    with ThreadPoolExecutor(max_workers=2)as pool:
        for future in as_completed([pool.submit(run,case)for case in CASES]):
            label,report=future.result();results[label]=report
            (out/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(label,report['status'],report.get('count'),flush=True)
if __name__=='__main__':main()
