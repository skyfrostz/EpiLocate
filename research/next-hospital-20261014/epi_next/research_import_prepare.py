"""Build RI itemized request from already saved inventory/evidence, never ZIP."""
import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
import re
from . import research_import as ri


def natural(path):
    tail=path.rsplit('/',1)[-1];m=re.search(r'(\d+)$',tail)
    return (int(m[1]) if m else 2**63,path.encode())


def selected_groups(inventory):
    categories={'COVID-19 Cases':('COVID-19',10,5),'Cap Cases':('CAP',10,5),'Normal Cases':('Normal',20,10)}
    dirs={}
    for member in inventory:
        parts=member['name'].split('/')
        if len(parts)==3 and parts[0] in categories and parts[-1].lower().endswith('.dcm'):
            dirs.setdefault('/'.join(parts[:2]),[]).append(member)
    result=[]
    for category,(label,ntrain,nval) in categories.items():
        names=sorted((d for d in dirs if d.startswith(category+'/')),key=natural)
        if len(names)<ntrain+nval:raise ri.Reject('INSUFFICIENT_FIXED_SOURCE_GROUPS')
        for i,directory in enumerate(names[:ntrain+nval]):
            result.append({'directory':directory,'source_diagnosis':label,'task_label':int(label!='Normal'),
                           'split':'train_weak' if i<ntrain else 'val_classification',
                           'members':sorted(dirs[directory],key=lambda m:m['name'].encode())})
    return result


def build(root):
    root=Path(root).resolve();private=root/'.local/phase2';out=private/'ri-v2-approval-request-20261011';out.mkdir(mode=0o700,exist_ok=False)
    a3path=private/'a3-structure-audit-v1-request-20261011/A3_EXACT_READONLY_MANIFEST.json'
    a1path=private/'a1-exact-request-v1-20261011/A1_TWO_STAGE_REQUEST_V1.json'
    a3=json.loads(a3path.read_text());a1=json.loads(a1path.read_text())
    ri.assert_file(a3['inventory_binding'])
    inventory=[json.loads(line) for line in Path(a3['inventory_binding']['path']).read_text().splitlines()]
    groups=selected_groups(inventory);seeds={g['directory'] for g in a3['selection']}
    evidence=a1['public_source_evidence'][:3]
    for item in evidence:ri.assert_file(item)
    label_provenance={'publisher_evidence':evidence,'subject_structure_readme_lines':[38,49],
                      'source_category_weak_label_only':True,'slice_level_label_files_read':False,
                      'clinical_patient_independence_status':'UNKNOWN','selection_not_algorithm_based':True}
    def group(g,stage,single=False):
        row=copy.deepcopy(g)
        if single:row['members']=[next(x['member'] for x in a3['selection'] if x['directory']==g['directory'])]
        row['source_group_id']=ri.digest((a3['source_archive']['version']+'|'+g['directory']).encode())
        row['record_id']=stage.replace('-','')+'-'+row['source_group_id'][:16]
        row['label_provenance']=label_provenance
        row['A3_seed_identity_nonconformant']=g['directory'] in seeds
        row['full_member_content_hashes']=None
        n=len(row['members']);compressed=sum(m['compressed_bytes'] for m in row['members']);inflated=sum(m['uncompressed_bytes'] for m in row['members'])
        caps=dict(compressed_input_bytes=compressed+sum(30+len(m['name'].encode())+65535 for m in row['members']),
                  inflated_member_bytes_total=inflated,output_bytes_total=n*512*512*4+2*1024**2,
                  RSS_stop_bytes=2*1024**3,wall_seconds=30 if single else 300)
        row['caps']=caps;row['metadata_counts']={'members':n,'payload_compressed_bytes':compressed,'uncompressed_bytes':inflated}
        return row
    six=[g for g in groups if g['directory'] in seeds]
    assert len(six)==6
    stages={}
    for stage,chosen,single,wall in [('RI-a',six,True,180),('RI-b',six,False,1800),('RI-c',groups,False,18000)]:
        rows=[group(g,stage,single) for g in chosen]
        caps=dict(**{k:sum(g['caps'][k] for g in rows) for k in ('compressed_input_bytes','inflated_member_bytes_total','output_bytes_total')},RSS_stop_bytes=2*1024**3,wall_seconds=wall)
        # Worst case RI-c counts all 60, including 6 potentially reused RI-b.
        stages[stage]={'groups':rows,'caps':caps,'per_group_wall_seconds':30 if single else 300,'stage_wall_seconds':wall,
                       'locked_member_count':sum(len(g['members']) for g in rows),
                       'payload_compressed_bytes':sum(g['metadata_counts']['payload_compressed_bytes'] for g in rows),
                       'reuse_policy':'SAME_RUN_ACCEPTED_RIB_SIX_ONLY; CAPS INCLUDE ALL_60' if stage=='RI-c' else 'NO_REUSE_RIA_SEED_REREAD_COUNTED',
                       'control_output_reserve_bytes':0}
    request={'schema':'RI_EXACT_BOUNDED_REQUEST_V1','status':'PREPARED_NOT_APPROVED_NOT_EXECUTED','contract_sha256':ri.old.sha(ri.CONTRACT),
             'source_archive':a3['source_archive'],'inventory_binding':a3['inventory_binding'],
             'A3_known_nonconformant_members':[x['member']['name'] for x in a3['selection']],
             'parent_bindings':[{'path':str(p),'sha256':ri.old.sha(p)} for p in (a3path,a1path)],
             'publisher_evidence':evidence,'publisher_group_semantics':'PUBLISHER_SUBJECT_DIRECTORY_BOUND',
             'stages':stages,'full_member_bytes_max':max(m['uncompressed_bytes'] for g in groups for m in g['members']),
             'overall_wall_seconds':20100,'disk_free_floor_bytes':20*1024**3,'CPU_threads':1,'max_attempts':1,
             'receipt_bytes_max':64*1024**2,'consumer_bytes_max':1024**2,'control_output_reserve_bytes':65*1024**2,
             'models_permitted':False,'training_permitted':False,'source_repair_permitted':False,
             'output_root':str(private/'ri-v2-execution-20261011'),
             'split_counts':{'train_weak':{'COVID-19':10,'CAP':10,'Normal':20},'val_classification':{'COVID-19':5,'CAP':5,'Normal':10}},
             'patient_count_claim':None,'clinical_patient_independence_status':'UNKNOWN','pretraining_overlap_status':'UNKNOWN','independent_test_claim':False,
             'selection_policy':'ascending trailing source-directory integer, UTF8 path tie; direct DCM only; fixed no substitutions',
             'scope':'CPU import audit only; encoder and training require separate approval'}
    ri.validate_request(request)
    def write(path,data):
        with open(path,'x') as handle:handle.write(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
        path.chmod(0o600);return ri.old.sha(path)
    reqpath=out/'RI_EXACT_REQUEST_V1.json';request_sha=write(reqpath,request)
    b=json.loads((private/'a2-diagnostic-v2-request-20261011/A2_DIAGNOSTIC_V2_READINESS.json').read_text())
    b.update(schema='RI_READINESS_V1',status='GENERATED_TESTED_PENDING_NEW_ITEMIZED_APPROVAL',request_path=str(reqpath),request_sha256=request_sha,
             generated_tests={'path':str(root/'research/next-hospital-20261014/tests/test_research_import.py')},real_header_reads=0,real_decodes=0,model_calls=0)
    for p in [Path(ri.__file__),ri.CONTRACT,Path(__file__),root/'research/next-hospital-20261014/tests/test_research_import.py']:
        b['source_bindings'].append({'path':str(p.resolve()),'sha256':ri.old.sha(p)})
    bound={i['module'] for i in b['decoder_module_bindings']}
    for name in ('pydicom.filereader','pydicom.filebase','pydicom.dataelem','pydicom.dataset','pydicom.values','pydicom.valuerep','pydicom.misc','pydicom.config'):
        if name not in bound:
            module=importlib.import_module(name);b['decoder_module_bindings'].append({'module':name,'path':module.__file__,'sha256':ri.old.sha(module.__file__)})
    readpath=out/'RI_READINESS_V1.json';readsha=write(readpath,b)
    template={'schema':'RI_ITEMIZED_APPROVAL_V1','status':'TEMPLATE_NOT_APPROVED','request_sha256':request_sha,'readiness_sha256':readsha,
              'permit_RI-a':False,'permit_RI-b':False,'permit_RI-c':False,'permit_full_member_reads':False,
              'permit_opaque_uid_fingerprints':{s:False for s in stages},'permit_model':False,'permit_training':False,'permit_source_repair':False}
    write(out/'RI_ITEMIZED_APPROVAL_TEMPLATE.json',template)
    summary={'request_path':str(reqpath),'request_sha256':request_sha,'readiness_path':str(readpath),'readiness_sha256':readsha,
             'stages':{s:{k:v for k,v in spec.items() if k!='groups'} for s,spec in stages.items()},'real_archive_body_reads':0}
    write(out/'RI_PREPARATION_DELIVERY.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args();build(args.root)
