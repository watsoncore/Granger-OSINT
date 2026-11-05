"""Camera acceptance must reject rewinds, unintended zoom and stale end state."""
from scripts.qa_v5_motion import check_motion_frames,find_pan_path
from scripts.qa_clean_release import QaFailure
import pytest


def frame(x,y=0,scale=1,event='frame'):return {'x':x,'y':y,'scale':scale,'event':event}


def test_pan_accepts_monotonic_real_frames_and_duplicate_ack_at_final_camera():
    frames=[frame(0),frame(10),frame(30),frame(50),frame(50,event='commit'),frame(50,event='ack')]
    result=check_motion_frames(frames,frame(0),frame(50),(50,0))
    assert result['passed'] and result['backward_jumps']==0 and result['stable_scale']


@pytest.mark.parametrize('frames,end',[
    ([frame(0),frame(20),frame(3),frame(50)],frame(50)),
    ([frame(0),frame(20,scale=.9),frame(30),frame(50)],frame(50)),
    ([frame(0),frame(20),frame(30),frame(2,event='ack')],frame(2)),
])
def test_pan_rejects_snapback_scale_change_and_endpoint_mismatch(frames,end):
    assert not check_motion_frames(frames,frame(0),end,(50,0))['passed']


def test_motion_trajectory_avoids_cards_and_minimap():
    canvas={'width':800,'height':500,'qaNodes':[{'x':80,'y':70,'width':100,'height':80}],
        'qaFarClusters':'[]','qaEdges':'[]'}
    path=find_pan_path(canvas)
    assert len(path)==7 and path[-1][0]-path[0][0]==108
    assert all(not (6<=x<=154 and 6<=y<=134) for x,y in path)
    assert all(not (595<=x<=800 and 365<=y<=500) for x,y in path)


def test_motion_fails_closed_when_no_free_pan_corridor_is_available():
    with pytest.raises(QaFailure,match='no_free_pan_corridor'):
        find_pan_path({'width':800,'height':500,'qaNodes':[{'x':400,'y':250,'width':800,'height':500}]})


def test_path_accounts_for_cards_translating_with_a_successful_pan():
    canvas={'width':800,'height':500,'qaNodes':[{'x':150,'y':100,'width':140,'height':100}]}
    path=find_pan_path(canvas)
    assert path[0][0]<56 and path[-1][0]>56
    assert path[-1][0]-path[0][0]==108
