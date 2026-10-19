"""Research-only P2 class-specific recall frontier via exact EDAT adaptive partitions."""
import json,random,hashlib,datetime,time,xml.etree.ElementTree as ET
from pathlib import Path
from query_probe_precision_20261019 import api,FILTER
SOURCE=json.loads(Path('configs/pubmed/medication-adherence-SELECTED.v1.json').read_text())['queries']['V04_S0']
SPEC='''(antiretroviral*[tiab] OR PrEP[tiab] OR antipsychotic*[tiab] OR antiepileptic*[tiab] OR antiseizure[tiab] OR biologic*[tiab] OR insulin[tiab] OR statin*[tiab] OR inhaler*[tiab] OR anticoagulant*[tiab] OR immunosuppress*[tiab] OR ixekizumab[tiab] OR riluzole[tiab])'''
P2='((' + SPEC + ') AND (adheren*[tiab] OR nonadheren*[tiab] OR complian*[tiab] OR persisten*[tiab] OR "missed doses"[tiab]))'
QUERY='('+P2+') AND '+FILTER
start=datetime.date(1800,1,1)
end=datetime.date(2100,12,31)
def es(s,n=0,offset=0):
  r=json.loads(api('esearch.fcgi',{'db':'pubmed','term':s,'retmode':'json','retmax':n,'retstart':offset,'sort':'pub_date'}))['esearchresult']
  time.sleep(0.46)
  return r
def count_day(a,b):
  f=f'{a:%Y/%m/%d}:{b:%Y/%m/%d}[edat]'
  return int(es('('+QUERY+') AND '+f)['count']),f
top=int(es(QUERY)['count'])
shards=[]
def partition(a,b,n):
  if n<=9000:
    shards.append((a,b,n))
    return
  d=(b-a).days
  if d==0:raise ValueError('day over PubMed 10k')
  mid=a+datetime.timedelta(days=d//2)
  ln,_=count_day(a,mid)
  rn,_=count_day(mid+datetime.timedelta(days=1),b)
  if ln+rn != n:raise ValueError('EDAT partition overlap/missing')
  partition(a,mid,ln)
  partition(mid+datetime.timedelta(days=1),b,rn)
partition(start,end,top)
total=sum(c for _,_,c in shards)
print('P2_COUNT',top,'SHARDS',len(shards),'MAX_SHARD',max(x[2] for x in shards),flush=True)
assert total==top
rng=random.Random(int(hashlib.sha256(b'Pro_Adherence|P2_missing_frontier|2026-10-19').hexdigest(),16))
chosen=sorted(rng.sample(range(total),80))
pmids=[]
for p in chosen:
  off=p
  for a,b,c in shards:
    if off<c:break
    off-=c
  z=f'{a:%Y/%m/%d}:{b:%Y/%m/%d}[edat]'
  r=es('('+QUERY+') AND '+z,n=1,offset=off)
  if len(r['idlist'])!=1:raise ValueError('missing sampled PMID')
  pmids.extend(r['idlist'])
assert len(set(pmids))==len(pmids)
print('SAMPLE_80',','.join(pmids),flush=True)
matched=set()
for st in range(0,len(pmids),20):
  group=pmids[st:st+20]
  s='('+SOURCE+') AND ('+' OR '.join(x+'[uid]' for x in group)+')'
  matched.update(es(s,80)['idlist'])
outside=set(pmids)-matched
print('P2_SOURCE_RETENTION',len(matched),'OUTSIDE',len(outside),'N',len(pmids),flush=True)
xml=ET.fromstring(api('efetch.fcgi',{'db':'pubmed','id':','.join(pmids),'retmode':'xml'}))
found=set()
for row in xml.findall('.//PubmedArticle'):
 id=row.findtext('./MedlineCitation/PMID')
 if id not in outside:continue
 found.add(id)
 e=row.find('./MedlineCitation/Article/ArticleTitle')
 t=''.join(e.itertext()).strip() if e is not None else ''
 a=' '.join(''.join(z.itertext()).strip() for z in row.findall('./MedlineCitation/Article/Abstract/AbstractText'))
 print('UNIQUE_ARTICLE',json.dumps({'pmid':id,'title':t,'abstract_excerpt':a[:1800],'has_abstract':bool(a)},ensure_ascii=False),flush=True)
assert found==outside
print('CLASS_FRONTIER_DONE',flush=True)
