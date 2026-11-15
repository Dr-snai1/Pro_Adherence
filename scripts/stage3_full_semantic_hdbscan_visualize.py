#!/usr/bin/env python3
"""Descriptive figures and metadata diagnostics for three full semantic HDBSCAN lenses.
No topic labels, method rankings, or private output in source code.
"""
import json,gzip,hashlib,collections,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def sha(path):
 with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main(root):
 views=['pubmedbert_cls','pubmedbert_mean','specter2_proximity']
 display=['PubMedBERT CLS','PubMedBERT Mean','SPECTER2']
 keys=['30','80','150']
 data={}
 roster=list(map(json.loads,gzip.open(root.parent/'stage3_pubmedbert_hdbscan_20261115_private/cohort.article_roster.private.jsonl.gz','rt')))
 assert len(roster)==57204
 states=np.array([x['text_state'] for x in roster])
 metrics={}
 for name in views:
  rep=json.loads((root/name/'summary.private.json').read_text())
  labels={k:np.full(57204,-2,dtype=np.int32) for k in keys}
  strengths={k:np.zeros(57204,dtype=np.float64) for k in keys}
  for i,line in enumerate(gzip.open(root/name/'assignments.private.jsonl.gz','rt')):
   x=json.loads(line)
   assert i<57204 and x['node_index']==i and x['article_id']==roster[i]['article_id']
   for k in keys:
    v=x['labels'][k];labels[k][i]=v if v is not None else -1
    strengths[k][i]=x['membership_strength'][k]
  assert all(np.all(labels[k]!=-2) for k in keys)
  data[name]={'labels':labels,'strengths':strengths}
  diag={}
  for k in keys:
   lab=labels[k]
   count=collections.Counter(lab[lab>=0])
   assert len(count)==rep['results'][k]['cluster_count']
   checks={}
   for state in ['title_abstract','title_only']:
    sel=states==state
    checks[state]={'total':int(sel.sum()),'assigned':int((lab[sel]>=0).sum()),'noise':int((lab[sel]<0).sum()),
                   'noise_rate':float((lab[sel]<0).mean()),
                   'mean_member_strength_all':float(strengths[k][sel].mean())}
   diag[k]={'clusters':len(count),'assigned':int((lab>=0).sum()),'noise':int((lab<0).sum()),
            'noise_pct':round(100*float((lab<0).mean()),4),
            'largest_cluster':max(count.values(),default=0),
            'cluster_size_median':float(np.median(list(count.values()))) if count else None,
            'title_abstract_vs_title_only':checks}
  metrics[name]=diag
 out=root/'figures';out.mkdir(parents=True,exist_ok=True)
 # Two-dimensional summaries of actual 57,204-row full fits (no coordinates projected)
 X=np.arange(len(keys))
 fig,axs=plt.subplots(1,2,figsize=(12.5,4.8),layout='constrained')
 for label,name in zip(display,views):
  axs[0].plot(X,[metrics[name][k]['clusters'] for k in keys],marker='o',label=label)
  axs[1].plot(X,[metrics[name][k]['noise_pct'] for k in keys],marker='o',label=label)
 for ax,title,ylab in [(axs[0],'Number of clusters','Clusters'),(axs[1],'Fraction labeled noise','Noise (%)')]:
  ax.set_xticks(X,keys);ax.set_xlabel('min_cluster_size');ax.set_ylabel(ylab);ax.set_title(title);ax.grid(alpha=.25)
 axs[0].legend(loc='best',fontsize=8)
 fig.suptitle('Full-cohort HDBSCAN diagnostics | 57,204 articles | 768d | min_samples=10')
 fig.savefig(out/'full_semantic_hdbscan_sensitivity.png',dpi=180)
 plt.close(fig)
 # Top clusters plus noise, with no comparative "quality" claims
 fig,axs=plt.subplots(3,1,figsize=(12,11),layout='constrained')
 for ax,name,label in zip(axs,views,display):
  vals=sorted(collections.Counter(data[name]['labels']['30'][data[name]['labels']['30']>=0]).values(),reverse=True)
  ax.bar(np.arange(min(25,len(vals))),vals[:25]);ax.set_title(f'{label}: largest cluster sizes at min_cluster_size=30')
  ax.set_xlabel('Cluster size rank (descriptive)');ax.set_ylabel('Articles')
  ax.grid(axis='y',alpha=.3)
 fig.savefig(out/'full_semantic_hdbscan_cluster_sizes.png',dpi=180)
 plt.close(fig)
 fig,axs=plt.subplots(1,3,figsize=(15,4.5),layout='constrained')
 for ax,name,label in zip(axs,views,display):
  subset=metrics[name]['30']['title_abstract_vs_title_only']
  ax.bar(['title+abstract','title only'],[subset['title_abstract']['noise_rate']*100,subset['title_only']['noise_rate']*100]);ax.set_ylim(0,100)
  ax.set_ylabel('Noise (%)');ax.set_title(label);ax.grid(axis='y',alpha=.25)
 fig.suptitle('Descriptive HDBSCAN noise by source text availability (not causal)')
 fig.savefig(out/'full_semantic_hdbscan_text_availability.png',dpi=180)
 plt.close(fig)
 # Cross lens ARI as illustration only. Data from independent audit.
 audit=json.loads((root/'independent_audit.private.json').read_text())
 pairs=[('pubmedbert_cls','pubmedbert_mean'),('pubmedbert_cls','specter2_proximity'),('pubmedbert_mean','specter2_proximity')]
 vals=np.array([[next(d['ari_with_noise'] for d in audit['between_views'] if d['a']==a and d['b']==b and d['min_cluster_size']==int(k)) for k in keys] for a,b in pairs])
 fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained');hm=ax.imshow(vals,aspect='auto',vmin=-1,vmax=1,cmap='coolwarm')
 ax.set_xticks(range(3),keys);ax.set_yticks(range(3),['CLS vs Mean','CLS vs SPECTER2','Mean vs SPECTER2']);ax.set_xlabel('min_cluster_size');ax.set_title('Adjusted Rand index, noise included (diagnostic only)')
 for i in range(3):
  for j in range(3):ax.text(j,i,f'{vals[i,j]:.3f}',ha='center',va='center',color='black',fontsize=9)
 fig.colorbar(hm,ax=ax,fraction=.045,label='Adjusted Rand index')
 fig.savefig(out/'full_semantic_hdbscan_cross_lens_ari.png',dpi=180);plt.close(fig)
 output={'schema':'stage3-full-semantic-hdbscan-descriptive-analytics/v1','n':57204,'thresholds':[30,80,150],
         'min_samples':10,'results':metrics,'figures':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.glob('*.png'))},
         'scope':'full original 768d cohort; descriptive, not thematic validation'}
 p=root/'descriptive_analytics.private.json';p.write_text(json.dumps(output,sort_keys=True,indent=2)+'\n')
 print(json.dumps({'status':'COMPLETE','figures':list(output['figures']),'metrics':{k:[v[t]['clusters'] for t in keys] for k,v in metrics.items()}}))
if __name__=='__main__':main(Path(sys.argv[1]))
