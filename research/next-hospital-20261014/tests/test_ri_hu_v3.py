"""Six targeted classes, generated assets only; no actual DICOM access."""
import copy,io,json,sys
import numpy as np
import pydicom
import pytest
from epi_next import ri_hu_v3 as v3
from test_a2_six_sop import dicom
from test_a3_structure_audit import Guarded


def conditions():
    values={'SOPClassUID':v3.old.CT,'MediaStorageSOPClassUID':v3.old.CT,'RescaleSlope':2.,'RescaleIntercept':-1000.,'RescaleType':'HU',
            'ImageType':'ORIGINAL\\PRIMARY\\AXIAL'}
    states={k:'PRESENT' for k in values};states.update({k:'ABSENT' for k in v3.MAPS.values()},MultiEnergyCTAcquisition='ABSENT')
    return values,states


def test_explicit_and_conditional_no_source_overrides():
    v,s=conditions();assert v3.interpret(v,s)['unit_branch']=='EXPLICIT_HU'
    s['RescaleType']='ABSENT';v.pop('RescaleType');assert v3.interpret(v,s)['unit_branch']=='DICOM_CONDITIONAL_HU'
    s['MultiEnergyCTAcquisition']='PRESENT';v['MultiEnergyCTAcquisition']='NO';assert v3.interpret(v,s)['unit_branch']=='DICOM_CONDITIONAL_HU'
    v['RescaleType']='US';s['RescaleType']='PRESENT';assert v3.interpret(v,s,True,True)['unit_branch']=='CONFLICT'
    v['ImageType']='DERIVED\\PRIMARY\\AXIAL';assert v3.interpret(v,s,True,True)['unit_branch']=='NON_HU'


def test_unknown_conditions_need_explicit_source_acceptance():
    v,s=conditions();s['RescaleType']='ABSENT';v.pop('RescaleType');v['ImageType']='ORIGINAL\\PRIMARY'
    assert v3.interpret(v,s,True,False)['unit_branch']=='UNKNOWN'
    assert v3.interpret(v,s,True,True)['unit_branch']=='SOURCE_SUPPORTED_RESEARCH_ONLY'
    s['MultiEnergyCTAcquisition']='NOT_READ';assert v3.interpret(v,s,True,True)['unit_branch']=='UNKNOWN'


@pytest.mark.parametrize('key,value',[('RescaleSlope',0),('RescaleSlope',float('nan')),('RescaleIntercept',float('inf')),('RescaleSlope',1e-50),('RescaleIntercept',1e300)])
def test_invalid_parameters_no_branch_passes(key,value):
    v,s=conditions();v[key]=value;assert v3.interpret(v,s,True,True)['unit_branch']=='CONFLICT'


@pytest.mark.parametrize('key,state,value',[
 ('ImageType','PRESENT','ORIGINAL\\PRIMARY\\LOCALIZER'),('ImageType','PRESENT','ORIGINAL\\PRIMARY\\UNKNOWN'),
 ('ImageType','EMPTY',''),('MultiEnergyCTAcquisition','PRESENT','YES'),('MultiEnergyCTAcquisition','PRESENT','UNKNOWN'),
 ('MultiEnergyCTAcquisition','EMPTY',''),('RescaleType','EMPTY',''),('RescaleType','INVALID',None),
 ('ModalityLUTSequence','PRESENT',None),('RealWorldValueMappingSequence','PRESENT',None),('CTAdditionalXRaySourceSequence','PRESENT',None)])
def test_conflicting_or_unsupported_profile_isolated(key,state,value):
    v,s=conditions();v[key]=value;s[key]=state;assert v3.interpret(v,s,True,True)['unit_branch']=='CONFLICT'


def test_real_generated_header_does_not_infer_missing_image_value3():
    raw,_=dicom(1);stream=Guarded(raw);row=v3.TechnicalWalker(stream).scan()
    assert row['complete'] and row['states']['MultiEnergyCTAcquisition']=='ABSENT'
    assert row['values']['ImageType']=='ORIGINAL\\PRIMARY'
    assert 'GENERATED_FORBIDDEN_NAME' not in json.dumps(row) and 'SOPInstanceUID' not in row['values']
    assert row['states']['ModalityLUTSequence']=='ABSENT'
    assert stream.emitted<len(raw) and row['stop_code']=='ROOT_PIXEL_VALUE_BOUNDARY'


def test_signed_unsigned_one_rescale_two_instances_and_double_oracle():
    for signed,slope,intercept in [(False,2.,-1000.),(True,-3.,7.)]:
        raw,expected=dicom(1,signed);ds=pydicom.dcmread(io.BytesIO(raw))
        values={k:getattr(ds,k) for k in ('Rows','Columns','SamplesPerPixel','PhotometricInterpretation','BitsAllocated','BitsStored','HighBit','PixelRepresentation')}
        values.update(RescaleSlope=slope,RescaleIntercept=intercept,PixelPaddingValue=int(expected.flat[0]))
        stored,rescaled,qa=v3.stored_to_rescaled(values,ds.PixelData)
        np.testing.assert_array_equal(stored,expected)
        np.testing.assert_array_equal(rescaled,expected.astype(np.float32)*slope+intercept)
        assert qa['scalar_rescale_applications']==1 and qa['padding_count']==1
        with pytest.raises(v3.v1.Reject,match='RESCALE_NUMERICAL_QA'):
            v3.check_rescale(stored,rescaled*slope+intercept,slope,intercept)
        assert qa['VOI_window_applied'] is False and qa['model_normalization_applied'] is False


def test_generated_full_member_pipeline_once_no_source_identity_output(tmp_path):
    from test_a2_six_sop import fixture
    r=fixture(tmp_path);r.update(member=r['selection'][0]['member'],output_root=str(tmp_path/'generated-out'),bound_source_HU_claim=False)
    (tmp_path/'generated-out').mkdir()
    result=v3.audit(r,False)
    assert result['status']=='SINGLE_FRAME_NUMERICAL_QA_COMPLETE',result
    assert result['pixel_decoder_calls']==1 and result['qa']['scalar_rescale_applications']==1
    assert result['source_member_CRC']=='PASS'
    assert 'GENERATED_FORBIDDEN' not in json.dumps(result)
    assert result['identity_values_interpreted_or_modified'] is False
    assert np.load(result['artifacts'][0]['path']).dtype==np.uint16


def test_mapping_sequence_detected_before_payload():
    from test_a3_structure_audit import element,part10,pixel
    raw=part10(element((8,22),'UI',v3.old.CT.encode())+element((40,0x3000),'SQ',b'')+pixel())
    # Ensure even generated class encoding; avoid conflating an odd VL fixture.
    if len(v3.old.CT)%2:raw=part10(element((8,22),'UI',v3.old.CT.encode()+b'\0')+element((40,0x3000),'SQ',b'')+pixel())
    stream=Guarded(raw);row=v3.TechnicalWalker(stream).scan()
    assert row['states']['ModalityLUTSequence']=='PRESENT'
    assert row['stop_code']=='MAPPING_PATH_REQUIRES_SEPARATE_REVIEW' and not row['complete']
    assert stream.emitted<len(raw)


@pytest.mark.parametrize('first',[b'',b'bad-number'])
def test_empty_invalid_then_duplicate_never_overridden(first):
    from test_a3_structure_audit import element,part10,pixel
    raw=part10(element((40,0x1053),'DS',first)+element((40,0x1053),'DS',b'2 ')+pixel())
    if len(first)%2:raw=part10(element((40,0x1053),'DS',first+b' ')+element((40,0x1053),'DS',b'2 ')+pixel())
    row=v3.TechnicalWalker(Guarded(raw)).scan()
    assert not row['complete'] and row['states']['RescaleSlope'] in ('EMPTY','INVALID')
    assert row['stop_code'] in ('DUPLICATE_TECHNICAL_FIELD','DUPLICATE_OR_REVERSED_TAG_ORDER')


def test_transform_underflow_stops_before_decoder(monkeypatch):
    monkeypatch.setattr(v3.v1.codec,'decode_pixels',lambda *a:pytest.fail('decoder called'))
    with pytest.raises(v3.v1.Reject,match='RESCALE_FLOAT32_PARAMETERS'):
        v3.stored_to_rescaled({'RescaleSlope':1e-50,'RescaleIntercept':0},b'')
    with pytest.raises(v3.v1.Reject,match='RESCALE_FLOAT32_PARAMETERS'):
        v3.stored_to_rescaled({'RescaleSlope':1,'RescaleIntercept':1e-50},b'')


def test_late_failure_retains_header_and_unit_decision(tmp_path,monkeypatch):
    from test_a2_six_sop import fixture
    r=fixture(tmp_path);r.update(member=r['selection'][0]['member'],output_root=str(tmp_path/'out'),bound_source_HU_claim=False)
    (tmp_path/'out').mkdir()
    def corrupt_geometry(self):
        row=original(self);row['values']['ImagePositionPatient']=None;return row
    original=v3.TechnicalWalker.scan;monkeypatch.setattr(v3.TechnicalWalker,'scan',corrupt_geometry)
    result=v3.audit(r,False)
    assert result['status']=='STOPPED_NO_RETRY' and result['failure_stage']=='NATIVE_2D_GEOMETRY'
    assert result['unit_interpretation']['unit_branch']=='EXPLICIT_HU'
    assert result['states']['RescaleSlope']=='PRESENT' and result['pixel_decoder_attempts']==0


def test_one_total_budget_includes_partial_outputs_and_ledger(tmp_path,monkeypatch):
    (tmp_path/'retained.part').write_bytes(b'x'*30)
    monkeypatch.setitem(v3.CAPS,'output_bytes_total',40)
    with pytest.raises(v3.old.GuardError,match='OUTPUT_LIMIT'):v3.publish_ledger(tmp_path,{})
    assert not (tmp_path/'single-frame-ledger-v3.json').exists()
    assert sum(p.stat().st_size for p in tmp_path.iterdir())==30


def test_condition_ledger_retains_only_allowed_nonidentity_terms():
    v,s=conditions();s['RescaleType']='ABSENT';v.pop('RescaleType')
    decision=v3.interpret(v,s)
    assert decision['conditions']['ImageType_V1']=='ORIGINAL'
    assert decision['conditions']['ImageType_V3']=='AXIAL'
    assert decision['conditions']['MultiEnergy_status']=='ABSENT'
    assert decision['conditions']['classic_CT_class_pair'] is True
    assert v3.old.CT not in json.dumps(decision)


def test_cli_default_and_no_new_approval_never_compute(monkeypatch,capsys):
    from pathlib import Path
    r={'schema':'RI_HU_SINGLE_CONDITIONAL_DECODE_REQUEST_V3','caps':v3.CAPS,'evidence_bindings':[],
       'bindings':{'source_bindings':[{'path':str(Path(v3.__file__).resolve())}],'decoder_distributions':{},'decoder_module_bindings':[],'decoder_binary_bindings':[]},
       'parent_request':{'path':'parent','sha256':'2'*64},'member':{},'source_archive':{},'inventory_binding':{}}
    parent={'stages':{'RI-a':{'groups':[{'members':[{}]}]}},'source_archive':{},'inventory_binding':{}}
    monkeypatch.setattr(v3,'bound_json',lambda p,h:r if p=='r' else parent)
    monkeypatch.setattr(v3.old,'verify_readiness',lambda b:None)
    monkeypatch.setattr(v3,'pipeline',lambda *args:pytest.fail('new real operation'))
    args=['generated','--request','r','--request-sha256','1'*64]
    monkeypatch.setattr(sys,'argv',args);v3.main();assert 'CHECK_ONLY' in capsys.readouterr().out
    monkeypatch.setattr(sys,'argv',args+['--execute'])
    with pytest.raises(v3.v1.Reject,match='NEW_V3_APPROVAL'):v3.main()


def test_empty_image_type_real_walker_to_interpret_is_explicit_invalid():
    ds=pydicom.dcmread(io.BytesIO(dicom(1)[0]));ds.ImageType=[]
    output=io.BytesIO();pydicom.dcmwrite(output,ds,enforce_file_format=True)
    row=v3.TechnicalWalker(Guarded(output.getvalue())).scan()
    assert row['states']['ImageType']=='EMPTY' and row['values']['ImageType'] is None
    result=v3.interpret(row['values'],row['states'],True,True)
    assert result['unit_branch']=='CONFLICT' and result['unit_reason']=='INVALID_IMAGE_TYPE'
