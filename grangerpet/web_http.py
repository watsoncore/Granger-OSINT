"""Pinned public text requests with shared limits and scoped session cookies."""
from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import urljoin,urlsplit,urlencode,urlunsplit

import httpx


async def fetch_public(url,*,method='GET',form=None,approved_post=False,cancel_event=None,
                       deadline=None,resolver=None,client_factory=None,cookies=None,rate_interval=.25,
                       allowed_types=None,params=None,accepted_statuses=(200,),user_agent=None,before_request=None):
    """Public-only raw text transport for reviewed source-specific adapters.

    It deliberately accepts no arbitrary headers or credentials. POST must be a
    caller-reviewed public search form, never a login/upload/state change. Every
    redirect resolves again and every connection uses a validated literal IP.
    """
    from .agent_browser import (MAX_BYTES,PageReadError,PinnedTransport,resolve_public,public_address,
        public_url,_SENSITIVE_QUERY,_REQUEST_SLOTS,_DOMAIN_LOCK,_DOMAIN_SLOTS,_DOMAIN_NEXT,_DOMAIN_USERS)
    from .download_budget import check as check_bytes
    check_bytes()
    method=str(method).upper()
    agent=user_agent or 'Granger-OSINT/3.1 (+https://github.com/watsoncore/Granger-OSINT) public-reader'
    if not isinstance(agent,str) or not 1<=len(agent)<=240 or any(ord(c)<32 or ord(c)>126 for c in agent):
        raise PageReadError('invalid_application_identity','blocked')
    if params:
        parsed=urlsplit(url)
        query=parsed.query+('&' if parsed.query else '')+urlencode(params,doseq=True)
        url=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,query,''))
    if method not in ('GET','POST'):raise PageReadError('method_not_supported','blocked')
    if method=='POST' and (not approved_post or not isinstance(form,dict) or not 1<=len(form)<=20):
        raise PageReadError('unreviewed_search_form','blocked')
    if form is not None and (method!='POST' or any(not isinstance(k,str) or _SENSITIVE_QUERY.search(k)
        or not isinstance(v,(str,int)) or len(str(v))>1000 for k,v in form.items())):
        raise PageReadError('unsafe_search_form','blocked')
    end=deadline or time.monotonic()+15
    factory=client_factory or httpx.AsyncClient;resolve=resolver or resolve_public
    jars=cookies if cookies is not None else {}
    accepted=allowed_types or ('text/html','application/xhtml+xml','text/plain','application/json','application/ld+json',
        'application/xml','text/xml','application/rss+xml','application/atom+xml','text/csv','application/csv','text/tab-separated-values','application/pdf')
    async def check():
        if cancel_event and cancel_event.is_set():raise PageReadError('cancelled','cancelled')
        if time.monotonic()>=end:raise PageReadError('timeout','timeout')
    async def acquire(semaphore):
        while not semaphore.acquire(blocking=False):await check();await asyncio.sleep(.02)
    redirects=[]
    for hop in range(4):
        await check();url=public_url(url);parsed=urlsplit(url);host=parsed.hostname
        if before_request is not None:await before_request(url)
        port=443 if parsed.scheme=='https' else 80
        addresses=await resolve(host,port)
        if not addresses or any(not public_address(address) for address in addresses):
            raise PageReadError('private_or_service_address','blocked')
        with _DOMAIN_LOCK:
            if len(_DOMAIN_SLOTS)>=256 and host not in _DOMAIN_SLOTS:
                expired=next((key for key in _DOMAIN_SLOTS if not _DOMAIN_USERS.get(key)),None)
                if expired is None:raise PageReadError('domain_budget_exhausted','limit_reached')
                _DOMAIN_SLOTS.pop(expired,None);_DOMAIN_NEXT.pop(expired,None);_DOMAIN_USERS.pop(expired,None)
            import threading
            domain_slot=_DOMAIN_SLOTS.setdefault(host,threading.BoundedSemaphore(1))
            _DOMAIN_USERS[host]=_DOMAIN_USERS.get(host,0)+1
        domain_owned=False;global_owned=False
        try:
            await acquire(domain_slot);domain_owned=True
            while True:
                with _DOMAIN_LOCK:remaining=_DOMAIN_NEXT.get(host,0)-time.monotonic()
                if remaining<=0:break
                await check();await asyncio.sleep(min(.03,remaining))
            await acquire(_REQUEST_SLOTS);global_owned=True
            with _DOMAIN_LOCK:_DOMAIN_NEXT[host]=time.monotonic()+max(0,min(5,rate_interval))
            # No session cookies ever cross origins. Jar is task-local memory,
            # never imported from browsers, credentials or persisted evidence.
            origin=(parsed.scheme,host)
            jar=jars.setdefault(origin,httpx.Cookies())
            response_data=None
            for attempt in range(2):
                await check()
                transport=PinnedTransport(host,port,addresses)
                async with factory(transport=transport,trust_env=False,follow_redirects=False,
                    timeout=httpx.Timeout(min(10,max(.1,end-time.monotonic()))),cookies=jar,
                    headers={'User-Agent':agent,
                             'Accept':', '.join(accepted),'Accept-Encoding':'gzip, deflate'}) as client:
                    async with client.stream(method,url,data=form if method=='POST' else None) as response:
                        status=response.status_code
                        if status in (502,503) and method=='GET' and attempt==0:
                            await check();await asyncio.sleep(min(.25,max(0,end-time.monotonic())));continue
                        if status==429:
                            try:backoff=max(1,min(60,float(response.headers.get('retry-after','5'))))
                            except ValueError:backoff=5
                            with _DOMAIN_LOCK:_DOMAIN_NEXT[host]=time.monotonic()+backoff
                        jar.update(response.cookies)
                        if len(jar)>40:
                            jar.clear()
                        headers={key:response.headers[key] for key in ('content-type','content-security-policy','location','retry-after',
                            'x-ratelimit-remaining','x-ratelimit-reset','link','etag','last-modified') if key in response.headers}
                        if status in (301,302,303,307,308):
                            response_data={'status':status,'headers':headers};break
                        if status not in accepted_statuses and (status in (401,403,407,429) or status>=400):
                            raise PageReadError('http_'+str(status),'auth_required' if status in (401,407) else 'unavailable')
                        if status not in accepted_statuses:raise PageReadError('http_'+str(status))
                        content_type=response.headers.get('content-type','').lower()
                        if status==200 and not any(kind in content_type for kind in accepted):raise PageReadError('unsupported_content_type')
                        length=response.headers.get('content-length','')
                        if length.isdigit() and int(length)>MAX_BYTES:raise PageReadError('response_too_large')
                        chunks=bytearray()
                        async for chunk in response.aiter_bytes():
                            from .download_budget import consume
                            consume(len(chunk))
                            await check();chunks.extend(chunk)
                            if len(chunks)>MAX_BYTES:raise PageReadError('response_too_large')
                        return {'final_url':url,'status':status,'headers':headers,'body':bytes(chunks),
                            'content_type':content_type,'redirects':redirects,'method':method}
            if not response_data:raise PageReadError('network_error')
            if hop>=3:raise PageReadError('redirect_limit')
            location=response_data['headers'].get('location')
            if not location:raise PageReadError('invalid_redirect')
            target=public_url(urljoin(url,location))
            if parsed.scheme=='https' and urlsplit(target).scheme!='https':raise PageReadError('insecure_redirect','blocked')
            if method=='POST' and urlsplit(target).netloc!=parsed.netloc:
                raise PageReadError('cross_origin_post_redirect','blocked')
            if response_data['status'] in (301,302,303):method='GET';form=None
            redirects.append({'from':url,'to':target,'status':response_data['status']});url=target
        finally:
            if global_owned:_REQUEST_SLOTS.release()
            if domain_owned:domain_slot.release()
            with _DOMAIN_LOCK:_DOMAIN_USERS[host]=max(0,_DOMAIN_USERS.get(host,1)-1)
    raise PageReadError('redirect_limit')
