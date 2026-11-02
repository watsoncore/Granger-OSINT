"""Evidence-bound GEOINT view. Reading it never runs a model or a network call."""
from copy import deepcopy
import re

from ..agent_evidence import current_observation
from ..public_media import MediaStore, media_reference
from .research import hypotheses


def present(snapshot, *, store, media_store=None, cancel_event=None):
    media_store=media_store or MediaStore()
    records=[current_observation(row) for row in snapshot.get('evidence',[]) if isinstance(row,dict)]
    attachments=set();candidates={};scenes=[];images=[];diagnostics=[]
    for row in records:
        if cancel_event and cancel_event.is_set():raise InterruptedError('GEOINT view cancelled')
        data=row.get('details') or {}
        if not isinstance(data,dict):continue
        identifier=data.get('attachment_id')
        if not identifier and isinstance(data.get('image'),dict):identifier=data['image'].get('id')
        if isinstance(identifier,str) and re.fullmatch(r'img_[a-f0-9]{64}',identifier):attachments.add(identifier)
        if data.get('tool')=='image_understand':
            from .scene_language import russian_scene
            localized=russian_scene(data)
            scenes.append({'evidence_id':row.get('evidence_id'),'attachment_id':identifier,
                **{key:deepcopy(localized[key]) for key in ('description','description_original','description_presentation','observations','model_version','limitations') if key in localized}})
        if row.get('type')=='geoint_candidate' and data.get('candidate_id'):
            candidates[data['candidate_id']]={key:deepcopy(data[key]) for key in ('candidate_id','attachment_id','latitude','longitude',
                'region','source_model','raw_score','verification_status','model_observations','nearby_landmarks','reference_images',
                'research_queries','uncertainty_radius_m','supporting_evidence','contradicting_evidence','location_role',
                'camera_position_verified','terrain_geometry','reference_selection','review_order','review_score') if key in data}
            candidates[data['candidate_id']]['evidence_id']=row.get('evidence_id')
        if row.get('type')=='reference_image':
            reference=media_reference(row)
            try:
                cached=media_store.cached(reference) if reference else None
                if cached and hasattr(media_store,'comparison_preview'):
                    cached={**cached,'thumbnail':media_store.comparison_preview(reference)}
            except (OSError,ValueError):cached=None
            images.append({'evidence_id':row.get('evidence_id'),'candidate_id':data.get('candidate_id'),'attachment_id':identifier,
                'title':row.get('title'),'source_url':row.get('url'),
                **{key:deepcopy(data[key]) for key in ('provider','image_url','original_image_url','license','license_url','author','captured_at',
                    'latitude','longitude','comparison','reference_scene','match_kind','distance_to_candidate_m','selection') if key in data},
                'media':cached or {'state':'unavailable'}})
            if isinstance(images[-1].get('reference_scene'),dict):
                from .scene_language import russian_scene
                images[-1]['reference_scene']=russian_scene(images[-1]['reference_scene'])
        if row.get('type')=='geoint_research_report':
            diagnostics.append({key:deepcopy(data[key]) for key in ('stages','source_diagnostics','optional_providers','limitations') if key in data})
    images=[image for image in images if (image.get('selection') or {}).get('score',0)>=0]
    images.sort(key=lambda image:-(image.get('selection') or {}).get('score',0))
    if not candidates:
        for identifier in attachments:
            for candidate in hypotheses(records,identifier):candidates[candidate['candidate_id']]=candidate
    originals=[]
    for identifier in sorted(attachments)[:4]:
        try:
            preview=store.comparison_preview(identifier,cancel_event)
            originals.append({'attachment_id':identifier,'thumbnail':preview,'state':'ready'})
        except (ValueError,OSError):
            originals.append({'attachment_id':identifier,'state':'unavailable'})
    return {'state':'ready','investigation_id':snapshot.get('id'),'revision':snapshot.get('checkpoint_revision',0),
        'scenes':scenes,'originals':originals,'candidates':sorted(candidates.values(),key=lambda candidate:candidate.get('review_order',1000)),'images':images,'diagnostics':diagnostics,
        'has_geoint':bool(attachments or candidates or images),'map_attribution':'© OpenStreetMap contributors',
        'limitations':['Модельные точки и разброс не являются точностью определения адреса.',
            'Геопривязка эталона относится к эталону. Совпадения деталей фасада не доказывают один ракурс.']}
