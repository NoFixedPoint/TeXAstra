"""Compact complete frames; every frame remains independently decodable."""

REGION_FIELDS=('id','rect','file','start','end','line','column','endLine','endColumn','text','kind')

def wire_message(message):
    if message.get('type')!='frame':return message
    result={k:v for k,v in message.items() if k not in {'regions','characters'}}
    result['regionFields']=REGION_FIELDS
    result['regionRows']=[[region.get(k) for k in REGION_FIELDS] for region in message['regions']]
    result['characterRows']=[[char['text'],char['rect']] for char in message['characters']]
    return result
