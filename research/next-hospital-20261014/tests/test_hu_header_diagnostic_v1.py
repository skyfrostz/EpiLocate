"""Generated headers; forbid reaching PixelData or leaking values/identities."""
import json,struct,sys
from pathlib import Path
import pytest
from epi_next import hu_header_diagnostic_v1 as hu
from test_a3_structure_audit import element,part10,pixel,Guarded,sq,item


def generated(fields,leading=b'',caps=None):
    data=leading+b''.join(element((40,tag),vr,raw+b' '*(len(raw)%2)) for tag,vr,raw in fields)+pixel()
    raw=part10(data);stop=raw.index(b'GENERATED_PIXEL_VALUE_FORBIDDEN');stream=Guarded(raw,stop)
    walker=hu.HUWalker(stream)
    if caps:walker.caps=caps
    return walker.diagnose(),stream,stop


@pytest.mark.parametrize('raw,parseable,finite,nonzero',[(b'2',True,True,True),(b'0',True,True,False),(b'not-number',False,None,None),(b'nan',True,False,None),(b'inf',True,False,None),(b'',False,None,None)])
def test_slope_states(raw,parseable,finite,nonzero):
    row,s,stop=generated([(0x1053,'DS',raw)])
    state=row['fields']['RescaleSlope'];assert (state['parseable'],state['finite'],state['nonzero'])==(parseable,finite,nonzero)
    assert row['fields']['RescaleIntercept']['status']=='ABSENT' and s.emitted==stop
    assert 'not-number' not in json.dumps(row)


@pytest.mark.parametrize('raw,empty,match',[(b'HU',False,True),(b'US',False,False),(b'',True,None),(b'hu',False,False)])
def test_type_states(raw,empty,match):
    row,_,_=generated([(0x1054,'LO',raw)])
    s=row['fields']['RescaleType'];assert (s['empty'],s['HU_match'])==(empty,match)


def test_three_distinct_combination_failures_and_nonleakage():
    marker=b'GENERATED_PRIVATE'
    leading=element((8,24),'UI',marker+b' ')+sq(item(element((40,0x1053),'DS',b'0 '),False),False)
    row,s,stop=generated([(0x1052,'DS',b'-1000'),(0x1053,'DS',b'2'),(0x1054,'LO',b'US')],leading)
    assert row['fields']['RescaleSlope']['nonzero'] is True
    assert row['fields']['RescaleIntercept']['finite'] is True
    assert row['fields']['RescaleType']['HU_match'] is False
    assert marker.decode() not in json.dumps(row) and '-1000' not in json.dumps(row)
    assert row['pixel_values_emitted']==0 and s.emitted==stop
    assert row['scientific_qualification']=='UNCHANGED_NOT_EVALUATED'


def test_partial_not_absent_and_cap():
    row,_,_=generated([(0x1053,'DS',b'2')],caps=dict(hu.CAPS,inflated_header_prefix_bytes_per_member=144))
    assert row['status']=='PARTIAL' and row['fields']['RescaleSlope']['status']=='NOT_REACHED'
    row,_,_=generated([(0x1053,'DS',b'1'*66)])
    assert row['status']=='PARTIAL' and row['stop_code']=='HU_FIELD_VALUE_LIMIT'


def test_default_and_no_approval_do_not_dispatch(monkeypatch,capsys):
    binding={'request_sha256':'1'*64,'source_bindings':[{'path':str(Path(hu.__file__).resolve())},{'path':str(Path(hu.a3.__file__).resolve())}]}
    monkeypatch.setattr(hu,'bound_json',lambda p,h:{} if p=='r' else binding)
    monkeypatch.setattr(hu.old,'verify_readiness',lambda b:None);monkeypatch.setattr(hu,'validate',lambda r:None)
    monkeypatch.setattr(hu,'pipeline',lambda r:pytest.fail('archive opened'))
    argv=['generated','--request','r','--request-sha256','1'*64,'--readiness','b','--readiness-sha256','2'*64]
    monkeypatch.setattr(sys,'argv',argv);hu.main();assert 'CHECK_ONLY' in capsys.readouterr().out
    monkeypatch.setattr(sys,'argv',argv+['--execute'])
    with pytest.raises(ValueError,match='NEW_SINGLE_DIAGNOSTIC'):hu.main()


def test_wrong_container_and_truncated_scalar_are_not_absent():
    row,_,_=generated([(0x1053,'SQ',b'')])
    assert row['fields']['RescaleSlope']['status']=='INVALID_CONTAINER'
    assert row['fields']['RescaleSlope']['present'] is True
    raw=part10(element((40,0x1053),'DS',b'1 ',64))
    row=hu.HUWalker(Guarded(raw)).diagnose()
    assert row['status']=='PARTIAL'
    assert row['fields']['RescaleSlope']['status']=='HEADER_SEEN_VALUE_NOT_READ'
    assert row['fields']['RescaleType']['status']=='NOT_REACHED'
