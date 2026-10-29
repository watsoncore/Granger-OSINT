"""Validate the finite JSON input schemas of registered multi-input tools.

This is deliberately not a JSON-Schema interpreter: no references, expressions,
remote schemas or model-defined schemas are accepted. Callers supply repo-owned
schemas; adapters must also validate source-specific semantics before execution.
"""
from copy import deepcopy
import math


def validate_object(value,schema,*,_depth=0,_budget=None):
    budget=_budget if _budget is not None else [500]
    budget[0]-=1
    if _depth>6 or budget[0]<0:raise ValueError('Input complexity exceeded')
    kind=schema.get('type')
    if kind=='object':
        if not isinstance(value,dict) or len(value)>30:raise ValueError('Expected bounded object')
        properties=schema.get('properties',{})
        if set(value)-set(properties) or any(key not in value for key in schema.get('required',[])):
            raise ValueError('Unknown or missing argument')
        result={key:validate_object(item,properties[key],_depth=_depth+1,_budget=budget) for key,item in value.items()}
    elif kind=='array':
        if not isinstance(value,list) or not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',30):raise ValueError('Invalid list')
        result=[validate_object(item,schema['items'],_depth=_depth+1,_budget=budget) for item in value]
        if schema.get('uniqueItems') and any(item in result[:index] for index,item in enumerate(result)):
            raise ValueError('Duplicate list item')
    elif kind=='string':
        if not isinstance(value,str) or not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',2000) or any(ord(c)<32 and c not in schema.get('allowedControlCharacters','') for c in value):raise ValueError('Invalid string')
        result=value
    elif kind in ('number','integer'):
        if (type(value) not in ((int,) if kind=='integer' else (int,float)) or not math.isfinite(value)
                or not schema.get('minimum',-1e15)<=value<=schema.get('maximum',1e15)):raise ValueError('Invalid number')
        if 'exclusiveMinimum' in schema and value<=schema['exclusiveMinimum']:raise ValueError('Number below exclusive bound')
        if 'exclusiveMaximum' in schema and value>=schema['exclusiveMaximum']:raise ValueError('Number above exclusive bound')
        result=value
    elif kind=='boolean':
        if type(value) is not bool:raise ValueError('Expected boolean')
        result=value
    else:raise ValueError('Unsupported input schema')
    if 'enum' in schema and result not in schema['enum']:raise ValueError('Unknown option')
    return deepcopy(result)
