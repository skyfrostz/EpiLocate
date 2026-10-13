"""Read numerical HSPI records without changing masks, thresholds or model output."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def diagnose_hspi(result, image_shape, valid_mask=None):
    # One canonical independent witness: avoid diverging CPF/geometry logic.
    from .verification_vnext import hspi_witness
    return hspi_witness(result, image_shape, valid_mask)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,required=True);parser.add_argument('--input-sha',required=True);parser.add_argument('--height',type=int,required=True);parser.add_argument('--width',type=int,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError('prior evidence preserved')
    raw=args.input.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=args.input_sha:raise ValueError('source artifact hash mismatch')
    payload=json.loads(raw);result=diagnose_hspi(payload.get('E2',payload),(args.height,args.width))
    result.update(source_artifact_sha256=digest,source_git_sha=payload.get('git_sha'),source_checkpoint_sha256=payload.get('checkpoint_sha256'),source_input_sha256=payload.get('input_sha256'),patient_count=payload.get('patient_count'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'],sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
