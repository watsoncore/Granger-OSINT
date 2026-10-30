"""Technical page navigation stays available as evidence, outside main branches."""
from urllib.parse import urlsplit
import re


def unscoped_web_marker(record):
    """CSS-like scraped markers without a Telegram source need source review."""
    details=record.get('details') or {}
    if record.get('type')!='label' or not isinstance(details,dict) or record.get('url'):
        return False
    label=details.get('label') or record.get('title') or ''
    if not isinstance(label,str) or not re.fullmatch(r'Telegram marker: @(?:media|supports|font-face|keyframes|import|page|charset|layer)',label,re.I):
        return False
    return str(details.get('source') or '').endswith('_public') and not any(
        details.get(field) for field in ('source_url','telegram_url','observed_text','content_region'))


def technical_url(value):
    try:parts=urlsplit(value);host=(parts.hostname or '').lower();path=parts.path.lower()
    except (TypeError,ValueError):return True
    if host in ('camo.githubusercontent.com','avatars.githubusercontent.com','github.githubassets.com'):return True
    if host in ('githubstatus.com','www.githubstatus.com','support.github.com','support.github.io','github.community'):return True
    if host=='docs.github.com' and any(part in path for part in ('reporting-abuse','reporting-abuse-or-spam','contacting-github-support','site-policy','privacy','terms-of-service')):return True
    if host=='github.com':
        segments=path.strip('/').split('/')
        if segments[0] in ('login','signup','settings','features','enterprise','pricing','marketplace','sponsors','topics','collections','about','security','site','contact','readme','customer-stories','solutions','resources','search','sessions','notifications','orgs'):return True
        if len(segments)>2 and segments[2] in ('stargazers','watchers','forks','network','pulse'):return True
    return host in ('telegram.org','desktop.telegram.org','apps.apple.com','play.google.com')


CONTENT_REGIONS=frozenset(('main_content','authored_content','content_block','profile_field','post_content','record_field'))


def substantive_link(link):
    """Unknown legacy anchors are not upgraded to author claims by a page hash."""
    return (isinstance(link,dict) and isinstance(link.get('url'),str) and not technical_url(link['url'])
        and link.get('content_region') in CONTENT_REGIONS
        and link.get('extraction_method') in ('inert_html_parser','inert_xml_parser','official_api','public_post_parser'))
