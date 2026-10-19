"""Weighted random PubMed sampling using non-overlapping EDAT windows."""
import hashlib,json,random,time,xml.etree.ElementTree as ET
from query_probe_precision_20261019 import Q, api, FILTER
YEARS=[(1800,1999),(2000,2009),(2010,2014),(2015,2019),(2020,2023),(2024,2026)]
GOLD=[
'9404746','12441805','17110087','22021483','23032359','23065532','25301330',
'26495883','28807035','29081045','29427293','31626087','31929426','33371973',
'35173501','35416595','37091492','38603915','38730371','39525610','41798698'
]
def search(term,retstart=0,retmax=0):
  doc=json.loads(api('esearch.fcgi',{'db':'pubmed','term':term,'retmode':'json','retstart':retstart,'retmax':retmax,'sort':'pub_date'}))['esearchresult']
  time.sleep(0.45)
  if doc.get('warninglist'):print('WARNING',doc['warninglist'],flush=True)
  return doc

def sample(label,q,n=50):
  base='('+q+') AND '+FILTER
  counts=[]
  for yr1,yr2 in YEARS:
    term=base+f' AND {yr1}:{yr2}[edat]'
    v=search(term)
    counts.append((yr1,yr2,int(v['count']),term))
  total=sum(c for _,_,c,_ in counts)
  print('BIN_COUNTS',label,json.dumps([[a,b,c] for a,b,c,_ in counts]),'TOTAL',total,flush=True)
  if total!=int(search(base)['count']):raise RuntimeError('EDAT_PARTITION_COUNTS_DO_NOT_SUM')
  if any(c>=10000 for _,_,c,_ in counts):raise RuntimeError('ONE_PARTITION_OVER_10000')
  rng=random.Random(int(hashlib.sha256((label+'|2026-10-19|weighted-holdout-v1').encode()).hexdigest(),16))
  positions=sorted(rng.sample(range(total),n))
  ids=[]
  for p in positions:
    offset=p
    for a,b,c,term in counts:
      if offset<c:break
      offset-=c
    r=search(term,retstart=offset,retmax=1)
    rows=r.get('idlist') or []
    if len(rows)!=1:raise RuntimeError('MISSING_ONE_SAMPLE_ID')
    ids.extend(rows)
  if len(set(ids))!=n:raise RuntimeError('DUPLICATE_IDS')
  print('SAMPLED_IDS',label,','.join(ids),flush=True)
  return ids

def fetch(ids):
  root=ET.fromstring(api('efetch.fcgi',{'db':'pubmed','id':','.join(ids),'retmode':'xml'}))
  time.sleep(.45)
  out=[]
  for row in root.findall('.//PubmedArticle'):
    pmid=row.findtext('./MedlineCitation/PMID','')
    e=row.find('./MedlineCitation/Article/ArticleTitle')
    title=''.join(e.itertext()).strip() if e is not None else ''
    ab=' '.join(''.join(x.itertext()).strip() for x in row.findall('./MedlineCitation/Article/Abstract/AbstractText'))
    out.append({'pmid':pmid,'title':title,'abstract':ab[:4000]})
  return out

if __name__=='__main__':
  print('STRATIFIED_RESEARCH_BEGIN',flush=True)
  for label in ('E_focus','H_titleonly'):
    q=Q[label]
    print('QUERY',label,'SHA',hashlib.sha256(q.encode()).hexdigest(),flush=True)
    ids=sample(label,q)
    articles=fetch(ids)
    if set(ids)!=set(a['pmid'] for a in articles):raise RuntimeError('PMID_XML_ID_MISMATCH')
    for x in articles:print('ARTICLE',label,json.dumps(x,ensure_ascii=False),flush=True)
    goldterm='('+' OR '.join(x+'[uid]' for x in GOLD)+')'
    found=search('('+q+') AND '+FILTER+' AND '+goldterm,retmax=100)
    print('KNOWN_POSITIVES_MATCHED',label,','.join(found.get('idlist',[])),'SOURCE',','.join(GOLD),flush=True)
  print('STRATIFIED_RESEARCH_END',flush=True)
