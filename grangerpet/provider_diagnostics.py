"""Classify bounded provider errors without retaining echoed prompts or secrets."""
import hashlib
import json
import re

PARAMETERS=frozenset(('model','messages','max_tokens','max_completion_tokens','stream',
                      'stream_options','tools','tool_choice','temperature','reasoning_effort'))


def classify(raw,status,payload,*,truncated=False):
    try:value=json.loads(raw.decode('utf-8','replace'))
    except (ValueError,UnicodeError):value={}
    error=value.get('error',{}) if isinstance(value,dict) else {}
    message=error.get('message','') if isinstance(error,dict) else error if isinstance(error,str) else ''
    message=message[:4096].casefold() if isinstance(message,str) else ''
    param=error.get('param') if isinstance(error,dict) else None
    if not isinstance(param,str) or param not in PARAMETERS:
        mentioned=[name for name in PARAMETERS if re.search(r'(?<![\w])'+re.escape(name)+r'(?![\w])',message)]
        param=mentioned[0] if len(mentioned)==1 else None
    unsupported=bool(re.search(r'unsupported|not supported|unknown parameter|unrecognized|not permitted|not allowed',message))
    cause=('unsupported_parameter' if param and unsupported else
           'context_limit' if re.search(r'context.{0,25}(?:length|limit|exceed)|too many tokens',message) else
           'invalid_tool_protocol' if re.search(r'tool_call_id|tool.{0,20}(?:missing|unmatched|order)',message) else
           'unspecified')
    return {'origin':'provider','http_status':status,'cause':cause,'parameter':param,
            'request_parameter_names':sorted(name for name in payload if name in PARAMETERS),
            'response_body_sha256':hashlib.sha256(raw).hexdigest(),
            'response_bytes_observed':len(raw),'response_truncated':bool(truncated)}
