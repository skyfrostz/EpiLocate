"""Generated-only doubles for the same protected runner seam; no Torch."""
from pathlib import Path
import threading
import time

from hospital_mvp_protected import MVPStopped, PLAN, app


class GeneratedGuard:
    def __init__(self):
        self.started=time.monotonic();self.case_started=None;self.cases=set();self.forward=0
        self.lock=threading.Lock()
    def check(self):
        now=time.monotonic()
        if now-self.started>=540:raise MVPStopped('GLOBAL_DEADLINE')
        if self.case_started is not None and now-self.case_started>=180:raise MVPStopped('CASE_DEADLINE')
    def begin_case(self,key):
        self.check()
        if key in self.cases or self.case_started is not None:raise MVPStopped('CASE_NO_RETRY')
        self.cases.add(key);self.case_started=time.monotonic()
    def end_case(self):self.case_started=None
    def before_forward(self):
        with self.lock:
            self.check()
            if self.forward>=96:raise MVPStopped('CALL_BUDGET_EXHAUSTED')
            self.forward+=1


class GeneratedTensor:
    def __init__(self,n):self.shape=(n,3,224,224)


class GeneratedLogits:
    def __init__(self,n):self.n=n
    def detach(self):return self
    def cpu(self):return self
    def tolist(self):return [[.5,-.5] for _ in range(self.n)]


class FakeDelegate:
    hardware={'accelerator':'CPU','evidence':'GENERATED_PROTECTED_RUNNER_ONLY'}
    def __init__(self,run,fence):self.run_root=Path(run);self.fence=fence
    def run(self,claim,input_path,output_dir):
        for n in PLAN:
            inputs=(GeneratedTensor(n),)
            self.fence.before(self,inputs)
            self.fence.after(self,inputs,GeneratedLogits(n))
        return app.FakeRunner(self.run_root).run(claim,input_path,output_dir)
