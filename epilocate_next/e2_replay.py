"""Zero-model replay of one chief-bound saved E2 result; never invokes LOC core."""
from dataclasses import dataclass
import hashlib
import gzip
import json
from pathlib import Path
import time
from .e2_assets import output_from_saved_e2


@dataclass(frozen=True)
class ReplayBinding:
    result_path: Path
    result_sha256: str
    source_sha256: str
    prepared_sha256: str
    model_adapter_sha256: str
    core_sha256: str
    geometry_ledger_sha256: str
    mapping_qa_sha256: str


class E2PrecomputedAdapter:
    def __init__(self,binding_provider):self.binding_provider=binding_provider
    def __call__(self,req,input_path,output_dir,context):
        start=time.monotonic()
        if req.algorithm_mode!='E2' or req.execution_mode!='PRECOMPUTED':raise ValueError('EXPLICIT_PRECOMPUTED_MODE_REQUIRED')
        if any((req.budget.forward,req.budget.backward,req.budget.updates)):raise ValueError('REPLAY_REQUIRES_ZERO_MODEL_BUDGET')
        binding=self.binding_provider(req)
        path=Path(binding.result_path)
        if path.is_symlink() or path.stat().st_size>req.budget.output_bytes//2:raise ValueError('PRECOMPUTED_SOURCE_UNSAFE')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=binding.result_sha256:raise ValueError('PRECOMPUTED_SOURCE_SHA_MISMATCH')
        if data[:2]==b'\x1f\x8b':
            import io
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                data=stream.read(req.budget.output_bytes*8+1)
            if len(data)>req.budget.output_bytes*8:raise ValueError('PRECOMPUTED_DECOMPRESSION_BUDGET')
        raw=json.loads(data)
        if (req.input.source_identity_status=='SYNTHETIC')!=(raw['evidence_type']=='SYNTHETIC'):raise ValueError('PRECOMPUTED_EVIDENCE_SCOPE_MISMATCH')
        expected=dict(input_sha256=binding.prepared_sha256,model_sha256=req.model.checkpoint_sha256,preprocessing_sha256=req.model.preprocessing_sha256,model_adapter_sha256=binding.model_adapter_sha256)
        if (binding.source_sha256!=req.input.input_sha256 or binding.geometry_ledger_sha256!=req.input.geometry_ledger_sha256
                or binding.mapping_qa_sha256!=req.input.mapping_qa_sha256 or raw['input_binding']!=dict(raw['input_binding'],**expected)
                or raw['config_sha256']!=req.config_sha256 or raw['core_sha256']!=binding.core_sha256):raise ValueError('PRECOMPUTED_BINDING_MISMATCH')
        return output_from_saved_e2(req,raw,output_dir,context,start,replay=True,source_result_sha256=binding.result_sha256)
