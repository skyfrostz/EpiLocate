"""Metadata-only reconciliation of the R77 failed aggregate receipt.
Reads bound JSON only. Never repairs the original terminal status or consumer.
"""
import argparse,hashlib,json,os
from pathlib import Path
from .a0_acquire import exclusive,publish

INDEX_LIMIT=256*1024
READ_LIMIT=128*1024**2
STAGE_GROUPS={'RIa':6,'RIb':6,'RIc':54}
STAGE_FRAMES={'RIa':6,'RIb':891,'RIc':8208}


class Reject(ValueError):pass


class Reader:
    def __init__(self,check=None):self.used=0;self.check=check or (lambda:None)
    def read(self,ref,limit):
        self.check();path=Path(ref['path'])
        if path.suffix!='.json' or path.is_symlink():raise Reject('BOUND_REGULAR_JSON_ONLY')
        with path.open('rb') as stream:raw=stream.read(limit+1)
        self.used+=len(raw)
        if len(raw)>limit or self.used>READ_LIMIT:raise Reject('METADATA_READ_LIMIT')
        if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise Reject('METADATA_SHA_DRIFT')
        if 'bytes' in ref and len(raw)!=ref['bytes']:raise Reject('METADATA_LENGTH_DRIFT')
        data=json.loads(raw);self.check();return data


def build_index(delivery_ref,reader=None):
    reader=reader or Reader();delivery=reader.read(delivery_ref,64*1024)
    if delivery['status']!='REPORTING_FAILURE_NO_RETRY' or delivery['CLI_exit_code']!=1 or delivery['primary_error']['reason_code']!='OUTPUT_LIMIT':raise Reject('FAILED_R77_RUN_REQUIRED')
    if delivery.get('model_calls')!=0 or delivery.get('training_calls')!=0 or delivery.get('retry') is not False:raise Reject('ORIGINAL_SCOPE_REQUIRED')
    consumer_ref={k:delivery['consumer'][k] for k in ('path','sha256','bytes')};consumer=reader.read(consumer_ref,1024**2)
    if len(consumer)!=60 or sum(x['split']=='train_weak' for x in consumer)!=40 or sum(x['split']=='val_classification' for x in consumer)!=20:raise Reject('FIXED60_SPLIT_REQUIRED')
    if len({x['source_group_id'] for x in consumer})!=60:raise Reject('FIXED60_GROUP_UNIQUENESS')
    references=delivery['group_ledger_index']
    if len(references)!=66 or len({x['path'] for x in references})!=66:raise Reject('EXACT66_LEDGER_INDEX_REQUIRED')
    root=Path(consumer_ref['path']).parent.resolve();items=[];groups={k:0 for k in STAGE_GROUPS};frames={k:0 for k in STAGE_FRAMES};calls={};cost={k:{n:0 for n in ('compressed_input_bytes','inflated_bytes','cumulative_written_bytes')} for k in STAGE_GROUPS};by_path={}
    for ref in references:
        path=Path(ref['path'])
        if path.name!='research-ledger.json' or path.resolve().parent.parent!=root:raise Reject('EXISTING_GROUP_LEDGER_ONLY')
        data=reader.read(ref,8*1024**2);stage=ref['stage'];records=data['frame_ledgers']
        if stage not in groups or data['record_id']!=ref['record_id'] or len(records)!=ref['frames']:raise Reject('LEDGER_INDEX_COUNTS_DRIFT')
        if data.get('PIXEL_QA')!='PASS' or data.get('RESCALE_QA')!='PASS_DECLARED_HU':raise Reject('PERSISTED_GROUP_QA_REQUIRED')
        groups[stage]+=1;frames[stage]+=len(records)
        for frame in records:
            diag=frame['diagnostic'];counts=diag['counts']
            if diag['primary_error'] is not None or diag['reporting_error'] is not None or not diag['integrity']['CRC_verified'] or not diag['integrity']['EOF_verified']:raise Reject('PERSISTED_FRAME_INTEGRITY_REQUIRED')
            if frame['qa']['scalar_rescale_applications']!=1 or frame['unit_interpretation']['unit_branch'] not in ('EXPLICIT_HU','DICOM_CONDITIONAL_HU'):raise Reject('PERSISTED_FRAME_HU_REQUIRED')
            for key in ('as_buffer_api_entered','as_buffer_api_returned','native_parameter_probe_entered','native_parameter_probe_returned'):
                if counts[key]!=1:raise Reject('PERSISTED_API_COUNTS_REQUIRED')
            for key,value in counts.items():
                if type(value) is int:calls[key]=calls.get(key,0)+value
        for key in ('compressed_input_bytes','inflated_bytes'):cost[stage][key]+=data['budget'][key]
        # Group JSON stored budget precedes its own write; add known JSON size.
        cost[stage]['cumulative_written_bytes']+=data['budget']['output_bytes']+ref['bytes']
        item={k:ref[k] for k in ('path','sha256','bytes','record_id','stage','frames')};items.append(item);by_path[str(path.resolve())]=ref
    if groups!=STAGE_GROUPS or frames!=STAGE_FRAMES or calls!= {k:v for k,v in delivery['calls'].items() if type(v) is int}:raise Reject('FAILED_DELIVERY_COUNTS_DRIFT')
    if cost!=delivery['observed_group_budget_totals']:raise Reject('FAILED_DELIVERY_COST_DRIFT')
    for row in consumer:
        ref=by_path.get(str(Path(row['geometry_ledger']['path']).resolve()))
        if ref is None or ref['stage']=='RIa' or ref['sha256']!=row['geometry_ledger']['sha256']:raise Reject('CONSUMER_EXISTING_GEOMETRY_BINDING_REQUIRED')
        if row['cross_group_duplicate_audit']!='PASS' or row['cross_split_duplicate_audit']!='PASS':raise Reject('CONSUMER_DUPLICATE_QA_REQUIRED')
    index={'schema':'R77_FAILED_RUN_LEDGER_REFERENCE_INDEX_V1','status':'METADATA_RECONCILIATION_ONLY_ORIGINAL_EXECUTION_FAILED','original_execution_status':delivery['status'],'original_CLI_exit_code':1,
           'original_failure':delivery['primary_error'],'original_final_receipt_missing':delivery['final_receipt_missing'],
           'delivery_binding':delivery_ref,'request_binding':delivery['request'],'consumer_binding':consumer_ref,'consumer_unchanged':True,
           'groups':groups,'member_visits':frames,'calls':dict(calls,plugin_entered='UNKNOWN',plugin_returned='UNKNOWN'),
           'observed_group_budget_totals':cost,'ledger_index':items,'original_exit_proof':delivery['exit_proof'],
           'metadata_bytes_read':reader.used,'source_zip_reads':0,'pixel_array_reads':0,'decode_calls':0,'model_calls':0,'training_calls':0,
           'original_release_modified':False,'downstream_admission':'NO_AUTOMATIC_ADMISSION_OR_SUCCESS_RELEASE'}
    if len(encoded(index))>INDEX_LIMIT:raise Reject('INDEX_OUTPUT_LIMIT')
    return index


def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n').encode()


def publish_index(index,destination):
    path=Path(destination)
    if path.name in ('receipt.json','release.json','ENC_RESEARCH_SOURCE_CASES_V2.json'):raise Reject('ORIGINAL_ARTIFACT_NAME_FORBIDDEN')
    content=encoded(index)
    if len(content)>INDEX_LIMIT:raise Reject('INDEX_OUTPUT_LIMIT')
    part=path.with_name(path.name+'.part')
    with os.fdopen(exclusive(part),'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
    publish(part,path)
    return {'path':str(path),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--delivery',required=True);p.add_argument('--delivery-sha256',required=True);p.add_argument('--publish-to');a=p.parse_args()
    index=build_index({'path':str(Path(a.delivery).resolve()),'sha256':a.delivery_sha256})
    if a.publish_to:print(json.dumps(publish_index(index,a.publish_to)))
    else:print(json.dumps({'status':'CHECK_ONLY_METADATA_REFERENCE_INDEX','index_bytes':len(encoded(index)),'metadata_bytes_read':index['metadata_bytes_read'],'original_execution_status':index['original_execution_status']}))

if __name__=='__main__':main()
