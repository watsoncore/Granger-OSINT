import pytest
from grangerpet.tool_inputs import validate_object

SCHEMA={'type':'object','properties':{'attachment_id':{'type':'string','minLength':68,'maxLength':68},'top_k':{'type':'integer','minimum':1,'maximum':10},'device':{'type':'string','enum':['cpu','auto']},'candidates':{'type':'array','maxItems':5,'items':{'type':'object','properties':{'latitude':{'type':'number','minimum':-90,'maximum':90},'longitude':{'type':'number','minimum':-180,'maximum':180}},'required':['latitude','longitude'],'additionalProperties':False}}},'required':['attachment_id'],'additionalProperties':False}


def test_bounded_structured_tool_input_keeps_real_numeric_arguments_and_copies():
    value={'attachment_id':'img_'+'a'*64,'top_k':5,'device':'cpu','candidates':[{'latitude':55.75,'longitude':37.6}]}
    result=validate_object(value,SCHEMA)
    assert result==value
    result['candidates'].clear()
    assert len(value['candidates'])==1


@pytest.mark.parametrize('change',[{'command':'whoami'},{'top_k':True},{'top_k':11},{'device':'remote'},{'candidates':[{'latitude':float('nan'),'longitude':0}]},{'candidates':[{'latitude':0,'longitude':0,'local_path':'C:/private'}]},{'attachment_id':'img_\n'+'a'*63}])
def test_schema_rejects_unknown_execution_fields_nonfinite_and_invalid_types(change):
    with pytest.raises(ValueError):validate_object({'attachment_id':'img_'+'a'*64,**change},SCHEMA)
