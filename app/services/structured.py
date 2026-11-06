"""Decode one bounded JSON object. Presentation wrappers never relax domain validation."""
import json
import re

class StructuredOutputError(ValueError):
    pass

def _pairs(values):
    result={}
    for key,value in values:
        if key in result:raise StructuredOutputError('duplicate_keys')
        result[key]=value
    return result

def _constant(value):raise StructuredOutputError('nonfinite_number')

def json_object(raw):
    if not isinstance(raw,str) or not raw.strip():raise StructuredOutputError('empty_response')
    if len(raw)>60000:raise StructuredOutputError('response_too_large')
    text=raw.strip().lstrip('\ufeff').strip()
    wrappers=[]
    # Some gateways place reasoning in a visible wrapper instead of a separate field.
    if text.startswith('<think>'):
        end=text.find('</think>')
        if end<0:raise StructuredOutputError('incomplete_reasoning')
        text=text[end+len('</think>'):].strip()
    if '```' in text:
        match=re.fullmatch(r'([^`]*?)```(?:json)?\s*([\s\S]*?)```([^`]*)',text,re.I)
        if not match or any(c in match[1]+match[3] for c in '{}[]'):
            raise StructuredOutputError('ambiguous_json')
        if len(match[1])+len(match[3])>1024:raise StructuredOutputError('unexpected_wrapper')
        wrappers.extend((match[1].strip(),match[3].strip()))
        text=match[2].strip()
    start=text.find('{')
    if start<0 or start>512 or any(c in text[:start] for c in '[]{}'):
        raise StructuredOutputError('expected_object')
    decoder=json.JSONDecoder(object_pairs_hook=_pairs,parse_constant=_constant)
    try:value,end=decoder.raw_decode(text,start)
    except (ValueError,RecursionError):raise StructuredOutputError('invalid_json') from None
    tail=text[end:].strip()
    if len(tail)>512 or any(c in tail for c in '{}[]'):
        raise StructuredOutputError('ambiguous_json')
    for outside in (*wrappers,text[:start].strip(),tail):
        if not outside:continue
        try:
            _,consumed=decoder.raw_decode(outside)
        except (ValueError,RecursionError):continue
        if not outside[consumed:].strip():raise StructuredOutputError('ambiguous_json')
    if not isinstance(value,dict):raise StructuredOutputError('expected_object')
    return value
