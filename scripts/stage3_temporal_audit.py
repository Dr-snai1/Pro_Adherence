"""Independent readback for the temporal control experiment and summary table."""
import collections as C,csv,json,sys,math
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score
from stage3_temporal_fixed import yearrows,load,sha,h,jread,seed,write,N

def run(root,out):
 R=yearrows(root,out);parts,_,_=load(root,R);Y=np.array([r['year'] or 0 for r in R]);frame=np.flatnonzero((Y>0)&(Y<=2025));idx=jread(out/'refit_sampling.private.json');sp=out/'refit_samples.private.npz';assert sha(sp)==idx['samples_npz_sha256'] and idx['year_roster_sha256']==sha(out/'publication_years.private.jsonl.gz');samples={};checks=C.Counter()
 with np.load(sp,allow_pickle=False) as z:
  assert set(z.files)=={r['sample'] for r in idx['samples']}
  for r in idx['samples']:
   a=z[r['sample']];assert a.dtype==np.int32 and len(a)==len(set(a.tolist()))==r['n'] and h(a.tobytes())==r['sha256'];assert set(a.tolist())<=set(frame.tolist());
   if r['kind']=='historical':assert np.array_equal(a,np.flatnonzero((Y>0)&(Y<=r['cutoff'])))
   else:assert r['seed']==seed('refit',r['cutoff'],int(r['sample'][-2:])) and np.array_equal(a,np.sort(np.random.default_rng(r['seed']).choice(frame,r['n'],replace=False)))
   samples[r['sample']]=a;checks['samples']+=1
 refs={p['name']:p['y'] for p in parts};all_records=[]
 for view in ['CLS','Mean','SPECTER2','node2vec','graphs']:
  report=jread(out/f'refit_{view}.private.json');p=out/f'refit_{view}.private.npz';assert sha(p)==report['assignments_sha256'];seen=set()
  with np.load(p,allow_pickle=False) as z:
   for r in report['records']:
    k=r['sample']+'__'+(r['mode'] if view!='graphs' else r['view']);assert k not in seen;seen.add(k);ix=samples[r['sample']];y=z[k];assert y.dtype==np.int32 and len(y)==len(ix)==r['n'] and h(y.tobytes())==r['assignment_sha256'];c=C.Counter(y.tolist());sizes=sorted([v for k,v in c.items() if k>=0],reverse=True);assert len(sizes)==r['clusters'] and sizes==r['cluster_sizes'] and sum(sizes)==r['assigned'] and c[-2]==r['missing_structural'] and c[-1]==r['noise'] and sum(s>=30 for s in sizes)==r['clusters_ge30'];assert r['ready']==len(ix)-c[-2]
    ref=refs[r['partition']][ix];ready=(y!=-2)&(ref!=-2);both=(y>=0)&(ref>=0);assert int(both.sum())==r['jointly_assigned']
    for mask,m in [(ready,'ari_same_ready'),(both,'ari_jointly_assigned')]:
     if mask.sum()>=2:assert abs(adjusted_rand_score(y[mask],ref[mask])-r[m])<1e-12
     else:assert r[m] is None
    if r['algorithm']=='HDBSCAN':assert np.array_equal(y==-2,ref==-2)
    else:assert c[-1]==0 and r['ready']==r['assigned']
    all_records.append(r);checks['refit_assignments']+=1
   assert seen==set(z.files)
 assert len(all_records)==363
 # Verify full annual counts by independent Python Counter from the frozen assignments, not from the summary.
 seen={};
 with (out/'temporal_annual_counts.private.tsv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f,delimiter='\t'):
   yr=0 if r['year']=='unknown' else int(r['year']);k=(r['partition'],yr,int(r['cluster_id_minus2_missing_minus1_noise']));assert k not in seen;seen[k]=int(r['count'])
 expected={}
 for p in parts:
  c=C.Counter(zip(Y.tolist(),p['y'].tolist()));expected.update({(p['name'],a,b):n for (a,b),n in c.items()})
 assert expected==seen;checks['annual_nonempty_rows']=len(seen)
 # Every fixed table observation independently rejoined by partition and slice.
 fixed=jread(out/'temporal_fixed_report.private.json');assert fixed['partition_count']==28 and len(fixed['results'])==336 and fixed['frame_n']==len(frame)
 totals=C.Counter();topic_rows=0;obs_counts={}
 for r in fixed['results']:
  p=refs[r['name']];period=r['period'];scope=r['scope'];mask=(Y>0)&(Y<=2025)
  if scope=='cumulative':mask&=(Y<=int(period[1:]))
  else:a,b=map(int,period.split('–'));mask&=(Y>=a)&(Y<=b)
  c=C.Counter(p[mask].tolist());assert sum(c.values())==r['n'];assert sum(k>=0 for k in c)==r['observed']['occupied'];assert abs((r['n']-c[-2]-c[-1])/r['n']-r['observed']['assigned_fraction'])<1e-12;obs_counts[(r['name'],scope,period)]=c;checks['fixed_slices']+=1
 with (out/'temporal_fixed_topics.private.tsv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f,delimiter='\t'):
   k=(r['partition'],r['slice_kind'],r['period']);c=obs_counts[k];n=int(r['n_in_slice']);assert n==c[int(r['cluster_id_minus2_missing_minus1_noise'])];totals[k]+=n;topic_rows+=1
 assert all(totals[k]==sum(c.values()) for k,c in obs_counts.items());checks['topic_rows']=topic_rows
 # Summarize all observed vs ten control ranges (not inferential CIs).
 summary=[];rows=[];fields=['clusters','clusters_ge30','noise_share_ready','missing_share_all','assigned_share_all','ari_same_ready','ari_jointly_assigned','assigned_jaccard','edges','modularity']
 for view,mode in sorted({(r['view'],r['mode']) for r in all_records}):
  x=[r for r in all_records if (r['view'],r['mode'])==(view,mode)]
  for cut in idx['cutoffs']:
   obs=next(r for r in x if r['sample']==f'{cut}_H');controls=[r for r in x if r['sample'].startswith(f'{cut}_R')];assert len(controls)==10 and all(r['n']==obs['n'] for r in controls)
   st={}
   for f in fields:
    vals=[r[f] for r in controls if f in r and r[f] is not None]
    if f in obs:st[f]={'historical':obs[f],'control_min':min(vals) if vals else None,'control_max':max(vals) if vals else None,'control_median':float(np.median(vals)) if vals else None}
   summary.append({'view':view,'mode':mode,'cutoff':cut,'n':obs['n'],'mcs':obs.get('mcs'),'metrics':st});rows.append([view,mode,cut,obs['n'],obs.get('mcs'),*[st.get(f,{}).get(k) for f in fields for k in ['historical','control_min','control_max']]])
 write(out,'temporal_refit_summary.private.tsv',['representation','threshold_rule','cutoff','n','min_cluster_size',*[f+'_'+k for f in fields for k in ['historical','control_min','control_max']]],rows)
 audit={'schema':'stage3-temporal-refit-and-fixed-independent-readback/v1','checks':dict(checks),'verification':'every sample seed and exact selection replay; every 363 serialized label vector SHA, sizes, missing/noise, ARI and coverage; all 28 annual count vectors independently reconstructed; all 336 fixed slice and 39,660 topic counts verified','refit_summary':summary,'limitations':'3 early cumulative cutoffs only; 10 uniform controls are descriptive ranges, not formal inference. HDBSCAN conditional on full-corpus fixed geometry, not refitting embeddings/UMAP. Leiden uses recomputed induced projections gamma=1 only, exploratory. No Louvain refit; fixed-map all 12 Louvain variants. Source/text-state matching only in fixed-map experiment. Original semantic text inputs have confirmed WoS omission and their temporal results are diagnostic only.'};(out/'temporal_refit_audit.private.json').write_text(json.dumps(audit,indent=2,allow_nan=False));print('AUDIT PASS',dict(checks),flush=True)
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
