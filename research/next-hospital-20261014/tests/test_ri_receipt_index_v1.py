"""Generated JSON only: reproduce old quota failure and test actual index publish."""
import json,hashlib,copy
from pathlib import Path
import pytest
from epi_next import ri_receipt_index_v1 as fix,a1_prepare as old


def write(path,data):
    raw=fix.encoded(data);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return {'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def generated(tmp_path,large=False):
    root=tmp_path/'out';index=[];consumer=[];stageframes={};cost={};calls={};ledgers=[]
    sizes={'RIa':[1]*6,'RIb':[148,133,168,131,144,167],'RIc':[152]*54}
    counts={'as_buffer_request':1,'as_buffer_api_entered':1,'as_buffer_api_returned':1,'native_parameter_probe_request':1,'native_parameter_probe_entered':1,'native_parameter_probe_returned':1,'as_array_api_entered':0,'as_array_api_returned':0,'decode_request':1,'python_parameter_parses':1,'plugin_entered':'UNKNOWN','plugin_returned':'UNKNOWN'}
    frame={'diagnostic':{'counts':counts,'primary_error':None,'reporting_error':None,'integrity':{'CRC_verified':True,'EOF_verified':True}},'qa':{'scalar_rescale_applications':1},'unit_interpretation':{'unit_branch':'DICOM_CONDITIONAL_HU'}}
    full=0
    for stage,values in sizes.items():
        stageframes[stage]=sum(values);cost[stage]={'compressed_input_bytes':0,'inflated_bytes':0,'cumulative_written_bytes':0}
        for i,n in enumerate(values):
            record=f'{stage}-{i}';d={'record_id':record,'frame_ledgers':[frame]*n,'PIXEL_QA':'PASS','RESCALE_QA':'PASS_DECLARED_HU','budget':{'compressed_input_bytes':n*2,'inflated_bytes':n*3,'output_bytes':n*4},'generated_unneeded_metadata_payload':'x'*(1100*1024 if large else 1)}
            ref=write(root/record/'research-ledger.json',d);ref.update(stage=stage,frames=n,record_id=record);index.append(ref);ledgers.append(d)
            cost[stage]['compressed_input_bytes']+=n*2;cost[stage]['inflated_bytes']+=n*3;cost[stage]['cumulative_written_bytes']+=n*4+ref['bytes']
            for k,v in counts.items():
                if type(v) is int:calls[k]=calls.get(k,0)+n*v
            if stage!='RIa':
                consumer.append({'source_group_id':f'generated-{full}','split':'train_weak' if full<40 else 'val_classification','geometry_ledger':{k:ref[k] for k in ('path','sha256')},'cross_group_duplicate_audit':'PASS','cross_split_duplicate_audit':'PASS'});full+=1
    cref=write(root/'ENC_RESEARCH_SOURCE_CASES_V2.json',consumer)
    delivery={'status':'REPORTING_FAILURE_NO_RETRY','CLI_exit_code':1,'primary_error':{'reason_code':'OUTPUT_LIMIT'},'model_calls':0,'training_calls':0,'retry':False,'consumer':cref,'group_ledger_index':index,'calls':dict(calls,plugin_entered='UNKNOWN',plugin_returned='UNKNOWN'),'observed_group_budget_totals':cost,'request':{'sha256':'GENERATED_ONLY'},'final_receipt_missing':True,'exit_proof':{'GENERATED_EXIT_ONLY':True}}
    ref=write(tmp_path/'claim'/'generated-failure.json',delivery);release=write(tmp_path/'claim'/'release.json',{'status':'DISPATCHED','released_lock_count':2})
    return ref,ledgers,cref,release


def test_old_final_entry_fails_64mib_index_final_entry_publishes(tmp_path):
    ref,ledgers,consumer,release=generated(tmp_path,large=True)
    original={'stages':ledgers};assert len(fix.encoded(original))>64*1024**2
    budget=old.Budget({'wall_seconds':60,'RSS_stop_bytes':2*1024**3,'output_bytes_total':64*1024**2})
    with pytest.raises(old.GuardError,match='OUTPUT_LIMIT'):old.json_output(tmp_path/'out'/'receipt.json',original,budget)
    assert not (tmp_path/'out'/'receipt.json').exists()
    index=fix.build_index(ref);target=tmp_path/'claim'/'reference-index.json';published=fix.publish_index(index,target)
    assert published['bytes']<fix.INDEX_LIMIT and len(index['ledger_index'])==66
    assert sum(index['member_visits'].values())==9105 and index['original_CLI_exit_code']==1
    assert index['status']=='METADATA_RECONCILIATION_ONLY_ORIGINAL_EXECUTION_FAILED'
    assert 'frame_ledgers' not in target.read_text() and 'generated_unneeded_metadata_payload' not in target.read_text()
    assert fix.Reader().read(consumer,1024**2) and fix.Reader().read(release,1024)['status']=='DISPATCHED'
    assert published['sha256']==hashlib.sha256(target.read_bytes()).hexdigest()


def test_incomplete_index_stops_before_publication(tmp_path):
    ref,_,_,_=generated(tmp_path);d=fix.Reader().read(ref,64*1024);d['group_ledger_index'].pop();ref=write(Path(ref['path']),d)
    with pytest.raises(fix.Reject,match='EXACT66'):fix.build_index(ref)


def test_sha_drift_stops_before_publication(tmp_path):
    ref,_,_,_=generated(tmp_path);d=fix.Reader().read(ref,64*1024);Path(d['group_ledger_index'][0]['path']).write_text('{}')
    with pytest.raises(fix.Reject,match='METADATA_SHA_DRIFT'):fix.build_index(ref)


def test_original_names_and_repeated_publication_refused(tmp_path):
    ref,_,consumer,release=generated(tmp_path);index=fix.build_index(ref)
    with pytest.raises(fix.Reject,match='ORIGINAL_ARTIFACT'):fix.publish_index(index,tmp_path/'claim'/'release.json')
    with pytest.raises(fix.Reject,match='ORIGINAL_ARTIFACT'):fix.publish_index(index,tmp_path/'out'/'receipt.json')
    target=tmp_path/'claim'/'index.json';fix.publish_index(index,target);before=target.read_bytes()
    with pytest.raises(FileExistsError):fix.publish_index(index,target)
    assert target.read_bytes()==before
