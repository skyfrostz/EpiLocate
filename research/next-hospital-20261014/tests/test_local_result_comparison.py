import io
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from epi_next.artifacts import canonical_json, persist_run
from epi_next.first_real_preparation import file_sha
from epi_next.local_result_comparison import validate_native_bundle, build_comparison, readback, comparison_html


def test_native_bundle_rejects_other_sop_and_tamper(tmp_path):
    path=tmp_path/'native.npz'
    np.savez(path, scores=np.zeros((4,5)), reliable=np.zeros((4,5),dtype=bool),
             SOPInstanceUID='synthetic-sop',native_case_manifest_sha256='a'*64,native_slice_index=2)
    ref={'path':str(path),'sha256':file_sha(path)}
    record={'source_sop_uid':'synthetic-sop','native_manifest_sha256':'a'*64,'native_slice_index_zero_based':2}
    scores, reliable=validate_native_bundle(ref,record,(4,5))
    assert not reliable.any() and not scores.any()
    with pytest.raises(ValueError,match='IDENTITY_OR_SHAPE'):
        validate_native_bundle(ref,dict(record,source_sop_uid='other-sop'),(4,5))
    with pytest.raises(ValueError,match='IDENTITY_OR_SHAPE'):
        validate_native_bundle(ref,record,(5,4))
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='HASH_MISMATCH'):validate_native_bundle(ref,record,(4,5))


def test_wrong_output_rejected_before_any_upstream_read(tmp_path):
    args=SimpleNamespace(output=tmp_path/'wrong',run_delivery=tmp_path/'absent')
    with pytest.raises(ValueError,match='PROTECTED_LOCAL_OUTPUT'):
        build_comparison(args)
    assert not args.output.exists()


def test_three_readbacks_preserve_assets_and_detect_upstream_change(tmp_path):
    upstream=tmp_path/'source.json';upstream.write_bytes(b'{}')
    stream=io.BytesIO();Image.new('L',(4,5)).save(stream,format='PNG')
    manifest={'cases':[{'source_result_path':str(upstream),
                       'summary':{'source_result_sha256':file_sha(upstream),'case_index':1},
                       'native_algorithm_assets':[], 'official_reference_assets':[]}]}
    root=tmp_path/'EPI-NEXT-test'
    persist_run(tmp_path,root.name,{'binding_manifest.json':canonical_json(manifest),'case-1-comparison.png':stream.getvalue()})
    outputs=[readback(root) for _ in range(3)]
    assert outputs[0]==outputs[1]==outputs[2]
    upstream.write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError,match='UPSTREAM_RESULT_CHANGED'):readback(root)


def test_html_abstention_partial_reference_and_escaping():
    page=comparison_html([{'summary':{'case_index':1,'native_slice_index':2,
                                      'E1_status':'OK','E2_status':'NO_FEASIBLE_MASK',
                                      'baseline_logits':['<script>']}}]).decode()
    assert 'NO_FEASIBLE_MASK' in page and 'UNKNOWN' in page
    assert '&lt;script&gt;' in page and '<script>' not in page
    assert 'https://' not in page and 'http://' not in page
    assert "connect-src 'none'" in page
