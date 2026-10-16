"""Prepare a NOT READY metadata fragment. No CT, weights, Torch or queue access.

DATA and current protected-browser receipts must arrive through the chief before
a final readiness may be published. This tool creates neither an allowlist nor
a chief dispatch. It never upgrades the fragment to READY.
"""

from pathlib import Path as _PublicPath
_PUBLIC_ROOT = _PublicPath(__file__).resolve().parents[1]
import argparse
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

from hospital_mvp_protected import ROOT,TASK,REQUEST_SHA,OWNER_SHA,DECISION_SHA,INDEX_SHA,RUNTIME_PACKAGES,bound,sha,json_new,required_source_paths

AUTHORITY=Path(str(_PUBLIC_ROOT / '.local/private-bindings/manifests/epi-next-phase2-coordinator/next-sprint-20261011'))


def prepare(output,dist):
    refs={
        'request':dict(path=str(AUTHORITY/'CONSOLIDATED_NEXT_ACTIONS_REQUEST_V1.json'),sha256=REQUEST_SHA),
        'owner':dict(path=str(AUTHORITY/'OWNER_APPROVAL_V1.json'),sha256=OWNER_SHA),
        'decision':dict(path=str(AUTHORITY/'ADMINISTRATIVE_RECOVERY_NEW_C1_V1.json'),sha256=DECISION_SHA),
        'supervisor_index':dict(path=str(ROOT/'hospital-release/20261011-recovery-chain-v12/manifest.json'),sha256=INDEX_SHA)}
    request=bound(refs['request'])
    for key in ['owner','decision','supervisor_index']:bound(refs[key])
    approved=request['items']['MVP_LOCAL']['request']
    prepared=bound(approved['data']['fixed_slice_input_reference'])
    fragment=dict(schema='EPI_NEXT_MVP_PROTECTED_READINESS_V1',status='NOT READY',
        blockers=['WAIT_CANONICAL_DATA_DERIVATIVES_VIA_CHIEF','WAIT_CURRENT_PROTECTED_GENERATED_BROWSER_WINDOW',
                  'WAIT_P1_TERMINAL_RECOVERY_AND_CHIEF_MVP_DISPATCH'],
        task_key=TASK,compute=approved['compute'],model=approved['model'],
        source_git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_sha256={p:sha(p) for p in sorted(required_source_paths(dist))},
        python=sys.executable,packages={name:importlib.metadata.version(name) for name in RUNTIME_PACKAGES},
        dist=str(dist),run_directory=str(ROOT/'frontend/.local/mvp-real-three-20261013-v1'),
        supervision_root=str(ROOT/'research/next-hospital-20261014/.local/phase2/mvp-protected-supervision-v1'),
        frozen_root=str(Path(prepared['checkpoint_path']).parents[4]),
        data_delivery=None,generated_protected_acceptance=None,generated_owned_completion=None,
        hospital_display_authorized=False,**refs)
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    json_new(output/'readiness-fragment.json',fragment)
    json_new(output/'metadata-receipt.json',dict(schema='EPI_NEXT_MVP_METADATA_ONLY_V1',status='NOT READY',
        fragment_sha256=sha(output/'readiness-fragment.json'),source_git_sha=fragment['source_git_sha'],
        source_files=len(fragment['source_sha256']),patient_pixels_opened=0,checkpoints_opened=0,
        torch_imported='torch' in sys.modules,device_queue_reads=0,device_queue_writes=0,
        medical_forward=0,medical_backward=0,updates=0))
    print(json.dumps(dict(status='NOT READY',fragment=str(output/'readiness-fragment.json'),
                         sha256=sha(output/'readiness-fragment.json'))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',type=Path,required=True)
    parser.add_argument('--dist',type=Path,default=ROOT/'frontend/.local/mvp-20261011-dist')
    args=parser.parse_args();output=args.output_directory.absolute();dist=args.dist.absolute()
    if (not output.is_relative_to(ROOT/'research/next-hospital-20261014/.local')
            or not dist.is_relative_to(ROOT/'frontend/.local') or not (dist/'index.html').is_file()):
        parser.error('fresh task-local metadata directory and existing local dist required')
    prepare(output,dist)


if __name__=='__main__':main()
