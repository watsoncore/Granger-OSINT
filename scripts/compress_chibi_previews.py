"""Export compact review copies of real captures; retain original frames locally."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'method':'Animated WebP quality 90; native dimensions, original order and timing. '
        'Identical adjacent frames may be coalesced by the codec. Original lossless WebP/PNG retained locally.',
        'clips':[]}
    for source in sorted(args.source.glob('*.webp')):
        destination=args.output/source.name
        if destination.exists():raise ValueError('Previous review exports preserved: '+str(destination))
        frames=[];durations=[]
        with Image.open(source) as clip:
            for i in range(clip.n_frames):
                clip.seek(i);clip.load();frames.append(clip.convert('RGB'))
                durations.append(clip.info['duration'])
        frames[0].save(destination,save_all=True,append_images=frames[1:],duration=durations,
            quality=90,method=4,loop=0)
        with Image.open(destination) as check:
            actual_duration=0
            for i in range(check.n_frames):
                check.seek(i);check.load();actual_duration+=check.info['duration']
            if check.size!=frames[0].size or actual_duration!=sum(durations):
                raise AssertionError('Review copy changed camera or duration')
        row={'name':source.stem,'native_dimensions':frames[0].size,'duration_ms':sum(durations),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'preview_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
            'bytes':destination.stat().st_size,'codec_frames':len(frames)}
        report['clips'].append(row);print(json.dumps(row),flush=True)
    (args.output/'encoding.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
