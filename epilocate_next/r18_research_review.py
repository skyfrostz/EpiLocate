"""Local research tool: metadata validation, generated-only HTML preview."""
import argparse
import json
import os
from pathlib import Path

from .r18_research_artifact import from_encoder_contributions, load_json_metadata, metadata_summary, validate_artifact

TEMPLATE = Path(__file__).with_name('r18_research_review.html')


def render_review(artifact, *, real_metadata_page=False):
    if artifact.evidence != 'GENERATED' and not real_metadata_page:
        raise ValueError('REAL_ARTIFACT_METADATA_ONLY_NO_AUTOMATIC_DISPLAY')
    # Data stays inert even for strings containing closing script tags.
    payload = json.dumps(artifact.model_dump(), ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')
    return TEMPLATE.read_text().replace('__ARTIFACT_JSON__', payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--profile', choices=['consumer-v1', 'enc-r92-v1', 'r102-metadata-v1', 'metadata-v1'], default='consumer-v1')
    parser.add_argument('--cache-metadata', type=Path)
    parser.add_argument('--cache-sha')
    parser.add_argument('--slice-contributions-json', type=Path)
    parser.add_argument('--slice-contributions-sha')
    parser.add_argument('--fixed8-control-json', type=Path)
    parser.add_argument('--fixed8-control-sha')
    parser.add_argument('--real-metadata-page', action='store_true', help='Explicit static numeric-metadata page; no image/heatmap references are opened')
    parser.add_argument('--html', type=Path, help='Exclusive static file; real numeric metadata requires explicit flag; never starts a browser/server')
    parser.add_argument('--normalized', type=Path, help='Exclusive normalized JSON output; source files are never modified')
    args = parser.parse_args()
    data = load_json_metadata(args.artifact, args.sha)
    if bool(args.cache_metadata) != bool(args.cache_sha) or (args.cache_metadata and args.profile != 'enc-r92-v1'):
        parser.error('ENC_PROFILE_AND_CACHE_PATH_SHA_PAIR_REQUIRED')
    cache = load_json_metadata(args.cache_metadata, args.cache_sha) if args.cache_metadata else None
    metadata_profile = args.profile in {'r102-metadata-v1', 'metadata-v1'}
    if metadata_profile:
        from .r103_research_metadata import from_r102_receipt, validate_metadata, metadata_summary as new_summary
        artifact = (from_r102_receipt(data, dict(path=str(args.artifact), sha256=args.sha))
                    if args.profile == 'r102-metadata-v1' else validate_metadata(data))
    else:
        artifact = (from_encoder_contributions(data, dict(path=str(args.artifact), sha256=args.sha), cache=cache,
                                         cache_ref=dict(path=str(args.cache_metadata), sha256=args.cache_sha) if cache is not None else None)
                if args.profile == 'enc-r92-v1' else validate_artifact(data))
    join_args = [args.slice_contributions_json, args.slice_contributions_sha, args.fixed8_control_json, args.fixed8_control_sha]
    if any(join_args):
        if not all(join_args) or not metadata_profile:
            parser.error('METADATA_PROFILE_AND_BOTH_EXPLICIT_JSON_SHA_PAIRS_REQUIRED')
        from .r103_research_metadata import join_saved_contributions
        scalar = from_encoder_contributions(load_json_metadata(args.slice_contributions_json, args.slice_contributions_sha),
            dict(path=str(args.slice_contributions_json), sha256=args.slice_contributions_sha),
            evidence='GENERATED' if artifact.evidence == 'GENERATED' else 'REAL_PRECOMPUTED')
        control = load_json_metadata(args.fixed8_control_json, args.fixed8_control_sha)
        artifact = join_saved_contributions(artifact, scalar, control, dict(path=str(args.fixed8_control_json), sha256=args.fixed8_control_sha))
    if args.html:
        if metadata_profile:
            from .r103_research_review import render_metadata_review
            page = render_metadata_review(artifact)
        else:
            page = render_review(artifact, real_metadata_page=args.real_metadata_page)
        fd = os.open(args.html, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(page)
    if args.normalized:
        fd = os.open(args.normalized, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(artifact.model_dump(), out, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            out.write('\n')
    summary = new_summary(artifact) if metadata_profile else metadata_summary(artifact)
    summary['json_metadata_files_read'] = 1 + int(cache is not None) + 2*int(all(join_args))
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as exc:
        # Never dump protected case payloads through a validation traceback.
        print(json.dumps(dict(status='REJECTED_METADATA', error_type=type(exc).__name__,
                              model_calls=0, output_state='RECONCILE_EXISTING_FILES_NO_OVERWRITE')))
        raise SystemExit(2)
