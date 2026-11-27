"""Repair omitted WoS AB/PY fields in a versioned Stage3 text derivative, not frozen Stage2.
Use the already-approved complete-record-first PubMed > WoS > APA selection policy.
No source data in this code; exact source provenance and independent parser checks.
"""
import collections as C,gzip,hashlib,json,re,sys,zipfile
from pathlib import Path
from stage3_temporal_years import sha,rows
from stage3_temporal_fixed import yearrows

PRIORITY={'pubmed':0,'woscc':1,'apa_psycinfo':2}

def parse(data):
 fields={};last=None;ordinal=0
 for line in data.decode('utf-8-sig').splitlines():
  if line=='ER':
   ordinal+=1
   def val(k):return ' '.join(fields.get(k,[])) or None
   assert val('UT');yield ordinal,val('UT'),val('TI'),val('AB'),val('PY');fields={};last=None;continue
  m=re.match(r'^([A-Z0-9]{2}) (.*)$',line)
  if m:
   tag,value=m.groups()
   if tag in ('FN','VR'):continue
   fields.setdefault(tag,[]).append(value);last=tag
  elif line.startswith('   ') and last:fields[last][-1]+=' '+line.strip()
 assert not fields

def independently_parse(data):
 # Independent record splitting and field regex (same continuation semantics as research parser).
 text=data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
 segments=re.split(r'(?m)^ER[ \t]*$',text);result=[]
 for segment in segments[:-1]:
  def field(tag):
   values=re.findall(r'(?m)^'+tag+r' ([^\n]*(?:\n   [^\n]*)*)',segment)
   return ' '.join(' '.join([v.split('\n')[0],*[l.strip() for l in v.split('\n')[1:]]]) for v in values) or None
  result.append((len(result)+1,field('UT'),field('TI'),field('AB'),field('PY')))
 assert not re.search(r'(?m)^UT ',segments[-1]);return result

def checks():
 synthetic=b'FN X\nVR 1.0\nPT J\nUT WOS:A\nTI Example title\n   continued\nAB Line one\n   line two\nPY 2010\nER\n\nPT J\nUT WOS:B\nTI Other\nPY 2020\nER\nEF\n';expected=[(1,'WOS:A','Example title continued','Line one line two','2010'),(2,'WOS:B','Other',None,'2020')];assert list(parse(synthetic))==independently_parse(synthetic)==expected

def present(s):return isinstance(s,str) and bool(s.strip())
def text_hash(r):return hashlib.sha256(json.dumps([r['title'],r.get('abstract')],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def dump_gzip(path,records):
 with path.open('wb') as f,gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0) as g:
  for r in records:g.write((json.dumps(r,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n').encode())

def run(root,d):
 checks();R=yearrows(root,d);yr=json.loads((d/'year_report.private.json').read_text());p=root/'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_INPUTS.zip';assert sha(p)==yr['source_sha256'][p.name];stage2=d/'frozen_stage2.zip';assert sha(stage2)==yr['source_sha256'][stage2.name];first=root/'WOS_CORE_20261029_FULL180_ARTICLE_ENGLISH_000001-000500.txt';wzip=root/'WOS_STAGE2_ALL_REMAINING_501-30635.zip';assert sha(first)==yr['source_sha256'][first.name] and sha(wzip)==yr['source_sha256'][wzip.name]
 w={};wstats=C.Counter();rawfile_count=0
 def consume(name,b):
  nonlocal rawfile_count
  p1=list(parse(b));p2=independently_parse(b);assert p1==p2,(name,len(p1),len(p2));digest=hashlib.sha256(b).hexdigest();rawfile_count+=1
  for ordinal,ut,title,abstract,year in p1:
   assert ut not in w;w[ut]={'title':title,'abstract':abstract,'year':year,'raw_export_sha256':digest,'raw_filename':name,'raw_record_ordinal':ordinal};wstats['raw_records']+=1;wstats['raw_nonempty_abstract']+=present(abstract);wstats['raw_nonempty_title']+=present(title);wstats['raw_nonempty_year']+=present(year)
 consume(first.name,first.read_bytes())
 with zipfile.ZipFile(wzip) as z:
  assert z.testzip() is None
  for n in sorted(z.namelist()):
   if n.endswith('.txt'):consume(n,z.read(n))
 assert len(w)==30635 and rawfile_count==62
 source={};old_source={};wos_title_checks=0;abs_only=0
 with zipfile.ZipFile(stage2) as z:
  for r in rows(z,'source_records.jsonl.gz'):
   sid=r['source_record_id'];assert sid not in source;s=r['source_id'];q={k:r.get(k) for k in ('source_id','source_record_id','title','abstract','year','raw_export_sha256','raw_record_ordinal')}
   old_source[sid]={**q,'title':(q['title'] or '').strip(),'abstract':(q['abstract'] or '').strip()}
   if s=='woscc':
    v=w[r['source_native_id']];assert (r['raw_export_sha256'],r['raw_filename'],r['raw_record_ordinal'],r['title'])==(v['raw_export_sha256'],v['raw_filename'],v['raw_record_ordinal'],v['title']);wos_title_checks+=1;wstats['frozen_AB_missing_raw_present']+=present(v['abstract']) and not present(r.get('abstract'));wstats['frozen_PY_missing_raw_present']+=present(v['year']) and not present(r.get('year'));q.update({k:v[k] for k in ('abstract','year')})
   q['title']=(q['title'] or '').strip();q['abstract']=(q['abstract'] or '').strip();source[sid]=q;abs_only+=present(q['abstract']) and not present(q['title'])
 assert len(source)==87511 and wos_title_checks==30635
 out=[];changes=[];stats=C.Counter();transitions=C.Counter();old_records=[];problem=[]
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None
  for i,r in enumerate(rows(z,'full_pubmedbert_inputs.private.jsonl.gz')):
   a=r['article_id'];assert a==R[i]['article_id'];sids=[x['source_record_id'] for x in R[i]['source_years']];assert r['source_record_id'] in sids;old_available=[old_source[s] for s in sids];old_full=[s for s in old_available if present(s['title']) and present(s['abstract'])];old_best=min(old_full or [s for s in old_available if present(s['title'])],key=lambda s:(PRIORITY[s['source_id']],s['source_record_id']));assert (r['source_record_id'],r['title'],r.get('abstract'),r['text_state'])==(old_best['source_record_id'],old_best['title'],old_best['abstract'] if old_full else None,'title_abstract' if old_full else 'title_only');available=[source[s] for s in sids];full=[s for s in available if present(s['title']) and present(s['abstract'])];titles=[s for s in available if present(s['title'])];assert titles
   if not full and any(present(s['abstract']) for s in available):problem.append(a);raise AssertionError('abstract-only source resolution required')
   best=min(full or titles,key=lambda s:(PRIORITY[s['source_id']],s['source_record_id']));state='title_abstract' if full else 'title_only';q=dict(r);q.update(title=best['title'],abstract=best['abstract'] if full else None,text_state=state,source_id=best['source_id'],source_record_id=best['source_record_id'],raw_export_sha256=best['raw_export_sha256'],raw_record_ordinal=best['raw_record_ordinal'],year_raw=best['year'])
   # Preserve exact selected text and metadata for non-WoS rows which need no change.
   if best['source_record_id']==r['source_record_id'] and best['source_id']!='woscc':
    assert state==r['text_state'];assert (r['title'],r.get('abstract'))==(q['title'],q.get('abstract'));q=r.copy()
   change=text_hash(r)!=text_hash(q);source_change=q['source_record_id']!=r['source_record_id'];state_change=q['text_state']!=r['text_state'];metadata_change=q!=r;assert not (source_change or state_change) or change
   stats['old_title_only']+=r['text_state']=='title_only';stats['new_title_only']+=state=='title_only';stats['text_changed']+=change;stats['source_changed']+=source_change;stats['title_only_to_full']+=r['text_state']=='title_only' and state=='title_abstract';stats['any_row_changed']+=metadata_change;stats['metadata_only_changed']+=metadata_change and not change
   if change:transitions[(r['source_id'],r['text_state'],q['source_id'],state)]+=1
   if metadata_change:changes.append(dict(article_id=a,row_index=i,text_changed=change,source_changed=source_change,old_text_state=r['text_state'],new_text_state=state,old_source_record_id=r['source_record_id'],new_source_record_id=q['source_record_id'],old_text_sha256=text_hash(r),new_text_sha256=text_hash(q),new_raw_export_sha256=q['raw_export_sha256'],new_raw_record_ordinal=q['raw_record_ordinal']))
   out.append(q);old_records.append(r)
 assert len(out)==57204 and stats['text_changed']==6497 and stats['old_title_only']==7806 and stats['new_title_only']==1529 and stats['title_only_to_full']==6277 and stats['source_changed']==227 and len(problem)==0
 dest=d/'corrected_full_inputs.private.jsonl.gz';delta=d/'corrected_input_changes.private.jsonl.gz';dump_gzip(dest,out);dump_gzip(delta,changes)
 # Independent replay of serialized rows and eligibility, direct source field comparisons, and text-change census.
 reread=list(map(json.loads,gzip.open(dest,'rt')));dread=list(map(json.loads,gzip.open(delta,'rt')));assert reread==out and dread==changes and len(reread)==len(R) and len({x['article_id'] for x in reread})==len(R);changed_set={r['article_id'] for r in dread if r['text_changed']};assert len(changed_set)==stats['text_changed'];counter=C.Counter()
 for i,(q,r,yy) in enumerate(zip(reread,old_records,R)):
  assert q['article_id']==r['article_id']==yy['article_id'] and (q['peer_review_unknown'],q['wos_nr_cr_mismatch'])==(r['peer_review_unknown'],r['wos_nr_cr_mismatch']);s=source[q['source_record_id']];assert q['title']==s['title'] and q.get('abstract')==(s['abstract'] if q['text_state']=='title_abstract' else None);members=[source[x['source_record_id']] for x in yy['source_years']];assert q['source_record_id'] in {v['source_record_id'] for v in members}
  if q['text_state']=='title_only':assert not any(present(v['abstract']) for v in members)
  else:assert all(PRIORITY[v['source_id']]>=PRIORITY[s['source_id']] for v in members if present(v['title']) and present(v['abstract']))
  assert (q['article_id'] in changed_set)==(text_hash(q)!=text_hash(r));counter[q['source_id'],q['text_state']]+=1
 codezip=root/'STAGE2_PRIVATE_20261031_compute_code_evidence.zip';assert sha(codezip)=='c100e1371034d5234cf691d96e79fd5d2fb6058f7845b5884dc5ea48a2bb09b6'
 with zipfile.ZipFile(codezip) as z:
  assert z.testzip() is None;code=z.read('pro_adherence/stage2_sources.py').decode();wos_line=next(l for l in code.splitlines() if "source_id='woscc'" in l);assert "title=val('TI')" in wos_line and 'abstract=' not in wos_line and 'year=' not in wos_line;code_sha=hashlib.sha256(code.encode()).hexdigest()
 report={'schema':'stage3-wos-text-input-restoration/v1','status':'CORRECTED_INPUTS_PREPARED_AND_TECHNICALLY_VERIFIED_NOT_REEMBEDDED','defect':'Actual frozen Stage2 research WoS parser omitted AB/PY despite raw fields. This is a data lineage failure, not an approved scientific choice. Stage2 frozen identity, source records and citation graph left unchanged. Corrected derivative uses existing complete-record-first source policy.','source_sha256':yr['source_sha256'],'historical_research_code_archive_sha256':sha(codezip),'historical_wos_parser_sha256':code_sha,'source_counts':dict(wstats),'wos_title_identity_checks':wos_title_checks,'raw_wos_files':rawfile_count,'abstract_only_source_rows':abs_only,'source_resolution_cases_in_eligible':len(problem),'counts':dict(stats),'changed_text_transitions':[{'old_source':a,'old_state':b,'new_source':c,'new_state':e,'n':n} for (a,b,c,e),n in sorted(transitions.items())],'corrected_source_state_counts':[{'source':s,'state':t,'n':n} for (s,t),n in sorted(counter.items())],'outputs':{dest.name:{'sha256':sha(dest),'rows':len(out)},delta.name:{'sha256':sha(delta),'rows':len(changes)}},'verification':'2 independent full WoS field parsers agree exactly; all 30,635 UT/file SHA/ordinal/title joins match; synthetic continuation/absent AB test; original source selection and stripped texts replayed exactly on all 57,204 rows; all 57,204 serialized corrected inputs independently compared to same-source text, priority and eligible roster; changed-text hashes independently recounted; frozen corpus and graph untouched','boundaries':'No embeddings or clusters refit on corrected inputs. Existing semantic partitions preserved as diagnostic of omitted metadata, not as scientifically compliant full-text outputs. No change to node2vec or classic graph identity; no Stage gate/publication.'}
 (d/'wos_text_restoration_report.private.json').write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
