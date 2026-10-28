"""The Windows icon derives only from unchanged existing Hermione artwork."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtGui import QImage,QIcon
from PySide6.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('granger_icon_generator',ROOT/'scripts/generate_app_icon.py')
generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)

def test_multi_resolution_ico_matches_original_source_and_png_entries():
    app=QApplication.instance() or QApplication([])
    source=ROOT/'grangerpet/assets/character.png'
    before=source.read_bytes()
    image=QImage(str(source));data=generator.icon_bytes(image)
    assert source.read_bytes()==before
    assert data==(ROOT/'resources/Granger-OSINT.ico').read_bytes()
    assert struct.unpack_from('<HHH',data)==(0,1,7)
    sizes=[]
    for i in range(7):
        width,height,_,_,planes,bpp,length,offset=struct.unpack_from('<BBBBHHII',data,6+i*16)
        size=width or 256;sizes.append(size)
        assert (height or 256)==size and planes==1 and bpp==32
        encoded=data[offset:offset+length]
        assert encoded.startswith(b'\x89PNG\r\n\x1a\n')
        decoded=QImage.fromData(encoded)
        assert decoded.width()==size and decoded.height()==size and decoded.hasAlphaChannel()
    assert tuple(sizes)==generator.SIZES
    icon=QIcon(str(ROOT/'resources/Granger-OSINT.ico'))
    assert sorted(size.width() for size in icon.availableSizes())==list(generator.SIZES)

def test_icon_is_exact_crop_with_no_new_face_or_background():
    app=QApplication.instance() or QApplication([])
    source=QImage(str(ROOT/'grangerpet/assets/character.png'))
    portrait=generator.icon_image(source)
    assert portrait.size().width()==portrait.size().height()==384
    assert portrait.pixelColor(0,0).alpha()==0
    for x,y in ((160,170),(200,170),(160,200),(270,130)):
        assert portrait.pixelColor(x-64,y-8+32)==source.pixelColor(x,y)
    provenance=json.loads((ROOT/'resources/Granger-OSINT-icon.provenance.json').read_text(encoding='utf-8'))
    assert provenance['source_sha256']==hashlib.sha256((ROOT/provenance['source']).read_bytes()).hexdigest()
    assert 'NOT been established' in provenance['rights']

