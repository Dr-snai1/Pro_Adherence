"""Live PubMed checks for measurement-based V04 recall expansion candidate."""
import collections,hashlib,json,xml.etree.ElementTree as ET,time
from pathlib import Path
from query_probe_precision_20261019 import api
base=json.loads(Path("configs/pubmed/medication-adherence-SELECTED.v1.json").read_text())["queries"]["V04_S0"]
c=json.loads(Path("research/pubmed_method_expansion_CANDIDATE_v2_20261020.json").read_text())
candidate=c["query"]
proxy=c["method_branch"]
oldpos="9404746 12441805 17110087 22021483 23032359 23065532 25301330 26495883 28807035 29081045 29427293 31626087 31929426 33371973 35173501 35416595 37091492 38603915 38730371 39525610 41798698".split()
newpos="36334241 36436161 37682179 42876567 34031152 24702721 33464991".split()
def request(term,retmax=0,sort=None):
 opts={'db':'pubmed','term':term,'retmode':'json','retmax':retmax}
 if sort:opts['sort']=sort
 data=json.loads(api('esearch.fcgi',opts))
 time.sleep(.4)
 if "esearchresult" not in data:
  print("PUBMED_ERROR",json.dumps(data)[:1200],flush=True)
  raise RuntimeError("no ESearch result")
 r=data["esearchresult"]
 if "count" not in r:raise RuntimeError("ESearch count missing: "+str(r)[:1200])
 return r
def ids(q,pids):
 grouped='('+' OR '.join(p+'[uid]' for p in pids)+')'
 return set(request('('+q+') AND '+grouped,200)['idlist'])
def validate(q):
 b=0;quoted=False
 for x in q:
  if x=='"':quoted=not quoted
  if not quoted:
   if x=='(':b+=1
   if x==')':b-=1
   assert b>=0
 assert b==0 and not quoted,(b,quoted)
assert c["status"]=="CANDIDATE_RESEARCH_ONLY_NOT_ACCEPTED"
assert candidate!=base and candidate.endswith('AND (english[la] AND "journal article"[pt]))')
suffix=' AND (english[la] AND "journal article"[pt]))'
assert candidate.startswith(base[:-len(suffix)]) and candidate.endswith(suffix)
validate(base);validate(candidate)
a=request(base);b=request(candidate);p=request('('+proxy+') AND (english[la] AND "journal article"[pt])')
print('COUNTS','BASE',a['count'],'EXPANDED',b['count'],'PROXY',p['count'],'GAIN',int(b['count'])-int(a['count']),'EXPANDED_WARN',b.get('warninglist'),flush=True)
assert not b.get('warninglist',{}).get('quotedphrasesnotfound'),b.get('warninglist')
assert int(b['count'])>=int(a['count'])
orig=ids(base,oldpos)
expanded=ids(candidate,oldpos)
assert orig==expanded==set(oldpos),("old positives dropped",sorted(set(oldpos)-expanded))
print('CONTROL_RECALL',len(orig),len(expanded),'of',len(oldpos),flush=True)
olds=ids(base,newpos);news=ids(candidate,newpos)
print('SENTINEL_NEW','BASE_FOUND',sorted(olds),'CANDIDATE_FOUND',sorted(news),'GAINED',sorted(news-olds),'MISSED',sorted(set(newpos)-news),flush=True)
assert news>=olds
assert {'36334241','36436161','37682179','42876567','34031152'}<=news,sorted({'36334241','36436161','37682179','42876567','34031152'}-news)
# Additional live distribution diagnostic from method-only retrieval. Not a random/global PPV estimate.
r=request('('+proxy+') AND (english[la] AND "journal article"[pt])',retmax=80,sort='pub_date')
pool=r['idlist']
sample=sorted(pool,key=lambda x:hashlib.sha256(('methods20261020|'+x).encode()).hexdigest())[:35]
inbase=ids(base,sample)
out=[x for x in sample if x not in inbase]
print('METHOD_SAMPLE','N',len(sample),'MISSED_BASE',len(out),flush=True)
if out:
 root=ET.fromstring(api('efetch.fcgi',{'db':'pubmed','id':','.join(out[:18]),'retmode':'xml'}))
 for z in root.findall('./PubmedArticle'):
  pmid=z.findtext('./MedlineCitation/PMID','')
  tit=z.find('./MedlineCitation/Article/ArticleTitle')
  title=''.join(tit.itertext()) if tit is not None else ''
  print('NEW_ARTICLE',json.dumps({'pmid':pmid,'title':title},ensure_ascii=False),flush=True)
print('CANDIDATE_TEST_DONE',flush=True)
