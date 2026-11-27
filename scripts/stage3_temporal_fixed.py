"""Temporal composition of frozen partitions; same-size random counts (without replacement).
Separately condition the null on selected source and text state. No refit or cross-lens comparison.
"""
import collections as C,csv,gzip,hashlib,io,json,sys,zipfile
from pathlib import Path
import numpy as np
from stage3_temporal_years import sha
N=57204; B=999; CUTOFFS=[2000,2005,2010,2015,2020,2025]; BASE_SEED=20261127
SELECTED=[('CLS','U00-5-30-EOM',0,5,30),('Mean','U10-5-150-EOM',10,5,150),('SPECTER2','U17-10-150-EOM',17,10,150)]
def jread(p):return json.loads(p.read_text())
def gzrows(p):return list(map(json.loads,gzip.open(p,'rt')))
def h(b):return hashlib.sha256(b).hexdigest()
def jzip(z,k):return json.loads(z.read(k))
def seed(*x):return int.from_bytes(hashlib.sha256('|'.join(map(str,(BASE_SEED,*x))).encode()).digest()[:8],'little')
def yearrows(root,out):
 r=jread(out/'year_report.private.json');p=out/'publication_years.private.jsonl.gz';assert sha(p)==r['output_sha256'];R=gzrows(p);assert len(R)==N and all(x['row_index']==i for i,x in enumerate(R)) and len({x['article_id'] for x in R})==N
 roster=root/'STAGE3_20261115_PRIVATE_PUBMEDBERT_HDBSCAN_roster.jsonl.gz';assert sha(roster)=='3435a2e83d44e42db6c0f7de685f3e1e80ca6b4762b665af2daa9eef2fc09acf';assert [(x['article_id'],x['text_state']) for x in gzrows(roster)]==[(x['article_id'],x['text_state']) for x in R];return R

def load(root,R,include_graphs=True,projections=False):
 ids=[x['article_id'] for x in R];index={a:i for i,a in enumerate(ids)};parts=[];projs={};evidence={}
 def add(name,view,algorithm,approved,labels,y,**kw):
  assert y.shape==(N,) and set(np.unique(y[y>=0]).tolist())==set(labels);parts.append(dict(name=name,view=view,algorithm=algorithm,approved=approved,labels=labels,y=y,**kw))
 catp=root/'STAGE3_20261127_PRIVATE_CLUSTER_LABELS_TFIDF.json';assert sha(catp)=='a95a386da0afb07e57235624b4a84a4f3a58b2db0ca865d2ba0a86d84d87256a';cat=jread(catp);acceptp=root/'STAGE3_20261127_PRIVATE_UMAP_FULL_GRID_TECHNICAL_ACCEPTANCE.json';assert sha(acceptp)==cat['acceptance_sha256'];a=jread(acceptp);assert a['roster_sha256']==cat['roster_sha256'];evidence['semantic_catalog']=sha(catp);evidence['semantic_acceptance']=sha(acceptp)
 for view,key,ix,ms,mcs in SELECTED:
  run=next(p for p in cat['partitions'] if p[0]==key);cfg=a['configurations'][ix];assert cfg['config']['index']==ix and cfg['config']['n_components']==10;cp=next(c for c in cfg['checkpoints'] if c['drive_id']==run[16]);p=root/cp['name'];assert sha(p)==cp['sha256'];evidence[key]=sha(p)
  with zipfile.ZipFile(p) as z:
   assert z.testzip() is None;raw=z.read(f'hdbscan_ms{ms}.npz');assert h(raw)==run[17]
   with np.load(io.BytesIO(raw),allow_pickle=False) as d:y=np.array(d[f'eom_labels_{mcs}'],np.int32)
  cs=[c for c in cat['clusters'] if c[0]==key];labels={int(c[8]):c[12] for c in cs};assert len(labels)==run[8] and int((y==-1).sum())==run[10] and int((y>=0).sum())==run[9] and all(int((y==int(c[8])).sum())==c[10] for c in cs);add(key,view,'HDBSCAN',True,labels,y,ms=ms,mcs=mcs,config=cfg['config'])
  if projections:
   pj=next((c for c in cfg['checkpoints'] if 'PROJECTION' in c['name']),cp);q=root/pj['name'];assert sha(q)==pj['sha256']
   with zipfile.ZipFile(q) as z:
    v=z.read('projection.float32.npy');assert h(v)==cfg['projection_sha256'];X=np.load(io.BytesIO(v),allow_pickle=False);assert X.shape==(N,10) and np.isfinite(X).all();projs[view]=X
 nodep=root/'STAGE3_20261115_PRIVATE_node2vec_hdbscan_assignments.private.jsonl.gz';nodecatp=root/'STAGE3_20261127_PRIVATE_NODE2VEC_TFIDF_CATALOG.json';nodecat=jread(nodecatp);assert sha(nodep)==nodecat['assignment_sha256']=='f5043d0757445041e2610eae5357116998cc4dc8700e6e5fe56f3904a4d72cea';r=gzrows(nodep);assert len(r)==N and {x['article_id'] for x in r}==set(ids);y=np.full(N,-2,np.int32)
 for i,x in enumerate(r):
  assert x['node_index']==i
  if x['vector_status']=='ready':
   q=next(t for t in x['results'] if t['min_cluster_size']==30);y[index[x['article_id']]]=-1 if q['is_noise'] else int(q['cluster']);assert (q['cluster'] is None)==q['is_noise']
 p=next(p for p in nodecat['partitions'] if p['mcs']==30);labels={x['cluster_id']:x['label'] for x in p['clusters']};assert len(labels)==38 and int((y==-1).sum())==32335 and int((y==-2).sum())==13596 and all(int((y==c['cluster_id']).sum())==c['n'] for c in p['clusters']);add('node2vec-10-30-EOM','node2vec','HDBSCAN',True,labels,y,ms=10,mcs=30,config={'dimension':128});evidence['node2vec_assignments']=sha(nodep);evidence['node2vec_catalog']=sha(nodecatp)
 if projections:
  p=root/'STAGE3_20261112_PRIVATE_NODE2VEC_FULL_CPU.zip';assert sha(p)=='51f086fb71484065f54e4a8999528417607a817019feb13eef5941f9820947b4';evidence['node2vec_vectors']=sha(p)
  with zipfile.ZipFile(p) as z:
   assert z.testzip() is None;m=jzip(z,'manifest.private.json')
   for k,v in m['files'].items():assert h(z.read(k))==(v['sha256'] if isinstance(v,dict) else v)
   X=np.load(io.BytesIO(z.read('unit.float32.npy')),allow_pickle=False);assert X.shape==(43608,128) and np.isfinite(X).all();nx=np.load(io.BytesIO(z.read('node_indices.int32.npy')),allow_pickle=False);Y=np.full((N,128),np.nan,np.float32)
   A=list(map(json.loads,gzip.decompress(z.read('article_status.private.jsonl.gz')).decode().splitlines()));assert len(A)==N and {x['canonical_article_id'] for x in A}==set(ids)
   for j,x in enumerate(A):
    assert x['node_index']==j;i=index[x['canonical_article_id']];v=x['vector_row'];assert (v is None)==(y[i]==-2)
    if v is not None:assert nx[v]==j;Y[i]=X[v]
   assert np.array_equal(np.isfinite(Y).all(axis=1),y!=-2);projs['node2vec']=Y
 if not include_graphs:return parts,projs,evidence
 zpath=root/'STAGE3_20261127_PRIVATE_LEIDEN_FULL_EXPLORATORY.zip';assert sha(zpath)=='cff670c3c77772a986f9c65e075481878a4a64cdee113302b03df8f22052e95f';evidence['leiden_archive']=sha(zpath);active={}
 with zipfile.ZipFile(zpath) as z:
  assert z.testzip() is None;m=jzip(z,'archive_manifest.json');assert all(h(z.read(k))==v['sha256'] and len(z.read(k))==v['bytes'] for k,v in m['members'].items());gids=jzip(z,'mapping.json');assert len(gids)==N and set(gids)==set(ids);perm=np.array([index[x] for x in gids]);lc=jzip(z,'STAGE3_20261127_PRIVATE_LEIDEN_TFIDF_CATALOG.json')
  for graph in ['direct','cocitation','coupling']:
   a=list(map(json.loads,gzip.decompress(z.read(f'{graph}_assignments.private.jsonl.gz')).decode().splitlines()));assert len(a)==N and all(x['article_id']==gids[i] and x['node_index']==i for i,x in enumerate(a));rr=jzip(z,f'{graph}_report.private.json')
   for j,run in enumerate(rr['runs']):
    raw=np.array([x['community'][j] if x['community'][j] is not None else -1 for x in a],np.int32);assert h(raw.tobytes())==run['assignment_sha256'];y=np.full(N,-2,np.int32);y[perm]=np.where(raw>=0,raw,-2);active[graph]=(y>=0);p=next(p for p in lc['partitions'] if p['graph']==graph and p['resolution']==run['resolution'] and p['seed']==run['seed']);assert sorted(np.bincount(y[y>=0]).tolist(),reverse=True)==run['cluster_sizes'];labels={x['cluster_id']:x['label'] for x in p['clusters']};assert all(int((y==c['cluster_id']).sum())==c['n'] for c in p['clusters']);add(f'Leiden-{graph}-g{run["resolution"]}-{run["seed"]}',graph,'Leiden',False,labels,y,config={'gamma':run['resolution'],'seed':run['seed']})
 ap=root/'STAGE3_20261115_PRIVATE_LOUVAIN_ACCEPTANCE_MANIFEST.json';bp=root/'STAGE3_20261115_PRIVATE_COUPLING_SPARSE_LOUVAIN_ACCEPTANCE.json';assert sha(ap)=='72eca18012f4dd13a7045886dc5cf961c42d53597d9e10a3b245baea2efb3a97' and sha(bp)=='7335d454417af70a6b1bcfa1181db2b352c3d1c4191300ee10e325b960739be5';a=jread(ap);b=jread(bp);evidence['louvain_acceptance']=sha(ap);evidence['coupling_louvain_acceptance']=sha(bp)
 for graph,fn,prefix,runs,record in [('direct','direct_binary.assignments.private.jsonl.gz','STAGE3_20261115_PRIVATE_LOUVAIN_',a['results']['direct_binary']['runs'],a['files']),('cocitation','co_citation_weighted.assignments.private.jsonl.gz','STAGE3_20261115_PRIVATE_LOUVAIN_',a['results']['co_citation_weighted']['runs'],a['files']),('coupling','coupling_louvain_membership_articles.private.jsonl.gz','STAGE3_20261115_PRIVATE_',b['headline_runs'],b['outputs'])]:
  p=root/(prefix+fn);assert sha(p)==record[fn]['sha256'];evidence[f'louvain_{graph}']=sha(p);a2=gzrows(p);assert len(a2)==N and all(x['article_id']==gids[i] and x['node_index']==i for i,x in enumerate(a2))
  for j,run in enumerate(runs):
   raw=np.array([x['communities'][j] if x['communities'][j] is not None else -2 for x in a2],np.int32);y=np.full(N,-2,np.int32);y[perm]=raw;assert np.array_equal(y>=0,active[graph]);counts=C.Counter(int(k) for k in y if k>=0);assert len(counts)==run['communities'] and max(counts.values())==run['largest'];add(f'Louvain-{graph}-g{run["resolution"]}-{run["seed"]}',graph,'Louvain',False,{k:f'community {k}' for k in counts},y,config={'gamma':run['resolution'],'seed':run['seed']})
 assert len(parts)==28;return parts,projs,evidence

def metrics(counts,ref,matched):
 counts=np.atleast_2d(counts);n=counts.sum(axis=1);s=counts[:,2:];assigned=s.sum(axis=1);p=counts/n[:,None];a=np.maximum(assigned,1);q=s/a[:,None];ss=np.sum(q*q,axis=1);return {'occupied':(s>0).sum(axis=1),'occupied_ge30':(s>=30).sum(axis=1),'assigned_fraction':assigned/n,'noise_fraction':counts[:,1]/n,'structural_missing_fraction':counts[:,0]/n,'largest_among_assigned':s.max(axis=1)/a,'effective_clusters':np.divide(1,ss,out=np.zeros_like(ss),where=ss>0),'tv_full':.5*np.abs(p-ref).sum(axis=1),'tv_matched_expected':.5*np.abs(p-matched).sum(axis=1)}
def envelope(v):return {'median':float(np.median(v)),'p025':float(np.quantile(v,.025)),'p975':float(np.quantile(v,.975)),'min':float(v.min()),'max':float(v.max())}
def draw(rng,counts,n,b):
 if n==0:return np.zeros((b,len(counts)),np.int64)
 if n==counts.sum():return np.broadcast_to(counts,(b,len(counts))).copy()
 return rng.multivariate_hypergeometric(counts,int(n),size=b)
def write(out,name,header,rows):
 with (out/name).open('w',encoding='utf-8-sig',newline='') as f:w=csv.writer(f,delimiter='\t');w.writerow(header);w.writerows(rows)

def run(root,out):
 R=yearrows(root,out);parts,_,evidence=load(root,R);Y=np.array([x['year'] or 0 for x in R]);conf=np.array([x['year_status']=='conflict' for x in R]);frame=(Y>0)&(Y<=2025);strict=frame&~conf;strata=[(x['selected_source'],x['text_state']) for x in R];uniq=sorted(set(strata));G=np.array([uniq.index(s) for s in strata]);ns=int(frame.sum());assert ns==53229
 periods=[('cumulative',f'≤{c}',frame&(Y<=c)) for c in CUTOFFS]+[('disjoint',f'{a+1}–{b}',frame&(Y>a)&(Y<=b)) for a,b in zip([1968,*CUTOFFS[:-1]],CUTOFFS)];rows=[];topics=[];annual=[];detail=[];base=[]
 for p in parts:
  y=p['y']+2;K=int(y.max())+1;labels={0:'structural missing',1:'HDBSCAN noise',**{int(k)+2:v for k,v in p['labels'].items()}};assert all(int(k) in labels for k in np.unique(y));full=np.bincount(y,minlength=K);ref=np.bincount(y[frame],minlength=K);st=np.array([np.bincount(y[frame&(G==j)],minlength=K) for j in range(len(uniq))]);assert np.array_equal(st.sum(axis=0),ref);refp=ref/ns;refstrict=np.bincount(y[strict],minlength=K)/strict.sum();assert full.sum()==N;meta={k:v for k,v in p.items() if k not in ('y','labels')};base.append({**meta,'full_count':full.tolist(),'dated_count':ref.tolist(),'labels':labels})
  for yr in sorted(set(Y.tolist())):
   mask=Y==yr;c=np.bincount(y[mask],minlength=K);assert c.sum()==mask.sum()
   for k in np.flatnonzero(c):annual.append([p['name'],yr if yr else 'unknown',int(k)-2,labels[k],int(c[k]),int(mask.sum()),float(c[k]/mask.sum())])
  for scope,period,mask in periods:
   n=int(mask.sum());obs=np.bincount(y[mask],minlength=K);cc=C.Counter(y[mask].tolist());assert all(obs[k]==cc.get(k,0) for k in range(K)) and obs.sum()==n;nsj=np.bincount(G[mask],minlength=len(uniq));assert nsj.sum()==n and np.all(nsj<=st.sum(axis=1));s1=seed(p['name'],scope,period,'uniform');s2=seed(p['name'],scope,period,'matched');r1=np.random.default_rng(s1);r2=np.random.default_rng(s2);u=draw(r1,ref,n,B);m=np.zeros_like(u);ex=np.zeros(K)
   for j,num in enumerate(nsj):
    if num:m+=draw(r2,st[j],num,B);ex+=num*st[j]/st[j].sum()
   assert np.all(u.sum(axis=1)==n) and np.all(m.sum(axis=1)==n) and np.all(u<=ref) and np.all(m<=ref) and abs(ex.sum()-n)<1e-8
   o=metrics(obs,refp,ex/n);mu=metrics(u,refp,ex/n);mm=metrics(m,refp,ex/n);cs=np.bincount(y[mask&strict],minlength=K);strict_tv=float(.5*np.abs(cs/cs.sum()-refstrict).sum());os={k:float(v[0]) for k,v in o.items()};us={k:envelope(v) for k,v in mu.items()};ms={k:envelope(v) for k,v in mm.items()};detail.append({**meta,'scope':scope,'period':period,'n':n,'source_text_stratum_counts':nsj.tolist(),'conflicting_years_in_slice':int((mask&conf).sum()),'strict_n':int(cs.sum()),'strict_tv_full':strict_tv,'observed':os,'uniform_control':us,'source_text_matched_control':ms,'uniform_seed':s1,'matched_seed':s2,'repeats':B})
   rows.append([p['name'],p['view'],p['algorithm'],p['approved'],scope,period,n,int(os['occupied']),us['occupied']['p025'],us['occupied']['p975'],ms['occupied']['p025'],ms['occupied']['p975'],os['assigned_fraction'],os['noise_fraction'],os['structural_missing_fraction'],os['tv_full'],us['tv_full']['p025'],us['tv_full']['p975'],ms['tv_full']['p025'],ms['tv_full']['p975'],os['tv_matched_expected'],ms['tv_matched_expected']['p975'],strict_tv,os['effective_clusters'],us['effective_clusters']['p025'],us['effective_clusters']['p975'],ms['effective_clusters']['p025'],ms['effective_clusters']['p975']]);ul,uh=np.quantile(u,[.025,.975],axis=0);ml,mh=np.quantile(m,[.025,.975],axis=0)
   for k in sorted(labels):topics.append([p['name'],scope,period,n,k-2,labels[k],int(obs[k]),float(obs[k]/n),float(refp[k]),float(ex[k]/n),float(ul[k]/n),float(uh[k]/n),float(ml[k]/n),float(mh[k]/n)])
   if p['approved'] and scope=='cumulative':print(p['view'],period,n,'TV',round(os['tv_full'],4),'null',round(us['tv_full']['p975'],4),'matched',round(ms['tv_full']['p975'],4),'noise',round(os['noise_fraction'],4),'missing',round(os['structural_missing_fraction'],4),flush=True)
  assert np.array_equal(sum((np.bincount(y[Y==yr],minlength=K) for yr in set(Y.tolist())),start=np.zeros(K,dtype=np.int64)),full)
 write(out,'temporal_fixed_summary.private.tsv',['partition','view','algorithm','owner_selected','slice_kind','period','n','occupied','uniform_occ_p025','uniform_occ_p975','matched_occ_p025','matched_occ_p975','assigned_share_all','noise_share_all','structural_missing_share_all','TV_full','uniform_TV_p025','uniform_TV_p975','matched_TV_p025','matched_TV_p975','TV_matched_expected','matched_residual_TV_p975','strict_year_TV_full','effective_clusters','uniform_effective_p025','uniform_effective_p975','matched_effective_p025','matched_effective_p975'],rows)
 write(out,'temporal_fixed_topics.private.tsv',['partition','slice_kind','period','n','cluster_id_minus2_missing_minus1_noise','automatic_label_or_id','n_in_slice','share_all_slice','share_full_dated_frame','matched_expected_share','uniform_p025_share','uniform_p975_share','matched_p025_share','matched_p975_share'],topics)
 write(out,'temporal_annual_counts.private.tsv',['partition','year','cluster_id_minus2_missing_minus1_noise','automatic_label_or_id','count','year_total','share_all_year'],annual)
 outj={'schema':'stage3-temporal-fixed-composition/v1','scope':'retrospective fixed partitions; no refit; no claim of topic birth or structural evolution; no between-method rankings or external validation','sampling_frame':'all known selected years ≤2025; conflicts retained and strict-year sensitivity reported; 2026, 2027 and missing dates shown in annual table, excluded from control frame','frame_n':ns,'strict_n':int(strict.sum()),'control':'999 independent random subsets without replacement via exact multivariate hypergeometric count distribution; source × text-state matched draws additionally; no joint inference across partitions; descriptive pointwise envelopes, not multiplicity-adjusted inference','base_seed':BASE_SEED,'cutoffs':CUTOFFS,'strata':[list(s) for s in uniq],'stratum_counts':np.bincount(G[frame],minlength=len(uniq)).tolist(),'sources':evidence,'year_roster_sha256':sha(out/'publication_years.private.jsonl.gz'),'partition_count':len(parts),'partitions':base,'results':detail,'verification':'frozen archive and membership hashes/ID joins/coverage; independent Counter per slice; all control sizes and finite-population bounds; annual accounting PASS'};(out/'temporal_fixed_report.private.json').write_text(json.dumps(outj,ensure_ascii=False,indent=2,allow_nan=False));print('DONE fixed',len(parts),len(detail),len(topics),len(annual),flush=True)
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
