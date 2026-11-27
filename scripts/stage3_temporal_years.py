"""Reconstruct publication years from frozen source metadata; no mutable source calls."""
import collections as C, gzip, hashlib, json, re, sys, zipfile
from pathlib import Path
import numpy as np

def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rows(z,m):
    with gzip.GzipFile(fileobj=z.open(m)) as f:
        for l in f: yield json.loads(l)
def year(raw):
    m=re.match(r'^(19\d{2}|20\d{2})\b',str(raw or '').strip()); return int(m[1]) if m else None

def wos_records(name,data):
    digest=hashlib.sha256(data).hexdigest(); rec={};i=0
    for line in data.decode('utf-8-sig').splitlines():
        if line.startswith('PT '):
            assert not rec;rec={'PT':line[3:]}
        elif line.startswith(('UT ','PY ')):
            tag=line[:2];assert tag not in rec;rec[tag]=line[3:].strip()
        elif line.strip()=='ER':
            i+=1;assert 'UT' in rec and 'PT' in rec;yield rec['UT'],(name,digest,i,year(rec.get('PY')));rec={}
    assert not rec

def run(root,out):
    zpath=out/'frozen_stage2.zip'; wos=root/'WOS_STAGE2_ALL_REMAINING_501-30635.zip';first=root/'WOS_CORE_20261029_FULL180_ARTICLE_ENGLISH_000001-000500.txt'; ep=root/'STAGE3_20261110_PRIVATE_article_eligibility.jsonl.gz';rp=root/'STAGE3_20261115_PRIVATE_PUBMEDBERT_HDBSCAN_roster.jsonl.gz';sp=root/'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_INPUTS.zip'
    expected={zpath:'a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127',wos:'513e5837858801f72bc4063ca03cb482223b4b07a569276e1a1796cc1286d6bf',first:'3247ec52dabe2ab3a156df6b57bfdd38b4e0496861458e70d0de0f5fe59ce020',ep:'c080449e4a3450e6ff2e396c0463d05960d8b1cd101f42c7f99ccf3ab202e234',rp:'3435a2e83d44e42db6c0f7de685f3e1e80ca6b4762b665af2daa9eef2fc09acf',sp:'cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'}
    assert all(sha(p)==v for p,v in expected.items())
    w=dict(wos_records(first.name,first.read_bytes()));assert len(w)==500
    with zipfile.ZipFile(wos) as z:
        assert z.testzip() is None
        for n in sorted(z.namelist()):
            if n.endswith('.txt'):
                for ut,r in wos_records(n,z.read(n)):
                    assert ut not in w;w[ut]=r
    assert len(w)==30635
    source={};members={};wos_ordinal_offset=C.Counter()
    with zipfile.ZipFile(zpath) as z:
        assert z.testzip() is None
        for r in rows(z,'source_records.jsonl.gz'):
            sid=r['source_record_id'];assert sid not in source
            y=year(r.get('year'));s=r['source_id']
            if s=='woscc':
                name,digest,ordinal,y=w[r['source_native_id']];assert (name,digest)==(r['raw_filename'],r['raw_export_sha256']);offset=r['raw_record_ordinal']-ordinal;assert offset in (-1,0);wos_ordinal_offset[offset]+=1
            source[sid]=(s,y,r.get('year'),r['raw_export_sha256'])
        for r in rows(z,'canonical_articles.jsonl.gz'):
            aid=r['canonical_article_id'];assert aid not in members;members[aid]=r['source_record_ids']
    assert len(source)==87511 and len(members)==57293 and sum(wos_ordinal_offset.values())==30635 and len(wos_ordinal_offset)==1
    E={r['article_id']:r for r in map(json.loads,gzip.open(ep,'rt'))};assert len(E)==len(members) and set(E)==set(members)
    eligible={a for a,r in E.items() if r['primary_eligible']};assert len(eligible)==57204
    R=list(map(json.loads,gzip.open(rp,'rt')));assert len(R)==57204 and {r['article_id'] for r in R}==eligible
    stats=C.Counter(); records=[];priority={'pubmed':0,'woscc':1,'apa_psycinfo':2}
    with zipfile.ZipFile(sp) as z:
        assert z.testzip() is None
        for i,r in enumerate(rows(z,'full_pubmedbert_inputs.private.jsonl.gz')):
            a=r['article_id'];assert (a,r['text_state'])==(R[i]['article_id'],R[i]['text_state']);sids=members[a];assert set(sids)==set(E[a]['source_record_ids']);chosen=r['source_record_id'];assert chosen in sids; assert source[chosen][0]==r['source_id'] and source[chosen][3]==r['raw_export_sha256']
            vals=[(sid,*source[sid][:2]) for sid in sids]; known=[x for x in vals if x[2] is not None];ys=sorted(set(x[2] for x in known));old=year(r.get('year_raw'));sy=source[chosen][1];assert old is None or sy==old
            # Use the dated source selected for embeddings, else first dated canonical member by fixed source priority.
            used=chosen if sy is not None else (min(known,key=lambda x:(priority[x[1]],x[0]))[0] if known else None);y=source[used][1] if used else None
            flag='conflict' if len(ys)>1 else ('missing' if not ys else 'unanimous_known')
            stats['raw_selected_year_missing']+=old is None;stats['selected_source_year_missing_after_wos']+=sy is None;stats['recovered_from_selected_wos']+=old is None and sy is not None;stats['recovered_from_other_source']+=sy is None and y is not None;stats[flag]+=1;stats['post2026']+=y is not None and y>2026;stats['year_2026']+=y==2026
            records.append({'article_id':a,'row_index':i,'year':y,'selected_source':r['source_id'],'year_source_record_id':used,'year_source':source[used][0] if used else None,'source_years':[{'source_record_id':sid,'source':s,'year':yy} for sid,s,yy in vals],'year_min':min(ys) if ys else None,'year_max':max(ys) if ys else None,'year_status':flag,'text_state':r['text_state']})
    assert len(records)==57204 and stats['unanimous_known']+stats['conflict']+stats['missing']==57204
    dest=out/'publication_years.private.jsonl.gz'
    with dest.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as f:
        for r in records:f.write((json.dumps(r,separators=(',',':'))+'\n').encode())
    reread=list(map(json.loads,gzip.open(dest,'rt')));assert reread==records and len({r['article_id'] for r in reread})==len(records)
    count=C.Counter(r['year'] for r in records);conflicts=C.Counter((r['year_max']-r['year_min']) for r in records if r['year_status']=='conflict');
    report={'schema':'stage3-temporal-year-provenance/v1','source_sha256':{p.name:v for p,v in expected.items()},'scope':'derived analysis only; immutable frozen Stage2 unchanged','policy':'selected text source publication year; if missing, first dated canonical member PubMed > WoS > APA; use leading explicit year in raw date; WoS PY recovered by exact UT, filename, SHA and ordinal; retain all conflicts, min/max; no invented dates','counts':dict(stats),'annual_counts':{str(k):v for k,v in sorted(count.items(),key=lambda x:(x[0] is None,x[0] or 0))},'conflict_span_years':dict(conflicts),'source_year_coverage':{s:{'known':sum(x[0]==s and x[1] is not None for x in source.values()),'total':sum(x[0]==s for x in source.values())} for s in priority},'wos_ordinal_offsets':dict(wos_ordinal_offset),'output_sha256':sha(dest),'verification':'frozen ZIP SHA/CRC, exact source+canonical+eligibility+roster joins, WoS SHA/UT/ordinal, full serialized replay PASS'}
    (out/'year_report.private.json').write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
