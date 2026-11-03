"""Files only: controlled atomic writer/reader; no P1 or model invocation."""
import ast
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import pytest
from epi_next.p1_storage_v4 import BoundedStore
from epi_next.hspi_core_v3 import BudgetStopped

BASE='d678a2546830292b81bab08d22ad6549d25940d3'
REL='research/next-hospital-20261014/epi_next/p1_storage_v4.py'


def legacy_size():
    # Execute the actual historical method, not a rewritten approximation.
    root=Path(__file__).resolve().parents[3]
    raw=subprocess.check_output(['git','show',f'{BASE}:{REL}'],cwd=root,text=True)
    cls=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='BoundedStore')
    method=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='size'))
    module=ast.Module(body=[method],type_ignores=[]);ast.fix_missing_locations(module)
    scope={'os':os,'Path':Path};exec(compile(module,'historical_storage_size','exec'),scope)
    return scope['size']


def store_fixture(tmp_path,*,cap=268435456):
    extra=tmp_path/'supervision';extra.mkdir(parents=True)
    store=BoundedStore(tmp_path/'runner',cap=cap,reserve=65536,extra_roots=(extra,))
    (store.root/'owned.bin').write_bytes(b'x'*64)
    target=extra/'telemetry.json';target.write_bytes(b'o'*100)
    temporary=extra/'telemetry.json.123.456.tmp';temporary.write_bytes(b'n'*200)
    return store,target,temporary


def controlled_writer(temporary,target):
    ready=threading.Event();done=threading.Event();errors=[]
    def writer():
        try:
            if not ready.wait(3):raise RuntimeError('fixture reader timeout')
            os.replace(temporary,target)
        except BaseException as exc:errors.append(exc)
        finally:done.set()
    thread=threading.Thread(target=writer);thread.start()
    def trigger():
        ready.set();assert done.wait(3);assert not errors
    return trigger,thread


def test_exact_old_race_and_same_controlled_schedule_new_conservative_charge(tmp_path,monkeypatch):
    old,target,temporary=store_fixture(tmp_path/'old')
    trigger,thread=controlled_writer(temporary,target);original=Path.stat
    def stat_after_rename(path,*a,**k):
        if path==temporary:trigger()
        return original(path,*a,**k)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'stat',stat_after_rename)
        with pytest.raises(FileNotFoundError) as error:legacy_size()(old)
    thread.join(3);assert not thread.is_alive() and error.value.filename==str(temporary)
    new,target,temporary=store_fixture(tmp_path/'new')
    trigger,thread=controlled_writer(temporary,target);open_original=os.open
    def open_after_rename(path,*a,**k):
        if Path(path)==temporary:trigger()
        return open_original(path,*a,**k)
    with monkeypatch.context() as patch:
        patch.setattr(os,'open',open_after_rename)
        charged=new.size()
    thread.join(3);assert not thread.is_alive()
    assert charged==64+100+65536 and charged>=64+target.stat().st_size
    assert new.last_scan['attempts']==1 and new.last_scan['telemetry_race_reserved_bytes']==65536
    print('STORAGE_DIFFERENTIAL='+json.dumps({'legacy':'FileNotFoundError','new_charged_bytes':charged,
        'current_bytes':64+target.stat().st_size,'attempts':1,'file_io_only':True,'model_calls':0}))


def test_open_inode_survives_rename_without_missing_name_exception(tmp_path,monkeypatch):
    store,target,temporary=store_fixture(tmp_path);original=os.open
    def rename_after_open(path,*a,**k):
        fd=original(path,*a,**k)
        if Path(path)==temporary:os.replace(temporary,target)
        return fd
    monkeypatch.setattr(os,'open',rename_after_open)
    assert store.size()==64+100+200
    assert store.last_scan['telemetry_race_reserved_bytes']==0


def test_normal_missing_file_is_not_silently_removed_from_later_listings(tmp_path,monkeypatch):
    store,target,temporary=store_fixture(tmp_path);temporary.unlink()
    victim=store.root/'trace.jsonl';victim.write_bytes(b'cannot skip')
    original=os.open;calls=[]
    def remove_before_open(path,*a,**k):
        if Path(path)==victim:
            calls.append(path)
            if victim.exists():victim.unlink()
        return original(path,*a,**k)
    monkeypatch.setattr(os,'open',remove_before_open)
    with pytest.raises(BudgetStopped,match='OUTPUT_SCAN_UNSTABLE'):store.size()
    assert len(calls)==4 and store.last_scan['attempts']==4


def test_full_rescan_recovered_file_retains_partial_high_water(tmp_path,monkeypatch):
    store,target,temporary=store_fixture(tmp_path,cap=65536+8192);temporary.unlink()
    (store.root/'owned.bin').write_bytes(b'x'*9000)
    victim=store.root/'z-last';victim.write_bytes(b'z')
    original=os.open;calls=0
    def transient_missing(path,*a,**k):
        nonlocal calls
        if Path(path)==victim:
            calls+=1
            if calls==1:
                victim.unlink()
                return original(path,*a,**k)
            if calls==2:
                victim.write_bytes(b'z');(store.root/'owned.bin').write_bytes(b'x')
        return original(path,*a,**k)
    monkeypatch.setattr(os,'open',transient_missing)
    with pytest.raises(BudgetStopped,match='OUTPUT_BYTE_LIMIT'):store.ensure(0)
    assert store.last_scan['attempts']==2 and store.last_scan['charged_bytes']==9000
    assert store.last_scan['scan_bytes']==102


def test_missing_telemetry_reserve_can_exceed_cap(tmp_path,monkeypatch):
    store,target,temporary=store_fixture(tmp_path,cap=65536+10000);original=os.open
    def race(path,*a,**k):
        if Path(path)==temporary:os.replace(temporary,target)
        return original(path,*a,**k)
    monkeypatch.setattr(os,'open',race)
    with pytest.raises(BudgetStopped,match='OUTPUT_BYTE_LIMIT'):store.ensure(0)
    assert store.last_scan['charged_bytes']==64+100+65536


@pytest.mark.parametrize('kind',['wrong-name','missing-target','oversized-target','owned-root'])
def test_telemetry_exception_is_narrow_and_bounded(tmp_path,monkeypatch,kind):
    store,target,temporary=store_fixture(tmp_path)
    if kind=='wrong-name':temporary=temporary.rename(temporary.with_name('telemetry.json.x.456.tmp'))
    if kind=='owned-root':temporary=temporary.rename(store.root/temporary.name)
    original=os.open;first=True
    def unsafe_missing(path,*a,**k):
        nonlocal first
        if Path(path)==temporary and first:
            first=False;temporary.unlink()
            if kind=='missing-target':target.unlink()
            if kind=='oversized-target':target.write_bytes(b'x'*65537)
        return original(path,*a,**k)
    monkeypatch.setattr(os,'open',unsafe_missing)
    with pytest.raises(BudgetStopped,match='OUTPUT_SCAN_UNSTABLE'):store.size()
    assert store.last_scan['attempts']==4


@pytest.mark.parametrize('which',['runner','supervision'])
def test_directory_deleted_during_scan_stops_at_four_attempts(tmp_path,monkeypatch,which):
    store,target,temporary=store_fixture(tmp_path)
    root=store.root if which=='runner' else store.extra_roots[0]
    original=os.scandir;first=True
    def disappearing(path):
        nonlocal first
        if not isinstance(path,int) and Path(path)==root and first:first=False;shutil.rmtree(root)
        return original(path)
    monkeypatch.setattr(os,'scandir',disappearing)
    with pytest.raises(BudgetStopped,match='OUTPUT_SCAN_UNSTABLE'):store.size()
    assert store.last_scan['attempts']==4


def test_continuous_atomic_target_updates_need_no_identical_snapshots(tmp_path,monkeypatch):
    store,target,temporary=store_fixture(tmp_path);temporary.unlink();original=os.open;updates=0
    def updating(path,*a,**k):
        nonlocal updates
        fd=original(path,*a,**k)
        if Path(path)==target:
            updates+=1;temporary.write_bytes(b'u'*(100+updates));os.replace(temporary,target)
        return fd
    monkeypatch.setattr(os,'open',updating)
    for _ in range(20):
        assert store.size()>=164
        assert store.last_scan['attempts']==1
    assert updates==20


def test_static_scan_is_exact_including_existing_large_temporary_and_symlink_refusal(tmp_path):
    store,target,temporary=store_fixture(tmp_path);temporary.write_bytes(b'n'*70000)
    assert store.size()==legacy_size()(store)==64+100+70000
    (store.root/'link').symlink_to(target)
    with pytest.raises(ValueError,match='SYMLINK'):store.size()


def test_own_atomic_replacement_still_charges_old_plus_new_bytes(tmp_path):
    store=BoundedStore(tmp_path,cap=65536+300000,reserve=65536)
    store.write('state.bin',b'x'*200000)
    with pytest.raises(BudgetStopped,match='OUTPUT_BYTE_LIMIT'):
        store.write('state.bin',b'y'*200000,replace=True)
    assert store.path('state.bin').read_bytes()==b'x'*200000
    assert not store.path('state.bin.pending').exists()
