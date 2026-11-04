"""Old release entrypoints must stop before recreating archives or QA trees."""
import importlib

import pytest


@pytest.mark.parametrize('name',[
    'audit_v3_baseline',
    'package_pet_scene_validation',
    'package_reconstruction_validation',
])
def test_retired_export_has_no_filesystem_side_effects(name,tmp_path,monkeypatch):
    module=importlib.import_module('scripts.'+name)
    monkeypatch.setattr(module,'ROOT',tmp_path)
    for attribute in ('OUT','QA'):
        if hasattr(module,attribute):monkeypatch.setattr(module,attribute,tmp_path/'output')
    with pytest.raises(SystemExit,match='Retired'):
        module.main()
    assert not list(tmp_path.iterdir())
