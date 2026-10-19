"""Research-only recall diagnostic. No changes to accepted PubMed source."""
import json,hashlib,urllib.parse,time
from query_probe_20261019 import Q as first
from query_probe_precision_20261019 import Q as second,api,FILTER,TITLE,MAJOR,HIST,PAIR
POS=['9404746','12441805','17110087','22021483','23032359','23065532','25301330','26495883','28807035','29081045','29427293','31626087','31929426','33371973','35173501','35416595','37091492','38603915','38730371','39525610','41798698']
NEG=['1332520','2448571','2792052','2898461','3555041','7414106','8141977','8914177','9676753','9730424','9888412','10103334']
# Controlled extra alternatives: explicit textual medication-taking terms without all-purpose MeSH.
DIRECT='''("medication adherence"[tiab] OR "medication nonadherence"[tiab] OR "medication non-adherence"[tiab] OR "adherence to medication"[tiab] OR "adherence to medications"[tiab] OR "drug adherence"[tiab] OR "prescription adherence"[tiab] OR "medication compliance"[tiab] OR "drug compliance"[tiab])'''
I='('+TITLE+' OR '+MAJOR+' OR '+DIRECT+')'
J='('+I+' OR ('+HIST+' AND (adheren*[tiab] OR nonadheren*[tiab] OR complian*[tiab] OR noncomplian*[tiab])))'
ALL={**first,**second,'I_explicit':I,'J_explicit_historical':J}
def es(q,retmax=100):
 data=api('esearch.fcgi',{'db':'pubmed','term':'('+q+') AND '+FILTER,'retmode':'json','retmax':retmax})
 time.sleep(.5)
 return json.loads(data)['esearchresult']
for name,q in ALL.items():
 counts=es(q,0)
 print('STRATEGY',name,'COUNT',counts['count'],'QUERY_SHA256',hashlib.sha256(q.encode()).hexdigest(),flush=True)
 for typ,ids in [('POS',POS),('NEG',NEG)]:
  group='('+' OR '.join(x+'[uid]' for x in ids)+')'
  got=es('('+q+') AND '+group,100)
  found=set(got['idlist'])
  print('SENTINEL',name,typ,'FOUND',','.join(x for x in ids if x in found),'MISSED',','.join(x for x in ids if x not in found),flush=True)
