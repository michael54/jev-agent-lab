"""Paired Jev/SemIf diagnostic. Never sends gold labels or rationales to either model."""
import argparse
from collections import Counter
import datetime
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
import urllib.parse

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--semif-url',required=True)
p.add_argument('--output',required=True)
p.add_argument('--rounds',type=int,default=2)
a=p.parse_args()
folder=Path(a.output); folder.mkdir(parents=True,exist_ok=False)
source=(ROOT/'benchmarks/agent-cases-v1.json').read_bytes()
(folder/'cases.json').write_bytes(source)
cases=json.loads(source)['cases']
meta={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'dataset_sha256':hashlib.sha256(source).hexdigest(),'seed':19092026,
      'semif_url':a.semif_url,'jev_model':'jev-1.13.0','rounds':a.rounds,
      'method':'Same semantic state/question/options, native API adapters. Persistent HTTPS per provider. Randomized paired provider order, case order and option order each round. No retries. First calls and three warmups per provider excluded. All raw outcomes saved immediately.',
      'reference':'Current GPT-6 assistant authored cases and reference labels before any scored model call; not an independent human benchmark or timed GPT-6 API evaluation.'}
(folder/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
keys={'semif':(ROOT/'.local/api-key').read_text().strip(),
      'jev':os.environ.get('TYPESAFE_API_KEY') or (ROOT/'.local/typesafe-api-key').read_text().strip()}
u=urllib.parse.urlsplit(a.semif_url)
connections={'semif':http.client.HTTPSConnection(u.hostname,u.port,timeout=20),
             'jev':http.client.HTTPSConnection('api.typesafe.ai',timeout=20)}
records=[]

def call(provider,c,options,phase,round_index):
    if provider=='jev':
        payload={'model':'jev-1.13.0','state':c['state'],'questions':{'decision':{
            'type':'choice','instructions':c['question'],'criteria':dict(options)}}}
        path='/v1/systemone'
    else:
        payload={'id':c['id'],'state':c['state'],'question':c['question'],
                 'options':[{'id':k,'description':v} for k,v in options]}
        path='/v1/decide'
    encoded=json.dumps(payload,ensure_ascii=False).encode()
    record={'provider':provider,'case_id':c['id'],'category':c['category'],
            'language':c['language'],'variant':c['variant'],'phase':phase,
            'round':round_index,'option_order':[k for k,v in options]}
    start=time.perf_counter()
    try:
        conn=connections[provider]
        conn.request('POST',path,encoded,{'Content-Type':'application/json',
                     'Authorization':'Bearer '+keys[provider],'User-Agent':'jev-semif-comparison/1.0'})
        response=conn.getresponse(); raw=response.read()
        record.update(status=response.status,http_ms=(time.perf_counter()-start)*1000)
        if response.status==200:
            result=json.loads(raw)
            record['response']=result
            if provider=='jev':
                answer=result['answers']['decision']; choice=answer['choice'];probs=answer['probabilities']
            else:
                choice=result['choice'];probs=dict(zip(result['option_ids'],result['probabilities']))
            if choice not in c['options'] or set(probs)!=set(c['options']):
                raise ValueError('Option mismatch in response')
            record.update(choice=choice,correct=choice==c['gold'],gold=c['gold'],
                          probabilities=probs,top_probability=probs[choice],
                          brier=sum((v-(k==c['gold']))**2 for k,v in probs.items()))
        else:
            record['error']='HTTP '+str(response.status)
    except Exception as error:
        record.update(error=type(error).__name__,http_ms=(time.perf_counter()-start)*1000)
        record.setdefault('status','transport_error')
        connections[provider].close()
        host=u.hostname if provider=='semif' else 'api.typesafe.ai'
        connections[provider]=http.client.HTTPSConnection(host,u.port if provider=='semif' else None,timeout=20)
    records.append(record)
    with (folder/'requests.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    return record

warm={'id':'warmup','category':'warmup','language':'en','variant':'warmup',
      'state':'Please check live weather in Paris.','question':'Choose the appropriate tool.',
      'options':{'weather':'Live weather lookup','calculator':'Arithmetic calculator'},'gold':'weather'}
for provider in connections:
    for i in range(4):
        r=call(provider,warm,list(warm['options'].items()),'first' if i==0 else 'warmup',-1)
        if 'error' in r:raise SystemExit('Warmup failed for '+provider+': '+str(r['status']))
rng=random.Random(meta['seed'])
scored_started=time.monotonic()
for round_index in range(a.rounds):
    ordered=cases.copy();rng.shuffle(ordered)
    for index,c in enumerate(ordered):
        if time.monotonic()-scored_started>240:
            raise SystemExit('Scored run exceeded 240 seconds; partial raw results preserved')
        options=list(c['options'].items());rng.shuffle(options)
        providers=['jev','semif'];rng.shuffle(providers)
        for provider in providers:
            r=call(provider,c,options,'scored',round_index)
            if 'error' in r:print(json.dumps({'error':r['error'],'provider':provider,'case':c['id']}),flush=True)
        if (index+1)%9==0:print('Round',round_index+1,'paired cases',index+1,'/',len(cases),flush=True)
for conn in connections.values():conn.close()

def timing(values):
    if not values:return None
    s=sorted(values)
    return {'n':len(s),'p50_ms':statistics.median(s),'p95_ms':s[math.ceil(.95*len(s))-1]}
def wilson(correct,n):
    if not n:return None
    z=1.96;phat=correct/n;d=1+z*z/n
    center=(phat+z*z/(2*n))/d
    radius=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/d
    return [center-radius,center+radius]
summary={'manifest':meta,'providers':{}}
for provider in ('jev','semif'):
    rows=[r for r in records if r['provider']==provider and r['phase']=='scored']
    ok=[r for r in rows if 'choice' in r and 'error' not in r]
    primary=[r for r in rows if r['round']==0 and r['variant']=='base']
    correct=sum(r.get('correct',False) for r in primary)
    s={'requests':len(rows),'errors':sum('error' in r for r in rows),'status_counts':dict(Counter(str(r['status']) for r in rows)),
       'primary_unique_base':{'correct':correct,'total':len(primary),'accuracy':correct/len(primary),
                              'wilson95':wilson(correct,len(primary))},
       'by_category':{},'by_language':{},'latency':{},
       'all_scored_correct':sum(r.get('correct',False) for r in rows),
       'disagreements':[{'case_id':r['case_id'],'round':r['round'],'gold':r.get('gold'),
                         'choice':r.get('choice'),'top_probability':r.get('top_probability')}
                        for r in rows if not r.get('correct',False)]}
    for field,key in [('category','by_category'),('language','by_language')]:
        for value in sorted(set(r[field] for r in primary)):
            subset=[r for r in primary if r[field]==value]
            s[key][value]={'correct':sum(r.get('correct',False) for r in subset),'total':len(subset)}
    for variant in ['base','long']:
        subset=[r for r in ok if r['variant']==variant]
        s['latency'][variant]=timing([r['http_ms'] for r in subset])
        if provider=='semif':s['latency'][variant+'_forward']=timing([r['response']['forward_seconds']*1000 for r in subset])
    s['round_inconsistent_cases']=[c['id'] for c in cases if len({r['choice'] for r in ok if r['case_id']==c['id']})>1]
    s['mean_brier_primary']=statistics.mean(r['brier'] for r in primary if 'brier' in r)
    s['high_probability_errors_primary']=sum(not r.get('correct',False) and r.get('top_probability',0)>=.9 for r in primary)
    s['model_ids']=sorted({str(r['response']['model']) for r in ok})
    if provider=='jev':s['input_tokens_including_warmup']=sum(r.get('response',{}).get('usage',{}).get('input_tokens',0) for r in records if r['provider']=='jev')
    summary['providers'][provider]=s
base=[c for c in cases if c['variant']=='base'];paired=Counter()
for c in base:
    matches={r['provider']:r.get('correct',False) for r in records if r['phase']=='scored' and r['round']==0 and r['case_id']==c['id']}
    paired['both_correct' if all(matches.values()) else 'jev_only' if matches['jev'] else 'semif_only' if matches['semif'] else 'both_wrong']+=1
summary['paired_primary']=dict(paired)
(folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
