"""Three value-free HU field states; reuse frozen A3 traversal, no pixels."""
import argparse
import json
import math
import os
from pathlib import Path
import time
from . import a3_structure_audit as a3
from .a0_acquire import bound_json,exclusive,phase,secure_parent

old=a3.old
FIELDS={'0028,1052':('RescaleIntercept','DS'),'0028,1053':('RescaleSlope','DS'),'0028,1054':('RescaleType','LO')}
CAPS=dict(a3.CAPS,compressed_input_bytes=512*1024,inflated_header_prefix_bytes_total=128*1024,
          output_bytes_total=32*1024,wall_seconds=30,whitelist_value_bytes_per_element=64)
OVERALL=dict(a3.OVERALL,wall_seconds=60)


def field_state(key,raw,vr):
    expected='LO' if key=='RescaleType' else 'DS'
    s={'status':'PRESENT','present':True,'empty':not bool(raw.strip(b' ')),'expected_VR':vr==expected,
       'parseable':False,'finite':None,'nonzero':None,'HU_match':None,'raw_value_retained':False}
    if s['empty'] or vr!=expected:return s
    try:text=raw.decode('ascii').strip(' ')
    except UnicodeError:return s
    if key=='RescaleType':s.update(parseable=True,HU_match=text=='HU');return s
    try:value=float(text)
    except (ValueError,OverflowError):return s
    s.update(parseable=True,finite=math.isfinite(value))
    if key=='RescaleSlope' and s['finite']:s['nonzero']=value!=0
    return s


class HUWalker(a3.Walker):
    # The inherited boundary/sequence/PixelData stop rules remain unchanged.
    def __init__(self,stream):
        super().__init__(stream,'RI_FIRST_FAILED_MEMBER',CAPS)
        self.hu={key:{'status':'NOT_REACHED','present':None,'empty':None,'parseable':None,'finite':None,'nonzero':None,'HU_match':None,'raw_value_retained':False} for key,_ in FIELDS.values()}
    def header(self,end,path,domain):
        tag,vr,n=super().header(end,path,domain)
        if domain=='dataset' and self.ctx['tag'] in FIELDS:
            key,_=FIELDS[self.ctx['tag']]
            if self.hu[key]['present'] is True:self.fail('DUPLICATE_HU_FIELD')
            self.hu[key].update(status='HEADER_SEEN_VALUE_NOT_READ',present=True)
            if vr in ('SQ','UN') or n==0xffffffff:self.hu[key].update(status='INVALID_CONTAINER',expected_VR=False,parseable=False)
        return tag,vr,n
    def selected(self,key,vr,n,end):
        if key=='TransferSyntaxUID':return super().selected(key,vr,n,end)
        return super().skip(n,end)  # do not convert any source identity/class
    def skip(self,n,end):
        tag=self.ctx['tag']
        if self.ctx['domain']!='dataset' or tag not in FIELDS:return super().skip(n,end)
        key,_=FIELDS[tag]
        if self.hu[key]['status']!='HEADER_SEEN_VALUE_NOT_READ':self.fail('HU_SCALAR_STATE_CONFLICT')
        if n>64:self.fail('HU_FIELD_VALUE_LIMIT','resource_stop')
        self.hu[key].update(status='PRESENT_NOT_READ',present=True)
        self.hu[key]=field_state(key,self.read(n,end),self.ctx['VR'])
    def diagnose(self):
        row=super().run()
        complete=row['root_completed_up_to_pixel_or_member_end']
        if complete:
            for key,s in self.hu.items():
                if s['status']=='NOT_REACHED':self.hu[key].update(status='ABSENT',present=False)
        return {'stage':'HEADER_HU_STATE_DIAGNOSTIC','status':'COMPLETE_HEADER_STATES' if complete else 'PARTIAL',
                'fields':self.hu,'stop_code':row['stop_code'],'stop_class':row['stop_class'],
                'fields_seen':sum(s.get('present') is True for s in self.hu.values()),
                'fields_parseable':sum(s.get('parseable') is True for s in self.hu.values()),
                'element_count':row['element_count'],'consumed_prefix_bytes':row['consumed_prefix_bytes'],
                'prefix_sha256':row['prefix_sha256'],'pixel_values_emitted':0,'pixel_decodes':0,'model_calls':0,
                'scientific_qualification':'UNCHANGED_NOT_EVALUATED','full_member_CRC_SHA':'NOT_RUN_HEADER_ONLY'}


def audit(r):
    budget=a3.diagnostics.v1.Budget(CAPS)
    stream=old.Member(old.open_bound_archive(r),r['member'],budget,128*1024,r['source_archive'])
    try:row=HUWalker(stream).diagnose()
    finally:stream.close()
    return {'row':row,'attempted_members':1,'budget':budget.report(),'attempts':1}


def validate(r):
    if r['schema']!='HU_FIRST_MEMBER_DIAGNOSTIC_REQUEST_V1' or r['caps']!=CAPS or r['overall_caps']!=OVERALL:raise ValueError('EXACT_HU_DIAGNOSTIC_SCOPE_REQUIRED')
    parent=bound_json(r['parent_request']['path'],r['parent_request']['sha256'])
    if r['member']!=parent['stages']['RI-a']['groups'][0]['members'][0] or r['source_archive']!=parent['source_archive'] or r['inventory_binding']!=parent['inventory_binding']:raise ValueError('FIRST_FAILED_MEMBER_ONLY')
    if r['value_fields']!=[list(v) for v in FIELDS.values()] or r['pixel_decode_permitted'] is not False or r['models_permitted'] is not False:raise ValueError('ONLY_VALUE_FREE_HU_STATES')


def pipeline(r):
    start=time.monotonic();out=Path(r['output_root']);secure_parent(out);out.mkdir(mode=0o700,exist_ok=False)
    receipt={'status':'PARTIAL','stage':'HEADER_HU_STATE_DIAGNOSTIC','attempts':1,'pixel_decodes':0,'model_calls':0}
    try:
        result=phase(audit,(r,),30,start+60,out,OVERALL['disk_free_floor_bytes'])
        control=a3.diagnostics.v1.Budget(dict(CAPS,output_bytes_total=24*1024))
        receipt.update(status=result['row']['status'],report_sha256=old.json_output(out/'hu-field-states.json',result,control),
                       header_budget=result['budget'],report_bytes=control.report()['output_bytes'])
    except Exception as exc:
        receipt.update(reason_code='BOUNDED_HU_DIAGNOSTIC_STOP',failure_type=type(exc).__name__,header_budget='UNKNOWN_NO_PHASE_RESULT')
    receipt['elapsed_seconds']=time.monotonic()-start
    old.json_output(out/'receipt.json',receipt,a3.diagnostics.v1.Budget(dict(CAPS,output_bytes_total=8*1024)))
    return receipt


def main():
    p=argparse.ArgumentParser()
    for f in ('request','request-sha256','readiness','readiness-sha256'):p.add_argument('--'+f,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');args=p.parse_args()
    r=bound_json(args.request,args.request_sha256);b=bound_json(args.readiness,args.readiness_sha256);old.verify_readiness(b)
    if b['request_sha256']!=args.request_sha256 or not {str(Path(__file__).resolve()),str(Path(a3.__file__).resolve())}.issubset({i['path'] for i in b['source_bindings']}):raise ValueError('NEW_DIAGNOSTIC_BINDING_REQUIRED')
    validate(r)
    if not args.execute:print(json.dumps({'status':'CHECK_ONLY_NO_ARCHIVE_READ'}));return
    if not args.approval or not args.approval_sha256:raise ValueError('NEW_SINGLE_DIAGNOSTIC_APPROVAL_REQUIRED')
    a=bound_json(args.approval,args.approval_sha256)
    expected={'schema':'HU_FIRST_MEMBER_DIAGNOSTIC_APPROVAL_V1','request_sha256':args.request_sha256,'readiness_sha256':args.readiness_sha256,'permit_header_diagnostic':True,'permit_pixel_decode':False,'permit_model':False,'permit_retry':False}
    if any(type(a.get(k)) is not type(v) or a.get(k)!=v for k,v in expected.items()):raise ValueError('EXACT_NEW_DIAGNOSTIC_APPROVAL_REQUIRED')
    if any(os.environ.get(k)!='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS')):raise ValueError('CPU_ONE_THREAD_REQUIRED')
    result=pipeline(r);print(json.dumps({'status':result['status']}))
    if result['status']!='COMPLETE_HEADER_STATES':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception:
        print(json.dumps({'status':'REJECTED','reason_code':'HU_DIAGNOSTIC_CONTROL_REJECTED','raw_error_retained':False}));raise SystemExit(1) from None
