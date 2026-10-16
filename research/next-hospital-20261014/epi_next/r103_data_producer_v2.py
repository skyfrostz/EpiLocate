"""Single bounded DATA producer: cached labels/version audit, conditional headers.
No model/CT pixel API. Default control check only; exact owner/dispatch required.
"""
import argparse,csv,hashlib,io,json,os,signal,struct,sys,time,urllib.request,zlib
import importlib.metadata
from pathlib import Path,PurePosixPath
from . import archive_bound_ab_v2 as ab
from . import medical_slice_registry_v2 as registry

SCHEMA='R103_DATA_REGISTRY_PRODUCER_REQUEST_V2'
RECEIPT_SCHEMA='R103_DATA_REGISTRY_PRODUCER_RECEIPT_V2'
CAPS={'wall_seconds':900,'RSS_stop_bytes':536870912,'compressed_input_bytes':806354944,
      'inflated_header_prefix_bytes_total':403177472,'output_bytes_total':16777216}
VERSION_CAPS=dict(CAPS,wall_seconds=120,compressed_input_bytes=0,inflated_header_prefix_bytes_total=0,output_bytes_total=1048576)

class ReferenceUnavailable(ValueError):pass


def blob_sha(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def cached_raw(ref,limit,expected_blob):
    p=Path(ref['path'])
    if p.is_symlink() or p.stat().st_size>limit:raise ValueError('CACHED_PAYLOAD_LIMIT')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256'] or blob_sha(raw)!=expected_blob:
        raise ValueError('CACHED_VERSION_SHA_DRIFT')
    return raw


def index_audit(raw,label_rows,groups):
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    columns=['Label Index','Diagnosis','Relative Path','Folder/ID']
    if not rows or any(set(columns)-r.keys() for r in rows):raise ValueError('INDEX_COLUMNS_UNRESOLVED')
    values=[int(r['Label Index']) for r in rows]
    if len(values)!=len(set(values)):raise ValueError('DUPLICATE_LABEL_INDEX')
    bases=[b for b in (0,1) if all(0<=v-b<label_rows for v in values)]
    if len(bases)!=1:return {'base':None,'reason':'INDEX_BASE_OR_VERSION_AMBIGUOUS','matched':[]}
    base=bases[0];lookup={g['source_subject_directory']:g for g in groups};matched=[];seen=set()
    for ordinal,r in enumerate(rows):
        folder=r['Folder/ID'].strip();rel=PurePosixPath(r['Relative Path'].strip().replace('\\','/'))
        if rel.is_absolute() or '..' in rel.parts or '/' in folder:raise ValueError('INDEX_SUBJECT_PATH_AMBIGUOUS')
        candidates={str(rel),str(rel/folder)};hits=[x for x in candidates if x in lookup]
        if len(hits)>1:raise ValueError('AMBIGUOUS_SUBJECT_JOIN')
        if not hits:continue
        group=lookup[hits[0]];gid=group['source_group_id']
        if gid in seen:raise ValueError('DUPLICATE_SUBJECT_INDEX_ROW')
        seen.add(gid)
        if r['Diagnosis'].strip()!=group['source_diagnosis']:raise ValueError('INDEX_DIAGNOSIS_CONFLICT')
        matched.append({'source_group_id':gid,'Index_row':ordinal,'original_Label_Index':int(r['Label Index']),
                        'annotation_case_index':int(r['Label Index'])-base,'folder':folder})
    corrected_rows=[int(r['Label Index'])-base for r in rows if r['Folder/ID'].strip() in ('P001','P006') and r['Diagnosis'].strip()=='COVID-19']
    return {'base':base,'base_basis':'INFERENCE_UNIQUE_IN_RANGE_BASE_NOT_EXPLICIT_AUTHOR_STATEMENT',
            'gaps_preserved':True,'rows':len(rows),'matched':matched,'global_author_correction_rows':corrected_rows}


def correction_scope_verified(original,updated,audit):
    if updated.shape!=original.shape:raise ValueError('UPDATED_SHAPE_ALIGNMENT_UNPROVEN')
    diff=updated!=original
    allowed=set(audit.get('global_author_correction_rows',[]))
    return int(diff.sum()),not any(diff[i].any() for i in range(diff.shape[0]) if i not in allowed)


class HeaderMember(ab.SecureMember):
    """Same mature FD/ZIP64/CRC code; bounded prefix stream, never finish DICOM."""
    def __init__(self,lease,row,budget,receipt):
        # This independent initializer generalizes only the allowed member name
        # and prefix bound; old SecureMember/Member sources remain unchanged.
        fd=os.dup(lease);self.f=os.fdopen(fd,'rb');self.row=row;self.budget=budget
        self.lease=lease;self.receipt=receipt;self.limit=131072;self.emitted=0
        self.crc=0;self.hash=hashlib.sha256();self.pending=b'';self.remaining=row['compressed_bytes'];self.decoder=None
        self.local_compressed=0
        try:
            self.verify();self.f.seek(row['header_offset']);h=self._compressed(30)
            sig,ver,flags,method,tm,dt,crc,cs,us,nl,el=struct.unpack('<4s5H3I2H',h)
            if sig!=b'PK\x03\x04' or flags&1 or method not in (0,8) or nl>4096 or el>65535:raise ValueError('LOCAL_ZIP_HEADER')
            name=self._compressed(nl).decode('utf-8' if flags&0x800 else 'cp437');extra=self._compressed(el)
            if name!=row['name'] or method!=row['compression_method']:raise ValueError('LOCAL_CENTRAL_MISMATCH')
            if not flags&8:
                if cs==0xffffffff or us==0xffffffff:
                    pos=0;data=None
                    while pos+4<=len(extra):
                        tag,n=struct.unpack_from('<HH',extra,pos);pos+=4
                        if pos+n>len(extra):raise ValueError('ZIP64_EXTRA_BOUNDS')
                        if tag==1:data=extra[pos:pos+n]
                        pos+=n
                    if data is None:raise ValueError('ZIP64_EXTRA_MISSING')
                    pos=0
                    if us==0xffffffff:
                        if len(data)<8:raise ValueError('ZIP64_EXTRA_SHORT')
                        us=struct.unpack_from('<Q',data,pos)[0];pos+=8
                    if cs==0xffffffff:
                        if len(data)<pos+8:raise ValueError('ZIP64_EXTRA_SHORT')
                        cs=struct.unpack_from('<Q',data,pos)[0]
                if (crc,cs,us)!=(row['crc32'],row['compressed_bytes'],row['uncompressed_bytes']):raise ValueError('LOCAL_CENTRAL_SIZE_CRC')
            if self.f.tell()+self.remaining>receipt['after']['size']:raise ValueError('ZIP_MEMBER_BOUNDS')
            if method==8:self.decoder=zlib.decompressobj(-15)
        except BaseException:self.f.close();raise
    def _compressed(self,n):
        self.local_compressed+=n
        if self.local_compressed>262144:raise ValueError('PER_HEADER_COMPRESSED_CAP')
        return super()._compressed(n)
    def finish(self):raise ValueError('DICOM_FULL_MEMBER_FINISH_FORBIDDEN')


def extract_location(lease,member,budget,identity_receipt):
    stream=HeaderMember(lease,member,budget,identity_receipt)
    try:
        walker=ab.prior.LocationWalker(stream,member,ab.prior.structural.CAPS);result=walker.run()
        if result['stop_code'] in ab.prior.structural.diagnostics.RESOURCE_CODES:raise ab.prior.old.GuardError(result['stop_code'])
        if result['stop_code']!='ROOT_PIXEL_VALUE_BOUNDARY':raise ValueError('HEADER_STRUCTURE_OR_BOUNDARY_FAILURE')
        if walker.location is None:raise ReferenceUnavailable('SLICE_LOCATION_ABSENT_OR_EMPTY')
        return {'slice_location':walker.location,'prefix_sha256':stream.hash.hexdigest(),
                'prefix_bytes':stream.emitted,'full_member_CRC_verified':False,'pixel_value_read':False}
    finally:stream.close()


def validate(request,sha,approval=None):
    if request['phase_scope']!='VERSION_INDEX_AUDIT_ONLY':raise ValueError('HEADER_PHASE_NOT_FROZEN_IN_THIS_VERSION')
    if request['schema']!=SCHEMA or request['caps']!=(VERSION_CAPS if request['phase_scope']=='VERSION_INDEX_AUDIT_ONLY' else CAPS):raise ValueError('EXACT_PRODUCER_REQUEST_REQUIRED')
    closure=hashlib.sha256(json.dumps(request['source_bindings'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if closure!=request['source_closure_sha256']:raise ValueError('PRODUCER_CLOSURE_DRIFT')
    for r in request['source_bindings']:
        if ab.prior.old.sha(r['path'])!=r['sha256']:raise ValueError('PRODUCER_SOURCE_DRIFT')
    if ab.prior.old.sha(sys.executable)!=request['runtime_sha256']:raise ValueError('PRODUCER_RUNTIME_DRIFT')
    for package,version in request.get('package_versions',{}).items():
        if importlib.metadata.version(package)!=version:raise ValueError('PRODUCER_PACKAGE_VERSION_DRIFT')
    if request['phase_scope']=='VERSION_INDEX_AUDIT_ONLY' and request['extent_proofs']:raise ValueError('VERSION_ONLY_CANNOT_ENABLE_HEADERS')
    if approval is not None:
        expected={'schema':'R103_DATA_PRODUCER_APPROVAL_V2','status':'APPROVED_NEW_SCOPE','request_sha256':sha,
                  'permit_cached_original_labels':True,'permit_conditional_updated_1':True,
                  'permit_conditional_development_headers':request['phase_scope']!='VERSION_INDEX_AUDIT_ONLY','permit_pairing_registry':True,
                  'permit_pixels':False,'permit_models':False,'permit_archive_rescan':False,'retry':False}
        if any(type(approval.get(k)) is not type(v) or approval.get(k)!=v for k,v in expected.items()):raise ValueError('EXACT_PRODUCER_APPROVAL_REQUIRED')


def produce(request,sha,approval=None,guard=None):
    validate(request,sha,approval)
    if approval is None:return {'status':'CHECK_ONLY_NO_REAL_LABEL_OR_HEADER_ACCESS'}
    metadata=ab.prior.read_bound(request['metadata']);groups=metadata['groups']
    if len(groups)!=60 or sum(g['split']=='val_classification' for g in groups)!=20:raise ValueError('FIXED60_20_REQUIRED')
    out=Path(request['output_root']);out.mkdir(mode=0o700,exist_ok=False)
    budget=ab.prior.old.Budget(request['caps']);original_check=budget.check;ident=None
    def check():
        original_check()
        if guard:guard.check()
        if lease is not None:
            if ab.identity.state(os.fstat(lease))!=ident['after']:raise ab.identity.IdentityError('PRODUCER_LEASE_DRIFT')
            ab.identity.namespace(request['original_source']['path'],ident['after'],chain)
    budget.check=check;lease=None;start=time.monotonic();previous=signal.getsignal(signal.SIGALRM)
    def stop(*_):raise ValueError('PRODUCER_WALL_LIMIT')
    signal.signal(signal.SIGALRM,stop);signal.setitimer(signal.ITIMER_REAL,request['caps']['wall_seconds'])
    receipt={'schema':RECEIPT_SCHEMA,'status':'FAILED_STOP_NO_RETRY','producer_request_sha256':sha,
             'source_closure_sha256':request['source_closure_sha256'],'consumer':request['consumer'],
             'ENC_fixed8_control':request['ENC_fixed8_control'],'new_model_calls':0,'new_pixel_reads':0,
             'new_archive_hash_bytes':0,'pairing_execution':'NOT_RUN','new_header_members':0,'updated_HTTP_calls':0}
    try:
        # Independent original anchor + same verified stat before any label/HTTP.
        ident,lease,chain=ab.bound_identity(request)
        raw_index=cached_raw(request['cached_Index'],8192,request['pinned_files']['Index.csv']['git_blob'])
        raw_original=cached_raw(request['cached_original_labels'],1048576,request['pinned_files']['Slice-level-labels.npy']['git_blob'])
        original=ab.prior.parse_labels(raw_original);budget.check()
        audit=index_audit(raw_index,original.shape[0],groups);receipt['Index_audit']=audit
        receipt['original_shape']=list(original.shape);receipt['input_payload_bindings']=[request['cached_Index'],request['cached_original_labels']]
        index_path=out/'INDEX_VERSION_AUDIT_V2.json'
        index_sha=ab.prior.old.json_output(index_path,audit,budget)
        index_proof={'path':str(index_path),'sha256':index_sha,'bytes':index_path.stat().st_size}
        selected=[x for x in audit['matched'] if next(g for g in groups if g['source_group_id']==x['source_group_id'])['split']=='val_classification']
        # Updated file is fixed/pinned, fetched once only if a matched registered
        # corrected subject is present; no open-ended discovery or fallback URL.
        corrected=[x for x in audit['matched'] if x['folder'] in ('P001','P006')]
        updated=None
        if corrected and request['updated_policy']=='IF_REGISTERED_MATCHED_CORRECTED_SUBJECT':
            descriptor=request['pinned_files']['Slice-level-labels-updated-1.npy']
            opener=urllib.request.build_opener(ab.prior.NoRedirect);receipt['updated_HTTP_calls']=1
            with opener.open(urllib.request.Request(descriptor['url'],headers={'User-Agent':'EpiLocate-R103-label-version'}),timeout=20) as response:
                raw=response.read(descriptor['bytes']+1)
            if len(raw)!=descriptor['bytes'] or blob_sha(raw)!=descriptor['git_blob']:raise ValueError('PINNED_UPDATED_FILE_IDENTITY')
            updated=ab.prior.parse_labels(raw)
            if updated.shape!=original.shape:raise ValueError('UPDATED_SHAPE_ALIGNMENT_UNPROVEN')
            target=out/'updated-1-labels.npy';budget.count('output',len(raw))
            with target.open('xb') as f:f.write(raw)
            receipt['updated_payload']={'path':str(target),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            receipt['updated_diff_count'],scope_verified=correction_scope_verified(original,updated,audit)
            if not scope_verified:
                receipt['updated_scope']='UNEXPECTED_DIFFERENCES_VERSION_UNKNOWN';updated=None
            else:receipt['updated_scope']='NAMED_CORRECTION_ROWS_ONLY'
        else:receipt['updated_scope']='NOT_NEEDED_OR_INDEX_UNRESOLVED_NO_HTTP'
        proofs=request['extent_proofs'];references=[];unresolved=[];base=ab.prior.read_bound(request['original_anchor_request'])
        lookup={g['source_group_id']:g for g in base['stages']['RI-c']['groups']}
        evidence=request['semantic_evidence']
        for match in selected:
            g=next(g for g in groups if g['source_group_id']==match['source_group_id']);gid=g['source_group_id']
            proof=proofs.get(gid)
            if proof is None:
                unresolved.append({'source_group_id':gid,'reason':'EFFECTIVE_EXTENT_UNPROVEN_HEADER_NOT_READ'});continue
            extent=ab.prior.read_bound(proof)
            if extent.get('source_group_id')!=gid or extent.get('effective_native_count')!=g['depth']:
                unresolved.append({'source_group_id':gid,'reason':'EXTENT_PROOF_CONFLICT'});continue
            if match['folder'] in ('P001','P006') and updated is None:
                unresolved.append({'source_group_id':gid,'reason':'CORRECTED_VERSION_UNRESOLVED'});continue
            matrix=updated if match['folder'] in ('P001','P006') else original
            if matrix.shape[1]<g['depth']:
                unresolved.append({'source_group_id':gid,'reason':'ARRAY_SHORTER_THAN_DECLARED_EXTENT'});continue
            ledger=ab.prior.read_bound(g['geometry_binding']);frames=ledger['frame_ledgers'];order=ledger['sorted_member_indices']
            physical=lookup[gid]['members']
            if len(frames)!=g['depth'] or len(physical)!=g['depth']:raise ValueError('SOURCE_MEMBER_DOMAIN_MISMATCH')
            native=[]
            try:
                for k,ordinal in enumerate(order):
                    budget.check();frame=frames[ordinal];member=physical[frame['member_index']]
                    receipt['new_header_members']+=1
                    if receipt['new_header_members']>3076:raise ValueError('HEADER_MEMBER_BUDGET')
                    location=extract_location(lease,member,budget,ident)
                    normal=ab.prior.group_normal(ledger['affine_LPS'])
                    native.append({'native_index':k,'member_key':frame['full_member_sha256'],
                        'ipp_normal_position':sum(a*b for a,b in zip(frame['IPP'],normal)),**location})
            except ReferenceUnavailable:
                unresolved.append({'source_group_id':gid,'reason':'SLICE_LOCATION_ABSENT_OR_EMPTY'});continue
            enriched=dict(g,native_slices=native);groups[groups.index(g)]=enriched
            mapping_path=out/(g['record_id']+'-member-mapping.json')
            mapping_sha=ab.prior.old.json_output(mapping_path,{'source_group_id':gid,'native_slices':native,'geometry_binding':g['geometry_binding']},budget)
            member_mapping={'path':str(mapping_path),'sha256':mapping_sha}
            labels=[int(x) for x in matrix[match['annotation_case_index'],:g['depth']]]
            ev=dict(evidence,member_mapping=member_mapping,index_base=index_proof,row_extent=proof,index=request['cached_Index'],
                    labels=receipt.get('updated_payload',request['cached_original_labels']) if match['folder'] in ('P001','P006') else request['cached_original_labels'],
                    label_version_resolved=True,order_policy='SLICE_LOCATION_DESCENDING')
            references.append(dict(match,source_diagnosis=g['source_diagnosis'],geometry_sha256=g['geometry_binding']['sha256'],
                label_index_base=audit['base'],version_applicability='VERIFIED_CURRENT' if match['folder'] in ('P001','P006') else 'ORIGINAL_VERSION_EXPLICIT_SCOPE',
                label_file_version='updated-1' if match['folder'] in ('P001','P006') else 'original-pinned',
                evidence=ev,labels_publisher_domain=labels,declared_valid_publisher_indices=list(range(g['depth'])),range_policy='EXPLICIT_PUBLISHER_EXTENT'))
        receipt['unresolved']=unresolved
        refs={'status':'EXECUTED' if references else 'NOT_RUN','rows':references}
        receipt['pairing_execution']=refs['status']
        result=registry.build_registry(metadata,refs);registry.validate_registry(result)
        target=out/'REGISTRY60_V2.json';digest=ab.prior.old.json_output(target,result,budget)
        parent_binding={'path':str(target),'sha256':digest,'bytes':target.stat().st_size}
        receipt['outputs']={'REGISTRY60_V2.json':parent_binding}
        target=out/'DEVELOPMENT20_V2.json'
        view=registry.export_development_view(result,metadata,request['consumer'],request['ENC_fixed8_control'],parent_binding,sha)
        digest=ab.prior.old.json_output(target,view,budget)
        receipt['outputs']['DEVELOPMENT20_V2.json']={'path':str(target),'sha256':digest,'bytes':target.stat().st_size}
        receipt['consumer_refs']={k:{'path':v['path'],'sha256':v['sha256']} for k,v in receipt['outputs'].items()}
        receipt['summaries']={k:result[k] for k in ('all60','development20','original_COVID_FN')}
        receipt['status']='PRODUCER_COMPLETE_WITH_REFERENCE_STATES'
    except BaseException as exc:
        receipt['failure_type']=type(exc).__name__;receipt['failure_reason']=str(exc)[:512]
        raise
    finally:
        receipt['budget_before_final_receipt']=budget.report();receipt['elapsed_seconds']=time.monotonic()-start
        try:budget.check=original_check;ab.prior.old.json_output(out/'PRODUCER_RECEIPT_V2.json',receipt,budget)
        finally:
            if lease is not None:os.close(lease)
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    return {'status':receipt['status'],'receipt_path':str(out/'PRODUCER_RECEIPT_V2.json')}


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');p.add_argument('--dispatch');p.add_argument('--dispatch-sha256');p.add_argument('--child',action='store_true');a=p.parse_args()
    req=ab.prior.read_bound({'path':a.request,'sha256':a.sha256})
    if not a.execute:print(json.dumps(produce(req,a.sha256)));return
    if not all((a.approval,a.approval_sha256,a.dispatch,a.dispatch_sha256)):raise ValueError('NEW_OWNER_DISPATCH_REQUIRED')
    app=ab.prior.read_bound({'path':a.approval,'sha256':a.approval_sha256});dispatch=ab.prior.read_bound({'path':a.dispatch,'sha256':a.dispatch_sha256})
    validate(req,a.sha256,app);ab.prior.validate_dispatch(req,a.sha256,a.approval_sha256,dispatch);shared=ab.prior.load_shared(req['supervisor'])
    if not a.child:
        command=[sys.executable,'-m','epi_next.r103_data_producer_v2','--request',a.request,'--sha256',a.sha256,'--approval',a.approval,'--approval-sha256',a.approval_sha256,'--dispatch',a.dispatch,'--dispatch-sha256',a.dispatch_sha256,'--execute','--child'];recovery=dispatch.get('administrative_recovery') or {}
        result=shared.run_supervised(shared.SupervisionSpec(**req['spec']),command,req['supervisor_output'],req['supervisor']['dependency_root'],req['supervisor']['dependency_sha256'],recovery_decision_path=recovery.get('path'),recovery_decision_sha=recovery.get('sha256'))
        if result['status']!='SUCCESS' or not result['slot_completed']:raise ValueError('PRODUCER_SUPERVISOR_FAILURE')
        print(json.dumps(result));return
    guard=shared.ChildGuard.from_environment()
    try:
        if vars(guard.spec)!=req['spec']:raise ValueError('PRODUCER_CHILD_SPEC')
        result=produce(req,a.sha256,app,guard);guard.complete('SUCCESS',device_recovered=True,actual_forward=0,actual_backward=0);print(json.dumps(result))
    except Exception:
        guard.complete('FAILED',reason='DATA_PRODUCER_FAILURE',device_recovered=False,actual_forward=0,actual_backward=0);raise


if __name__=='__main__':main()
