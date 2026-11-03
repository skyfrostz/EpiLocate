"""Programmatic structural bytes only. Never real files/pixel value reads."""
import hashlib
import json
import struct
from pathlib import Path
import pytest
from epi_next import a3_structure_audit as a3
from test_a2_diagnostic_v2 import Stream,request as zip_request

UNDEF=0xffffffff

def element(tag,vr,raw=b'',length=None):
    n=len(raw) if length is None else length
    return struct.pack('<HH',*tag)+vr.encode()+(b'\0\0'+struct.pack('<I',n) if vr in a3.old.LONG_VR else struct.pack('<H',n))+raw

def uid(value):
    raw=value.encode();return raw+b'\0'*(len(raw)%2)

def special(tag,n=0):return struct.pack('<HHI',0xfffe,tag,n)

def part10(dataset,missing_meta=False,meta_class=None):
    meta=element((2,2),'UI',uid(a3.old.CT if meta_class is None else meta_class))
    if not missing_meta:meta+=element((2,3),'UI',uid('1.2.3.4'))
    meta+=element((2,16),'UI',uid(a3.diagnostics.v1.JPEG))
    return b'\0'*128+b'DICM'+element((2,0),'UL',struct.pack('<I',len(meta)))+meta+dataset

def roots(sop=b'',sop_class=None):
    values=[((8,22),'UI',uid(a3.old.CT if sop_class is None else sop_class)),((8,24),'UI',sop),((8,96),'CS',b'CT'),((32,13),'UI',uid('1.2.4.5')),((32,14),'UI',uid('1.2.5.6'))]
    values+=[(tag,a3.old.FIELD_VR[key],b'MONOCHROME2 ' if key=='PhotometricInterpretation' else (b'1 ' if key=='NumberOfFrames' else struct.pack('<H',2))) for tag,key in a3.ROOT.items() if tag[0]==40]
    # MONOCHROME2 is 11 bytes incl trailing space? ensure even padding
    return b''.join(element(tag,vr,raw+b' '*(len(raw)%2)) for tag,vr,raw in values)

def sq(content,defined):return element((8,0x1140),'SQ',content+(b'' if defined else special(0xe0dd)),None if defined else UNDEF)

def item(content,defined):return special(0xe000,len(content) if defined else UNDEF)+content+(b'' if defined else special(0xe00d))

def pixel(tag=(0x7fe0,16)):return element(tag,'OW',b'',UNDEF)+b'GENERATED_PIXEL_VALUE_FORBIDDEN\0'

class Guarded(Stream):
    def __init__(self,raw,forbidden=None):
        super().__init__(raw);self.row={'uncompressed_bytes':len(raw)};self.forbidden=forbidden
    def read(self,n):
        if self.forbidden is not None and self.emitted+n>self.forbidden:raise AssertionError('PIXEL_VALUE_READ')
        return super().read(n)

def audit(raw,forbidden=None,caps=None):
    stream=Guarded(raw,forbidden);row=a3.Walker(stream,'GENERATED-ONLY',a3.CAPS if caps is None else caps).run()
    assert '1.2.3.4' not in json.dumps(row) and 'GENERATED_PRIVATE' not in json.dumps(row)
    return row,stream

@pytest.mark.parametrize('defined_sq',[True,False])
@pytest.mark.parametrize('defined_item',[True,False])
def test_all_sq_item_boundary_combinations(defined_sq,defined_item):
    nested=element((8,24),'UI',uid('1.2.999.99'))+element((16,16),'PN',b'GENERATED_PRIVATE ')
    r=roots();pos=r.index(struct.pack('<HH',32,13));raw=part10(r[:pos]+sq(item(nested,defined_item),defined_sq)+r[pos:]+pixel())
    stop=raw.index(b'GENERATED_PIXEL_VALUE_FORBIDDEN')
    row,s=audit(raw,stop)
    assert row['status']=='COMPLETE_SELECTED_ROOT_HEADER'
    assert row['fields']['SOPInstanceUID']['status']=='EMPTY'  # nested never overrides
    assert row['object_type']=='CLASSIC_CT' and row['element_count']>20
    assert row['reason_to_propose_pixel_decode']=='NO_OR_NOT_ESTABLISHED'
    assert s.emitted==stop

@pytest.mark.parametrize('tag',[(0x7fe0,16),(0x7fe0,8),(0x7fe0,9)])
@pytest.mark.parametrize('defined_sq',[True,False])
@pytest.mark.parametrize('defined_item',[True,False])
def test_any_nested_pixel_stops_before_value(tag,defined_sq,defined_item):
    p=pixel(tag);raw=part10(sq(item(p,defined_item),defined_sq)+roots())
    stop=raw.index(b'GENERATED_PIXEL_VALUE_FORBIDDEN')
    row,s=audit(raw,stop)
    assert row['status']=='PARTIAL' and row['stop_code']=='NESTED_PIXEL_VALUE_BOUNDARY'
    assert row['fields']['SOPInstanceUID']['status']=='NOT_REACHED' and s.emitted==stop

@pytest.mark.parametrize('bad,reason',[
 (sq(item(b'',False)[:-8],False),'UNEXPECTED_SPECIAL_ITEM_TAG'),
 (element((8,0x1140),'SQ',special(0xe000,UNDEF)+special(0xe00d,2)+special(0xe0dd),UNDEF),'UNEXPECTED_OR_NONZERO_ITEM_DELIMITER'),
 (element((8,0x1140),'SQ',special(0xe0dd,2),UNDEF),'UNEXPECTED_OR_NONZERO_SEQUENCE_DELIMITER'),
 (element((8,0x1140),'SQ',special(0xe0dd)),'UNEXPECTED_OR_NONZERO_SEQUENCE_DELIMITER'),
 (element((8,0x1140),'SQ',special(0xe000,100)),'DECLARED_LENGTH_EXCEEDS_PARENT'),
 (element((8,0x1140),'SQ',element((8,24),'UI',b'')),'SEQUENCE_EXPECTED_ITEM'),
 (element((8,0x1140),'SQ',special(0xe000,UNDEF)),'MISSING_ITEM_DELIMITER'),
 (element((8,24),'UI',b'1'),'ODD_VALUE_LENGTH'),
])
def test_invalid_delimiters_and_boundaries(bad,reason):
    row,s=audit(part10(bad))
    assert row['status']=='PARTIAL' and row['stop_code']==reason
    assert row['fields']['StudyInstanceUID']['status']=='NOT_REACHED'

def test_truncation_does_not_mark_unvisited_absent():
    raw=part10(element((8,24),'UI',b'1.',64))
    row,_=audit(raw)
    assert row['status']=='PARTIAL' and row['stop_class'] in ('boundary','truncation')
    assert row['fields']['Rows']['status']=='NOT_REACHED'

def test_root_absent_only_at_completed_boundary():
    row,_=audit(part10(pixel()))
    assert row['fields']['SOPInstanceUID']['status']=='ABSENT' and row['root_completed_up_to_pixel_or_member_end']

def test_missing_meta_empty_root_uid_and_public_class_only():
    row,_=audit(part10(roots()+pixel(),missing_meta=True))
    assert row['fields']['MediaStorageSOPInstanceUID']['status']=='ABSENT'
    assert row['fields']['SOPInstanceUID']['status']=='EMPTY'
    assert row['object_type']=='CLASSIC_CT' and row['Classic_CT_selected_violations']

def test_nonct_object_never_gets_classic_ct_type1():
    row,_=audit(part10(roots(sop_class='1.2.3.5')+pixel(),meta_class='1.2.3.5'))
    assert row['object_type']=='OTHER_SAME_CLASS' and not row['Classic_CT_selected_violations']

def test_invalid_uid_and_mismatched_encoding_safe():
    row,_=audit(part10(roots(b'1.02 ')+pixel()))
    assert row['fields']['SOPInstanceUID']['status']=='INVALID'
    raw=part10(roots()).replace(uid(a3.diagnostics.v1.JPEG),b'X'*len(uid(a3.diagnostics.v1.JPEG)))
    row,_=audit(raw)
    assert row['stop_code']=='UNKNOWN_OR_UNSUPPORTED_DATASET_ENCODING'
    assert row['fields']['SOPClassUID']['status']=='NOT_REACHED'

@pytest.mark.parametrize('kind',['depth','count'])
def test_depth_element_caps_partial(kind):
    nested=element((16,16),'PN',b'GENERATED_PRIVATE ')
    for _ in range(4):nested=sq(item(nested,False),True)
    caps=dict(a3.CAPS,depth_max=2) if kind=='depth' else dict(a3.CAPS,element_count_per_member=5)
    row,_=audit(part10(nested),caps=caps)
    assert row['status']=='PARTIAL' and row['stop_code']==('DEPTH_LIMIT' if kind=='depth' else 'ELEMENT_COUNT_LIMIT')
    assert row['stop_class']=='resource_stop'

def test_sequence_trace_count_bounded():
    row,_=audit(part10(sq(item(b'',True)*40,True)+pixel()))
    assert len(row['structural_events'])<=32 and row['structural_events_truncated']

@pytest.mark.parametrize('code',['RSS_LIMIT','WALL_LIMIT','INFLATED_LIMIT'])
def test_safe_resource_stop(code):
    class Stop(Guarded):
        def read(self,n):raise a3.old.GuardError(code)
    row=a3.Walker(Stop(b''),'GENERATED-ONLY').run()
    assert row['stop_code']==code and row['stop_class']=='resource_stop'

def test_pipeline_generated_zip_only(tmp_path,monkeypatch):
    request=zip_request(tmp_path,True);request['output_root']=str(tmp_path/'out')
    monkeypatch.setitem(a3.OVERALL,'disk_free_floor_bytes',0)
    receipt=a3.pipeline(request)
    assert receipt['audited_members']==6 and receipt['pixel_decodes']==0
    d=json.loads((tmp_path/'out'/'six-member-structure.json').read_text())
    assert all(r['fields']['SOPInstanceUID']['status']=='EMPTY' for r in d['rows'])
    assert not list((tmp_path/'out').glob('*.npy')) and not list((tmp_path/'out').glob('*.png'))

@pytest.mark.parametrize('tag',[(0x7fe0,16),(0x7fe0,8),(0x7fe0,9)])
def test_pixels_at_multiple_depths(tag):
    nested=pixel(tag)
    for depth in range(3):nested=sq(item(nested,depth%2==0),depth%2==1)
    raw=part10(nested);row,s=audit(raw,raw.index(b'GENERATED_PIXEL_VALUE_FORBIDDEN'))
    assert row['stop_code']=='NESTED_PIXEL_VALUE_BOUNDARY' and len(row['stop_context']['sequence_path'])==6

@pytest.mark.parametrize('dataset',[
 element((8,24),'UI',b'')+element((8,22),'UI',uid(a3.old.CT)),
 element((8,24),'UI',b'')+element((8,24),'UI',uid('1.2.6'))])
def test_order_and_duplicate_never_mark_complete(dataset):
    row,_=audit(part10(dataset+pixel()))
    assert row['status']=='PARTIAL' and row['stop_code']=='DUPLICATE_OR_REVERSED_TAG_ORDER'

def test_selected_value_boundary_preserves_current_tag():
    raw=part10(element((8,24),'UI',b'1.',64))
    row,_=audit(raw)
    assert row['stop_context']['tag']=='0008,0018'
    # Header already reveals oversized value relative to member boundary.
    assert row['stop_code']=='DECLARED_LENGTH_EXCEEDS_PARENT'
    assert row['fields']['SOPInstanceUID']['status']=='INVALID'

def test_class_mismatch_separate_from_same_other_class():
    row,_=audit(part10(roots(sop_class='1.2.840.10008.5.1.4.1.1.4')+pixel()))
    assert row['object_type']=='CLASS_MISMATCH' and row['meta_dataset_class_match'] is False
    assert row['public_class_symbols']==['CLASSIC_CT','MR_IMAGE']

def test_zero_rows_mr_modality_do_not_propose_decode():
    r=roots(uid('1.2.3.4')).replace(element((8,96),'CS',b'CT'),element((8,96),'CS',b'MR'))
    r=r.replace(element((40,16),'US',struct.pack('<H',2)),element((40,16),'US',struct.pack('<H',0)))
    row,_=audit(part10(r+pixel()))
    assert row['technical_values']['Rows']==0 and row['technical_values']['Modality']=='MR'
    assert 'CLASSIC_CT_MODALITY_MISMATCH' in row['limited_technical_findings']
    assert 'MATRIX_PROFILE_REJECTED' in row['limited_technical_findings']
    assert row['reason_to_propose_pixel_decode']=='NO_OR_NOT_ESTABLISHED'

def test_valid_limited_header_only_suggests_new_request():
    from test_a2_diagnostic_v2 import raw_dataset
    raw=raw_dataset();stop=raw.find(b'\xfe\xff\0\xe0')
    row,s=audit(raw,stop)
    assert row['reason_to_propose_pixel_decode']=='NO_REQUIRED_SELECTED_FIELD_VIOLATIONS'
    assert row['pixel_decode_authorized'] is False
    assert row['meta_dataset_instance_match'] is True

def test_timeout_retains_partial_without_claiming_zero_io(tmp_path,monkeypatch):
    r=zip_request(tmp_path);r['output_root']=str(tmp_path/'out')
    def timeout(*a,**kw):raise TimeoutError('PHASE_OR_OVERALL_TIMEOUT')
    monkeypatch.setattr(a3,'phase',timeout)
    receipt=a3.pipeline(r)
    assert receipt['status']=='PARTIAL' and receipt['audit_budget']=='UNKNOWN_NO_PHASE_RESULT'
    report=json.loads((tmp_path/'out'/'six-member-structure.json').read_text())
    assert all(x['fields']['Rows']['status']=='NOT_REACHED' for x in report['rows'])
    assert all(x['consumed_prefix_bytes'] is None for x in report['rows'])

def test_compressed_budget_before_member_retains_partial(tmp_path,monkeypatch):
    r=zip_request(tmp_path);r['output_root']=str(tmp_path/'out')
    monkeypatch.setitem(a3.OVERALL,'disk_free_floor_bytes',0);monkeypatch.setitem(a3.CAPS,'compressed_input_bytes',0)
    receipt=a3.pipeline(r)
    assert receipt['status']=='PARTIAL' and receipt['global_stop']
    report=json.loads((tmp_path/'out'/'six-member-structure.json').read_text())
    assert len(report['rows'])==6 and report['rows'][0]['stop_code']=='COMPRESSED_LIMIT'
    assert all(row['stop_code']=='STOP_BEFORE_MEMBER' and row['fields']['Rows']['status']=='NOT_REACHED' for row in report['rows'][1:])
    assert receipt['attempted_members']==1 and receipt['audited_members']==0


def test_nested_duplicate_and_missing_sequence_delimiter():
    duplicated=element((8,24),'UI',b'')*2
    row,_=audit(part10(sq(item(duplicated,True),True)))
    assert row['status']=='PARTIAL' and row['stop_code']=='DUPLICATE_OR_REVERSED_TAG_ORDER'
    bad=element((8,0x1140),'SQ',special(0xe000,0),UNDEF)
    row,_=audit(part10(bad))
    assert row['status']=='PARTIAL' and row['stop_class']=='boundary'

def test_report_and_receipt_share_fixed_output_cap(tmp_path,monkeypatch):
    r=zip_request(tmp_path);r['output_root']=str(tmp_path/'out')
    def oversized(*args):return {'rows':[],'global_stop':False,'budget':{},'padding':'X'*(490*1024),'header_scan_started_members':0,'attempted_members':0}
    monkeypatch.setattr(a3,'phase',oversized)
    receipt=a3.pipeline(r)
    assert receipt['status']=='PARTIAL' and receipt['reason_code']=='OUTPUT_LIMIT'
    assert sum(p.stat().st_size for p in (tmp_path/'out').iterdir() if p.is_file())<=512*1024
