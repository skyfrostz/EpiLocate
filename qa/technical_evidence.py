"""Atomic step evidence with distinct primary and cleanup failures. No payloads."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

class Evidence:
    def __init__(self,path,value):
        self.path=Path(path);self.value=value;self.value.setdefault('steps',[]);self.value.setdefault('cleanup_errors',[])
        self.save()
    def save(self):
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w') as f:
            json.dump(self.value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,self.path)
    def step(self,name,**fields):
        self.value['current_step']=name
        self.value['steps'].append(dict(name=name,time=datetime.now(timezone.utc).isoformat(),**fields));self.save()
    def failure(self,exc,cleanup=False):
        value=dict(type=type(exc).__name__,message=str(exc)[:300],step=self.value.get('current_step'))
        if cleanup:self.value['cleanup_errors'].append(value)
        else:self.value['primary_failure']=value
        self.value['status']='FAILED_OR_PARTIAL';self.save()
