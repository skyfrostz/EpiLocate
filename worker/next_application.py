"""Opt-in one-attempt application worker. Legacy Worker config/loop unchanged."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from epilocate_next.contracts import ApplicationRequest
from .agent import WorkerAgent
from .client import WorkerClient, WorkerAPIError, BackendUnavailable

@dataclass(frozen=True)
class ApplicationWorkerConfig:
    worker_id: str
    backend_url: str
    token: str
    model_hash: str
    data_root: Path
    tls_ca_file: Path | None = None
    poll_seconds: float = 5.0
    def __post_init__(self):
        p=urlsplit(self.backend_url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.path not in {'','/'} or p.query or p.fragment:raise ValueError('HTTPS_ORIGIN_REQUIRED')
        if not re.fullmatch(r'node_[A-Za-z0-9_-]{1,123}',self.worker_id) or not re.fullmatch('[a-f0-9]{64}',self.model_hash):raise ValueError('EXPLICIT_WORKER_MODEL_REQUIRED')
        if not self.token or any(c.isspace() for c in self.token):raise ValueError('WORKER_TOKEN_REQUIRED')

class ApplicationWorkerClient(WorkerClient):
    def __init__(self,*args,model_id,**kwargs):
        super().__init__(*args,**kwargs);self.model_id=model_id
    def register(self, worker_id, model_hash, hardware):
        return self._request('/api/v2/workers/register',json=dict(worker_id=worker_id,worker_version='next-1',hardware=hardware,supported_model_versions=[dict(model_id=self.model_id,checkpoint_sha256=model_hash)],max_concurrent_jobs=1)).json()
    def claim(self,worker_id,model_hash,key,capacity):
        response=self._request('/api/v2/workers/jobs/claim',key=key,json=dict(worker_id=worker_id,available_capacity=capacity,supported_model_versions=[dict(model_id=self.model_id,checkpoint_sha256=model_hash)]))
        return None if response.status_code==204 else response.json()
    def accepted_receipt(self,job_id,manifest,assets):
        return self._request(f'/api/v2/workers/jobs/{job_id}/receipt',json=dict(worker_id=manifest['worker_id'],attempt_id=manifest['attempt_id'],submission_digest=submission_digest(manifest,assets))).json()

def submission_digest(manifest,assets):
    body=dict(manifest={k:v for k,v in manifest.items() if k!='lease_token'},assets={k:hashlib.sha256(v).hexdigest() for k,(v,_) in sorted(assets.items())})
    return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()

def manifest_for_application(worker_id,claim,input_hash,output):
    layers={l['asset_id']:l for l in output.result['application']['layers']}
    assets=[dict(asset_id=name,part_name=name,layer_kind=layers[name]['layer_kind'],media_type=media,size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,(data,media) in sorted(output.assets.items())]
    return dict(worker_id=worker_id,job_id=claim['job_id'],attempt_id=claim['attempt_id'],lease_token=claim['lease_token'],outcome='SUCCEEDED',model_id=claim['model_version']['model_id'],checkpoint_sha256=claim['model_version']['checkpoint_sha256'],input_sha256=input_hash,result=output.result,assets=assets)

class ApplicationWorkerAgent(WorkerAgent):
    def process_claim(self,claim,claim_key=None):
        # A failed download is a failed attempt; do not refresh/replay a claim.
        return super().process_claim(claim,None)

    @staticmethod
    def _validate_claim(claim):
        if claim.get('job_parameters',{}).get('kind')!='ALGORITHM':raise WorkerAPIError(502,'ALGORITHM_CLAIM_REQUIRED')
        # Reuse every existing wire/identity check; only the new kind is an extension.
        legacy=dict(claim,job_parameters=dict(claim['job_parameters'],kind='PREDICTION'))
        WorkerAgent._validate_claim(legacy)
        req=ApplicationRequest.model_validate(claim['job_parameters']['application'])
        if req.input.input_sha256!=claim['input_reference']['sha256'] or req.model.checkpoint_sha256!=claim['model_version']['checkpoint_sha256']:raise WorkerAPIError(502,'ALGORITHM_CLAIM_BINDING_MISMATCH')
    def _submit_with_retry(self,claim,manifest,assets):
        # One send, then a read-only transaction lookup. Never resend or re-infer.
        try:response=self.client.submit(claim['job_id'],manifest,assets)
        except (BackendUnavailable,WorkerAPIError):
            response=self.client.accepted_receipt(claim['job_id'],manifest,assets)
        if response.get('accepted') is not True or response.get('job_id')!=claim['job_id'] or response.get('attempt_id')!=claim['attempt_id']:raise BackendUnavailable('ALGORITHM_SUBMISSION_RECONCILE_REQUIRED')
        return response


def run_one_application(config,runner,*,client=None,download_transport=None):
    """Call only inside existing chief admission/supervisor; creates no GPU lock."""
    if client is None and not runner.model_id:raise ValueError('EXPLICIT_APPLICATION_MODEL_ID_REQUIRED')
    client=client or ApplicationWorkerClient(config.backend_url,config.token,model_id=runner.model_id,verify=str(config.tls_ca_file) if config.tls_ca_file else True)
    agent=ApplicationWorkerAgent(config,runner=runner,client=client,download_transport=download_transport)
    try:
        agent.register();agent.start_heartbeats()
        return agent.run_once()
    finally:
        agent.stop()
        if agent._heartbeat_thread is not None and agent._heartbeat_thread.is_alive():
            raise RuntimeError('OWNED_HEARTBEAT_STILL_RUNNING')
