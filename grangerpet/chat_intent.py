"""Conversation-scoped read-only research intent; no network or permission grants."""
from dataclasses import dataclass
import re
from .context import is_social_turn,is_defer_turn
from .entity_router import route,route_goal


def concrete_targets(text):
    return [target for target in route_goal(text) if target.entity_type not in ('username',)]


def explicit_research(text):
    return bool(concrete_targets(text)) or bool(re.search(r'(?iu)(найд[иуё]|найти|поищ|поиск|провер[ьить]|исслед|упоминан|сопостав|пробей|whois|rdap|dns|lookup|investigat|search\b|профил|кошел[её]к|блокчейн|прочита|прочти|открой|изучи|страниц|https?://|geoint|geoclip|waypoint|инвентар|(?:какие|доступн|готов).{0,35}инструмент|инструмент.{0,35}(?:доступн|готов))',text))


@dataclass
class SessionIntent:
    conversation_id:str=''
    target:dict|None=None

    def reset(self,conversation_id=''):
        self.conversation_id=conversation_id;self.target=None

    def restore(self,messages,conversation_id):
        self.reset(conversation_id)
        for row in reversed(messages[-50:]):
            if not isinstance(row,dict) or row.get('role')!='user':continue
            text=row.get('text','')
            if is_defer_turn(text):return
            targets=concrete_targets(text)
            if targets:self.target=targets[0].to_dict();return
            images=row.get('attachments',[])
            if isinstance(images,list):
                for image in images:
                    target=route(image.get('id','')) if isinstance(image,dict) else None
                    if target and target.entity_type=='image':self.target=target.to_dict();return

    def decide(self,text,conversation_id,*,no_tools=False,images=()):
        if self.conversation_id!=conversation_id:self.reset(conversation_id)
        if is_defer_turn(text):self.target=None;return {'kind':'defer','entity_context':None}
        if is_social_turn(text) and not images:return {'kind':'social','entity_context':None}
        targets=concrete_targets(text)
        if targets:self.target=targets[0].to_dict()
        elif isinstance(images,(list,tuple)):
            for image in images:
                target=route(image.get('id','')) if isinstance(image,dict) else None
                if target and target.entity_type=='image':self.target=target.to_dict();break
        if no_tools:return {'kind':'conversation','entity_context':None}
        scoped=False
        if self.target and not targets:
            kind=self.target['entity_type']
            scoped=bool(re.fullmatch(r'(?iu)\s*(?:разрешаю|можешь проверить|запускай проверку)[.!?\s]*',text))
            if kind in ('infrastructure_asset','network_range','autonomous_system','domain','website'):
                scoped |= bool(re.search(r'(?iu)\bip\b|\basn\b|локаци|местополож|какая.{0,15}стран|кто.{0,15}оператор|какой.{0,15}префикс|(?:его|этот|этого).{0,15}домен',text))
            if self.target.get('platform')=='steam':scoped |= bool(re.search(r'(?iu)инвентар|скин|предмет|стоимост|цены|аватар',text))
            if kind=='image':scoped |= bool(re.search(r'(?iu)где|место|локаци|координат|фото|изображени|геометри|рельеф|сравни|geoint|geoclip|waypoint',text))
        research=bool(images or explicit_research(text) or scoped)
        context={'conversation_id':conversation_id,'target':self.target} if research and scoped else None
        return {'kind':'research' if research else 'conversation','entity_context':context}
