#!/usr/bin/env python3
"""Source-free exact sklearn HDBSCAN pilot for original 768d PubMedBERT CLS & Mean.

Full frozen cohort is validated but algorithm is executed only on deterministic
12k/6k samples. No PCA, no UMAP, no approximate graph. This MUST NOT be
represented as full-corpus clustering or scientific topic validation.
"""
import argparse,gzip,hashlib,json,os,platform,time,collections,resource
from pathlib import Path
import numpy as np,sklearn
from sklearn.cluster import HDBSCAN
from sklearn.cluster._hdbscan.hdbscan import tree_to_labels
from sklearn.metrics import adjusted_rand_score

def sha(path):
 with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def extract_thresholds(X, min_samples, thresholds=(30,80,150), n_jobs=4):
 """Fit single MST once per min_samples; extract all three EOM flat clusterings exactly."""
 t=time.perf_counter();model=HDBSCAN(min_samples=min_samples,min_cluster_size=thresholds[0],
     metric='euclidean',algorithm='auto',leaf_size=40,n_jobs=n_jobs,copy=True,
     cluster_selection_method='eom',allow_single_cluster=False)
 labels0=model.fit_predict(X)
 tree=model._single_linkage_tree_
 results={}
 for size in thresholds:
  lab,prob=tree_to_labels(tree,size,cluster_selection_method='eom',allow_single_cluster=False,
                          cluster_selection_epsilon=0.0,max_cluster_size=None)
  lab=np.asarray(lab,dtype=np.int32);prob=np.asarray(prob,dtype=np.float64)
  if size==thresholds[0] and not np.array_equal(lab,labels0):raise AssertionError('MST extraction mismatch base model')
  unique,counts=np.unique(lab[lab>=0],return_counts=True)
  if not np.array_equal(unique,np.arange(len(unique))):raise AssertionError('Cluster labels not canonical')
  if not np.isfinite(prob).all() or not np.all((prob>=0)&(prob<=1)):raise AssertionError('Bad probability')
  results[size]={'labels':lab,'probabilities':prob,'metrics':{
      'min_cluster_size':int(size),'min_samples':int(min_samples),
      'clusters':int(len(unique)),'noise':int(np.sum(lab<0)),
      'assigned':int(np.sum(lab>=0)),'largest_cluster_sizes':sorted(counts.tolist(),reverse=True)[:20],
      'noise_fraction':float(np.mean(lab<0))}}
 return results,time.perf_counter()-t

def execute(src,out):
 if out.exists():raise FileExistsError(out)
 out.mkdir(parents=True,mode=0o700);os.chmod(out,0o700)
 raw=json.loads((src/'input_manifest.private.json').read_text())
 if raw.get('status')!='FULL_FROZEN_INPUT_VERIFIED' or raw['article_count']!=57204:raise ValueError('Source full input not verified')
 for name,details in raw['outputs'].items():
  p=src/name
  if p.stat().st_size!=details['bytes'] or sha(p)!=details['sha256']:raise ValueError(f'Input SHA mismatch: {name}')
 ids=[json.loads(s)['article_id'] for s in gzip.open(src/'cohort.article_roster.private.jsonl.gz','rt')]
 if len(ids)!=57204 or len(set(ids))!=57204:raise ValueError('Wrong article-id roster')
 rng=np.random.default_rng(20261031)
 sample12=np.sort(rng.choice(57204,size=12000,replace=False))
 sample6=np.sort(rng.choice(sample12,size=6000,replace=False))
 sample_hash={'n12000_sha256':hashlib.sha256(sample12.tobytes()).hexdigest(),
              'n6000_sha256':hashlib.sha256(sample6.tobytes()).hexdigest()}
 membership={};report={};timings={}
 for view in ('cls','mean'):
  mm=np.load(src/f'{view}_unit.float32.npy',mmap_mode='r')
  if mm.shape!=(57204,768):raise ValueError('Shape mismatch')
  runs={};timings[view]={}
  for sn,chosen,ms in [('n12000_ms10',sample12,10),('n6000_ms10',sample6,10),('n6000_ms5',sample6,5)]:
   X=np.asarray(mm[chosen],dtype=np.float64)
   xnorm=np.linalg.norm(X,axis=1)
   if not np.isfinite(X).all() or np.max(abs(xnorm-1))>3e-5:raise ValueError('Nonunit sample')
   print(json.dumps({'progress':'fit_start','pooling':view,'sample':sn,'n':len(chosen),'dimensions':X.shape[1]}),flush=True)
   vals,elapsed=extract_thresholds(X,ms)
   timings[view][sn]=round(elapsed,2)
   runs[sn]={'indices':chosen,'values':vals}
   print(json.dumps({'progress':'fit_complete','pooling':view,'sample':sn,'seconds':round(elapsed,2),
         'grid':[v['metrics'] for v in vals.values()],
         'max_rss_mb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)}),flush=True)
  membership[view]=runs
  sens=[]
  for name,slot in runs.items():
   for a,b in ((30,80),(80,150),(30,150)):
    A=slot['values'][a]['labels'];B=slot['values'][b]['labels'];keep=(A>=0)&(B>=0)
    sens.append({'sample':name,'min_cluster_size_a':a,'min_cluster_size_b':b,
      'ari_with_noise_as_label':float(adjusted_rand_score(A,B)),
      'both_assigned':int(keep.sum()),
      'ari_joint_assigned':float(adjusted_rand_score(A[keep],B[keep])) if keep.sum()>1 else None})
  for threshold in (30,80,150):
   A=runs['n6000_ms10']['values'][threshold]['labels'];B=runs['n6000_ms5']['values'][threshold]['labels'];keep=(A>=0)&(B>=0)
   sens.append({'comparison':'min_samples_10_vs_5_on_same_6000','min_cluster_size':threshold,
     'ari_with_noise_as_label':float(adjusted_rand_score(A,B)),
     'both_assigned':int(keep.sum()),
     'ari_joint_assigned':float(adjusted_rand_score(A[keep],B[keep])) if keep.sum()>1 else None})
  ref=runs['n12000_ms10'];rest=runs['n6000_ms10'];rel=np.searchsorted(sample12,sample6)
  if not np.array_equal(sample12[rel],sample6):raise ValueError('Sample not nested')
  for threshold in (30,80,150):
   A=ref['values'][threshold]['labels'][rel];B=rest['values'][threshold]['labels'];keep=(A>=0)&(B>=0)
   sens.append({'comparison':'sample_size_12000_to_6000_same_members','min_cluster_size':threshold,
     'ari_with_noise_as_label':float(adjusted_rand_score(A,B)),
     'both_assigned':int(keep.sum()),
     'ari_joint_assigned':float(adjusted_rand_score(A[keep],B[keep])) if keep.sum()>1 else None})
  report[view]={'runs':{name:{'sample_size':len(z['indices']),'min_samples':5 if name.endswith('ms5') else 10,
       'thresholds':[z['values'][k]['metrics'] for k in (30,80,150)]} for name,z in runs.items()},
       'sensitivity':sens}
 # Different view ARIs for same sampled article ids and comparable settings.
 between=[]
 for name in ('n12000_ms10','n6000_ms10','n6000_ms5'):
  for threshold in (30,80,150):
   A=membership['cls'][name]['values'][threshold]['labels'];B=membership['mean'][name]['values'][threshold]['labels'];keep=(A>=0)&(B>=0)
   between.append({'sample':name,'min_cluster_size':threshold,
     'ari_with_noise_as_label':float(adjusted_rand_score(A,B)),'both_assigned':int(keep.sum()),
     'ari_joint_assigned':float(adjusted_rand_score(A[keep],B[keep])) if keep.sum()>1 else None})
 summary={'schema':'pro-adherence-stage3-pubmedbert-cls-mean-hdbscan-pilot/v1','date_utc':'2026-11-15',
  'status':'SAMPLE_DIAGNOSTIC_ONLY_FULL_57204_NOT_CLUSTERED',
  'frozen_input_manifest_sha256':sha(src/'input_manifest.private.json'),
  'eligible_full_corpus':57204,'vector_dimension':768,'full_input_verified':True,
  'sample_strategy':'numpy PCG64 default_rng(20261031), uniform without replacement; n6000 nested in n12000',
  'samples_hashes':sample_hash,'method':'sklearn HDBSCAN exact original 768d L2-unit vectors, Euclidean, EOM; no PCA/UMAP/approximate graph',
  'min_samples_grid':[5,10],'min_cluster_size_grid':[30,80,150],
  'threshold_grid_optimization':'single MST per (sample,min_samples) reused for 30/80/150 via sklearn.cluster._hdbscan.hdbscan.tree_to_labels',
  'algorithm_package_versions':{'python':platform.python_version(),'numpy':np.__version__,'sklearn':sklearn.__version__},
  'timings_seconds':timings,'poolings':report,'between_poolings':between,
  'scientific_acceptance':False,
  'boundaries':['not full-corpus clustering','sample sensitivity not proof of thematic validity','high-dimensional clustering and density noise sensitive to sample and min_samples','no cluster topic labels','no external relevance test']}
 sp=out/'summary.private.json';sp.write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
 selected=set(sample12.tolist());chosen6=set(sample6.tolist())
 for view in ('cls','mean'):
  membership_path=out/f'{view}.pilot_assignments.private.jsonl.gz'
  with open(membership_path,'xb') as raw_file,gzip.GzipFile(fileobj=raw_file,mode='wb',filename='',mtime=0,compresslevel=6) as gz:
   lookup={name:dict(zip(run['indices'].tolist(),range(len(run['indices'])))) for name,run in membership[view].items()}
   for idx,aid in enumerate(ids):
    record={'article_id':aid,'node_index':idx,'sample12':idx in selected,'sample6':idx in chosen6,'results':{}}
    for name,run in membership[view].items():
     j=lookup[name].get(idx)
     if j is None:record['results'][name]=None
     else:record['results'][name]=[{'min_cluster_size':t,
       'cluster':int(run['values'][t]['labels'][j]) if run['values'][t]['labels'][j]>=0 else None,
       'is_noise':bool(run['values'][t]['labels'][j]<0),
       'membership_strength':float(run['values'][t]['probabilities'][j])} for t in (30,80,150)]
    gz.write((json.dumps(record,sort_keys=True,separators=(',',':'))+'\n').encode())
  with gzip.open(membership_path,'rt') as z:
   n12=n6=total=0
   for line in z:
    r=json.loads(line);total+=1;n12+=r['sample12'];n6+=r['sample6']
    if r['sample12']!=(r['results']['n12000_ms10'] is not None):raise AssertionError('12000 label mismatch')
    if r['sample6']!=(r['results']['n6000_ms10'] is not None):raise AssertionError('6000 label mismatch')
  if (total,n12,n6)!=(57204,12000,6000):raise AssertionError(f'Full roster count mismatch {view}')
 manifest={'schema':'pro-adherence-stage3-pubmedbert-hdbscan-pilot-output/v1',
  'status':'LOCAL_VERIFIED_REMOTE_PENDING','full_corpus_n':57204,'sampled_n':12000,
  'code_sha256':sha(__file__),'frozen_input_manifest_sha256':sha(src/'input_manifest.private.json'),
  'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in [sp,out/'cls.pilot_assignments.private.jsonl.gz',out/'mean.pilot_assignments.private.jsonl.gz']}}
 (out/'manifest.private.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'final':'PILOT_COMPLETE','summary':str(sp),'metrics':{p:{key:[z['metrics']['clusters'] for z in r['values'].values()] for key,r in membership[p].items()} for p in membership},'manifest':manifest}),flush=True)
 return summary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--src',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();execute(a.src,a.out)
