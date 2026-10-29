import sys

if '--public-render-worker' in sys.argv:
    from grangerpet.web_render_worker import main
else:
    from grangerpet.app import main


if __name__ == "__main__":
    raise SystemExit(main())
