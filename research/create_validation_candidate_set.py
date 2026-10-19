"""Generate reproducible, PROVISIONAL high-recall query evaluation pool. Not gold labels.

Source: PubMed ESearch/EFetch 2026-10-19 via selected and archived experimental queries.
Silver labels use conservative, interpretable title/abstract rules. Uncertain NEVER
silently converts to negative. Publication-level dedupe by PMID.
"""
import collections,csv,datetime,hashlib,json,math,random,re,time,xml.etree.ElementTree as ET
from pathlib import Path
from query_probe_precision_20261019 import api,FILTER,Q as focus
from query_probe_20261019 import Q as old
EXPERT_POS='9404746 12441805 17110087 22021483 23032359 23065532 25301330 26495883 28807035 29081045 29427293 31626087 31929426 33371973 35173501 35416595 37091492 38603915 38730371 39525610 41798698'.split()
USER_NEG='1332520 2448571 2792052 2898461 3555041 7414106 8141977 8914177 9676753 9730424 9888412 10103334'.split()

ROOT=Path("research/validation_candidate_set_20261019")
ROOT.mkdir(parents=True,exist_ok=True)
Q=json.loads(Path('configs/pubmed/medication-adherence-SELECTED.v1.json').read_text())['queries']['V04_S0']
PROXY='''("proportion of days covered"[tiab] OR "medication possession ratio"[tiab] OR "missed doses"[tiab] OR "pill count"[tiab] OR "directly observed therapy"[tiab] OR "medication taking"[tiab] OR "medication-taking"[tiab] OR "prescription refill"[tiab] OR "refill gaps"[tiab])'''
SPEC='''(antiretroviral*[tiab] OR PrEP[tiab] OR antipsychotic*[tiab] OR antiepileptic*[tiab] OR antiseizure[tiab] OR biologic*[tiab] OR insulin[tiab] OR statin*[tiab] OR inhaler*[tiab] OR anticoagulant*[tiab] OR immunosuppress*[tiab] OR ixekizumab[tiab] OR riluzole[tiab])'''
CLASSES='('+SPEC+' AND (adheren*[tiab] OR nonadheren*[tiab] OR complian*[tiab] OR persisten*[tiab] OR "missed doses"[tiab]))'\n# Stratified hard-negative challenge subset is still a subset of the archived B query.\nNONPATIENT='''(cell*[ti] OR protein*[ti] OR molecular[ti] OR enzyme*[ti] OR pharmacokinetic*[ti] OR surgical[ti] OR laboratory[ti] OR gene*[ti] OR nanoparticle*[ti] OR "drug resistance"[ti] OR "drug delivery"[ti] OR "physician adherence"[ti] OR "guideline adherence"[ti] OR "protocol compliance"[ti] OR epithelial[ti] OR cancer[ti] OR bacteria*[ti])'''\nB_HARD='('+old['B_context']+' AND '+NONPATIENT+')'
SOURCES={
'H_titleonly':focus['H_titleonly'],
'E_focus':focus['E_focus'],
'G_proximity':focus['G_proximity'],
'C_anchored':old['C_anchored'],
'B_context':old['B_context'],
'A_direct':old['A_direct'],
'P1_proxy':PROXY,
'P2_drugclass':CLASSES,
'B_hard_topic':B_HARD,
}
YEARS=[(1800,1999),(2000,2009),(2010,2012),(2013,2014),(2015,2016),(2017,2018),(2019,2020),(2021,2022),(2023,2024),(2025,2026)]
TARGETS={'H_titleonly':460,'E_focus':380,'G_proximity':480,'C_anchored':380,'B_context':400,'A_direct':500,'P1_proxy':300,'P2_drugclass':430,'B_hard_topic':950}
FIXEDPOS=set(EXPERT_POS)
FIXEDNEG=set(USER_NEG)
USER_R={'9404746'}
assert USER_R<=FIXEDPOS and not FIXEDPOS&FIXEDNEG
SEED=int(hashlib.sha256(b'Pro_Adherence|reference_1000|2026-10-19|v1').hexdigest(),16)
randomizer=random.Random(SEED)
def request(path,p):
 for attempt in range(4):
  try:
   raw=api(path,p)
   time.sleep(.38)
   return raw
  except Exception as ex:
   if attempt==3: raise
   print('RETRY',path,str(ex)[:150],flush=True)
   time.sleep(2*(attempt+1))
def search(q,start=0,n=0):
 r=json.loads(request('esearch.fcgi',{'db':'pubmed','term':q,'retmode':'json','retstart':start,'retmax':n,'sort':'pub_date'}))['esearchresult']
 if r.get('warninglist',{}).get('phrasesignored'):raise ValueError('PubMed ignored phrases '+str(r['warninglist']))
 return r
def fetch(ids):
 out={}
 for i in range(0,len(ids),90):
  ids0=ids[i:i+90]
  root=ET.fromstring(request('efetch.fcgi',{'db':'pubmed','id':','.join(ids0),'retmode':'xml'}))
  for node in root.findall('./PubmedArticle'):
   pmid=node.findtext('./MedlineCitation/PMID','')
   t=node.find('./MedlineCitation/Article/ArticleTitle')
   title=''.join(t.itertext()).strip() if t is not None else ''
   ab=' '.join(''.join(z.itertext()).strip() for z in node.findall('./MedlineCitation/Article/Abstract/AbstractText'))
   date=node.findtext('./MedlineCitation/Article/Journal/JournalIssue/PubDate/Year','')
   journal=node.findtext('./MedlineCitation/Article/Journal/Title','')
   out[pmid]={'pmid':pmid,'title':title,'abstract':ab,'publication_year':date,'journal':journal}
  print('FETCHED',len(out),'/',len(ids),flush=True)
 return out
def split_count(q,a,b):
 clause=f'({q}) AND {a:%Y/%m/%d}:{b:%Y/%m/%d}[edat]'
 count=int(search(clause)['count'])
 if count<=9000:
  return [(a,b,count)]
 if a==b:raise ValueError('EDAT single-day partition >9000')
 middle=a+datetime.timedelta(days=(b-a).days//2)
 return split_count(q,a,middle)+split_count(q,middle+datetime.timedelta(days=1),b)
def source_sample(name,term,target):
 # Restrict all retrieval to the same language/publication-type decision.
 expr='('+term+') AND '+FILTER
 bins=[]
 for a,b in YEARS:
  bins.extend(split_count(expr,datetime.date(a,1,1),datetime.date(b,12,31)))
 pop=sum(c for _,_,c in bins)
 expected=int(search(expr)['count'])
 if expected!=pop:raise RuntimeError(f'count mismatch {name} {expected} vs {pop}')
 existing=[(a,b,c) for a,b,c in bins if c]
 # Weight by sqrt(size): representation for small historical bins without eliminating large years.
 ws=[math.sqrt(c) for _,_,c in existing]
 quotas=[max(2,round(target*w/sum(ws))) for w in ws]
 # Several discontinuous random pages per time shard; no PMID filtering based on target label.
 ids=[];seen=set()
 for (a,b,c),quota in zip(existing,quotas):
  chunks=min(4,max(2,math.ceil(quota/28)))
  page=max(1,min(55,math.ceil(quota/chunks)))
  for _ in range(chunks):
   page0=min(page,c)
   start=randomizer.randint(0,max(0,c-page0))
   r=search(f'({expr}) AND {a:%Y/%m/%d}:{b:%Y/%m/%d}[edat]',start,page0)
   if len(r['idlist'])!=page0:raise RuntimeError('sample window unexpectedly short')
   for x in r['idlist']:
    if x not in seen:ids.append(x);seen.add(x)
 print('SOURCE',name,'COUNT',expected,'BINS',len(existing),'SAMPLED',len(ids),flush=True)
 return ids,expected
membership=collections.defaultdict(set)
counts={}
for name,term in SOURCES.items():
 hits,counts[name]=source_sample(name,term,TARGETS[name])
 for pmid in hits:membership[pmid].add(name)
# Include existing confirmed user labels and expert-selected previous hits.
for pmid in FIXEDPOS|FIXEDNEG:membership[pmid].add('existing_validation_seed')
print('TOTAL_UNIQUE_TO_FETCH',len(membership),flush=True)
rows=fetch(sorted(membership,key=int))
assert len(rows)>=len(membership)*.99, 'EFetch missing unusual number of PMIDs'
def has(pat,s):return bool(re.search(pat,s,re.I))
DRUG=r'\b(?:medicat(?:ion|ions|ed|e)?|drug[s]?|prescri\w+|pharmacotherap\w*|tablet[s]?|pill[s]?|antiretroviral\w*|antidepressant\w*|antipsychotic\w*|anticoagulant\w*|antiepileptic\w*|antiseizure|statin[s]?|biologic[s]?|insulin|antihypertensive\w*|PrEP|immunosuppress\w*|inhaler[s]?|oral agents?|treatment regimen[s]?)\b'
ADH=r'\b(?:adheren\w*|non.?adheren\w*|complian\w*|non.?complian\w*|persisten\w*|non.?persisten\w*)\b'
MEASURE=r'(?:\b(?:PDC|MPR|MMAS|Morisky)\b|proportion of days covered|medication possession ratio|refill adherence|pill count[s]?|medication event monitoring|electronic (?:pill|medication) monitor|missed doses?|self.reported adherence|adherence (?:was|were|is) (?:measured|assessed|evaluated)|(?:measured|assessed|evaluated|reported) adherence|patients? (?:were|was) adherent|adherence (?:rate|score|level)[s]?)'
OBVIOUS_MED_TITLE=r'(?:medicat\w*|drug adherence|prescription adherence|pharmacotherap\w*|antiretroviral\w*|PrEP adherence|antidepressant\w*|antipsychotic\w*|statin[s]?|anticoagulant\w*|antiepileptic\w*|insulin|inhaler\w*|oral anticoagulant\w*)'
NEG_FIELD=r'(?:cell.?cell adhesion|adhesive|adherent cells?|molecul\w+ adhesion|bacterial persistence|microbial persistence|persistent organic pollutant|persistent inflammation|persistent symptom[s]?|treatment guideline compliance|physician[s]? adherence|clinician[s]? adherence|protocol adherence|nursing compliance|guideline.concordant care|adherence to guidelines|guideline adherence|policy compliance|regulatory compliance|prEP awareness|osteoblast adhesion|patient safety events)'
PATIENT=r'(?:patient[s]?|participant[s]?|people|persons|women|men|adolescents?|children|caregiver|self.report|cohort|observational|clinical trial)'
STRONG_NEG=r'(?:biological|cell|microbial|gene|toxicant|ecosystem|crop|materials|bacteria|enzyme|protein|chemotaxis|surgery|imaging|molecular|mice|mechanism)'
def label(row):
 title=row['title'];ab=row['abstract'];joined=title+' '+ab
 if not title or not ab:return ('U',0,'missing_title_or_abstract')
 tadh=has(ADH,title);tdrug=has(OBVIOUS_MED_TITLE,title)
 ba=has(ADH,ab);bd=has(DRUG,ab)
 meas=has(MEASURE,ab)
 clinical=has(PATIENT,ab)
 negtitle=has(NEG_FIELD,title)
 positive=( (tadh and tdrug and ba and bd and clinical) or
            (ba and bd and meas and clinical and not negtitle) or
            (tdrug and has(r'non.?adheren\w*|adheren\w*|compliance|persistence',ab) and meas and clinical))
 if positive and not negtitle:
  evidence='explicit_title_plus_patient_drug_adherence' if tadh and tdrug else 'patient_drug_adherence_measure_in_abstract'
  score=3 if tadh and tdrug and meas else 2
  return 'R',score,evidence
 if negtitle and not (tadh and tdrug and ba and bd and meas):
  return 'N',3,'nonpatient_adherence_or_other_topic_title'
 if not tadh and not (ba and bd) and not meas:
  if (not tdrug and has(STRONG_NEG,title)) or not ba:
   return 'N',2,'no_patient_medication_adherence_evidence'
 return 'U',0,'ambiguous_or_weakly_evidenced'
labeled=[]
for pmid,row in rows.items():
 cls,score,basis=label(row)
 # Existing human labels are protected and separately tagged. Past expert positive labels
 # are NOT presented as newly human-validated.
 if pmid in USER_R:
  cls,score,basis='R',5,'human_preexisting_confirmed'
 elif pmid in FIXEDNEG:
  cls,score,basis='N',5,'human_preexisting_confirmed'
 elif pmid in FIXEDPOS:
  if cls=='N':cls,score,basis='U',0,'conflict_with_preexisting_expert_R'
  elif cls=='R':basis='expert_previously_read_plus_rules'
 row.update(label=cls,confidence=score,label_basis=basis,sources=';'.join(sorted(membership[pmid])),has_abstract=bool(row['abstract']),abstract_sha256=hashlib.sha256(row['abstract'].encode()).hexdigest(),pubmed_url='https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/')
 labeled.append(row)
# Independent negative-evidence triage. New lower-confidence negatives must be
# individually reviewed before gold-standard use. Never treat no abstract as N.
def weak_negative_strength(x):
 t=x['title'];a=x['abstract']
 if not t or not a or x['pmid'] in FIXEDPOS:return 0
 if has(ADH,t) or has(MEASURE,a):return 0
 if has(r'(?:\\b(?:missed|skipped) dose[s]?\\b|\\b(?:dose[s]? taken|patient.s? uptake|refill gap[s]?|pharmacy dispensing|pill taking|drug taking|self.discontinuation|treatment discontinuation)\\b)',t+' '+a):return 0
 if has(NEG_FIELD,t):return 4
 if has(STRONG_NEG,t) and not has(OBVIOUS_MED_TITLE,t):return 3
 if not has(ADH,a) and not has(r'\\b(?:dose[s]?|refill|persistence|medication.taking)\\b',a):return 2
 if has(r'(?:surgery|gene[s]?|biomarker[s]?|cell[s]?|enzyme[s]?|molecular|nanoparticle|drug release|pharmacokinetic[s]?|preclinical|antimicrobial resistance|radiology)',t):return 2
 return 0
initial=collections.Counter(x['label'] for x in labeled)
if initial.get('N',0)<500:
 candidates=[x for x in labeled if x['label']=='U' and weak_negative_strength(x)>=2]
 candidates.sort(key=lambda x:(-weak_negative_strength(x),hashlib.sha256((str(SEED)+'|'+x['pmid']).encode()).hexdigest()))
 needed=500-initial['N']
 print('WEAK_NEG_CANDIDATES',len(candidates),'NEEDED',needed,flush=True)
 for x in candidates[:needed]:
  x['label']='N';x['confidence']=1
  x['label_basis']='provisional_negative_other_topic_requires_expert_review'
stats=collections.Counter(x['label'] for x in labeled)
# Persist all annotation candidates in independently readable shards, including U.
cols=['pmid','label','confidence','label_basis','sources','publication_year','journal','title','has_abstract','abstract_sha256','pubmed_url']
for shard_no in range(0,len(labeled),170):
 with (ROOT/f'all_candidates_part_{shard_no//170+1:02}.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
  for row in labeled[shard_no:shard_no+170]:w.writerow({k:row.get(k,'') for k in cols})

print('LABELS_ALL',dict(stats),flush=True)
for group in ('R','N','U'):
 parts=collections.Counter(x['label_basis'] for x in labeled if x['label']==group)
 print('LABEL_BY_REASON',group,json.dumps(parts),flush=True)
# The benchmark deliberately balances labels. It is not a natural-prevalence sample.
# Positives with strongest title outcome evidence first, but ensure 45% are not H-title-only.
rng=random.Random(SEED+7)
R=[x for x in labeled if x['label']=='R']
N=[x for x in labeled if x['label']=='N']
for x in R+N:
 x['_rnd']=rng.random()
R.sort(key=lambda x:(-x['confidence'],x['_rnd']))
N.sort(key=lambda x:(-x['confidence'],x['_rnd']))
if len(R)<500 or len(N)<500:
 print('INSUFFICIENT',len(R),len(N),flush=True)
 raise ValueError('not enough screened silver references')
# Build two positive buckets where direct title query H is not the source (avoid trivial leakage).
indirect=[x for x in R if 'H_titleonly' not in x['sources'].split(';')]
explicit=[x for x in R if 'H_titleonly' in x['sources'].split(';')]
pickR=indirect[:min(230,len(indirect))]+explicit[:max(0,500-min(230,len(indirect)))]
if len(pickR)<500:
 seen={x['pmid'] for x in pickR}
 pickR += [x for x in R if x['pmid'] not in seen][:500-len(pickR)]
pickN=N[:500]
selected=pickR+pickN
assert len(selected)==1000 and len(set(x['pmid'] for x in selected))==1000
assert collections.Counter(x['label'] for x in selected)=={'R':500,'N':500}
selected.sort(key=lambda x:(x['label'],int(x['pmid'])))
with (ROOT/'silver_1000_labels.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for row in selected:w.writerow({k:row.get(k,'') for k in cols})

with (ROOT/'unresolved_candidates.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for row in labeled:
  if row['label']=='U':w.writerow({k:row.get(k,'') for k in cols})
metadata={
 'version':'2026-10-19-silver-v1','status':'provisional_silver_not_gold',
 'warning':'Automatic title/abstract heuristics; some N are lower-confidence triage; NOT independently expert-confirmed for 1000 labels; unsuitable as ground truth for final scientific gate.',
 'purpose':'Challenge/diagnostic set for candidate PubMed query comparison, not population precision estimation.',
 'labels':{'R':500,'N':500},'sampling': 'deterministic EDAT-stratified random pages for eight original/experimental PubMed queries plus B_context AND independent hard-negative topic strata; publication type English journal article, plus previously discussed sentinels',
 'seed_sha256':hashlib.sha256(str(SEED).encode()).hexdigest(),
 'source_counts':counts,'source_query_sha256':{x:hashlib.sha256(q.encode()).hexdigest() for x,q in SOURCES.items()},
 'all_candidates':len(labeled),'all_labels':dict(stats),'unresolved_count':stats.get('U',0),
 'human_previously_confirmed':{'R':sorted(USER_R),'N':sorted(FIXEDNEG)},
 'known_previous_expert_positives':sorted(FIXEDPOS),
 'non_titleonly_positive_count':sum('H_titleonly' not in x['sources'].split(';') for x in pickR),
 'sampled_from_source_counts':dict(collections.Counter(s for x in selected for s in x['sources'].split(';'))),
 'no_PubMed_query_NOT':'All corpus source expressions without exclusion (NOT); NOT label uses explicit evidence and metadata',
}
(ROOT/'manifest.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
(ROOT/'README.md').write_text("""# Provisional PubMed evaluation cohort (2026-10-19)
**NOT a validated gold standard.** Contains 500 auto-screened R and 500 auto-screened N,
with PubMed PMIDs, title, source, and label provenance. Label confidence and rule provenance are explicit.
This is a deliberately balanced challenge set and MUST NOT be used to estimate
prevalence, overall PubMed retrieval precision, or external recall.

- R = evidence in title+abstract consistent with actual patient medication-taking adherence,
  persistence or refill/coverage outcome; includes historical examples.
- N = clear other-topic or absent substantive patient medication adherence evidence.
- U = ambiguous/missing abstract; kept in unresolved_candidates.csv and not forced N.
- Existing user labels from the 150-sheet are preserved and marked human-confirmed;
  earlier assistant-read positives are *not* independently human-confirmed.
- Query provenance in manifest.json; original V04_S0 config has not been changed.
- Audit of *silver label noise* and expert dual review are mandatory before release gate.
- Full copyrighted abstracts are deliberately NOT redistributed in GitHub; obtain them from PubMed by PMID when reviewing.
- Candidate set selection is biased toward clear labels; test sensitivity on held-out
  documented clinical benchmark separately, not just on these generated rows.
""",encoding='utf-8')
print('SILVER_DATASET_COMPLETE',len(selected),'R',len(pickR),'N',len(pickN),'U',stats.get('U',0),'INDIRECT_R',metadata['non_titleonly_positive_count'],flush=True)
print('SAMPLE_FIRST_IDS',','.join(x['pmid'] for x in selected[:10]),flush=True)
