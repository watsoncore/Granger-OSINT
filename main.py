import sys

if '--visual-model-worker' in sys.argv:
    from grangerpet.visual_models.worker import main
elif '--scene-vision-worker' in sys.argv:
    from grangerpet.visual_models.scene_worker import main
elif '--public-render-worker' in sys.argv:
    from grangerpet.web_render_worker import main
else:
    from grangerpet.app import main


if __name__ == "__main__":
    raise SystemExit(main())
