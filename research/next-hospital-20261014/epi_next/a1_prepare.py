"""Exact A1 application consumer. No torch, network, labels or unlisted members."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import resource
import stat
import struct
import sys
import time
import zlib

from .a0_acquire import bound_json, exclusive, phase, publish, secure_parent
from .weak_records import validate_records

APPLICATION_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
CT = '1.2.840.10008.5.1.4.1.1.2'
SYNTAXES = {'1.2.840.10008.1.2': False, '1.2.840.10008.1.2.1': True}
PIXELS = {(0x7fe0, 0x0010), (0x7fe0, 0x0008), (0x7fe0, 0x0009)}
LONG_VR = {'OB', 'OD', 'OF', 'OL', 'OV', 'OW', 'SQ', 'UC', 'UN', 'UR', 'UT'}
VRS = LONG_VR | {'AE','AS','AT','CS','DA','DS','DT','FD','FL','IS','LO','LT','PN','SH','SL','SS','ST','SV','TM','UI','UL','US','UV'}
NUMERIC = {'US': ('H',2), 'SS': ('h',2), 'UL': ('I',4), 'SL': ('i',4)}
FIELD_VR = {
    'MediaStorageSOPClassUID':'UI','MediaStorageSOPInstanceUID':'UI','TransferSyntaxUID':'UI',
    'SpecificCharacterSet':'CS','ImageType':'CS','SOPClassUID':'UI','SOPInstanceUID':'UI','Modality':'CS',
    'PatientID':'LO','IssuerOfPatientID':'LO','SliceThickness':'DS','SpacingBetweenSlices':'DS',
    'StudyInstanceUID':'UI','SeriesInstanceUID':'UI','InstanceNumber':'IS','ImagePositionPatient':'DS',
    'ImageOrientationPatient':'DS','FrameOfReferenceUID':'UI','TemporalPositionIdentifier':'IS',
    'SamplesPerPixel':'US','PhotometricInterpretation':'CS','NumberOfFrames':'IS','Rows':'US',
    'Columns':'US','PixelSpacing':'DS','BitsAllocated':'US','BitsStored':'US','HighBit':'US',
    'PixelRepresentation':'US','PixelPaddingValue':'US','PixelPaddingRangeLimit':'US',
    'RescaleIntercept':'DS','RescaleSlope':'DS','RescaleType':'LO',
}


class GuardError(ValueError):
    pass


class HeaderError(ValueError):
    pass


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while chunk:=f.read(1024*1024): h.update(chunk)
    return h.hexdigest()


class Budget:
    def __init__(self,caps):
        self.caps=caps;self.compressed=0;self.inflated=0;self.output=0
        self.start=time.monotonic()

    def check(self):
        if time.monotonic()-self.start>self.caps['wall_seconds']:raise GuardError('WALL_LIMIT')
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform!='darwin':rss*=1024
        if rss>self.caps['RSS_stop_bytes']:raise GuardError('RSS_LIMIT')

    def count(self,kind,n):
        self.check();key={'compressed':'compressed_input_bytes','inflated':'inflated_header_prefix_bytes_total' if 'inflated_header_prefix_bytes_total' in self.caps else 'inflated_member_bytes_total','output':'output_bytes_total'}[kind]
        value=getattr(self,kind)+n
        if value>self.caps[key]:raise GuardError(kind.upper()+'_LIMIT')
        setattr(self,kind,value)

    def report(self):
        return {'compressed_input_bytes':self.compressed,'inflated_bytes':self.inflated,'output_bytes':self.output}


class Member:
    """Local ZIP structure + bounded raw inflater; never ZipExtFile read-ahead."""
    def __init__(self,archive,row,budget,prefix_limit,source_binding=None):
        fd=os.open(archive,os.O_RDONLY|os.O_NOFOLLOW)
        self.f=os.fdopen(fd,'rb');self.row=row;self.budget=budget
        self.limit=prefix_limit;self.emitted=0;self.crc=0;self.hash=hashlib.sha256()
        self.pending=b'';self.remaining=row['compressed_bytes'];self.decoder=None
        try:
            opened=os.fstat(self.f.fileno())
            if not stat.S_ISREG(opened.st_mode):raise GuardError('ARCHIVE_NOT_REGULAR')
            if source_binding is not None:
                binding=source_binding['stat_binding']
                if (opened.st_dev,opened.st_ino,opened.st_mtime_ns,opened.st_size)!=(binding['device'],binding['inode'],binding['mtime_ns'],source_binding['bytes']):raise GuardError('ARCHIVE_OPEN_STAT_DRIFT')
            self.f.seek(row['header_offset']);h=self._compressed(30)
            sig,ver,flags,method,tm,dt,crc,cs,us,nl,el=struct.unpack('<4s5H3I2H',h)
            if sig!=b'PK\x03\x04' or flags&1 or method not in (0,8) or nl>4096 or el>65535:raise GuardError('LOCAL_ZIP_HEADER')
            name=self._compressed(nl).decode('utf-8' if flags&0x800 else 'cp437');extra=self._compressed(el)
            if name!=row['name'] or method!=row['compression_method']:raise GuardError('LOCAL_CENTRAL_MISMATCH')
            if not flags&8:
                if cs==0xffffffff or us==0xffffffff:
                    pos=0;data=None
                    while pos+4<=len(extra):
                        tag,n=struct.unpack_from('<HH',extra,pos);pos+=4
                        if pos+n>len(extra):raise GuardError('ZIP64_EXTRA_BOUNDS')
                        if tag==1:data=extra[pos:pos+n]
                        pos+=n
                    if data is None:raise GuardError('ZIP64_EXTRA_MISSING')
                    pos=0
                    if us==0xffffffff:
                        if len(data)<pos+8:raise GuardError('ZIP64_EXTRA_SHORT')
                        us=struct.unpack_from('<Q',data,pos)[0];pos+=8
                    if cs==0xffffffff:
                        if len(data)<pos+8:raise GuardError('ZIP64_EXTRA_SHORT')
                        cs=struct.unpack_from('<Q',data,pos)[0]
                if (crc,cs,us)!=(row['crc32'],row['compressed_bytes'],row['uncompressed_bytes']):raise GuardError('LOCAL_CENTRAL_SIZE_CRC')
            if self.f.tell()+self.remaining>os.fstat(self.f.fileno()).st_size:raise GuardError('ZIP_MEMBER_BOUNDS')
            if method==8:self.decoder=zlib.decompressobj(-15)
        except BaseException:
            self.f.close();raise

    def _compressed(self,n):
        self.budget.count('compressed',n);data=self.f.read(n)
        if len(data)!=n:raise GuardError('ZIP_SHORT_READ')
        return data

    def read(self,n):
        if n<0 or self.emitted+n>self.limit or self.emitted+n>self.row['uncompressed_bytes']:raise GuardError('INFLATED_PREFIX_OR_SIZE_LIMIT')
        global_key='inflated_header_prefix_bytes_total' if 'inflated_header_prefix_bytes_total' in self.budget.caps else 'inflated_member_bytes_total'
        if self.budget.inflated+n>self.budget.caps[global_key]:raise GuardError('INFLATED_LIMIT')
        pieces=[];need=n
        while need:
            if self.decoder is None:
                if need>self.remaining:raise GuardError('STORED_MEMBER_SHORT')
                data=self._compressed(need);self.remaining-=need
            else:
                if not self.pending:
                    take=min(32768,self.remaining)
                    if not take:raise GuardError('DEFLATE_SHORT')
                    self.pending=self._compressed(take);self.remaining-=take
                data=self.decoder.decompress(self.pending,need)
                self.pending=self.decoder.unconsumed_tail
                if self.decoder.unused_data:raise GuardError('DEFLATE_TRAILING_DATA')
                if not data and self.decoder.eof:raise GuardError('DEFLATE_SHORT')
            self.budget.count('inflated',len(data));self.emitted+=len(data)
            self.crc=zlib.crc32(data,self.crc);self.hash.update(data);pieces.append(data);need-=len(data)
        return b''.join(pieces)

    def skip(self,n):
        while n:
            take=min(n,32768);self.read(take);n-=take

    def finish(self):
        self.skip(self.row['uncompressed_bytes']-self.emitted)
        if self.decoder:
            # Drive only the deflate end marker; any extra emitted byte is rejected.
            while not self.decoder.eof:
                if not self.pending:
                    take=min(32768,self.remaining)
                    if not take:raise GuardError('DEFLATE_NO_END')
                    self.pending=self._compressed(take);self.remaining-=take
                extra=self.decoder.decompress(self.pending,1);self.pending=self.decoder.unconsumed_tail
                if extra:raise GuardError('DEFLATE_OVERSIZE')
            if self.pending or self.decoder.unused_data or self.remaining:raise GuardError('DEFLATE_TRAILING_DATA')
        if self.remaining or self.crc!=self.row['crc32']:raise GuardError('MEMBER_CRC_MISMATCH')
        return self.hash.hexdigest()

    def close(self):self.f.close()


def whitelist(request):
    return {tuple(int(v,16) for v in field['tag'].split(',')):field['keyword'] for field in request['requests'][0]['field_value_whitelist']}


def field_value(raw,vr,key,values):
    if key in ('PixelPaddingValue','PixelPaddingRangeLimit'):
        vr='SS' if values.get('PixelRepresentation')==1 else 'US'
    if vr in NUMERIC:
        fmt,size=NUMERIC[vr]
        if len(raw)!=size:raise HeaderError('NUMERIC_VM')
        return struct.unpack('<'+fmt,raw)[0]
    encoding={'':'ascii','ISO_IR 6':'ascii','ISO_IR 100':'latin-1','ISO_IR 192':'utf-8'}.get(values.get('SpecificCharacterSet',''))
    if encoding is None:raise HeaderError('UNSUPPORTED_CHARACTER_SET')
    try:text=raw.decode('ascii' if vr=='UI' else encoding).rstrip(' \x00')
    except UnicodeError:raise HeaderError('HEADER_ENCODING') from None
    if vr=='UI':
        import re
        if not text or len(raw)>64 or re.fullmatch(r'[0-9]+(?:\.[0-9]+)*',text) is None:raise HeaderError('INVALID_UID')
    if key in ('PatientID','IssuerOfPatientID') and len(raw)>128:raise HeaderError('IDENTITY_LENGTH')
    if vr in ('DS','IS'):
        if not text:return None
        try:items=[float(v) if vr=='DS' else int(v) for v in text.split('\\')]
        except ValueError:raise HeaderError('NUMERIC_TEXT') from None
        if not all(math.isfinite(v) for v in items):raise HeaderError('NONFINITE_HEADER')
        return items if len(items)>1 else items[0]
    return text


def parse_header(stream,allowed,caps):
    if stream.read(132)[128:]!=b'DICM':raise HeaderError('DICM_REQUIRED_NO_FORCE')
    values={};explicit=True;meta=True
    for _ in range(caps['element_count_per_member']):
        tag=struct.unpack('<HH',stream.read(4))
        if meta and tag[0]!=2:
            syntax=values.get('TransferSyntaxUID')
            if syntax not in SYNTAXES:raise HeaderError('UNSUPPORTED_TRANSFER_SYNTAX')
            explicit=SYNTAXES[syntax];meta=False
        if explicit:
            try:vr=stream.read(2).decode('ascii')
            except UnicodeError:raise HeaderError('INVALID_VR') from None
            if vr not in VRS:raise HeaderError('INVALID_VR')
            if vr in LONG_VR:
                if stream.read(2)!=b'\x00\x00':raise HeaderError('VR_RESERVED')
                length=struct.unpack('<I',stream.read(4))[0]
            else:length=struct.unpack('<H',stream.read(2))[0]
        else:
            length=struct.unpack('<I',stream.read(4))[0];vr=FIELD_VR.get(allowed.get(tag),'UN')
        if tag in PIXELS:
            return {'values':values,'pixel_tag':list(tag),'pixel_offset':stream.emitted,'pixel_length':length,'header_sha256':stream.hash.hexdigest()}
        if length==0xffffffff:raise HeaderError('UNDEFINED_LENGTH_UNSUPPORTED')
        key=allowed.get(tag)
        if not explicit and not key:
            from pydicom.datadict import dictionary_VR
            try:vr=dictionary_VR((tag[0]<<16)|tag[1])
            except KeyError:raise HeaderError('UNKNOWN_IMPLICIT_STRUCTURE') from None
        # Reject containers rather than inflating an embedded icon's PixelData
        # while skipping a non-whitelisted sequence or ambiguous UN value.
        if vr in ('SQ','UN'):raise HeaderError('SEQUENCE_OR_UNKNOWN_STRUCTURE_UNSUPPORTED')
        if key:
            if key in values:raise HeaderError('DUPLICATE_WHITELIST_TAG')
            if length>caps['whitelist_value_bytes_per_element']:raise GuardError('WHITELIST_VALUE_LIMIT')
            expected=FIELD_VR[key]
            if vr!=expected and not (key.startswith('PixelPadding') and vr in ('US','SS')):raise HeaderError('WHITELIST_VR_MISMATCH')
            values[key]=field_value(stream.read(length),vr,key,values)
        else:stream.skip(length)  # uninterpreted, discarded header bytes only
    raise GuardError('ELEMENT_COUNT_LIMIT')


def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n').encode()


def json_output(path,value,budget,publish_now=True):
    raw=encoded(value);budget.count('output',len(raw));part=Path(str(path)+'.part')
    with os.fdopen(exclusive(part),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    if publish_now:publish(part,path)
    return hashlib.sha256(raw).hexdigest()


def open_bound_archive(request):
    item=request['source_archive'];p=Path(item['path']);before=p.lstat();binding=item['stat_binding']
    if not stat.S_ISREG(before.st_mode) or (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_size)!=(binding['device'],binding['inode'],binding['mtime_ns'],item['bytes']):raise GuardError('ARCHIVE_STAT_DRIFT')
    # These small provenance files were already permitted under A0.
    if sha(item['receipt_path'])!=item['receipt_sha256'] or sha(request['inventory_binding']['path'])!=request['inventory_binding']['sha256']:raise GuardError('PROVENANCE_DRIFT')
    return p


def geometry(headers,caps):
    import numpy as np
    values=[h['values'] for h in headers]
    if len(values)<2 or len(values)>caps['slices_per_directory_max']:raise HeaderError('STACK_COUNT')
    unique=['PatientID','IssuerOfPatientID','StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID','Rows','Columns','SamplesPerPixel','PhotometricInterpretation','BitsAllocated','BitsStored','HighBit','PixelRepresentation']
    for key in unique:
        if len({encoded(v.get(key)) for v in values})!=1:raise HeaderError('STACK_IDENTITY_OR_REPRESENTATION_MIX')
    first=values[0];patient=first.get('PatientID','')
    if not patient or patient.casefold() in {'unknown','anonymous','none','null','n/a','na','test'}:raise HeaderError('MISSING_OR_PLACEHOLDER_PATIENT')
    for key in ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID'):
        if not first.get(key):raise HeaderError('MISSING_IDENTITY_UID')
    if len({v.get('SOPInstanceUID') for v in values})!=len(values) or any(not v.get('SOPInstanceUID') for v in values):raise HeaderError('DUPLICATE_OR_MISSING_SOP')
    if len({v.get('TemporalPositionIdentifier') for v in values})>1:raise HeaderError('TEMPORAL_VOLUME_MIX')
    for v in values:
        if v.get('SOPClassUID')!=CT or v.get('MediaStorageSOPClassUID')!=CT or v.get('SOPInstanceUID')!=v.get('MediaStorageSOPInstanceUID') or v.get('Modality')!='CT':raise HeaderError('CT_IDENTITY')
        if v.get('TransferSyntaxUID') not in SYNTAXES or v.get('NumberOfFrames',1)!=1 or v.get('SamplesPerPixel')!=1 or v.get('PhotometricInterpretation')!='MONOCHROME2':raise HeaderError('UNSUPPORTED_PIXEL_REPRESENTATION')
        if not 0<v.get('Rows',0)<=caps['rows_max'] or not 0<v.get('Columns',0)<=caps['columns_max']:raise HeaderError('MATRIX_SIZE')
        if v.get('BitsAllocated') not in (8,16) or not 0<v.get('BitsStored',0)<=v['BitsAllocated'] or v.get('HighBit')!=v['BitsStored']-1 or v.get('PixelRepresentation') not in (0,1):raise HeaderError('PIXEL_BITS')
        if any(s in v.get('ImageType','').upper().split('\\') for s in ('LOCALIZER','SCOUT')):raise HeaderError('LOCALIZER')
        if 'RescaleSlope' in v and (v['RescaleSlope'] is None or v['RescaleSlope']==0):raise HeaderError('RESCALE_SLOPE')
        if 'RescaleIntercept' in v and v['RescaleIntercept'] is None:raise HeaderError('RESCALE_INTERCEPT')
    orient=np.asarray([v.get('ImageOrientationPatient') for v in values],dtype=float);pos=np.asarray([v.get('ImagePositionPatient') for v in values],dtype=float);spacing=np.asarray([v.get('PixelSpacing') for v in values],dtype=float)
    if orient.shape!=(len(values),6) or pos.shape!=(len(values),3) or spacing.shape!=(len(values),2) or not all(np.isfinite(a).all() for a in (orient,pos,spacing)):raise HeaderError('MISSING_OR_INVALID_GEOMETRY')
    u,w=orient[0,:3],orient[0,3:]
    if abs(np.linalg.norm(u)-1)>1e-4 or abs(np.linalg.norm(w)-1)>1e-4 or abs(u@w)>1e-4 or np.max(np.abs(orient-orient[0]))>1e-4:raise HeaderError('ORIENTATION')
    if (spacing<=0).any() or (spacing>10).any() or np.max(np.abs(spacing-spacing[0]))>1e-6:raise HeaderError('PIXEL_SPACING')
    normal=np.cross(u,w);projection=pos@normal;order=np.argsort(projection,kind='stable');ordered=pos[order];steps=np.diff(projection[order]);median=float(np.median(steps));tolerance=max(.05,.01*median)
    if (steps<=1e-4).any() or np.max(np.abs(steps-median))>tolerance:raise HeaderError('DUPLICATE_OR_NONUNIFORM_SLICE_POSITION')
    displacement=ordered-ordered[0];inplane=displacement-np.outer(displacement@normal,normal)
    if np.max(np.linalg.norm(inplane,axis=1))>.05:raise HeaderError('INPLANE_SHIFT_OR_TILT')
    if any(h['pixel_tag']!=[0x7fe0,0x0010] for h in headers):raise HeaderError('NONINTEGER_PIXEL_DATA')
    affine=np.eye(4);affine[:3,0]=normal*median;affine[:3,1]=w*spacing[0,0];affine[:3,2]=u*spacing[0,1];affine[:3,3]=ordered[0]
    return {'sorted_member_indices':[int(i) for i in order],'shape':[len(values),int(first['Rows']),int(first['Columns'])],'actual_spacing_mm':{'slice_median':median,'slice_min':float(steps.min()),'slice_max':float(steps.max()),'row':float(spacing[0,0]),'column':float(spacing[0,1])},'native_k_row_col_to_LPS':affine.tolist(),'LPS_to_native_k_row_col':np.linalg.inv(affine).tolist(),'source_local_patient_key':hashlib.sha256(encoded([patient,first.get('IssuerOfPatientID')])).hexdigest(),'global_patient_independence':'UNKNOWN','anatomical_completeness':'UNKNOWN'}


def discover(request,out):
    caps=request['requests'][0]['caps'];budget=Budget(caps);archive=open_bound_archive(request);allowed=whitelist(request);results=[]
    for candidate in request['candidates']:
        headers=[];failures=[]
        for row in candidate['members']:
            stream=Member(archive,row,budget,caps['inflated_header_prefix_bytes_per_member'],request['source_archive'])
            try:
                h=parse_header(stream,allowed,caps);h['member']=row;headers.append(h)
            except HeaderError as exc:failures.append({'member':row['name'],'reason':str(exc)})
            finally:stream.close()
        result={'candidate_id':candidate['candidate_id'],'headers':headers,'failures':failures,'status':'QUARANTINED'}
        if not failures:
            try:result['geometry']=geometry(headers,request['requests'][1]['caps']);result['status']='ELIGIBLE_SOURCE_LOCAL_ENGINEERING'
            except (HeaderError,TypeError,ValueError) as exc:result['geometry_rejection']=str(exc)
        results.append(result)
    ledgers={key:{} for key in ('patient','StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID','SOPInstanceUID')};conflicts=[]
    for result in results:
        for header in result['headers']:
            v=header['values'];identities={k:v.get(k) for k in ledgers if k!='patient'}
            if v.get('PatientID'):identities['patient']=encoded([v['PatientID'],v.get('IssuerOfPatientID')]).hex()
            for key,identity in identities.items():
                if not identity:continue
                owner=ledgers[key].setdefault(identity,result['candidate_id'])
                if owner!=result['candidate_id']:conflicts.append({'identity_type':key,'candidate_ids':sorted([owner,result['candidate_id']])})
    conflicts=list({encoded(c):c for c in conflicts}.values())
    count=sum(len(r['headers'])+len(r['failures']) for r in results)
    if count!=sum(c['dicom_member_count'] for c in request['candidates']):raise GuardError('DISCOVERY_ACCOUNTING')
    value={'status':'DISCOVERY_COMPLETE','results':results,'member_accounted_count':count,'identity_conflicts':conflicts,'A1b_batch_blocked':bool(conflicts),'eligible_candidate_ids':[] if conflicts else [r['candidate_id'] for r in results if r['status']=='ELIGIBLE_SOURCE_LOCAL_ENGINEERING'],'budget':budget.report(),'pixel_values_emitted':0,'model_calls':0}
    path=Path(out)/'a1a-discovery.json';h=json_output(path,value,budget)
    return {'path':str(path),'sha256':h,'eligible_candidate_ids':value['eligible_candidate_ids'],'batch_blocked':bool(conflicts),'budget':budget.report()}


def array_part(path,shape,dtype,budget):
    import numpy as np
    secure_parent(path)
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);f=os.fdopen(fd,'w+b')
    try:
        np.lib.format.write_array_header_1_0(f,{'descr':np.dtype(dtype).str,'fortran_order':False,'shape':tuple(shape)})
        offset=f.tell();size=offset+math.prod(shape)*np.dtype(dtype).itemsize;budget.count('output',size);f.flush();os.ftruncate(fd,size)
        return f,np.memmap(f,dtype=dtype,mode='r+',offset=offset,shape=tuple(shape)),size
    except BaseException:f.close();raise


def decode_case(request,result,out,remaining):
    import numpy as np
    from PIL import Image,ImageDraw
    caps=copy.deepcopy(request['requests'][1]['caps']);caps.update(remaining);caps['wall_seconds']=min(caps['wall_seconds'],caps['per_directory_wall_seconds']);budget=Budget(caps)
    archive=open_bound_archive(request);directory=Path(out)/result['candidate_id'];directory.mkdir(mode=0o700)
    headers=result['headers'];g=result['geometry'];shape=g['shape'];v0=headers[0]['values'];bits=v0['BitsAllocated'];dtype=('i' if v0['PixelRepresentation'] else 'u')+str(bits//8);dtype='<'+dtype
    rescale=all(h['values'].get('RescaleSlope') is not None and h['values'].get('RescaleIntercept') is not None for h in headers)
    units='HU' if rescale and all(h['values'].get('RescaleType')=='HU' for h in headers) else 'UNKNOWN'
    required=math.prod(shape)*(bits//8+(4 if rescale else 0))+256
    if required>caps['raw_plus_float32_native_output_bytes_per_directory_max']:raise GuardError('CASE_NATIVE_OUTPUT_LIMIT')
    stored_path=directory/'stored.npy.part';handle,stored,size=array_part(stored_path,shape,dtype,budget);scaled_handle=scaled=None;paths=[stored_path];ledger=[];qa=[]
    try:
        if rescale:
            scaled_path=directory/'rescaled.npy.part';scaled_handle,scaled,_=array_part(scaled_path,shape,'<f4',budget);paths.append(scaled_path)
        for k,index in enumerate(g['sorted_member_indices']):
            budget.check();expected=headers[index];row=expected['member'];stream=Member(archive,row,budget,caps['inflated_member_bytes_per_member'],request['source_archive'])
            try:
                actual=parse_header(stream,whitelist(request),request['requests'][0]['caps'])
                if actual!= {key:expected[key] for key in actual}:raise GuardError('HEADER_REPLAY_MISMATCH')
                count=shape[1]*shape[2];raw_bytes=count*(bits//8)
                if raw_bytes>caps['decoded_pixel_bytes_per_slice_max'] or actual['pixel_length']!=raw_bytes+(raw_bytes%2):raise GuardError('PIXEL_LENGTH')
                raw=stream.read(actual['pixel_length']);pixel=np.frombuffer(raw[:raw_bytes],dtype='<u'+str(bits//8)).astype(np.int32)
                mask=(1<<v0['BitsStored'])-1;pixel&=mask
                if v0['PixelRepresentation']:pixel=np.where(pixel&(1<<(v0['BitsStored']-1)),pixel-(1<<v0['BitsStored']),pixel)
                pixel=pixel.reshape(shape[1:]);stored[k]=pixel
                v=actual['values'];display=pixel.astype(np.float32)
                if rescale:
                    display=display*np.float32(v['RescaleSlope'])+np.float32(v['RescaleIntercept'])
                    if not np.isfinite(display).all():raise GuardError('NONFINITE_RESCALED_PIXELS')
                    scaled[k]=display
                content=stream.finish();ledger.append({'source_member':row['name'],'dicom_sha256':content,'SOPInstanceUID':v['SOPInstanceUID'],'sorted_index':k,'header_sha256':actual['header_sha256']})
            finally:stream.close()
            if k in {0,shape[0]//2,shape[0]-1}:
                low,high=(-1350,150) if units=='HU' else (float(display.min()),float(display.max()))
                img=np.clip((display-low)/max(high-low,1)*255,0,255).astype(np.uint8);png=Image.fromarray(img);draw=ImageDraw.Draw(png);draw.rectangle((0,0,min(png.width,310),14),fill=0);draw.text((1,1),'Units '+units+' | development QA',fill=255)
                import io
                buffer=io.BytesIO();png.save(buffer,format='PNG');raw_png=buffer.getvalue();budget.count('output',len(raw_png));path=directory/f'qa-{k:04d}.png.part'
                with os.fdopen(exclusive(path),'wb') as f:f.write(raw_png);f.flush();os.fsync(f.fileno())
                paths.append(path);qa.append({'path':str(path),'bytes':len(raw_png),'units':units})
        stored.flush();os.fsync(handle.fileno())
        if scaled is not None:scaled.flush();os.fsync(scaled_handle.fileno())
    finally:
        stored._mmap.close();handle.close()
        if scaled is not None:scaled._mmap.close();scaled_handle.close()
    if sum(q['bytes'] for q in qa)>caps['QA_PNG_bytes_total_max']:raise GuardError('QA_PNG_LIMIT')
    manifest={'candidate_id':result['candidate_id'],'geometry':g,'pixel_units':units,'headers':headers,'source_ledger':ledger,'qa':qa,'artifacts':[{'part_path':str(p),'final_path':str(p)[:-5],'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths],'budget':budget.report(),'patient_group_status':'UNKNOWN','use':'dev_localization','model_calls':0}
    path=directory/'case.json';json_output(path,manifest,budget,publish_now=False)
    return {'candidate_id':result['candidate_id'],'manifest':manifest,'manifest_part':str(path)+'.part','budget':budget.report(),'qa_bytes':sum(q['bytes'] for q in qa),'qa_count':len(qa)}


def pipeline(request,out,permit_pixels):
    start=time.monotonic();deadline=start+request['overall_budget']['wall_seconds'];out=Path(out);secure_parent(out);out.mkdir(mode=0o700,exist_ok=False)
    a=request['requests'][0]['caps'];b=request['requests'][1]['caps'];receipt={'status':'FAILED','stages':{},'model_calls':0,'attempts':1}
    try:
        discovery=phase(discover,(request,str(out)),a['wall_seconds'],deadline,out,a['disk_free_floor_bytes']);receipt['stages']['A1a']=discovery
        if not permit_pixels:receipt['status']='A1A_DISCOVERY_COMPLETE_A1B_NOT_APPROVED';return receipt
        if discovery['batch_blocked']:receipt['status']='A1B_BLOCKED_IDENTITY_CONFLICT';return receipt
        free=os.statvfs(out).f_bavail*os.statvfs(out).f_frsize
        if free<b['preflight_free_bytes']:raise GuardError('A1B_PREFLIGHT_DISK')
        data=bound_json(discovery['path'],discovery['sha256']);results=[];used={'compressed_input_bytes':0,'inflated_member_bytes_total':0,'output_bytes_total':128*1024,'QA_PNG_bytes_total_max':0};qa_count=0;b_start=time.monotonic()
        for result in data['results']:
            if result['candidate_id'] not in discovery['eligible_candidate_ids']:continue
            remaining={k:b[k]-n for k,n in used.items()};seconds=min(b['per_directory_wall_seconds'],b['wall_seconds']-(time.monotonic()-b_start))
            if seconds<=0:raise GuardError('A1B_STAGE_TIMEOUT')
            case=phase(decode_case,(request,result,str(out),remaining),seconds,deadline,out,b['disk_free_floor_bytes']);results.append(case)
            used['compressed_input_bytes']+=case['budget']['compressed_input_bytes'];used['inflated_member_bytes_total']+=case['budget']['inflated_bytes'];used['output_bytes_total']+=case['budget']['output_bytes'];used['QA_PNG_bytes_total_max']+=case['qa_bytes'];qa_count+=case['qa_count']
            if qa_count>b['QA_PNG_count_max']:raise GuardError('QA_PNG_COUNT_LIMIT')
        records=[]
        for case in results:
            row=copy.deepcopy(next(r for r in request['weak_record_candidates'] if r['record_id']==case['candidate_id']));image=case['manifest']['artifacts'][0];row.update(patient_group_id='COVID-CT-MD:'+case['manifest']['geometry']['source_local_patient_key'],patient_group_status='UNKNOWN',study_key=case['manifest']['headers'][0]['values']['StudyInstanceUID'],series_key=case['manifest']['headers'][0]['values']['SeriesInstanceUID'],image_ref=image['final_path'],image_sha256=image['sha256'],image_missing_reason=None,access_status='APPROVED_EXACT_SCOPE',geometry_qa='PASS');row['source_diagnosis']['provenance']['verification']='VERIFIED';records.append(row)
        validate_records(records)
        caps=copy.deepcopy(b);caps['output_bytes_total']=96*1024;control=Budget(caps)
        manifest={'status':'COMPLETE_ELIGIBLE_SUBSET' if results else 'NO_ELIGIBLE_DIRECTORIES','cases':results,'weak_records':records,'excluded':[{'candidate_id':r['candidate_id'],'reason':r.get('geometry_rejection') or r['failures']} for r in data['results'] if r['candidate_id'] not in discovery['eligible_candidate_ids']],'global_patient_independence':'UNKNOWN','model_calls':0}
        # Reserve is for small aggregate/receipt metadata; header-rich case data
        # already lives in per-case manifests and is not duplicated here.
        manifest['cases']=[{'candidate_id':c['candidate_id'],'manifest_path':c['manifest_part'][:-5],'budget':c['budget']} for c in results]
        json_output(out/'canonical-manifest.json',manifest,control,publish_now=False)
        for case in results:
            for item in case['manifest']['artifacts']:
                if time.monotonic()>deadline-12:raise GuardError('PUBLICATION_DEADLINE')
                publish(item['part_path'],item['final_path'])
            publish(case['manifest_part'],case['manifest_part'][:-5])
        publish(out/'canonical-manifest.json.part',out/'canonical-manifest.json')
        receipt['stages']['A1b']={'status':manifest['status'],'decoded_directories':len(results),'budget':used,'QA_PNG_count':qa_count,'canonical_manifest_sha256':sha(out/'canonical-manifest.json')};receipt['status']='A1_COMPLETE_ELIGIBLE_SUBSET'
        return receipt
    except Exception as exc:
        receipt['failure']=type(exc).__name__+':'+str(exc)[:160];return receipt
    finally:
        receipt['elapsed_seconds']=time.monotonic()-start


def verify_readiness(binding):
    from . import a0_acquire,weak_records
    expected={str(Path(m.__file__).resolve()) for m in (sys.modules[__name__],a0_acquire,weak_records)}
    if not expected.issubset({str(Path(i['path']).resolve()) for i in binding['source_bindings']}):raise GuardError('INCOMPLETE_LOADED_SOURCE_BINDING')
    for item in binding['source_bindings']:
        if sha(item['path'])!=item['sha256']:raise GuardError('SOURCE_BINDING_DRIFT')
    import numpy,PIL,pydicom
    if binding['numpy_version']!=numpy.__version__ or binding['pillow_version']!=PIL.__version__ or binding['pydicom_version']!=pydicom.__version__:raise GuardError('RUNTIME_VERSION_DRIFT')
    for module in (numpy,PIL,pydicom):
        item=next(i for i in binding['runtime_bindings'] if i['package']==module.__name__)
        if Path(item['path']).resolve()!=Path(module.__file__).resolve() or sha(module.__file__)!=item['sha256']:raise GuardError('LOADED_RUNTIME_BINDING_DRIFT')


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--request-sha256',required=True);p.add_argument('--readiness',required=True);p.add_argument('--readiness-sha256',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--approval');p.add_argument('--approval-sha256');args=p.parse_args()
    if args.request_sha256!=APPLICATION_SHA:raise GuardError('EXACT_APPLICATION_REQUIRED')
    request=bound_json(args.request,args.request_sha256);binding=bound_json(args.readiness,args.readiness_sha256);verify_readiness(binding)
    if binding['request_sha256']!=args.request_sha256:raise GuardError('READINESS_APPLICATION_MISMATCH')
    if not args.execute:print(json.dumps({'status':'CHECK_ONLY_NO_ARCHIVE_MEMBER_ACCESS','request_sha256':args.request_sha256}));return
    if not args.approval or not args.approval_sha256:raise GuardError('EXACT_OWNER_APPROVAL_REQUIRED')
    approval=bound_json(args.approval,args.approval_sha256)
    expected={'request_sha256':args.request_sha256,'readiness_sha256':args.readiness_sha256,'permit_A1a':True,'permit_model':False}
    if any(type(approval.get(k)) is not type(v) or approval.get(k)!=v for k,v in expected.items()):raise GuardError('APPROVAL_SCOPE_MISMATCH')
    if type(approval.get('permit_A1b')) is not bool:raise GuardError('ITEMIZED_A1B_DECISION_REQUIRED')
    receipt=pipeline(request,request['overall_budget']['output_root'],approval['permit_A1b']);receipt.update(request_sha256=args.request_sha256,readiness_sha256=args.readiness_sha256,approval_sha256=args.approval_sha256)
    raw=encoded(receipt)
    if len(raw)>32768:raise GuardError('RECEIPT_OUTPUT_LIMIT')
    with os.fdopen(exclusive(Path(request['overall_budget']['output_root'])/'receipt.json'),'wb') as f:f.write(raw)
    print(json.dumps({'status':receipt['status']}))
    if receipt['status'] in ('FAILED','A1B_BLOCKED_IDENTITY_CONFLICT'):raise SystemExit(1)


if __name__=='__main__':main()
