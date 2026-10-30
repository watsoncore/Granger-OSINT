"""Technical page navigation stays available as evidence, outside main branches."""
from urllib.parse import urlsplit


def technical_url(value):
    try:parts=urlsplit(value);host=(parts.hostname or '').lower();path=parts.path.lower()
    except (TypeError,ValueError):return True
    if host in ('camo.githubusercontent.com','avatars.githubusercontent.com','github.githubassets.com'):return True
    if host=='github.com':
        segments=path.strip('/').split('/')
        if segments[0] in ('login','signup','settings','features','enterprise','pricing','marketplace','sponsors','topics','collections','about','security','site','contact','readme','customer-stories','solutions','resources','search'):return True
        if len(segments)>2 and segments[2] in ('stargazers','watchers','forks','network','pulse'):return True
    return host in ('telegram.org','desktop.telegram.org','apps.apple.com','play.google.com')
