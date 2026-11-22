"""eBird v2 derived comparison; keep credentials and original responses out of files."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.ebird.org/v2'
DOCS = 'https://documenter.getpostman.com/view/664302/S1ENwy59'
TERMS = 'https://www.birds.cornell.edu/home/ebird-data-access-terms-of-use/'
SITES = [
    {'key':'west','label':'Iona Beach','region':'CA-BC','province':'British Columbia','coast':'Pacific','aliases':['Iona Island beach'],'match':'iona','bounds':[49.15,49.25,-123.25,-123.15]},
    {'key':'east','label':'Hartlen Point','region':'CA-NS','province':'Nova Scotia','coast':'Atlantic','aliases':['Eastern Passage--Hartlen Point','Hartlen Point','Hartlen Point (General)'],'match':'hartlen','bounds':[44.55,44.65,-63.5,-63.4]},
]
LIMIT = 10000

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def resolve_site(rows, site):
    if not isinstance(rows, list): raise ValueError('Invalid hotspot list')
    south,north,west,east = site['bounds']
    candidates = [r for r in rows if isinstance(r,dict) and site['match'] in r.get('locName','').lower() and south <= float(r.get('lat',999)) <= north and west <= float(r.get('lng',999)) <= east]
    matches = [r for r in candidates if r['locName'].casefold() in [a.casefold() for a in site['aliases']]]
    if len(matches) != 1:
        detail = ', '.join(f"{r.get('locId')}: {r.get('locName')}" for r in candidates)
        raise ValueError(f"Resolve {site['label']} exactly before collection; candidates: {detail or 'none'}")
    r = matches[0]
    if not re.fullmatch(r'L\d+',r.get('locId','')): raise ValueError('Invalid hotspot identity')
    return {k:site[k] for k in ['key','label','region','province','coast']} | {'id':r['locId'],'name':r['locName'],'url':'https://ebird.org/hotspot/'+r['locId']}

class Client:
    def __init__(self,key): self.key=key; self.last=0
    def get(self,path,params=None):
        url=API+path+('?' + urllib.parse.urlencode(params) if params else '')
        for attempt in range(3):
            time.sleep(max(0,1.1-(time.monotonic()-self.last)))
            self.last=time.monotonic()
            request=urllib.request.Request(url,headers={'X-eBirdApiToken':self.key,'User-Agent':'CoolCode Hotspot Ledger / noncommercial educational comparison (+https://coolcode.ca/hotspotledger/)','Accept':'application/json'})
            try:
                with urllib.request.urlopen(request,timeout=45) as response: raw=response.read(8_000_001)
                if len(raw)>8_000_000: raise ValueError('Source response exceeds 8 MB safety limit')
                result=json.loads(raw)
                if not isinstance(result,list): raise ValueError('Expected eBird array response')
                if len(result)>=LIMIT and '/obs/' in path: raise ValueError('Response reaches request cap; cannot claim complete coverage')
                return result, {'url':url,'retrieved_at':now(),'response_sha256':hashlib.sha256(raw).hexdigest(),'rows':len(result)}
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    try: retry=float(exc.headers.get('Retry-After','5'))
                    except ValueError: retry=5
                    if retry>60: raise RuntimeError('eBird asked for a longer pause; retry on next scheduled run') from None
                    time.sleep(max(1,retry)); continue
                raise RuntimeError(f'eBird request failed with HTTP {exc.code}; previous saved dataset is unchanged') from None
            except (urllib.error.URLError,TimeoutError):
                if attempt<2: time.sleep(2*(attempt+1)); continue
                raise RuntimeError('eBird request failed; previous saved dataset is unchanged') from None

def observation(row, site):
    if row.get('locId') != site['id']: raise ValueError('Observation outside the selected hotspot')
    species=row.get('speciesCode','')
    if not re.fullmatch(r'[a-z0-9]{3,20}',species): raise ValueError('Invalid species identity')
    date=row.get('obsDt','')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?',date): raise ValueError('Invalid observation date')
    try: datetime.fromisoformat(date)
    except ValueError: raise ValueError('Invalid observation calendar date') from None
    sub=row.get('subId','')
    if not re.fullmatch(r'S\d+',sub): raise ValueError('Invalid checklist identity')
    count=row.get('howMany')
    if count is not None and (type(count) is not int or count<0): raise ValueError('Invalid bird count')
    return species, {'date':date,'count':count,'checklist':'https://ebird.org/checklist/'+sub,'notable':False,'reviewed':bool(row.get('obsReviewed')),'valid':bool(row.get('obsValid'))}

def select_notable(rows, site):
    """A regional notable feed must be explicitly scoped to the exact hotspot."""
    if not isinstance(rows,list): raise ValueError('Invalid regional notable feed')
    retained=[]
    for row in rows:
        if not isinstance(row,dict) or not re.fullmatch(r'L\d+',str(row.get('locId',''))):
            raise ValueError('Regional notable observation has no valid location identity')
        if row['locId']==site['id']:
            observation(row,site)
            retained.append(row)
    return retained

def derive(feeds,sites):
    """One derived row per taxon, one latest observation per coast, no observer details."""
    grouped={}
    for site in sites:
        recent,notable=feeds[site['key']]
        notable_codes={observation(r,site)[0] for r in select_notable(notable,site)}
        for row in recent:
            species,obs=observation(row,site)
            if not row.get('comName') or not row.get('sciName'): raise ValueError('Missing species names')
            record=grouped.setdefault(species, {'id':species,'name':row['comName'],'scientific_name':row['sciName'],'west':None,'east':None})
            obs['notable']=species in notable_codes
            old=record[site['key']]
            if old is None or obs['date']>old['date']: record[site['key']]=obs
    return sorted(grouped.values(),key=lambda r:r['name'].casefold())

def validate(payload):
    if not isinstance(payload,dict) or payload.get('schema')!=1 or payload.get('status') not in ['ready','awaiting_source']: raise ValueError('Invalid dataset schema/status')
    if not isinstance(payload.get('records'),list) or len(payload['records'])>2000: raise ValueError('Invalid derived records')
    if payload['status']=='ready' and (not payload.get('captured_at') or len(payload.get('sites',[]))!=2): raise ValueError('Missing collection coverage')
    ids=set()
    for r in payload['records']:
        if not re.fullmatch(r'[a-z0-9]{3,20}',r.get('id','')) or r['id'] in ids: raise ValueError('Duplicate or invalid species')
        ids.add(r['id'])
        if not all(isinstance(r.get(k),str) and r[k] for k in ['name','scientific_name']): raise ValueError('Missing species name')
        if not r.get('west') and not r.get('east'): raise ValueError('Species needs an observation')
        for side in ['west','east']:
            obs=r.get(side)
            if obs is None: continue
            if not re.fullmatch(r'https://ebird\.org/checklist/S\d+',obs.get('checklist','')): raise ValueError('Invalid checklist source')
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?',obs.get('date','')): raise ValueError('Invalid source date')
            try: datetime.fromisoformat(obs['date'])
            except ValueError: raise ValueError('Invalid source calendar date') from None
            count=obs.get('count')
            if count is not None and (type(count) is not int or count<0): raise ValueError('Invalid source count')
            if type(obs.get('notable')) is not bool: raise ValueError('Invalid notable flag')
    json.dumps(payload,allow_nan=False)
    return payload

def save(payload, root=ROOT):
    validate(payload)
    folder=root/'data'; folder.mkdir(exist_ok=True)
    encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n'
    digest=hashlib.sha256(encoded).hexdigest()
    stamp=payload['captured_at'].replace(':','').replace('-','')
    name=f'archive/{stamp}-{digest[:12]}.json'
    target=root/name; target.parent.mkdir(exist_ok=True)
    with target.open('xb') as f: f.write(encoded)
    history=json.loads((folder/'history.json').read_text()) if (folder/'history.json').exists() else []
    history.append({'captured_at':payload['captured_at'],'file':name,'sha256':digest,'count':len(payload['records']),'window_days':30})
    index={'schema':1,'tool':'hotspotledger','title':'Hotspot Ledger','status':'ready','captured_at':payload['captured_at'],'checked_at':payload['captured_at'],'record_count':len(payload['records']),'snapshot_count':len(history),'window_days':30,'coverage':'Latest report per species at two exact hotspots, previous 30 days','source_url':DOCS,'current':'current.json','history':'history.json','latest_snapshot':'../'+name,'errors':[]}
    for filename,value in [('current.json',payload),('history.json',history),('index.json',index)]:
        dest=folder/filename; temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(dest)
    print(f"Saved {len(payload['records'])} derived species comparisons; {len(history)} immutable snapshots")

def collect():
    key=os.environ.get('EBIRD_API_KEY','').strip()
    if not key: raise RuntimeError('EBIRD_API_KEY is required for source collection; set the repository Actions secret. No source records have been invented.')
    client=Client(key); sites=[]; sources=[]; feeds={}
    for requested in SITES:
        rows,provenance=client.get('/ref/hotspot/'+requested['region'],{'fmt':'json'})
        site=resolve_site(rows,requested);sites.append(site);sources.append(provenance)
        public_locations={r.get('locId'):r.get('locName','') for r in rows if isinstance(r,dict) and re.fullmatch(r'L\d+',str(r.get('locId','')))}
        recent,p=client.get('/data/obs/'+site['id']+'/recent',{'back':30,'cat':'species','maxResults':LIMIT,'includeProvisional':'false','sort':'date'})
        p.update(feed='recent',scope='exact hotspot',hotspot_id=site['id'])
        if any(row.get('locId')!=site['id'] for row in recent):
            counts={}
            for row in recent:
                loc=row.get('locId')
                if loc in public_locations:counts[loc]=counts.get(loc,0)+1
            details='; '.join(loc+' '+public_locations[loc]+' ('+str(count)+' rows)' for loc,count in sorted(counts.items())[:20])
            unknown=sum(1 for row in recent if row.get('locId') not in public_locations)
            raise ValueError('Recent feed scope mismatch. Requested '+site['id']+' '+site['name']+'. Public returned hotspots: '+(details or 'none')+'. Non-public or unknown location rows withheld: '+str(unknown))
        sources.append(p)
        notable,p=client.get('/data/obs/'+site['region']+'/recent/notable',{'back':30,'maxResults':LIMIT,'detail':'simple','hotspot':'true'})
        retained=select_notable(notable,site)
        p.update(feed='notable',scope='province filtered to exact hotspot',region=site['region'],hotspot_id=site['id'],retained_rows=len(retained),excluded_other_locations=len(notable)-len(retained))
        sources.append(p); feeds[site['key']]=(recent,retained)
    payload={'schema':1,'collector_version':3,'status':'ready','captured_at':now(),'window_days':30,'records':derive(feeds,sites),'sites':sites,'sources':sources,'attribution':'Derived from eBird.org, Cornell Lab of Ornithology, and its contributors.','terms_url':TERMS,'coverage':'Only the latest accepted report per species at each exact hotspot within the previous 30 days. Notable means the species also occurs in the separate provincial eBird notable feed after exact hotspot filtering in that window.','warnings':['Reporting effort differs. Missing means not returned in this source window, not absent. These are not seasonal or historical species totals.','A notable label is an eBird feed flag from a provincial feed filtered to this exact hotspot, not a local rarity assessment. Provincial feed coverage can omit other notable reports. It can refer to a different checklist for the same species in the window.','Observation times are the source’s local checklist time; collection times are UTC. Sensitive or restricted records may be excluded by eBird.']}
    save(payload)
