"""Build bounded cached layers from approved art and a documented hair repair."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--hair-repair',type=Path,required=True)
    args=parser.parse_args()
    source=args.hair_repair.resolve();out=ROOT/'grangerpet/assets/scenes'
    # ImageGen's head is independently fitted to the original hair bounding box.
    # Only the occluded left curl is consumed; original face/bangs/right hair
    # are copied byte-for-byte before premultiplied composition at runtime.
    generated=Image.open(source).convert('RGBA')
    generated.putalpha(generated.getchannel('A').point(lambda a:a if a>8 else 0));box=generated.getbbox()
    cropped=generated.crop(box);aligned=Image.new('RGBA',(512,512))
    aligned.alpha_composite(cropped.resize((372,297),Image.Resampling.LANCZOS),(70,14))
    target=out/'hermione-left-curl-v2.png'
    # Keep 12px overlap for a soft interior transition, never feather outer alpha.
    mask=Image.new('L',(512,512));pixels=mask.load()
    for y in range(178,332):
        for x in range(60,151):
            pixels[x,y]=round(255*min(1,max(0,(151-x)/12))*min(1,max(0,(y-178)/10)))
    alpha=aligned.getchannel('A')
    from PIL import ImageChops
    aligned.putalpha(ImageChops.multiply(alpha,mask));aligned.save(target)
    archive=ROOT/'resources/cameo-masters/hermione-hair-repair-source.png'
    if not archive.exists():archive.write_bytes(source.read_bytes())
    metadata={'generator':'built-in ImageGen; head-only removal of original wand/hand',
        'source':str(archive.relative_to(ROOT)).replace('\\','/'),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_alpha_bbox':box,
        'used_region':'Only left outer curl x60..151 y184..332; original face and all other hair retained',
        'aligned_original_hair_bbox':[70,14,442,311],
        'target':str(target.relative_to(ROOT)).replace('\\','/'),
        'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (out/'articulated-provenance.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata))


if __name__=='__main__':main()
