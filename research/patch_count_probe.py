"""One-run candidate expansion count, sensitivity and translation audit."""
import json,time,hashlib
from pathlib import Path
from query_probe_precision_20261019 import api,FILTER
Q=json.loads(Path('configs/pubmed/medication-adherence-SELECTED.v1.json').read_text())['queries']['V04_S0']
P1='''("proportion of days covered"[tiab] OR "medication possession ratio"[tiab] OR "missed doses"[tiab] OR "pill count"[tiab] OR "directly observed therapy"[tiab] OR "medication taking"[tiab] OR "medication-taking"[tiab] OR "prescription refill"[tiab] OR "refill gaps"[tiab])'''
# Subject-specific medication types make adherence interpretable even when no generic drug/medication noun appears.
SPEC='''(antiretroviral*[tiab] OR PrEP[tiab] OR antipsychotic*[tiab] OR antiepileptic*[tiab] OR antiseizure[tiab] OR biologic*[tiab] OR insulin[tiab] OR statin*[tiab] OR inhaler*[tiab] OR anticoagulant*[tiab] OR immunosuppress*[tiab] OR ixekizumab[tiab] OR riluzole[tiab])'''
P2='((' + SPEC + ') AND (adheren*[tiab] OR nonadheren*[tiab] OR complian*[tiab] OR persisten*[tiab] OR "missed doses"[tiab]))'
PATCH={'P1_proxy':P1,'P2_drugclass':P2,'P12_union':f'({P1} OR {P2})'}
target='36334241 36436161 37682179 42876567 9404746 12441805 28807035 41040730'.split()
def req(term,n=0):
 x=json.loads(api('esearch.fcgi',{'db':'pubmed','term':term,'retmode':'json','retmax':n}))['esearchresult']
 time.sleep(0.45)
 return x
old=req(Q)
print('BASE_COUNT',old['count'],flush=True)
for name,p in PATCH.items():
 s='(('+Q+') OR (('+p+') AND '+FILTER+'))'
 r=req(s)
 alone=req('('+p+') AND '+FILTER)
 print('EXPANSION',name,'ALONE',alone['count'],'UNION',r['count'],'DELTA',int(r['count'])-int(old['count']),'WARN',r.get('warninglist'),flush=True)
 print('SHA',name,hashlib.sha256(s.encode()).hexdigest(),flush=True)
 uid='('+' OR '.join(x+'[uid]' for x in target)+')'
 got=req('('+s+') AND '+uid,50)
 found=set(got['idlist'])
 print('TARGETS',name,'INCLUDED',','.join(x for x in target if x in found),'MISSED',','.join(x for x in target if x not in found),flush=True)
print('PATCH_CHECK_DONE',flush=True)
