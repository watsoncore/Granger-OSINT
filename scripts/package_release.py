"""Compatibility entrypoint for the single checked canonical EXE release.

Source ZIPs, release directories, backups and sidecar files in dist are retired.
Run build.ps1 for dependency/frontend preparation, or this entrypoint afterwards.
Obsolete --qa/--dist-dir arguments are deliberately rejected.
"""
if __package__:
    from .build_release import main
else:
    from build_release import main


if __name__ == '__main__':
    raise SystemExit(main())
