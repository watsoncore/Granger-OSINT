"""Integrity boundary for the user's original artwork; derivatives stay separate."""
import hashlib
import json


def verify_original_assets(directory):
    manifest=json.loads((directory/'original-hermione/identity.json').read_text(encoding='utf-8'))
    prefix='grangerpet/assets/'
    for name,digest in manifest['immutable_files'].items():
        if not name.startswith(prefix):continue  # Source-only reference files.
        file=directory/name[len(prefix):]
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
            raise ValueError('Изменён исходный asset Гермионы: '+name+'. Восстановите проверенный оригинал.')
    neutral=directory/'original-hermione/neutral-512.png'
    if hashlib.sha256(neutral.read_bytes()).hexdigest()!=manifest['derived_neutral']['sha256']:
        raise ValueError('Изменён проверенный neutral reference Гермионы')
    return manifest
