#!/usr/bin/env python3
"""TASK-0003 V05: OFFLINE completion from all 250 immutable EFetch batches -> v3 canonical.

- Reuses pinned/previously proven collector evidence (never launches ESearch).
- Reuses exact previously owner-run V01 stage1_full_corpus_v2 and v3 canonical
  builder as byte-for-byte embedded code (their SHA256 are verified).
- Strict fail-closed Check A from every archived source response and manifest.
- Reuses frozen V05 complete PMID file; batches are resumable and append-only.
- No public promotion, no Stage2, no independent 04-QA claim.
- Prior failing query variants, source run, other corpus and human R/N/U unchanged.
"""
from __future__ import annotations
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import types
import zlib

CHECKOUT=Path(r'C:\Pro_Adherence\stage1-pilot-code-ae2dd813')
SOURCE=Path(r'C:\Pro_Adherence\research-backup\pubmed\TASK-0003\v05-proven-dp\r-d841c4b5c419f4f12eafee793f4c4fc0')
WORK=Path(r'C:\Pro_Adherence\stage1-v05-private\r-d841c4b5c419f4f12eafee793f4c4fc0')
DEPS=Path(r'C:\Pro_Adherence\stage1-pilot-deps-ae2dd813')
RUN_ID='r-d841c4b5c419f4f12eafee793f4c4fc0'
CODE_COMMIT='ae2dd8131fb7840ccb6f0ac9332dcf31ee4776ea'
CODE_BLOB='994879fcc9ee6e1b526f4c51fff296dcdf8ecd79'
QUERY_SHA='b042743ead0cd5f427d348972408917def58bc375b7daaf6da083cb8d298eb28'
UID_SHA='bbb34a0b69872c235d897d844b0338be4aa06adf167e090ae73e0d7e3ddcfe2b'
EXPECTED=49998
CHUNK_SIZE=200
FETCH_SHA='a8a6c993cf0b3632a188110a6d0bf75537b14175a8ebef3db8852d11ea50efbd'
BUILDER_SHA='7237f06a0c0afc9d9a907490222d9c9159d666b70e01c14b731e4c63a8169630'
# Frozen prior human review, not a model label or automatic scope decision.
CHECK_B={'verdict':'PASS','rule':'owner-post-review-2026-10-27-obvious-R-rationale-optional',
         'marked_R':37,'marked_N':8,'marked_U':5,'confirmed_R':36,'threshold_R':32,
         'conditional_R_not_counted':['31929433'],
         'review_uri':'https://docs.google.com/spreadsheets/d/1Q5yn8bbIp77w0nDlw3dAioVHTtL_C9Fq_2eVgWMjafo/edit'}
FETCH_EMBEDDED = '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'
BUILDER_EMBEDDED = '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'


def digest(raw): return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return (json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf-8')


def private_once(p,data):
    if p.is_symlink() or p.parent.is_symlink(): raise ValueError('UNSAFE_PRIVATE_PATH')
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        if p.read_bytes()!=data: raise ValueError('PRIVATE_ARTIFACT_CHANGED')
        return
    with p.open('xb') as f:f.write(data)


def unpack(text,p,expected):
    code=zlib.decompress(base64.b64decode(text))
    if digest(code)!=expected:raise ValueError('EMBEDDED_CODE_SHA_MISMATCH')
    private_once(p,code)
    return code


def load_module(path,namespace_name):
    ns={'__file__':str(path),'__name__':namespace_name,'__package__':None}
    exec(compile(path.read_bytes(),str(path),'exec'),ns)
    return ns


def run_source_a():
    if sys.version_info[:3]!=(3,13,16):raise ValueError('PYTHON_NOT_PINNED')
    if not SOURCE.is_dir() or SOURCE.is_symlink():raise ValueError('FROZEN_V05_SOURCE_MISSING')
    if not (CHECKOUT/'src'/'pro_adherence'/'pubmed_evidence.py').is_file():
        raise ValueError('PROVEN_COLLECTOR_NOT_INSTALLED')
    import subprocess
    def git(*args):
        return subprocess.run(['git','-C',str(CHECKOUT),*args],check=True,capture_output=True,text=True).stdout.strip()
    if git('rev-parse','HEAD')!=CODE_COMMIT or git('rev-parse','HEAD:src/pro_adherence/pubmed_evidence.py')!=CODE_BLOB:
        raise ValueError('PROVEN_COLLECTOR_CHECKOUT_DRIFT')
    if subprocess.run(['git','-C',str(CHECKOUT),'diff','--quiet','HEAD','--','src/pro_adherence/pubmed_evidence.py']).returncode:
        raise ValueError('PROVEN_COLLECTOR_CODE_MODIFIED')
    sys.path.insert(0,str((CHECKOUT/'src').resolve()))
    from pro_adherence import pubmed_evidence as ev
    if Path(ev.__file__).resolve()!=(CHECKOUT/'src'/'pro_adherence'/'pubmed_evidence.py').resolve():
        raise ValueError('UNEXPECTED_COLLECTOR_IMPORT')
    sourceinfo=ev.verify(SOURCE,require_final=True)
    manifest=json.loads((SOURCE/'manifest.json').read_bytes())
    if (manifest.get('status')!='final' or manifest.get('run_id')!=RUN_ID or
        manifest.get('code_commit')!=CODE_COMMIT or
        manifest.get('query_hashes')!={'SELECTED':QUERY_SHA} or
        manifest.get('partition_policy')!='pubdate-bisect/v1'):
        raise ValueError('SOURCE_MANIFEST_IDENTITY_DRIFT')
    rawquery=(SOURCE/'queries'/'SELECTED.txt').read_bytes()
    if digest(rawquery)!=QUERY_SHA:raise ValueError('SELECTED_QUERY_NOT_FROZEN')
    query=rawquery.decode('utf-8')
    if ('AND NOT' in query.upper() or 'english[la]' not in query or
         '"journal article"[pt]' not in query or 'medication adherence' not in query.lower()):
        raise ValueError('V05_SCOPE_FORMULA_UNEXPECTED')
    recon=manifest.get('reconciliation',{}).get('SELECTED',{})
    expected_uid=SOURCE/'pmids'/'SELECTED'/'union.txt'
    uidbytes=expected_uid.read_bytes()
    pmids=uidbytes.decode('ascii').splitlines()
    if (recon.get('unique_count')!=EXPECTED or recon.get('source_count')!=EXPECTED or
        len(pmids)!=EXPECTED or pmids!=sorted(set(pmids),key=int) or
        digest(uidbytes)!=UID_SHA or recon.get('union_sha256')!=UID_SHA):
        raise ValueError('FROZEN_UID_COVERAGE_DRIFT')
    requests=manifest.get('requests')
    if not isinstance(requests,list) or not requests:raise ValueError('SOURCE_REQUESTS_MISSING')
    n=benign=0
    roottrans=None
    request_dates=[]
    for item in requests:
        if item.get('endpoint')!=ev.ENDPOINT:continue
        if item.get('outcome')!='accepted':raise ValueError('SOURCE_REJECTED_RESPONSE_PRESENT')
        rel=item.get('file','')
        if not isinstance(rel,str) or not rel.startswith('raw/') or '..' in Path(rel).parts:
            raise ValueError('UNSAFE_SOURCE_RESPONSE_FILE')
        obj=json.loads((SOURCE/rel).read_bytes())['esearchresult']
        if 'error' in obj or any(bool(v) for v in (obj.get('errorlist') or {}).values()):
            raise ValueError('SOURCE_ERROR_IN_ARCHIVE')
        if not isinstance(obj.get('querytranslation'),str) or not obj['querytranslation'].strip():
            raise ValueError('SOURCE_QUERY_TRANSLATION_MISSING')
        transl=obj['querytranslation'].lower()
        # Search-set semantics, not exact PubMed text normalization: preserve
        # language, publication type and topic anchors in every translated request.
        for token in ('english','journal article','medication adherence'):
            if token not in transl:
                raise ValueError('SOURCE_QUERY_TRANSLATION_SCOPE_MISMATCH')
        warning=obj.get('warninglist') or {}
        if not isinstance(warning,dict):raise ValueError('SOURCE_WARNINGLIST_INVALID')
        active={k:v for k,v in warning.items() if v}
        if active:
            if not (active=={'outputmessages':['No items found.']} and
                    int(obj.get('count',-1))==0 and not obj.get('idlist')):
                raise ValueError('SOURCE_NONBENIGN_WARNING')
            benign+=1
        if item.get('exact_query')==query:
            if roottrans is not None:raise ValueError('SOURCE_ROOT_DUPLICATED')
            roottrans=obj['querytranslation']
        if not isinstance(item.get('utc'),str) or not item['utc']:
            raise ValueError('SOURCE_REQUEST_TIMESTAMP_MISSING')
        n+=1;request_dates.append(item['utc'])
    if roottrans is None:raise ValueError('SOURCE_ROOT_TRANSLATION_MISSING')
    if n<2 or 'SELECTED' not in manifest.get('query_states',{}):raise ValueError('SOURCE_TRACE_INCOMPLETE')
    if CHECK_B['confirmed_R']<CHECK_B['threshold_R']:raise ValueError('CHECK_B_NOT_PASSED')
    record={
        'schema':'task0003-v05-scientific-A-technical-evidence/v1',
        'scientific_verdict':'PASS_LOCAL_SOURCE_AUDIT_NOT_INDEPENDENT_01',
        'independent_04_QA':False,
        'v05_pinned_query_sha256':QUERY_SHA,'source_run_id':RUN_ID,
        'source_manifest_sha256':digest((SOURCE/'manifest.json').read_bytes()),
        'source_package_root_sha256':manifest['package_root_sha256'],
        'frozen_uid_sha256':UID_SHA,'unique_pmids':EXPECTED,
        'source_root_count':recon.get('source_count'),
        'overlap_occurrences':recon.get('duplicates'),
        'archived_esearch_requests':n,'benign_zero_hit_warnings':benign,
        'source_first_response_utc':min(request_dates),'source_last_response_utc':max(request_dates),
        'root_querytranslation_sha256':digest(roottrans.encode('utf-8')),
        'original_query_still_pinned':True,
        'raw_querytranslation_archived_in_source':True,
        'full_uid_reconciliation_reverified':True,
        'check_B':CHECK_B,
        'method':'byte-pinned ev.verify reparse + independent exact archived request translation/warning/count/uid source audit',
        'limitation':'External 01 scientific and 04 independent QA may audit archived evidence; no public promotion'
    }
    return manifest,query,pmids,record


def _retry_truncated_http_download(fn, *, sleep=None):
    """Retry only incomplete HTTP reads; preserve the pinned downloader and raw archive.

    Existing chunk handling remains untouched. A truncated HTTP response is never
    archived, because the pinned downloader raises before returning its bytes.
    """
    from http.client import IncompleteRead
    import time
    if sleep is None:
        sleep = time.sleep
    def wrapped(batch, timeout=60):
        for attempt in range(6):
            try:
                return fn(batch, timeout=timeout)
            except IncompleteRead:
                if attempt == 5:
                    raise RuntimeError('EFETCH_INCOMPLETE_READ_RETRIES_EXHAUSTED') from None
                sleep(min(30, 2 ** attempt + 1))
        raise AssertionError('unreachable')
    return wrapped


def run_pipeline():
    manifest,query,pmids,science=run_source_a()
    print('V05_CHECK_A_PRIVATE_SOURCE_PASS source_pmids=%d source_queries_reverified=true '
          'checkB=PASS_36of50 mass_efetch_authorized=true'%(len(pmids)),flush=True)
    srcroot=WORK/'_pinned_sources'
    fetch_code=unpack(FETCH_EMBEDDED,srcroot/'stage1_full_corpus_v2.py',FETCH_SHA)
    builder_code=unpack(BUILDER_EMBEDDED,srcroot/'stage1_canonical_build_v3.py',BUILDER_SHA)
    science_file=WORK/'scientific_checks_A_B.json'
    private_once(science_file,canonical(science))
    ns=load_module(srcroot/'stage1_full_corpus_v2.py','_pinned_v05_fetch')
    ns.update(EVIDENCE_ROOT=manifest['package_root_sha256'], EVIDENCE_RUN=RUN_ID,
              QUERY_ID='SELECTED',VERSION='stage1-V05-proven-dp-partitioned/v1')
    # Fail closed: this stage MUST NOT contact NCBI; all 250 responses are archived.
    def forbid_download(*args, **kwargs):
        raise ValueError('OFFLINE_CANONICAL_NO_NETWORK_ALLOWED')
    ns['download'] = forbid_download
    # Retarget ONLY legacy V01 source cursor namespace to frozen V05.
    orig_meta=ns['make_source_metadata']
    def v05_source_meta(query,pmid_hash,seq,batch,xml,*,stamp,time_basis):
        data=orig_meta(query,pmid_hash,seq,batch,xml,stamp=stamp,time_basis=time_basis)
        if not data['source_cursor'].startswith('frozen-S0:'):
            raise ValueError('FETCH_SOURCE_CURSOR_FORMAT_DRIFT')
        data['source_cursor']=data['source_cursor'].replace('frozen-S0:','frozen-V05:',1)
        return data
    ns['make_source_metadata']=v05_source_meta
    ing,ids,q,fullhash=ns['setup'](CHECKOUT,SOURCE)
    if ids!=pmids or fullhash!=UID_SHA or q.strip()!=query.strip():
        raise ValueError('FETCH_REVALIDATION_MISMATCH')
    total=(len(pmids)+CHUNK_SIZE-1)//CHUNK_SIZE
    if total!=250:raise ValueError('EFETCH_BATCH_COUNT_DRIFT')
    n=0
    for batchid,raw,meta,batch in ns['ensure_chunks'](
            ing,pmids,query,UID_SHA,WORK,fetch=False,batch_size=CHUNK_SIZE):
        n+=1
        if n%25==0:print(f'V05_FULL_EFETCH_PROGRESS archived_batches={n}/{total}',flush=True)
    if n!=total:raise ValueError('EFETCH_INCOMPLETE_STOP')
    print(f'V05_FULL_EFETCH_ARCHIVE_PASS archived_batches={total} pmids={len(pmids)}',flush=True)
    # Byte-identical conflict-preserving builder v3, retargeted in memory to the
    # completely verified V05 frozen source and its own private fetch archive.
    # Derive a code-hashed V05 wrapper of the proven builder; parsing/schema/
    # conflict-preserving semantics remain unchanged. Adapt only legacy V01
    # identity and source-science/status manifest labels for this V05 run.
    if builder_code.count(b"'query':'V01_S0'")!=1:
        raise ValueError('V3_ORIGINAL_MANIFEST_QUERY_SHAPE_DRIFT')
    adapted=builder_code.replace(b"'query':'V01_S0'",b"'query':ns['QUERY_ID']")
    adapted=adapted.replace(b"'status':'DRAFT_UNACCEPTED_NOT_QA'",b"'status':'DRAFT_NEEDS_QA'")
    adapted=adapted.replace(b"'scientific_source_status':'UNACCEPTED'",
                            b"'scientific_source_status':'CHECK_A_PRIVATE_PASS'")
    adapted=adapted.replace(b"scientific_status=UNACCEPTED",
                            b"scientific_status=CHECK_A_PRIVATE_PASS")
    adaptedpath=srcroot/'stage1_canonical_build_v3_V05_adapter.py'
    private_once(adaptedpath,adapted)
    bk=load_module(adaptedpath,'_pinned_v05_builder')
    bk['CHECKOUT']=CHECKOUT
    bk['PACKAGE']=SOURCE
    bk['WORKSPACE']=WORK
    bk['DEPS']=DEPS
    bk['FETCH']=srcroot/'stage1_full_corpus_v2.py'
    bk['EXPECTED_RECORDS']=len(pmids)
    bk['EXPECTED_BATCHES']=total
    # Root cause of the previous STOP: the old adapter assumed that the
    # journal-article PubMed filter implied no PubmedBookArticle XML families.
    # Derive an exact, independently rechecked family census from the validated
    # archived XML, never from a guess, and flag book-family records for 04 QA.
    family={'journal':0,'book':0}
    book_pmids=[]
    for seq,root,meta,rawhash,requested in bk['verified_batches'](ns,pmids):
        for entry in root:
            pmid,kind=bk['identity'](entry)
            if kind not in family:raise ValueError('UNSUPPORTED_SOURCE_RECORD_FAMILY')
            family[kind]+=1
            if kind=='book':book_pmids.append(pmid)
    if sum(family.values())!=len(pmids):
        raise ValueError('SOURCE_RECORD_FAMILY_CENSUS_NOT_COMPLETE')
    census={
        'schema':'task0003-v05-archived-record-family-census/v1',
        'method':'strict_xml and PMID membership from verified_batches plus identity on each immutable XML',
        'source_run_id':RUN_ID,'frozen_uid_sha256':UID_SHA,
        'source_family_counts':family,
        'book_family_pmids_sorted':sorted(book_pmids,key=int),
        'scientific_scope_note':('PubmedBookArticle record-family metadata exists in the frozen '
            'journal-article-filtered retrieval; preserve rather than silently exclude; '
            '04 independent QA/01 science to adjudicate record-family eligibility'),
        'no_network_requests':True,'public_promotion':False}
    census_path=WORK/'source_record_family_census.json'
    private_once(census_path,canonical(census))
    bk['EXPECTED_BOOKS']=family['book']
    bk['runpy']=types.SimpleNamespace(run_path=lambda path,run_name=None:ns)
    print('V05_ARCHIVED_RECORD_FAMILY_PASS journal=%d book=%d total=%d network_calls=0 '%(
          family['journal'],family['book'],len(pmids)),flush=True)
    if bk['build']()!=0:raise ValueError('V3_BUILD_FAILED')
    snaps=list((WORK/'corpus-v3').glob('*/corpus_manifest.json'))
    if len(snaps)!=1:raise ValueError('CANONICAL_SNAPSHOT_CARDINALITY')
    out=json.loads(snaps[0].read_bytes())
    if (out.get('canonical_records')!=len(pmids) or out.get('input_records')!=len(pmids) or
        out.get('query')!='SELECTED' or out.get('scientific_source_status')!='CHECK_A_PRIVATE_PASS' or
        out.get('status')!='DRAFT_NEEDS_QA' or out.get('qa_status')!='NOT_INDEPENDENTLY_QA_TESTED'):
        raise ValueError('CANONICAL_MANIFEST_READBACK_FAILED')
    report={
        'schema':'task0003-v05-private-handoff/v1',
        'source_run_id':RUN_ID,
        'v05_source':str(SOURCE),
        'canonical_snapshot':str(snaps[0].parent),
        'build_manifest_sha256':digest(snaps[0].read_bytes()),
        'proven_builder_original_sha256':BUILDER_SHA,
        'v05_manifest_label_adapter_sha256':digest(adapted),
        'source_record_family_census':str(census_path),
        'source_record_family_census_sha256':digest(canonical(census)),
        'family_counts':family,
        'book_family_scope_review_required':family['book']>0,
        'working_sqlite_sha256':out['sqlite_sha256'],
        'frozen_pmid_sha256':UID_SHA,
        'full_records':len(pmids),
        'technical_v3_status':'DRAFT_COMPLETE_NOT_INDEPENDENT_QA',
        'scientific_A':'PASS_LOCAL_SOURCE_AUDIT_NOT_INDEPENDENT_01',
        'scientific_B':'PASS_36_OF_50_OWNER_RULE_POST_REVIEW',
        'source_science_evidence':str(science_file),
        'raw_evidence_dir':str(WORK/'raw'),
        'license':'project-internal_only',
        'public_promotion':False,
        'qa_04_status':'NOT_EXECUTED'
    }
    private_once(WORK/'HOFF_0130_to_04_QA_payload.json',canonical(report))
    print('V05_TASK0003_PIPELINE_PASS source=49998 checkA=PASS checkB=PASS '
          f'efetch_batches={total} canonical_records={len(pmids)} '
          f'canonical_manifest_sha256={report["build_manifest_sha256"]} '
          f'sqlite_sha256={out["sqlite_sha256"]} qa04=OPEN public_promotion=false',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(run_pipeline())
    except Exception as exc:
        # Deliberately no raw source strings/PMIDs/email included in diagnostics.
        name=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r'[A-Z_0-9]{5,90}',str(exc)) else type(exc).__name__
        print(f'V05_TASK0003_STOP category={name} source_immutable=true public_promotion=false',flush=True)
        raise SystemExit(2)
