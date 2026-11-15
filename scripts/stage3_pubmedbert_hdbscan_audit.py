#!/usr/bin/env python3
"""Independent source-free replay auditor of private PubMedBERT CLS/Mean HDBSCAN pilot."""
import argparse,gzip,hashlib,json,collections,platform
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def audit(inp,outputs):
 source=json.loads((inp/'input_manifest.private.json').read_text())
 manifest=json.loads((outputs/'manifest.private.json').read_text())
 summary=json.loads((outputs/'summary.private.json').read_text())
 assert summary['status']=='SAMPLE_DIAGNOSTIC_ONLY_FULL_57204_NOT_CLUSTERED'
 assert len(source['shards'])==58 and sum(z['article_count'] for z in source['shards'])==57204
 assert summary['frozen_input_manifest_sha256']==sha(inp/'input_manifest.private.json')
 for n,details in manifest['outputs'].items():
  p=outputs/n;assert p.stat().st_size==details['bytes'] and sha(p)==details['sha256'],n
 gen=np.random.default_rng(20261031)
 idx12=np.sort(gen.choice(57204,12000,replace=False))
 idx6=np.sort(gen.choice(idx12,6000,replace=False))
 assert hashlib.sha256(idx12.tobytes()).hexdigest()==summary['samples_hashes']['n12000_sha256']
 assert hashlib.sha256(idx6.tobytes()).hexdigest()==summary['samples_hashes']['n6000_sha256']
 cohort=[json.loads(s)['article_id'] for s in gzip.open(inp/'cohort.article_roster.private.jsonl.gz','rt')]
 assert len(cohort)==57204 and len(set(cohort))==57204
 views={};count_by_view={};views_nonnull={}
 for view in ('cls','mean'):
  reader=gzip.open(outputs/f'{view}.pilot_assignments.private.jsonl.gz','rt')
  labels={k:{t:[] for t in (30,80,150)} for k in ('n12000_ms10','n6000_ms10','n6000_ms5')}
  i=0;n12=n6=0
  for line in reader:
   row=json.loads(line)
   assert i<57204 and row['node_index']==i and row['article_id']==cohort[i]
   if row['sample12']!=(i in idx12):raise AssertionError('Sample 12 status wrong')
   if row['sample6']!=(i in idx6):raise AssertionError('Sample 6 status wrong')
   n12+=int(row['sample12']);n6+=int(row['sample6'])
   for key in labels:
    target=key.startswith('n12000')
    selected=row['sample12'] if target else row['sample6']
    vals=row['results'][key]
    assert selected==(vals is not None)
    if not selected:continue
    assert len(vals)==3
    for t,record in zip((30,80,150),vals):
     assert record['min_cluster_size']==t
     noise=record['is_noise'];label=record['cluster']
     assert (label is None)==noise
     assert (label is None or (isinstance(label,int) and label>=0))
     assert 0<=record['membership_strength']<=1
     labels[key][t].append(-1 if noise else label)
   i+=1
  assert (i,n12,n6)==(57204,12000,6000)
  for key,series in labels.items():
   size=12000 if key.startswith('n12000') else 6000
   for t,r in series.items():
    values=np.asarray(r,dtype=np.int32)
    assert len(values)==size
    recorded=next(v for v in summary['poolings'][view]['runs'][key]['thresholds'] if v['min_cluster_size']==t)
    cc=collections.Counter(values[values>=0]);noise=int(sum(values<0))
    assert (recorded['clusters'],recorded['noise'],recorded['assigned'])==(len(cc),noise,size-noise)
    assert sorted(cc.values(),reverse=True)[:20]==recorded['largest_cluster_sizes']
  views[view]={k:{t:np.asarray(v,dtype=np.int32) for t,v in x.items()} for k,x in labels.items()}
  count_by_view[view]={'sample12':n12,'sample6':n6,'validated_runs':sum(len(x) for x in labels.values())}
 # Recompute sensitivity including noise and jointly-assigned without relying on runner calculations.
 res=[]
 for view in ('cls','mean'):
  for row in summary['poolings'][view]['sensitivity']:
   if 'min_cluster_size_a' in row:
    name=row['sample'];a=views[view][name][row['min_cluster_size_a']];b=views[view][name][row['min_cluster_size_b']]
   elif row.get('comparison')=='min_samples_10_vs_5_on_same_6000':
    t=row['min_cluster_size'];a=views[view]['n6000_ms10'][t];b=views[view]['n6000_ms5'][t]
   elif row.get('comparison')=='sample_size_12000_to_6000_same_members':
    t=row['min_cluster_size'];a=views[view]['n12000_ms10'][t][np.searchsorted(idx12,idx6)];b=views[view]['n6000_ms10'][t]
   else:raise AssertionError('Unknown sensitivity')
   ari=float(adjusted_rand_score(a,b));both=(a>=0)&(b>=0)
   ari_joint=float(adjusted_rand_score(a[both],b[both])) if both.sum()>1 else None
   assert abs(ari-row['ari_with_noise_as_label'])<1e-12
   assert int(both.sum())==row['both_assigned']
   if ari_joint is not None:assert abs(ari_joint-row['ari_joint_assigned'])<1e-12
   res.append(ari)
 for row in summary['between_poolings']:
  name=row['sample'];t=row['min_cluster_size'];a=views['cls'][name][t];b=views['mean'][name][t]
  ari=float(adjusted_rand_score(a,b));both=(a>=0)&(b>=0)
  assert abs(ari-row['ari_with_noise_as_label'])<1e-12 and int(both.sum())==row['both_assigned']
  if both.sum()>1:assert abs(float(adjusted_rand_score(a[both],b[both]))-row['ari_joint_assigned'])<1e-12
  res.append(ari)
 result={'schema':'pro-adherence-stage3-pubmedbert-hdbscan-independent-replay/v1','status':'PASS',
   'full_input_cohort':len(cohort),'shards':58,'sample_sizes':[12000,6000],
   'validated_label_grid':count_by_view,'independently_recomputed_ari':len(res),
   'all_expected_cluster_noise_sizes_match':True,'all_membership_probabilities_in_unit_interval':True,
   'full_57204_roster_sha_consistent':True,
   'source_input_sha256':sha(inp/'input_manifest.private.json'),'output_manifest_sha256':sha(outputs/'manifest.private.json'),
   'scientific_claims':False,'full_corpus_hdbscan_finished':False}
 (outputs/'independent_audit.private.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print(json.dumps(result),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--src',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.src,a.out)
