"""Offline Florence caption + dense regions, one disposable bounded CPU worker."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time


def infer(raw, model_path):
    import torch
    from transformers import Florence2ForConditionalGeneration, AutoProcessor
    from .worker import open_image
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    image = open_image(raw)
    model = Florence2ForConditionalGeneration.from_pretrained(str(model_path), local_files_only=True,
        trust_remote_code=False, dtype=torch.float32, attn_implementation='eager').eval()
    processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    def task(prompt, tokens, text=''):
        inputs = processor(text=prompt+text, images=image, return_tensors='pt')
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=tokens, num_beams=1, do_sample=False)
        text = processor.batch_decode(output, skip_special_tokens=False)[0]
        return processor.post_process_generation(text, task=prompt, image_size=image.size).get(prompt)
    caption = task('<MORE_DETAILED_CAPTION>', 256)
    regions = task('<DENSE_REGION_CAPTION>', 384)
    if not isinstance(caption, str) or not caption.strip():
        raise ValueError('empty_scene_description')
    grounded = task('<CAPTION_TO_PHRASE_GROUNDING>', 384, caption)
    observations = []
    regions = regions if isinstance(regions, dict) else {}
    grounded = grounded if isinstance(grounded, dict) else {}
    boxes = list(zip(regions.get('bboxes', []), regions.get('labels', []), ['dense_region_caption']*len(regions.get('bboxes', []))))
    boxes += list(zip(grounded.get('bboxes', []), grounded.get('labels', []), ['caption_phrase_grounding']*len(grounded.get('bboxes', []))))
    for box, label, method in boxes:
        if (not isinstance(box, (list, tuple)) or len(box) != 4 or not isinstance(label, str)
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in box)):
            continue
        normalized = [max(0.0, min(1.0, value/(image.width if index % 2 == 0 else image.height))) for index, value in enumerate(box)]
        if normalized[0] >= normalized[2] or normalized[1] >= normalized[3]:
            continue
        observations.append({'type':'visual_region', 'description':label, 'region':normalized,
            'confidence_kind':'model_estimate', 'extraction_method':'florence_'+method})
    return {'status':'completed', 'scene_type':'model_described_scene', 'description':caption,
        'observations':observations, 'readable_text':[], 'possible_languages':[], 'road_features':[],
        'vegetation':[], 'terrain':[], 'distinctive_landmarks':[],
        'coordinate_space':'normalized_xyxy_original_oriented_image',
        'input_sha256':hashlib.sha256(raw).hexdigest(), 'pixels_analyzed':True, 'image_uploaded':False,
        'limitations':['Описание и области — оценки vision-модели; возможны ошибки распознавания.',
            'Captioning не подтверждает личность, место или язык вывесок. OCR выполняется отдельным локальным этапом.',
            'Мелкие детали и надписи могут быть неразличимы; модель не выдаёт калиброванную вероятность.']}


def main():
    from ..web_render_worker import _binary_pipe
    incoming, outgoing = _binary_pipe('stdin'), _binary_pipe('stdout')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    sys.stdout = sys.stderr
    started = time.monotonic()
    stage = 'scene_runtime_not_installed'
    try:
        from .worker import configure_runtime
        configure_runtime(os.environ['GRANGERPET_VISUAL_ROOT'])  # Enforces socket-level offline mode.
        from .scene import manifest
        lock = manifest()
        root = Path(os.environ['GRANGERPET_SCENE_ROOT'])/'model'
        stage = 'scene_artifact_invalid'
        for artifact in lock['artifacts']:
            path = root/artifact['relative_path']
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                while block := stream.read(1024*1024):
                    digest.update(block)
            if path.stat().st_size != artifact['bytes'] or digest.hexdigest() != artifact['sha256']:
                raise ValueError()
        stage = 'scene_invalid_input'
        request = incoming.readline(28_000_001)
        if len(request) > 28_000_000:
            raise ValueError()
        value = json.loads(request.decode('utf-8'))
        raw = base64.b64decode(value['image'], validate=True)
        if not 0 < len(raw) <= 20*1024*1024:
            raise ValueError()
        stage = 'scene_inference_failed'
        result = infer(raw, root)
        from .worker import process_memory
        result.update(model_version=lock['model']+'@'+lock['revision'], model_sha256={
            row['relative_path']:row['sha256'] for row in lock['artifacts'] if row['relative_path'].endswith('.safetensors')},
            duration_ms=round((time.monotonic()-started)*1000), **process_memory())
    except Exception as error:
        result = {'status':'error','error_code':stage,'error_kind':type(error).__name__}
    outgoing.write(json.dumps(result, ensure_ascii=False).encode('utf-8')+b'\n')
    outgoing.flush()
    return 0 if result.get('status') == 'completed' else 2
