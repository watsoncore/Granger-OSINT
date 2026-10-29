"""Optional isolated visual inference; importing never loads/downloads a model."""
def __getattr__(name):
    if name in ('VisualModelManager','default_runtime_root'):
        from . import manager
        return getattr(manager,name)
    raise AttributeError(name)

__all__=['VisualModelManager','default_runtime_root']
