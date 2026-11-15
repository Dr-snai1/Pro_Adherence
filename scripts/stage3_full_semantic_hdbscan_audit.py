#!/usr/bin/env python3
"""Independent archive replay for full unprojected semantic HDBSCAN results.
No private data in this source file. Results remain owner-only.
"""
import sys,gzip,json,hashlib,collections,math,itertools
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score,normalized_mutual_info_score

def sha(path):
 with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def audit(root):
 roster=root.parent/'stage3_pubmedbert_hdbscan_20261115_private/cohort.article_roster.private.jsonl.gz'
 expected_ids=[json.loads(line)['article_id'] for line in gzip.open(roster,'rt')]
 assert len(expected_ids)==57204 and len(set(expected_ids))==57204
 results={};all_labels={}
 for view in ['pubmedbert_cls','pubmedbert_mean','specter2_proximity']:
  d=root/view;mf=json.loads((d/'manifest.private.json').read_text());report=json.loads((d/'summary.private.json').read_text());
  assert report['status']=='FULL_57204_EXACT_HDBSCAN_LOCAL_COMPUTED'
  for name,details in mf['data_paths'].items():
   p=d/name;assert p.stat().st_size==details['bytes'] and sha(p)==details['sha256'],(view,name)
  assert mf['input_roster_sha256']==sha(roster)
  labels={str(t):np.empty(57204,dtype=np.int32) for t in (30,80,150)}
  counts=collections.Counter();all_ids=set()
  for i,line in enumerate(gzip.open(d/'assignments.private.jsonl.gz','rt')):
   r=json.loads(line);assert r['node_index']==i and r['article_id']==expected_ids[i] and r['article_id'] not in all_ids
   all_ids.add(r['article_id'])
   for t,lab in labels.items():
    cid=r['labels'][t];noise=r['noise'][t];p=r['membership_strength'][t]
    assert isinstance(noise,bool) and noise==(cid is None) and math.isfinite(p) and 0<=p<=1
    lab[i]=-1 if cid is None else int(cid)
    counts[(t,int(lab[i]))]+=1
  assert len(all_ids)==57204,(view,len(all_ids))
  for t,arr in labels.items():
   a=report['results'][t];assigned=arr[arr>=0]
   clusters=np.unique(assigned)
   assert list(clusters)==list(range(a['cluster_count']))
   assert len(assigned)==a['assigned'] and int((arr<0).sum())==a['noise']
   assert sorted(collections.Counter(assigned).values(),reverse=True)==a['sizes_descending']
   assert sum(counts[(t,j)] for j in range(a['cluster_count']))==a['assigned']
  results[view]={'row_count':len(all_ids),'source_sha_verified':True,
   'view_summary_sha':sha(d/'summary.private.json'),'membership_sha':sha(d/'assignments.private.jsonl.gz'),
   'clusters':{k:report['results'][k]['cluster_count'] for k in labels}}
  all_labels[view]=labels
 comparisons=[]
 for a,b in itertools.combinations(all_labels,2):
  for t in ('30','80','150'):
   A=all_labels[a][t];B=all_labels[b][t];keep=(A>=0)&(B>=0)
   comparisons.append({'a':a,'b':b,'min_cluster_size':int(t),
    'ari_with_noise':float(adjusted_rand_score(A,B)),
    'nmi_with_noise':float(normalized_mutual_info_score(A,B)),
    'joint_assigned':int(keep.sum()),
    'ari_joint_assigned':float(adjusted_rand_score(A[keep],B[keep])) if keep.sum()>1 else None})
 within=[]
 for a,lbs in all_labels.items():
  for t,u in [('30','80'),('80','150'),('30','150')]:
   A=lbs[t];B=lbs[u];keep=(A>=0)&(B>=0)
   within.append({'view':a,'sizes':[int(t),int(u)],'ari_with_noise':float(adjusted_rand_score(A,B)),
    'joint_assigned':int(keep.sum()),'ari_joint_assigned':float(adjusted_rand_score(A[keep],B[keep])) if keep.sum()>1 else None})
 out={'schema':'pro-adherence-stage3-full-semantic-hdbscan-audit/v1','status':'PASS','source_roster_sha':sha(roster),
      'full_cohort':len(expected_ids),'views':results,'between_views':comparisons,'within_views':within,
      'warning':'ARI including noise and ARI for jointly assigned papers measure different things; neither establishes thematic validity'}
 (root/'independent_audit.private.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'PASS','views':list(results),'pairwise_checks':len(comparisons),'within_checks':len(within)}))
if __name__=='__main__':audit(Path(sys.argv[1]))
