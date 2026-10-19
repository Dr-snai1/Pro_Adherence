"""Temporary scientific PubMed research probe. Never a Stage1 accepted query."""
import json,hashlib,time,urllib.parse,urllib.request,xml.etree.ElementTree as ET

BASE='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
F='(english[la] AND "journal article"[pt])'
DRUG='(medication*[tiab] OR prescription*[tiab] OR pharmacotherap*[tiab] OR medicine*[tiab] OR (drug*[tiab] AND (patient*[tiab] OR taking[tiab] OR prescribed[tiab] OR regimen*[tiab] OR dosing[tiab])))'
BEH='(adheren*[tiab] OR nonadheren*[tiab] OR non-adheren*[tiab] OR complian*[tiab] OR noncomplian*[tiab] OR non-complian*[tiab] OR persisten*[tiab] OR nonpersisten*[tiab])'
A='''("Medication Adherence"[mh] OR "medication adherence"[tiab] OR "medication nonadherence"[tiab] OR "medication non-adherence"[tiab] OR "adherence to medication"[tiab] OR "adherence to medications"[tiab] OR "drug adherence"[tiab] OR "prescription adherence"[tiab] OR "medication compliance"[tiab] OR "drug compliance"[tiab] OR "medication persistence"[tiab] OR "drug persistence"[tiab] OR "nonadherence to medication"[tiab:~0] OR "non-adherence to medication"[tiab:~0] OR ("patient compliance"[ti] AND medication*[tiab]))'''
B='('+A+' OR ('+BEH+' AND '+DRUG+'))'
C='('+A+' OR ((adheren*[ti] OR nonadheren*[ti] OR non-adheren*[ti] OR complian*[ti] OR noncomplian*[ti] OR persisten*[ti]) AND (medication*[ti] OR prescription*[ti] OR pharmacotherap*[ti] OR (drug*[ti] AND patient*[ti]))) OR "medication possession ratio"[tiab] OR "proportion of days covered"[tiab] OR ("pharmacy refill"[tiab] AND '+DRUG+') OR (("missed doses"[tiab] OR "doses taken"[tiab] OR "medication refill"[tiab]) AND '+DRUG+'))'
D='('+B+' OR "medication possession ratio"[tiab] OR "proportion of days covered"[tiab] OR ("pharmacy refill"[tiab] AND '+DRUG+') OR (("missed doses"[tiab] OR "doses taken"[tiab]) AND '+DRUG+'))'
Q={'A_direct':A,'B_context':B,'C_anchored':C,'D_balanced':D}

def post(api,params):
    params={**params,'tool':'ProAdherenceQueryProbe'}
    data=urllib.parse.urlencode(params).encode()
    for attempt in range(3):
        try:
            req=urllib.request.Request(BASE+api, data=data, headers={'User-Agent':'ProAdherenceQueryProbe/1.0'})
            with urllib.request.urlopen(req,timeout=45) as r:return r.read()
        except Exception as ex:
            if attempt==2:raise
            print('RETRY',api,type(ex).__name__,str(ex)[:160],flush=True)
            time.sleep(3*(attempt+1))

def search(q,retmax=0,retstart=0):
    data=json.loads(post('esearch.fcgi',{'db':'pubmed','term':'('+q+') AND '+F,'retmode':'json','retmax':retmax,'retstart':retstart,'sort':'pub_date'}))
    time.sleep(0.5)
    x=data['esearchresult']
    print('ES',x.get('count'),x.get('warninglist'),flush=True)
    return x

def fetch(ids):
    root=ET.fromstring(post('efetch.fcgi',{'db':'pubmed','id':','.join(ids),'retmode':'xml'}))
    time.sleep(0.5)
    out=[]
    for row in root.findall('.//PubmedArticle'):
        pmid=row.findtext('./MedlineCitation/PMID','')
        e=row.find('./MedlineCitation/Article/ArticleTitle')
        title=''.join(e.itertext()).strip() if e is not None else ''
        abstract=' '.join(''.join(x.itertext()).strip() for x in row.findall('./MedlineCitation/Article/Abstract/AbstractText'))
        out.append({'pmid':pmid,'title':title,'abstract':abstract[:2700]})
    return out

if __name__=='__main__':
    print('RESEARCH_ONLY_BEGIN')
    for label,q in Q.items():
        print('CANDIDATE',label,'SHA256',hashlib.sha256(q.encode()).hexdigest(),flush=True)
        r=search(q)
        print('TOTAL',label,int(r['count']),'TRANSLATION',str(r.get('querytranslation'))[:400],flush=True)
        # First quick diagnostic: newest citations are not a random corpus sample.
        ids=r['idlist']
        if not ids:
            ids=search(q,retmax=35)['idlist']
        else:
            ids=search(q,retmax=35)['idlist']
        ids=sorted(ids,key=lambda x:hashlib.sha256((label+'|20261019|'+x).encode()).digest())[:8]
        print('DIAGNOSTIC_IDS',label,','.join(ids),flush=True)
        for row in fetch(ids):
            print('ARTICLE',label,json.dumps(row,ensure_ascii=False),flush=True)
    print('RESEARCH_ONLY_END')
