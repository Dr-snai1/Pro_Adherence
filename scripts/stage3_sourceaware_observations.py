#!/usr/bin/env python3
"""Reproducible PRIVATE Stage3 source-field observational networks, not person identity or normalized co-word.

Input: pinned Stage2 canonical ZIP, Stage3 eligible graph, exact WoS tagged raw + APA RIS.
Each source record contributes at most one event per exact NFC-trimmed label per field.
WoS AU continuation lines are author observations; WoS DE / ID are separate keyword fields.
APA AU and KW are repeated RIS tags; PubMed author strings are from frozen Stage2 source rows.
No within/cross-source person disambiguation, stemming, casefold, or inferred keyword absences.
"""
from __future__ import annotations
import collections, gzip, hashlib, json, os, pathlib, sqlite3, sys, unicodedata, zipfile
from itertools import combinations

FROZEN = {
 'stage2':'a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127',
 'graph':'33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c',
 'wos_first':'3247ec52dabe2ab3a156df6b57bfdd38b4e0496861458e70d0de0f5fe59ce020',
 'wos_rest':'513e5837858801f72bc4063ca03cb482223b4b07a569276e1a1796cc1286d6bf',
 'apa':'dfc9d2902459f068b5492e79d73ab57694a04647a56c2a2d7abd95e59c19a462'}
MEMBER = {'canonical_articles.jsonl.gz':'df9572a79db8063dc6b871cb0e03c6deae1fe4a4f1aaf1e06457932e048c311b',
'source_records.jsonl.gz':'b68a3e71eff44276a42da754fd4c2eaff09c4886c3a0f356130dcb14981aafba',
'author_observations.jsonl.gz':'68ef9997898c33a41eaf24a7f950290f0ceb199e7e922fee575f83517293d9f5'}
BASE=pathlib.Path('/mnt/data')
TMP=pathlib.Path('/tmp/proadh_private_work')
FILES={'stage2':TMP/'stage2_frozen.zip','graph':BASE/'STAGE3_20261111_PRIVATE_node2vec_graph.zip',
'wos_first':BASE/'WOS_CORE_20261029_FULL180_ARTICLE_ENGLISH_000001-000500.txt',
'wos_rest':BASE/'WOS_STAGE2_ALL_REMAINING_501-30635.zip',
'apa':BASE/'APA_PSYCINFO_20261030_EN_JOURNAL_ARTICLE_006878_ORIGINAL.ris.bin'}
OUT=TMP/'stage3_sourceaware_observations'

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for c in iter(lambda:f.read(2**20),b''):h.update(c)
 return h.hexdigest()

def memberdigest(z,n):
 h=hashlib.sha256()
 with z.open(n) as f:
  for c in iter(lambda:f.read(2**20),b''):h.update(c)
 return h.hexdigest()

def jsonlines(z,name):
 with gzip.open(z.open(name),'rt',encoding='utf8') as f:
  for line in f:
   if line.strip():yield json.loads(line)

def norm(s):
 if not isinstance(s,str):raise ValueError('non-string raw label')
 return unicodedata.normalize('NFC',s).strip()

def labels(items,split_semicolon=False):
 allraw=[]
 for s in items:
  s=norm(s)
  allraw.extend(s.split(';') if split_semicolon else [s])
 raw=[norm(s) for s in allraw if norm(s)]
 return sorted(set(raw)),len(raw)-len(set(raw))

def wos_records(f):
 """Parse Clarivate tagged file with explicit continuation lines and ER record boundary."""
 fields={};current=None
 for raw in f:
  line=raw.decode('utf-8-sig','replace').rstrip('\r\n')
  if line.startswith('ER') and line.strip()=='ER':
   if not fields.get('UT'):raise ValueError('WoS missing UT')
   yield fields
   fields={};current=None;continue
  if line.startswith('EF') and line.strip()=='EF':continue
  if len(line)>=3 and line[0:2].isalnum() and line[0].isupper() and line[2]==' ':
   key=line[:2];val=line[3:].strip();
   if key in ('AU','DE','ID','UT'):
    fields.setdefault(key,[]).append(val)
   current=key
  elif line.startswith('   ') and current in ('AU','DE','ID','UT'):
   val=line.strip()
   if current=='AU':fields[current].append(val)
   else:
    if not fields[current]:raise ValueError('WoS continuation without head')
    fields[current][-1]+=' '+val
  elif line.strip():
   # Ignore non-relevant continuation fields only.
   if not line.startswith('   '):raise ValueError('Malformed WoS line '+repr(line[:12]))
 if fields:raise ValueError('WoS record without ER')

def apa_records(f):
 fields=collections.defaultdict(list);current=None
 for raw in f:
  line=raw.decode('utf-8-sig','replace').rstrip('\r\n')
  if len(line)>=6 and line[2:6]=='  - ':
   key=line[:2]; val=line[6:].strip()
   if key=='ER':
    if len(fields['AN'])!=1:raise ValueError('APA missing AN')
    yield fields
    fields=collections.defaultdict(list);current=None
   else:
    fields[key].append(val);current=key
  elif line and line.startswith(' '):
   if current and fields[current]:fields[current][-1]+=' '+line.strip()
  elif line.strip():raise ValueError('Malformed RIS line '+repr(line[:15]))
 if fields:raise ValueError('RIS has trailing unterminated record')

def setup_db(db):
 db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF');db.execute('PRAGMA temp_store=MEMORY');db.execute('PRAGMA cache_size=-262144')
 db.execute('CREATE TABLE nodes(layer TEXT, source TEXT, hash TEXT, raw TEXT, PRIMARY KEY(layer,source,hash)) WITHOUT ROWID')
 db.execute('CREATE TABLE edges(layer TEXT, source TEXT, a TEXT, b TEXT, weight INTEGER NOT NULL, PRIMARY KEY(layer,source,a,b)) WITHOUT ROWID')

def observe(db,layer,source,phrases,stats):
 ps,dups=labels(phrases,split_semicolon=layer in ('wos_DE','wos_ID'))
 key=layer+'|'+source
 stats['duplicate_labels_within_record'][key]+=dups
 stats['observed_raw_mentions'][key]+=len(phrases)
 stats['unique_phrase_occurrences'][key]+=len(ps)
 stats['eligible_records_with_phrases'][key]+=int(bool(ps))
 stats['possible_pair_events'][key]+=len(ps)*(len(ps)-1)//2
 nodes=[]
 nodepairs=[]
 for raw in ps:
  h=hashlib.sha256((layer+'\x00'+source+'\x00'+raw).encode('utf-8')).hexdigest()
  nodes.append(h);nodepairs.append((layer,source,h,raw))
 db.executemany('INSERT OR IGNORE INTO nodes VALUES(?,?,?,?)',nodepairs)
 db.executemany('INSERT INTO edges VALUES(?,?,?,?,1) ON CONFLICT(layer,source,a,b) DO UPDATE SET weight=weight+1',((layer,source,a,b) for a,b in combinations(sorted(nodes),2)))
 return len(ps)

def write_gz(path,iterator):
 if path.exists():raise FileExistsError(path)
 n=0;digest_json=hashlib.sha256()
 with open(path,'xb') as f, gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0,compresslevel=6) as o:
  for row in iterator:
   line=(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8')
   o.write(line);digest_json.update(line);n+=1
 return {'name':path.name,'count':n,'bytes':path.stat().st_size,'sha256':digest(path),'jsonl_uncompressed_sha256':digest_json.hexdigest()}

def main():
 if OUT.exists() and any(OUT.iterdir()):raise RuntimeError('Output directory not empty')
 OUT.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(OUT,0o700)
 for n,p in FILES.items():
  actual=digest(p);assert actual==FROZEN[n],(n,actual)
 print('INPUT_SHA_ALL_PASS',flush=True)
 with zipfile.ZipFile(FILES['graph']) as gz,zipfile.ZipFile(FILES['stage2']) as sz:
  assert gz.testzip() is None and sz.testzip() is None
  for n,h in MEMBER.items():assert memberdigest(sz,n)==h,(n,memberdigest(sz,n))
  eligible={row['article_id'] for row in jsonlines(gz,'node2vec_node_mapping.private.jsonl.gz')}
  assert len(eligible)==57204
  src_to_article={};canon=set()
  for row in jsonlines(sz,'canonical_articles.jsonl.gz'):
   aid=row['canonical_article_id'];assert aid not in canon;canon.add(aid)
   for sid in row['source_record_ids']:
    if sid in src_to_article:raise ValueError('Duplicate source record id')
    src_to_article[sid]=aid
  assert len(canon)==57293 and len(src_to_article)==87511 and eligible<=canon
  meta={};pubmed=[];sourcecounts=collections.Counter();eligiblecounts=collections.Counter()
  observed_stage2_author_counts=collections.Counter()
  for r in jsonlines(sz,'source_records.jsonl.gz'):
   sid=r['source_record_id'];source=r['source_id'];article=src_to_article.get(sid)
   assert article is not None and sid not in meta
   native=r['source_native_id'];key=(source,native)
   assert key not in meta
   meta[key]=(article,sid,len(r['authors_raw']),r.get('raw_filename'),r.get('raw_record_ordinal'))
   sourcecounts[source]+=1
   if article in eligible:
    eligiblecounts[source]+=1
    observed_stage2_author_counts[source]+=len(r['authors_raw'])
    if source=='pubmed':pubmed.append((sid,article,r['authors_raw']))
  assert sum(sourcecounts.values())==87511
  assert sourcecounts=={'pubmed':49998,'woscc':30635,'apa_psycinfo':6878},sourcecounts
  assert eligiblecounts=={'pubmed':49910,'woscc':30632,'apa_psycinfo':6875},eligiblecounts
  assert sum(1 for _ in jsonlines(sz,'author_observations.jsonl.gz'))==381211
  print('STAGE2_ELIGIBILITY_AND_SOURCE_CENSUS_PASS',dict(eligiblecounts),flush=True)

 stats={k:collections.Counter() for k in ('duplicate_labels_within_record','observed_raw_mentions','unique_phrase_occurrences','eligible_records_with_phrases','possible_pair_events')}
 stats['source_records_total']=sourcecounts
 stats['eligible_source_records']=eligiblecounts
 stats['stage2_author_observation_string_count']=observed_stage2_author_counts
 stats['raw_author_string_count']=collections.Counter()
 stats['raw_keyword_field_missing']=collections.Counter()
 stats['original_source_records_read']=collections.Counter()
 stats['stage2_raw_filename_mismatch']=collections.Counter()
 stats['stage2_raw_ordinal_mismatch']=collections.Counter()
 stats['stage2_authors_list_count_mismatch']=collections.Counter()
 statmeta=stats
 db=sqlite3.connect(OUT/'network_temporary.sqlite3')
 setup_db(db)
 audit=[]
 # PubMed: frozen Stage2 parsed source author strings, no reconstructed PubMed XML keywords.
 for sid,article,raw_authors in pubmed:
  cnt=observe(db,'author_names','pubmed',raw_authors,stats)
  audit.append(['pubmed',sid,article,'author_names',cnt])
  stats['raw_author_string_count']['pubmed']+=len(raw_authors)
  stats['raw_keyword_field_missing']['pubmed_not_parsed_in_stage2']+=1
 print('PUBMED_AUTHOR_OBSERVATIONS_PASS',flush=True)

 # WoS verified, raw tagged files. Use original AU (not Stage2 authors_raw with one field per record).
 with zipfile.ZipFile(FILES['wos_rest']) as rest:
  assert rest.testzip() is None
  txts=[n for n in rest.namelist() if n.endswith('.txt')]
  assert len(txts)==61,len(txts)
  seen=set()
  groups=[(FILES['wos_first'].name,open(FILES['wos_first'],'rb'))]
  for n in txts:groups.append((n,rest.open(n)))
  for filename,f in groups:
   with f:
    for ordinal,rec in enumerate(wos_records(f),1):
     assert len(rec['UT'])==1
     native=rec['UT'][0];key=('woscc',native)
     if key not in meta:raise ValueError('WoS UT unknown in Stage2 source map')
     if key in seen:raise ValueError('Duplicate WOS UT')
     seen.add(key)
     article,sid,stageauthor,rawfile,rawordinal=meta[key]
     stats['original_source_records_read']['woscc']+=1
     if rawfile and pathlib.Path(rawfile).name!=filename:stats['stage2_raw_filename_mismatch']['woscc']+=1
     if rawordinal is not None and rawordinal!=ordinal:stats['stage2_raw_ordinal_mismatch']['woscc']+=1
     authors=rec.get('AU',[])
     if len(authors)!=stageauthor:stats['stage2_authors_list_count_mismatch']['woscc']+=1
     if article not in eligible:continue
     stats['raw_author_string_count']['woscc']+=len(authors)
     for layer,values in [('author_names',authors),('wos_DE',rec.get('DE',[])),('wos_ID',rec.get('ID',[]))]:
      cnt=observe(db,layer,'woscc',values,stats);audit.append(['woscc',sid,article,layer,cnt])
  assert len(seen)==30635,len(seen)
 print('WOS_ORIGINAL_AU_DE_ID_PARSED_AND_JOINED',dict(stats['stage2_authors_list_count_mismatch']),flush=True)

 # APA verified original RIS AU and KW tags, AN exact original ID. Key terms have no inferred vocabulary joins.
 seen=set()
 with open(FILES['apa'],'rb') as f:
  for ordinal,rec in enumerate(apa_records(f),1):
   native=rec['AN'][0];key=('apa_psycinfo',native)
   if key not in meta:raise ValueError('APA AN unknown in Stage2 source map')
   if key in seen:raise ValueError('Duplicate APA AN')
   seen.add(key)
   article,sid,stageauthor,rawfile,rawordinal=meta[key]
   stats['original_source_records_read']['apa_psycinfo']+=1
   if rawordinal is not None and rawordinal!=ordinal:stats['stage2_raw_ordinal_mismatch']['apa_psycinfo']+=1
   au=rec.get('AU',[])
   if len(au)!=stageauthor:stats['stage2_authors_list_count_mismatch']['apa_psycinfo']+=1
   if article not in eligible:continue
   stats['raw_author_string_count']['apa_psycinfo']+=len(au)
   for layer,values in [('author_names',au),('apa_KW',rec.get('KW',[]))]:
    cnt=observe(db,layer,'apa_psycinfo',values,stats);audit.append(['apa_psycinfo',sid,article,layer,cnt])
 assert len(seen)==6878,len(seen)
 print('APA_ORIGINAL_AU_KW_PARSED_AND_JOINED',dict(stats['stage2_authors_list_count_mismatch']),flush=True)

 db.commit()
 summary={}
 for layer,source,n,sumw in db.execute('SELECT layer,source,COUNT(*),SUM(weight) FROM edges GROUP BY 1,2'):
  summary[f'{layer}|{source}']={'unique_pairs':n,'weighted_events':sumw}
 for key,events in stats['possible_pair_events'].items():
  assert summary.get(key,{'weighted_events':0})['weighted_events']==events,(key,events,summary.get(key))
 print('WEIGHT_HANDSHAKING_PASS',summary,flush=True)
 files={}
 files['edges']=write_gz(OUT/'observed_edges.private.jsonl.gz',(
  [layer,source,a,b,w] for layer,source,a,b,w in db.execute('SELECT layer,source,a,b,weight FROM edges ORDER BY 1,2,3,4')))
 files['labels']=write_gz(OUT/'observed_labels.private.jsonl.gz',(
  [layer,source,h,raw] for layer,source,h,raw in db.execute('SELECT layer,source,hash,raw FROM nodes ORDER BY 1,2,3')))
 files['observation_audit']=write_gz(OUT/'observed_record_audit.private.jsonl.gz',iter(audit))
 db.close();(OUT/'network_temporary.sqlite3').unlink()
 # Independent serialized replay for count/order/event weights.
 check=collections.Counter();last=None
 with gzip.open(OUT/'observed_edges.private.jsonl.gz','rt') as f:
  for line in f:
   layer,source,a,b,w=json.loads(line);t=(layer,source,a,b)
   if (last is not None and t<=last) or a>=b or w<1:raise AssertionError('Invalid edge order/weight')
   last=t;check[(layer,source,'pairs')]+=1;check[(layer,source,'weight_sum')]+=w
 for key,rec in summary.items():
  layer,source=key.split('|');assert check[(layer,source,'pairs')]==rec['unique_pairs'];assert check[(layer,source,'weight_sum')]==rec['weighted_events']
 with gzip.open(OUT/'observed_labels.private.jsonl.gz','rt') as f:
  last=None
  for line in f:
   layer,source,h,raw=json.loads(line);t=(layer,source,h)
   if last is not None and t<=last:raise AssertionError('Invalid label order')
   assert h==hashlib.sha256((layer+'\x00'+source+'\x00'+raw).encode()).hexdigest()
   last=t

 manifest={
  'schema':'pro-adherence-stage3-sourceaware-raw-observation-networks/v1',
  'status':'TECHNICALLY_REPLAYED_PRIVATE_DIAGNOSTIC_NOT_DISAMBIGUATED_NOT_VALIDATED',
  'eligible_articles':57204,'eligible_source_records':dict(eligiblecounts),'full_source_records':dict(sourcecounts),
  'source_artifacts':{n:{'sha256':v,'path_hint':FILES[n].name} for n,v in FROZEN.items()},
  'drive_source_ids':{'stage2_parts':['1z6kfj0Rv5cVkPzkilCjyNVnFd7RQLPNr','1z8xmmJL0ObcXOSU-KeMc4Pk28g_Xfc3L','1NAlsS-T-dkHP_OdCBB21Umwn7op8qLeN','1-HW4NNpUaDMHkK57QieF3pw--SBP30AS'], 'stage3_graph':'1NysRCVbYlEAbW2FPXfdanKueaGjvYPsm','wos_first':'1_s3NXcNniPGS21L9BtzUWvZCeiddRMTP','wos_rest':'1lGv4i0HtsXCRViN4s_Qs-O-PiWElicl_','apa':'1cY8c7K2YiP6rtKZh8dgDQtEjsCJEA0dD'},
  'member_sha256':MEMBER,
  'source_semantics':{'author_names':'one exact source-tagged NFC-trimmed observed author string per article, not a person or verified co-authorship',
  'wos_DE':'author keyword phrases: semicolon-delimited from original WoS DE',
  'wos_ID':'Keywords Plus phrases: semicolon-delimited original WoS ID, kept separate from DE',
  'apa_KW':'APA original RIS KW tag values; not stemmed or lemmatized',
  'pubmed_keywords':'not materialized in Stage2; NOT assessed in original PubMed XML and not interpreted as zero'},
  'identity_joins':'NEVER unite equivalent names across sources; one node for exact label within (source,field); no casefold or ORCID disambiguation',
  'weights':'number of eligible source records co-observing a pair of unique exact labels in one field; each contributes 0/1',
  'raw_missingness':'no term output for PubMed; missing in Stage2 does NOT establish absent original author keywords',
  'stats':{k:dict(v) if isinstance(v,collections.Counter) else v for k,v in statmeta.items()},
  'edges':summary,'files':files,'verification':{'full_compressed_input_sha256':'pass','zip_crc':'pass','source_id_1_to_1':'pass','eligible_roster':'pass','weighted_events_equal_choose2':'pass','serialized_edge_stream_order_and_sum':'pass','serialized_label_node_sha256':'pass'},
  'scope': 'private source-aware observational diagnostics only; no release, no scientific or person-identity claims',
  'public_release_authorized':False,
  'code_sha256':digest(__file__)
 }
 path=OUT/'observations_private_manifest.json'
 if path.exists():raise FileExistsError(path)
 path.write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf8')
 print('OUTPUT_COMPLETE',json.dumps({'manifest_sha256':digest(path),'files':files,'edges':summary,'stats':{k:dict(v) for k,v in stats.items() if k in ('stage2_raw_filename_mismatch','stage2_raw_ordinal_mismatch','stage2_authors_list_count_mismatch')}},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
