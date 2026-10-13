"""One bounded metadata-only supplement, original R77 batch failure retained."""
import argparse,hashlib,json,os,resource,signal,sys,time
from pathlib import Path
from . import ri_receipt_index_v1 as ix
from .a0_acquire import exclusive,publish
CAPS={'wall_seconds':60,'RSS_bytes':512*1024**2,'output_bytes':1024**2,'attempts':1}


class Budget:
    def __init__(self):self.start=time.monotonic();self.output=0
    def check(self):
        if time.monotonic()-self.start>CAPS['wall_seconds']:raise ix.Reject('METADATA_WALL_LIMIT')
        if self.peak()>CAPS['RSS_bytes']:raise ix.Reject('METADATA_RSS_LIMIT')
    def peak(self):
        n=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return n if sys.platform=='darwin' else n*1024
    def write(self,path,data):
        self.check();raw=ix.encoded(data)
        if self.output+len(raw)>CAPS['output_bytes']:raise ix.Reject('METADATA_OUTPUT_LIMIT')
        self.output+=len(raw);part=path.with_name(path.name+'.part')
        with os.fdopen(exclusive(part),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        self.check();publish(part,path)
        return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def preview(refs,budget):
    reader=ix.Reader(budget.check);chief=reader.read(refs['chief_check'],64*1024);release=reader.read(refs['release'],64*1024)
    if chief['status']!='SAVED_METADATA_CHECK_PASS_BATCH_PUBLICATION_FAILED' or chief['old_batch_failure_preserved'] is not True or release['status']!='DISPATCHED' or release['released_lock_count']!=2:raise ix.Reject('ORIGINAL_FAILURE_AND_RELEASE_REQUIRED')
    index=ix.build_index(refs['failure'],reader)
    for key in ('path','sha256'):
        if chief['consumer'][key]!=refs['consumer'][key] or index['consumer_binding'][key]!=refs['consumer'][key]:raise ix.Reject('ORIGINAL_CONSUMER_DRIFT')
    actual=[{k:x[k] for k in ('path','sha256','bytes','stage','frames')} for x in index['ledger_index']]
    if actual!=chief['ledger_refs'] or index['ledger_index']!=refs['ledgers']:raise ix.Reject('EXACT66_CHIEF_LEDGER_DRIFT')
    if chief['fixed_projection_sha256']!='0000000000000000000000000000000000000000000000000000000000000000':raise ix.Reject('FIXED60_PROJECTION_DRIFT')
    index.update(release_binding=refs['release'],chief_check_binding=refs['chief_check'],fixed_projection_sha256=chief['fixed_projection_sha256'],source_identity_counts=chief['source_dicom_identity_counts'],clinical_patient_independence='UNKNOWN',pretraining_overlap='UNKNOWN',metadata_supplement_does_not_dispatch_models=True)
    budget.check();return index


def run(plan,plan_sha,acceptance=None):
    if plan['schema']!='R77_METADATA_ONLY_SUPPLEMENT_PLAN_V1' or plan['caps']!=CAPS:raise ix.Reject('EXACT_METADATA_PLAN_REQUIRED')
    runtime=plan['python_runtime']
    if Path(runtime['executable']).resolve()!=Path(sys.executable).resolve() or hashlib.sha256(Path(runtime['executable']).read_bytes()).hexdigest()!=runtime['sha256']:raise ix.Reject('METADATA_RUNTIME_BINDING_DRIFT')
    for ref in plan['source_bindings']:
        if hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['sha256']:raise ix.Reject('METADATA_SOURCE_BINDING_DRIFT')
    budget=Budget();previous=signal.getsignal(signal.SIGALRM)
    def deadline(*_):raise ix.Reject('METADATA_WALL_LIMIT')
    signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,CAPS['wall_seconds'])
    try:
        index=preview(plan['input_refs'],budget);raw=ix.encoded(index)
        if hashlib.sha256(raw).hexdigest()!=plan['preview_binding']['sha256']:raise ix.Reject('PREVIEW_BINDING_DRIFT')
        if acceptance is None:return {'status':'CHECK_ONLY_METADATA_PLAN','index_bytes':len(raw),'elapsed_seconds':time.monotonic()-budget.start,'observed_peak_RSS_bytes':budget.peak(),'metadata_bytes_read':index['metadata_bytes_read'],'original_batch_exit_code':1}
        if acceptance.get('TEMPLATE_NOT_AN_APPROVAL') is True:raise ix.Reject('ACCEPTANCE_TEMPLATE_NOT_APPROVED')
        expected={'schema':'R77_METADATA_ONLY_ACCEPTANCE_V1','plan_sha256':plan_sha,'accept_metadata_supplement':True,'accept_existing_exact60_for_original_CTFM_and_R18_permissions':True,'preserve_original_batch_exit1':True,'permit_source_zip_read':False,'permit_pixel_array_read':False,'permit_decode':False,'permit_model_calls':False,'permit_new_scientific_budget':False,'permit_queue_writes':False}
        if any(type(acceptance.get(k)) is not type(v) or acceptance.get(k)!=v for k,v in expected.items()):raise ix.Reject('EXACT_METADATA_ACCEPTANCE_REQUIRED')
        out=Path(plan['output_root']);out.mkdir(mode=0o700,exist_ok=False)
        ref=budget.write(out/'ledger-reference-index.json',index)
        receipt={'schema':'R77_ENGINEERING_METADATA_SUPPLEMENT_RECEIPT_V1','status':'ENGINEERING_SUPPLEMENT_PUBLISHED_ORIGINAL_BATCH_FAILED','plan_sha256':plan_sha,'index_binding':ref,'original_batch_exit_code':1,'model_dispatch':False,'queue_writes':0,'source_zip_reads':0,'pixel_array_reads':0,'decode_calls':0,'elapsed_seconds_before_receipt':time.monotonic()-budget.start,'observed_peak_RSS_bytes':budget.peak()}
        return budget.write(out/'engineering-supplement-receipt.json',receipt)
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--acceptance');p.add_argument('--acceptance-sha256');a=p.parse_args()
    reader=ix.Reader();plan=reader.read({'path':a.plan,'sha256':a.plan_sha256},128*1024)
    if a.execute and (not a.acceptance or not a.acceptance_sha256):raise ix.Reject('METADATA_ACCEPTANCE_REQUIRED')
    acceptance=reader.read({'path':a.acceptance,'sha256':a.acceptance_sha256},64*1024) if a.execute else None
    print(json.dumps(run(plan,a.plan_sha256,acceptance)))

if __name__=='__main__':main()
