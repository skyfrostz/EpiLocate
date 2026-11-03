"""Bounded durable P1 output. Atomic replacements charge transient bytes too."""
import hashlib
import io
import json
import os
import errno
import re
import stat
from pathlib import Path
import numpy as np
import torch
from .hspi_core_v3 import BudgetStopped


class _ScanChanged(RuntimeError):
    pass


class BoundedStore:
    SCAN_MAX_ATTEMPTS=4
    TELEMETRY_RENAME_RESERVE=65536
    TELEMETRY_TEMP=re.compile(r'telemetry\.json\.[0-9]+\.[0-9]+\.tmp\Z')
    def __init__(self,root,cap=268435456,reserve=2097152,extra_roots=()):
        self.root=Path(root).resolve();self.cap=cap;self.reserve=reserve
        self.extra_roots=tuple(Path(p).resolve() for p in extra_roots)
        if cap<=reserve or reserve<65536:raise ValueError('invalid output reserve')
        self.root.mkdir(parents=True,exist_ok=True)
        self.ensure(0,terminal=True)
    @staticmethod
    def _open_info(path):
        try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno==errno.ELOOP:raise ValueError('OUTPUT_SYMLINK_REFUSED') from exc
            raise
        try:return os.fstat(fd)
        finally:os.close(fd)
    def _missing_telemetry_charge(self,path):
        if path.parent not in self.extra_roots or self.TELEMETRY_TEMP.fullmatch(path.name) is None:
            return None
        target=self._open_info(path.parent/'telemetry.json')
        if not stat.S_ISREG(target.st_mode) or target.st_size>self.TELEMETRY_RENAME_RESERVE:
            raise _ScanChanged('telemetry target exceeds bounded producer assumption')
        # Fixed P1 supervisor emits small telemetry JSON. This reserve is charged,
        # never a skipped file; a producer exceeding it cannot use the exception.
        return self.TELEMETRY_RENAME_RESERVE
    def _scan_once(self,required_paths):
        self._scan_partial_bytes=0;self._scan_race_reserve=0
        # An unrelated missing path may not disappear from the next listing and
        # thereby silently turn an incomplete scan into a smaller valid total.
        for path in required_paths:self._open_info(path)
        def visit(folder):
            before=self._open_info(folder)
            if not stat.S_ISDIR(before.st_mode):raise _ScanChanged('directory replaced')
            with os.scandir(folder) as entries:names=sorted(entry.name for entry in entries)
            for name in names:
                path=folder/name
                try:info=self._open_info(path)
                except FileNotFoundError as missing:
                    try:charge=self._missing_telemetry_charge(path)
                    except (FileNotFoundError,_ScanChanged) as unsafe:
                        # Preserve the original missing name until it can be
                        # measured; an absent/unbounded target grants no waiver.
                        raise missing from unsafe
                    if charge is None:raise
                    self._scan_partial_bytes+=charge;self._scan_race_reserve+=charge
                    continue
                if stat.S_ISDIR(info.st_mode):visit(path)
                else:self._scan_partial_bytes+=info.st_size
            after=folder.lstat()
            if stat.S_ISLNK(after.st_mode):raise ValueError('OUTPUT_SYMLINK_REFUSED')
            if (after.st_dev,after.st_ino)!=(before.st_dev,before.st_ino):
                raise _ScanChanged('directory replaced during scan')
        for root in (self.root,*self.extra_roots):visit(root)
        return self._scan_partial_bytes
    def size(self):
        high_water=0;required_paths=set()
        for attempt in range(1,self.SCAN_MAX_ATTEMPTS+1):
            try:
                total=self._scan_once(required_paths)
            except FileNotFoundError as exc:
                if exc.filename is not None:required_paths.add(Path(exc.filename))
                high_water=max(high_water,self._scan_partial_bytes)
                continue
            except _ScanChanged:
                high_water=max(high_water,self._scan_partial_bytes)
                continue
            high_water=max(high_water,total)
            self.last_scan={'attempts':attempt,'scan_bytes':total,'charged_bytes':high_water,
                'telemetry_race_reserved_bytes':self._scan_race_reserve,
                'policy':'open/fstat inode samples; missing telemetry charged; retain observed high water'}
            return high_water
        self.last_scan={'attempts':self.SCAN_MAX_ATTEMPTS,'charged_bytes':high_water,
                        'policy':'unstable scan; fail closed'}
        raise BudgetStopped('OUTPUT_SCAN_UNSTABLE')
    def ensure(self,new_bytes,terminal=False):
        if self.size()+new_bytes>self.cap-(0 if terminal else self.reserve):
            raise BudgetStopped('OUTPUT_BYTE_LIMIT')
    def path(self,name):
        p=self.root/name
        if p.resolve().parent!=self.root or Path(name).name!=name:raise ValueError('flat owned output filename required')
        return p
    def write(self,name,raw,*,replace=False,terminal=False):
        p=self.path(name);self.ensure(len(raw),terminal)
        if replace:
            tmp=p.with_name(p.name+'.pending')
            with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            os.replace(tmp,p)
        else:
            with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        directory=os.open(self.root,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
        return hashlib.sha256(raw).hexdigest()
    def json(self,name,value,**kw):
        return self.write(name,json.dumps(value,sort_keys=True,allow_nan=False).encode()+b'\n',**kw)
    def checkpoint(self,name,state,**kw):
        # weights_only safe: NumPy RNG array becomes a tensor, never arbitrary pickle globals.
        state=dict(state);cp=dict(state['core']);rng=dict(cp['rng']);a=rng['numpy']
        rng['numpy']={'name':a[0],'keys':torch.from_numpy(a[1].astype(np.int64)),
                      'position':a[2],'has_gauss':a[3],'cached_gauss':a[4]}
        cp['rng']=rng;state['core']=cp
        buf=io.BytesIO();torch.save(state,buf)
        return self.write(name,buf.getvalue(),**kw)
    def load_checkpoint(self,name,digest):
        raw=self.path(name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('CHECKPOINT_BYTES_DRIFT')
        state=torch.load(io.BytesIO(raw),weights_only=True,map_location='cpu')
        a=state['core']['rng']['numpy']
        state['core']['rng']['numpy']=(a['name'],a['keys'].numpy().astype(np.uint32),a['position'],a['has_gauss'],a['cached_gauss'])
        return state


class TraceStream:
    def __init__(self,store,name):
        self.store=store;self.name=name;self.last=None;self.rows=0
        path=store.path(name)
        if path.exists():
            with path.open('rb') as f:
                for line in f:
                    if not line.endswith(b'\n'):raise ValueError('UNKNOWN_PARTIAL_TRACE_APPEND')
                    row=json.loads(line)
                    if self.last is not None and row['epoch']!=self.last['epoch']+1:raise ValueError('TRACE_SEQUENCE_GAP')
                    self.last=row;self.rows+=1
    def append(self,row):
        if self.last is not None and row['epoch']==self.last['epoch']:
            if row!=self.last:raise ValueError('PENDING_REPLAY_TRACE_DIVERGED')
            return # Same observed epoch replay costs forward but adds no second row.
        if self.last is not None and row['epoch']!=self.last['epoch']+1:raise ValueError('TRACE_SEQUENCE_GAP')
        raw=json.dumps(row,sort_keys=True,allow_nan=False).encode()+b'\n'
        self.store.ensure(len(raw))
        with self.store.path(self.name).open('ab') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        self.last=row;self.rows+=1
    def binding(self):
        p=self.store.path(self.name)
        return {'rows':self.rows,'last_epoch':None if self.last is None else self.last['epoch'],
                'bytes':p.stat().st_size if p.exists() else 0,
                'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None}
