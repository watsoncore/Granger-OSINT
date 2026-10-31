"""Directed shared-clock scenes built from authored full-body key drawings."""
from dataclasses import dataclass
import math
from .scene_pose import ActorPose,reading_pose,track,mix,rotate,elbow_track
from .key_poses import H,G,hero as hero_rest,guest as guest_rest,drawing_track,face_other_side


@dataclass
class Conversation:
    hero:ActorPose
    guest:ActorPose
    speaker:str=''
    phase:str='enter'
    note:tuple[float,float]|None=None
    note_owner:str=''
    note_angle:float=0.
    note_pocket:bool=False


def conversation_pose(life,separation=-260.,mirror=True):
    q,t,v=life.progress,life.elapsed,life.variant;direction=-1 if separation<0 else 1
    hero=hero_rest();guest=guest_rest();result=Conversation(hero,guest)
    if life.action=='malfoy':
        if v==0:
            hero=drawing_track(q,H,(0,'rest'),(.13,'turn'),(.25,'reject'),(.37,'cross'),(.49,'point'),
                (.59,'stomp'),(.65,'point'),(.77,'cross'),(.91,'calm'),(1,'rest'))
            guest=drawing_track(q,G,(0,'rest'),(.14,'turn'),(.25,'provoke'),(.35,'shrug'),(.48,'listen'),
                (.61,'retreat'),(.74,'shrug'),(.85,'retreat'),(1,'rest'))
            beats=[(.17,.28,'guest'),(.32,.51,'hero'),(.54,.61,'guest'),(.64,.77,'hero')]
        else:
            hero=drawing_track(q,H,(0,'rest'),(.12,'turn'),(.23,'reject'),(.34,'point'),(.44,'cross'),
                (.54,'stomp'),(.59,'cross'),(.615,'draw_wand'),(.68,'retort'),(.73,'retort'),(.81,'draw_wand'),(.86,'point'),(.94,'calm'),(1,'rest'))
            guest=drawing_track(q,G,(0,'rest'),(.13,'turn'),(.23,'provoke'),(.34,'listen'),(.44,'shrug'),
                (.53,'provoke'),(.65,'retreat'),(.72,'retreat'),(.81,'shrug'),(.90,'retreat'),(1,'rest'))
            beats=[(.16,.25,'guest'),(.28,.37,'hero'),(.40,.49,'guest'),(.52,.64,'hero'),(.69,.76,'guest'),(.78,.86,'hero')]
            hero.wand=.615<=q<=.81
            hero.pocket=q<.64 or q>.78
        result.phase='provocation' if q<.28 else 'argument' if q<.6 else 'retort' if q<.78 else 'calming'
    elif life.action=='harry':
        if v==0:
            hero=drawing_track(q,H,(0,'rest'),(.12,'turn'),(.23,'wave'),(.31,'listen'),(.41,'explain'),
                (.50,'point'),(.59,'open'),(.67,'listen'),(.77,'friendly'),(.88,'wave'),(1,'rest'))
            guest=drawing_track(q,G,(0,'rest'),(.13,'turn'),(.23,'wave'),(.32,'reply'),(.42,'listen'),
                (.51,'nod'),(.60,'think'),(.68,'nod'),(.77,'reply'),(.87,'friendly'),(1,'rest'))
            beats=[(.18,.31,'guest'),(.35,.59,'hero'),(.69,.80,'guest'),(.84,.91,'hero')]
        else:
            hero=drawing_track(q,H,(0,'rest'),(.12,'turn'),(.22,'wave'),(.32,'explain'),(.43,'point'),
                (.53,'open'),(.62,'listen'),(.70,'explain'),(.79,'friendly'),(.88,'wave'),(1,'rest'))
            guest=drawing_track(q,G,(0,'rest'),(.12,'turn'),(.22,'wave'),(.32,'listen'),(.42,'nod'),
                (.53,'think'),(.63,'reply'),(.71,'nod'),(.80,'glasses'),(.89,'friendly'),(1,'rest'))
            beats=[(.17,.25,'guest'),(.28,.54,'hero'),(.58,.66,'guest'),(.68,.77,'hero'),(.80,.88,'guest')]
        result.phase='greeting' if q<.29 else 'explanation' if q<.6 else 'response' if q<.81 else 'friendly_exit'
    elif life.action=='ron_chat':
        guest=drawing_track(q,G,(0,'rest'),(.13,'turn'),(.23,'wave'),(.34,'reply'),(.44,'listen'),
            (.54,'shrug'),(.64,'nod'),(.75,'reply'),(.87,'friendly'),(1,'rest'))
        if v==0 and q<=.56:
            # Ron interrupts before the next page turn. Start the closing
            # section from the identical two-hand open-book hold, rather than
            # compressing an entire page sweep into a fraction of a second.
            rq=track(q,(0.,0.),(.16,.30),(.31,.40)) if q<.31 else track(q,(.31,.77),(.56,1.))
            hero=reading_pose(rq,t,1);hero.gaze=(-5.,0.) if q>.32 else hero.gaze
            hero.head=track(q,(0.,0.),(.16,5.),(.30,3.),(.36,-5.),(.44,-5.),(.56,0.))
        else:
            hero=drawing_track(q,H,*(((0,'rest'),(.15,'turn'),(.25,'point'),(.36,'listen'),(.46,'explain'),(.56,'rest')) if v else ((.56,'rest'),)),
                (.65,'turn'),(.72,'explain'),(.81,'friendly'),(.90,'wave'),(1,'rest'))
        beats=[(.21,.37,'guest'),(.42,.58,'hero'),(.63,.76,'guest'),(.80,.87,'hero')]
        result.phase='interrupt_reading' if v==0 and q<.56 else 'conversation'
    else:
        hero,guest=_note_scene(result,q,t,separation,mirror)
        beats=[(.20,.31,'guest'),(.69,.77,'hero')]
    if direction>0 and life.action!='ron_note':
        if life.action=='ron_chat' and v==0 and q<=.56:
            hero.head=-hero.head;hero.gaze=(-hero.gaze[0],hero.gaze[1]);hero.lean=-hero.lean
        else:hero=face_other_side(hero)
    result.hero,result.guest=hero,guest
    # The mouth rhythm belongs to the current speaker only; silent poses retain
    # their listening expression and anticipatory/reaction body drawings.
    for start,end,speaker in beats:
        if start<=q<=end:
            result.speaker=speaker;actor=hero if speaker=='hero' else guest
            actor.mouth='open' if int((q-start)*life.elapsed/max(q,.001)*7)%2 else 'neutral';break
    hero.blink=max(0.,1-abs(t%5.9-4.4)/.075);guest.blink=max(0.,1-abs(t%5.7-3.9)/.075)
    entry=1-track(q,(0.,0.),(.14,1.),(.86,1.),(1.,0.))
    if entry:
        guest.leg_left+=math.sin(t*8)*12*entry;guest.leg_right-=math.sin(t*8)*12*entry
        if life.action!='ron_note':guest.shift=(guest.shift[0],guest.shift[1]-abs(math.sin(t*8))*2.5*entry)
    hero.hair=hero.head*.2-hero.lean*.35;guest.hair=guest.head*.15
    if q<.13:result.phase='enter'
    elif q>.9:result.phase='exit'
    return result


def _note_scene(result,q,t,separation,mirror,*,_draw_elbows=True):
    direction=-1 if separation<0 else 1
    hero,guest=hero_rest(),guest_rest();hero.grounded=guest.grounded=False
    hero.gaze=(direction*5.,0.);guest.gaze=(-5.,0.)
    def local(point):return (512-(point[0]-separation) if mirror else point[0]-separation,point[1])
    def world(point):return (separation+(512-point[0] if mirror else point[0]),point[1])
    side='left' if direction<0 else 'right';neutral=getattr(hero,side)
    contact=((171 if direction<0 else 281)+world((193.,281.))[0])/2,320.
    carry=world((179.,342.));carry=(carry[0]-direction*28,carry[1]-5)
    pocket=(175.,426.) if direction<0 else (280.,426.)
    note=track(q,(0.,(carry[0],433.)),(.18,carry),(.28,carry),(.42,contact),(.50,contact),
        (.63,(228.,285.)),(.76,(228.,285.)),(.90,pocket),(1.,pocket))
    result.note=note if .075<q<.93 else None
    result.note_owner='held_by_ron' if q<.44 else 'transferring' if q<.50 else 'held_by_hermione'
    result.note_angle=track(q,(0.,-10.),(.28,-10.),(.42,0.),(.50,0.),(.63,-5.),(.76,-5.),(.90,-15.),(1.,-15.))
    result.note_pocket=q<.17 or q>.80
    def edge(x):
        dx,dy=rotate((x,7.),result.note_angle);return note[0]+dx,note[1]+dy
    guest_grip=local(edge(direction*28));hero_grip=edge(-direction*28)
    last=local((contact[0]+direction*28,contact[1]+7))
    offered_elbow=((193+last[0])/2+30,350.)
    if q<.50:
        follow=track(q,(0.,0.),(.07,1.),(.50,1.));guest.left=mix(guest.left,guest_grip,follow)
        guest.elbow_left=track(q,(0.,(169.,338.)),(.16,(224.,316.)),(.28,(224.,316.)),(.42,offered_elbow),(.50,offered_elbow))
    else:
        release=track(q,(.50,1.),(.59,0.),(1.,0.))
        guest.left=mix(guest.left,last,release)
        guest.elbow_left=mix(guest.elbow_left,offered_elbow,release)
    reach=track(q,(0.,0.),(.30,0.),(.44,1.),(.88,1.),(.97,0.),(1.,0.))
    setattr(hero,side,mix(neutral,hero_grip,reach));setattr(hero,side+'_hand','grip' if reach>.6 else 'relaxed')
    elbow_keys=((0.,(136.,340.)),(.30,(136.,340.)),(.44,(131.,366.)),(.50,(131.,366.)),
        (.63,(204.,355.)),(.76,(204.,355.)),(.90,(161.,365.)),(1.,(136.,340.)))
    elbow=track(q,*elbow_keys)
    if direction>0:elbow=(452-elbow[0],elbow[1])
    setattr(hero,'elbow_'+side,elbow);guest.left_hand='grip' if q<.50 else 'palm' if q<.59 else 'relaxed'
    hero.head=track(q,(0.,0.),(.27,-5.),(.42,3.),(.50,3.),(.63,7.),(.72,7.),(.77,-4.),(.88,0.),(1.,0.))
    hero.gaze=(track(q,(0.,direction*5.),(.26,direction*5.),(.42,direction*4.),(.60,0.),(.73,0.),(.79,direction*5.),(1.,0.)),
        track(q,(0.,0.),(.27,0.),(.42,4.),(.63,5.),(.73,5.),(.79,0.),(1.,0.)))
    hero.brow=track(q,(0.,0.),(.70,0.),(.74,-1.),(.78,-1.),(.86,0.),(1.,0.))
    hero.mouth='smile' if .72<q<.89 else 'neutral'
    guest.head=track(q,(0.,0.),(.18,5.),(.28,0.),(.43,7.),(.53,0.),(.66,-5.),(.78,4.),(.87,-3.),(1.,0.))
    # The free hand gives a visible acknowledgement after reading.
    free='right' if direction<0 else 'left';free_neutral=getattr(hero,free)
    wave=track(q,(0.,0.),(.75,0.),(.80,1.),(.85,1.),(.91,0.),(1.,0.))
    target=(310.,268.) if direction<0 else (142.,268.)
    setattr(hero,free,mix(free_neutral,target,wave));setattr(hero,free+'_hand','palm' if wave>.3 else 'relaxed')
    setattr(hero,'elbow_'+free,mix(getattr(hero,'elbow_'+free),(325.,329.) if direction<0 else (127.,329.),wave))
    if _draw_elbows:
        def sample(u):return _note_scene(Conversation(None,None),u,u*16,separation,mirror,_draw_elbows=False)
        keys=tuple((at,(452-e[0],e[1]) if direction>0 else e) for at,e in elbow_keys)
        setattr(hero,'elbow_'+side,elbow_track(q,keys,lambda u:getattr(sample(u)[0],side)))
        guest_keys=((0.,(169.,338.)),(.16,(224.,316.)),(.28,(224.,316.)),(.42,offered_elbow),(.50,offered_elbow),(.59,(169.,338.)),(1.,(169.,338.)))
        guest.elbow_left=elbow_track(q,guest_keys,lambda u:sample(u)[1].left)
    result.phase='retrieve_note' if q<.20 else 'offer' if q<.32 else 'reach' if q<.44 else 'handoff' if q<.50 else 'take_note' if q<.63 else 'read_note' if q<.78 else 'stow_note'
    return hero,guest
