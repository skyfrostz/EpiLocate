"""New local MVP version from hash-bound owner pixel review; keep v1 intact."""
import argparse
import copy
import json
import os
from pathlib import Path

import numpy as np
import pydicom

from .a0_acquire import exclusive, secure_parent
from .a1_prepare import encoded, sha
from .mvp_three_sop import GEOMETRY, REPRESENTATION, SENSITIVE, pixels_sha, same_fields

REVIEW_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
DECISION_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
LEDGER_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
PREVIEW_SHA = '0000000000000000000000000000000000000000000000000000000000000000'


def create(root, evidence, out):
    review_path = evidence / 'OWNER_PIXEL_VISUAL_REVIEW_V1.json'
    decision_path = evidence / 'OWNER_DECISION_V1.json'
    ledger_path = root / '.local/phase2/mvp-three-sop-derivatives-v1-20261011/MVP_THREE_SOP_DERIVATIVE_LEDGER_V1.json'
    preview_path = root / '.local/phase2/mvp-three-sop-owner-pixel-review-v1-20261011/PREVIEW_BINDING_V1.json'
    for p, digest in ((review_path, REVIEW_SHA), (decision_path, DECISION_SHA),
                      (ledger_path, LEDGER_SHA), (preview_path, PREVIEW_SHA)):
        if sha(p) != digest:
            raise ValueError('OWNER_OR_DERIVATIVE_BINDING_DRIFT')
    review, decision, ledger, preview = [json.loads(p.read_text()) for p in
                                       (review_path, decision_path, ledger_path, preview_path)]
    assert decision['pixel_review_sha256'] == REVIEW_SHA
    assert review['derivative_ledger_sha256'] == LEDGER_SHA and review['preview_binding_sha256'] == PREVIEW_SHA
    assert review['reviewer'].strip() and review['reviewed_at'] and review['owner_visual_review_affirmed'] is True
    for data in (review, ledger, preview):
        assert [r['case_index'] for r in data['records']] == [1, 2, 3]
    for human, old, images in zip(review['records'], ledger['records'], preview['records']):
        assert human['all_preview_panels_reviewed'] is True and human['full_frame_including_edges_reviewed'] is True
        assert human['burned_in_identity_information_detected'] == 'NO'
        assert human['source_ct_sha256'] == old['source_ct_sha256'] == images['source_ct_sha256']
        assert human['derivative_sha256'] == old['sha256'] == images['derivative_sha256']
        assert human['decoded_pixel_sha256'] == old['derivative_decoded_pixel_sha256'] == images['decoded_pixel_sha256']
        assert human['preview_png_sha256'] == [p['sha256'] for p in images['previews']]
        assert len(images['previews']) == 3
        for p in images['previews']:
            assert sha(p['path']) == p['sha256'] and p['crop'] is False and p['resize'] is False
        assert sha(old['path']) == old['sha256']
    secure_parent(out)
    out.mkdir(mode=0o700, exist_ok=False)
    records = []
    for old in ledger['records']:
        src = pydicom.dcmread(old['path'])
        before = src.pixel_array
        assert pixels_sha(before) == old['derivative_decoded_pixel_sha256']
        dst = copy.deepcopy(src)
        dst.BurnedInAnnotation = 'NO'  # exact full-frame owner evidence above
        dst.PatientIdentityRemoved = 'YES'
        dst.DeidentificationMethod = 'Header allowlist; owner full-frame pixel visual review'
        path = out / f'case-{old["case_index"]}.dcm'
        with os.fdopen(exclusive(path), 'wb') as f:
            pydicom.dcmwrite(f, dst, enforce_file_format=True)
            f.flush()
            os.fsync(f.fileno())
        check = pydicom.dcmread(path)
        after = check.pixel_array
        assert np.array_equal(before, after) and src.PixelData == check.PixelData
        assert same_fields(src, check, GEOMETRY + REPRESENTATION)
        assert src.file_meta.TransferSyntaxUID == check.file_meta.TransferSyntaxUID
        assert str(check.BurnedInAnnotation) == 'NO' and str(check.PatientIdentityRemoved) == 'YES'
        assert not any(e.tag.is_private or (e.keyword in SENSITIVE and str(e.value).strip()) for e in check.iterall())
        assert path.stat().st_size <= 20 * 1024**2
        row = copy.deepcopy(old)
        row.update(path=str(path.resolve()), sha256=sha(path), bytes=path.stat().st_size,
                   previous_derivative_sha256=old['sha256'], derivative_decoded_pixel_sha256=pixels_sha(after),
                   deidentification_status='HEADER_PASS_OWNER_PIXEL_VISUAL_REVIEW_NO',
                   BurnedInAnnotation='NO', burned_in_phi_status='OWNER_VISUAL_REVIEW_NO_IDENTITY_FOUND',
                   pixel_phi_visual_review='OWNER_REVIEW_HASH_BOUND_AND_DATA_AUDITED',
                   upload_eligible=True, upload_scope='LOCAL_MVP_ONLY_NOT_EXTERNAL_UPLOAD_AUTHORIZATION',
                   upload_block_reason=None, owner_review_sha256=REVIEW_SHA,
                   owner_reviewed_at=review['reviewed_at'])
        row['operations'] = old['operations'] + ['set BurnedInAnnotation=NO using exact owner visual review evidence',
                                                'update DeidentificationMethod; no pixel edits or reencoding']
        records.append(row)
        assert sha(old['path']) == old['sha256']
    result = copy.deepcopy(ledger)
    result.update(schema='EPI_NEXT_MVP_DERIVATIVE_DELIVERY_V2',
                  status='LOCAL_MVP_CONTRACT_READY_WITH_OWNER_VISUAL_EVIDENCE',
                  previous_ledger_sha256=LEDGER_SHA, owner_pixel_review_path=str(review_path),
                  owner_pixel_review_sha256=REVIEW_SHA, owner_decision_sha256=DECISION_SHA,
                  preview_binding_sha256=PREVIEW_SHA, external_imaging_upload_authorized=False,
                  hospital_display_authorized=False, DATA_final_evidence_audit='PASS', records=records)
    p = out / 'MVP_THREE_SOP_DERIVATIVE_LEDGER_V2.json'
    with os.fdopen(exclusive(p), 'wb') as f:
        f.write(encoded(result))
        f.flush()
        os.fsync(f.fileno())
    assert sha(ledger_path) == LEDGER_SHA and sha(preview_path) == PREVIEW_SHA
    return p


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = create(Path(args.root), Path(args.evidence), Path(args.output))
    print(json.dumps({'ledger_path': str(path), 'sha256': sha(path), 'status': 'LOCAL_MVP_CONTRACT_READY'}))
