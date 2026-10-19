"""Focused-stage PubMed research; not approved stage source."""
import time,json,hashlib,random,urllib.parse,urllib.request,xml.etree.ElementTree as ET
BASE='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
FILTER='(english[la] AND "journal article"[pt])'
TITLE='''("medication adherence"[ti] OR "medication nonadherence"[ti] OR "medication non-adherence"[ti] OR "adherence to medication"[ti] OR "adherence to medications"[ti] OR "prescription adherence"[ti] OR "drug adherence"[ti] OR "medication compliance"[ti] OR "drug compliance"[ti] OR "medication persistence"[ti] OR "drug persistence"[ti] OR "medication possession ratio"[ti] OR "proportion of days covered"[ti] OR ("patient compliance"[ti] AND (medication*[tiab] OR prescription*[tiab] OR drug*[tiab])) OR (("treatment adherence"[ti] OR "therapy adherence"[ti] OR "treatment compliance"[ti]) AND (medication*[tiab] OR prescription*[tiab] OR pharmacotherap*[tiab])))'''
MAJOR='"Medication Adherence"[majr]'
HIST='("Patient Compliance"[majr] AND (medication*[tiab] OR prescription*[tiab] OR pharmacotherap*[tiab] OR (drug*[tiab] AND (patient*[tiab] OR prescribed[tiab] OR taking[tiab]))))'
PAIR='''("adherence medication"[tiab:~3] OR "nonadherence medication"[tiab:~3] OR "non-adherence medication"[tiab:~3] OR "compliance medication"[tiab:~3] OR "compliance prescription"[tiab:~3] OR "adherence prescription"[tiab:~3] OR "adherence drug"[tiab:~3])'''
PROXY='''("missed doses"[tiab] OR "proportion of days covered"[tiab] OR "medication possession ratio"[tiab] OR "prescription refill"[tiab])'''
Q={
'E_focus':'('+TITLE+' OR '+MAJOR+')',
'F_historical':'('+TITLE+' OR '+MAJOR+' OR '+HIST+')',
'G_proximity':'('+TITLE+' OR '+MAJOR+' OR '+PAIR+' OR '+PROXY+')',
'H_titleonly':TITLE
}

def api(endpoint,params):
    body=urllib.parse.urlencode({**params,'tool':'ProAdherenceQueryProbe'}).encode()
    for attempt in range(3):
        try:
            req=urllib.request.Request(BASE+endpoint,data=body,headers={'User-Agent':'ProAdherenceQueryProbe/1.0'})
            with urllib.request.urlopen(req,timeout=40) as res:return res.read()
        except Exception as ex:
            if attempt==2:raise
            print('RETRY',endpoint,type(ex).__name__,str(ex)[:200],flush=True)
            time.sleep(3*(attempt+1))

def search(q,n=0,start=0):
    r=json.loads(api('esearch.fcgi',{'db':'pubmed','term':'('+q+') AND '+FILTER,'retmode':'json','retmax':n,'retstart':start,'sort':'pub_date'}))['esearchresult']
    time.sleep(.45)
    return r

def fetch(ids):
    root=ET.fromstring(api('efetch.fcgi',{'db':'pubmed','id':','.join(ids),'retmode':'xml'}))
    time.sleep(.45)
    for row in root.findall('.//PubmedArticle'):
        pmid=row.findtext('./MedlineCitation/PMID','')
        e=row.find('./MedlineCitation/Article/ArticleTitle')
        title=''.join(e.itertext()).strip() if e is not None else ''
        ab=' '.join(''.join(x.itertext()).strip() for x in row.findall('./MedlineCitation/Article/Abstract/AbstractText'))
        yield {'pmid':pmid,'title':title,'abstract':ab[:3500]}

if __name__=='__main__':
 print('FOCUSED_BEGIN',flush=True)
 for label,q in Q.items():
    x=search(q)
    print('COUNT',label,x['count'],'SHA256',hashlib.sha256(q.encode()).hexdigest(),'WARNING',x.get('warninglist'),flush=True)
    y=search(q,n=120)
    ids=sorted(y['idlist'],key=lambda a:hashlib.sha256((label+'|focus|20261019|'+a).encode()).digest())[:12]
    print('IDS',label,','.join(ids),flush=True)
    for a in fetch(ids):print('ARTICLE',label,json.dumps(a,ensure_ascii=False),flush=True)
 print('FOCUSED_END',flush=True)
