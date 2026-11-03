"""Local header derivatives of only the hash-bound three approved SOPs."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.pixels import get_decoder
from pydicom.uid import PYDICOM_IMPLEMENTATION_UID

from .a0_acquire import exclusive, secure_parent
from .a1_prepare import CT, encoded, sha

DELIVERY_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
SCOPE_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
OWNER_SHA = '0000000000000000000000000000000000000000000000000000000000000000'
KEEP = {
    'SpecificCharacterSet', 'ImageType', 'SOPClassUID', 'SOPInstanceUID', 'Modality',
    'StudyInstanceUID', 'SeriesInstanceUID', 'FrameOfReferenceUID', 'SeriesNumber',
    'InstanceNumber', 'PatientPosition', 'ImagePositionPatient',
    'ImageOrientationPatient', 'PixelSpacing', 'SliceThickness', 'SpacingBetweenSlices',
    'SamplesPerPixel', 'PhotometricInterpretation', 'PlanarConfiguration',
    'NumberOfFrames', 'Rows', 'Columns', 'BitsAllocated', 'BitsStored', 'HighBit',
    'PixelRepresentation', 'PixelPaddingValue', 'PixelPaddingRangeLimit',
    'RescaleSlope', 'RescaleIntercept', 'RescaleType', 'WindowCenter', 'WindowWidth',
    'VOILUTFunction', 'PresentationLUTShape', 'LossyImageCompression',
    'LossyImageCompressionRatio', 'LossyImageCompressionMethod', 'PixelData',
    'BurnedInAnnotation',
}
SENSITIVE = {'PatientName', 'PatientID', 'PatientBirthDate', 'AccessionNumber',
             'InstitutionName', 'ReferringPhysicianName', 'StudyDate', 'SeriesDate',
             'AcquisitionDate', 'PatientAddress', 'StudyDescription',
             'SeriesDescription', 'ImageComments'}
GEOMETRY = ('Rows', 'Columns', 'PixelSpacing', 'ImageOrientationPatient',
            'ImagePositionPatient', 'SliceThickness', 'SpacingBetweenSlices',
            'FrameOfReferenceUID', 'InstanceNumber')
REPRESENTATION = ('BitsAllocated', 'BitsStored', 'HighBit', 'PixelRepresentation',
                  'SamplesPerPixel', 'PhotometricInterpretation', 'NumberOfFrames',
                  'RescaleSlope', 'RescaleIntercept', 'RescaleType', 'PixelPaddingValue',
                  'PixelPaddingRangeLimit', 'WindowCenter', 'WindowWidth',
                  'VOILUTFunction', 'PresentationLUTShape')


def same_fields(a, b, fields):
    return all((k in a) == (k in b) and (k not in a or a[k] == b[k]) for k in fields)


def pixels_sha(array):
    canonical = np.ascontiguousarray(array, dtype=array.dtype.newbyteorder('<'))
    return hashlib.sha256(canonical.tobytes()).hexdigest()


def derive(delivery, owner, out):
    if sha(delivery) != DELIVERY_SHA or sha(owner) != OWNER_SHA:
        raise ValueError('APPROVED_DELIVERY_OR_OWNER_DRIFT')
    records = json.loads(Path(delivery).read_text())['records']
    if [r['case_index'] for r in records] != [1, 2, 3]:
        raise ValueError('EXACT_THREE_ORDER_REQUIRED')
    out = Path(out)
    secure_parent(out)
    out.mkdir(mode=0o700, exist_ok=False)
    rows = []
    for r in records:
        source = Path(r['source_ct_path'])
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 20 * 1024**2:
            raise ValueError('SOURCE_FILE_TYPE_OR_SIZE')
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as f:
            opened = os.fstat(f.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
                raise ValueError('SOURCE_OPEN_DRIFT')
            digest = hashlib.sha256(f.read(20 * 1024**2 + 1)).hexdigest()
            if digest != r['source_ct_sha256']:
                raise ValueError('EXACT_SOURCE_SHA_MISMATCH')
            f.seek(0)
            src = pydicom.dcmread(f)
        if any(str(src.get(k, '')) != r[v] for k, v in (
                ('SOPInstanceUID', 'source_sop_uid'), ('StudyInstanceUID', 'study_uid'),
                ('SeriesInstanceUID', 'series_uid'))):
            raise ValueError('EXACT_UID_BINDING_MISMATCH')
        if (str(src.SOPClassUID) != CT or str(src.Modality) != 'CT'
                or str(src.PhotometricInterpretation) != 'MONOCHROME2'
                or int(src.get('NumberOfFrames', 1)) != 1
                or int(src.get('SamplesPerPixel', 1)) != 1
                or any(v in str(src.get('ImageType', '')).upper() for v in ('LOCALIZER', 'SCOUT'))):
            raise ValueError('CLASSIC_CT_CONTRACT')
        if not (2 <= int(src.Rows) <= 4096 and 2 <= int(src.Columns) <= 4096
                and int(src.Rows) * int(src.Columns) <= 16777216):
            raise ValueError('MATRIX_LIMIT')
        if 'VOILUTSequence' in src or 'ModalityLUTSequence' in src:
            raise ValueError('LUT_SEQUENCE_REQUIRES_SEPARATE_PRESERVATION_REVIEW')
        syntax = src.file_meta.TransferSyntaxUID
        if not get_decoder(syntax).is_available:
            raise ValueError('EXISTING_DECODER_UNAVAILABLE_NO_INSTALL')
        original_pixels = src.pixel_array
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = src.SOPClassUID
        meta.MediaStorageSOPInstanceUID = src.SOPInstanceUID
        meta.TransferSyntaxUID = syntax
        meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
        dst = FileDataset(None, {}, file_meta=meta, preamble=b'\0' * 128)
        removed_keywords = set()
        for element in src:
            if not element.tag.is_private and element.keyword in KEEP:
                dst.add(copy.deepcopy(element))
            elif element.keyword:
                removed_keywords.add(element.keyword)  # names only, never values
        dst.remove_private_tags()
        dst.PatientIdentityRemoved = 'YES'
        dst.DeidentificationMethod = 'Header allowlist; pixel identity status UNKNOWN'
        # No inferred BurnedInAnnotation=NO. Preserve a source declaration if
        # present; otherwise omit the tag and block upload readiness.
        path = out / f'case-{r["case_index"]}.dcm'
        with os.fdopen(exclusive(path), 'wb') as f:
            pydicom.dcmwrite(f, dst, enforce_file_format=True)
            f.flush()
            os.fsync(f.fileno())
        if path.stat().st_size > 20 * 1024**2:
            raise ValueError('DERIVATIVE_SIZE_LIMIT')
        check = pydicom.dcmread(path)
        derived_pixels = check.pixel_array
        if not np.array_equal(original_pixels, derived_pixels):
            raise ValueError('PIXEL_VALUES_CHANGED')
        if src.PixelData != check.PixelData:
            raise ValueError('ENCODED_PIXEL_PAYLOAD_CHANGED')
        if not same_fields(src, check, GEOMETRY) or not same_fields(src, check, REPRESENTATION):
            raise ValueError('GEOMETRY_OR_REPRESENTATION_CHANGED')
        if any(e.tag.is_private or (e.keyword in SENSITIVE and str(e.value).strip())
               for e in check.iterall()):
            raise ValueError('DERIVATIVE_HEADER_DEIDENTIFICATION_FAILED')
        annotation = str(check.get('BurnedInAnnotation', 'UNKNOWN'))
        row = {'case_index': r['case_index'], 'path': str(path.resolve()), 'sha256': sha(path),
               'bytes': path.stat().st_size, 'source_ct_sha256': r['source_ct_sha256'],
               'source_sop_uid': r['source_sop_uid'], 'study_uid': r['study_uid'],
               'series_uid': r['series_uid'], 'native_slice_index_zero_based': r['native_slice_index_zero_based'],
               'source_decoded_pixel_sha256': pixels_sha(original_pixels),
               'derivative_decoded_pixel_sha256': pixels_sha(derived_pixels),
               'decoded_pixel_dtype': original_pixels.dtype.str, 'shape': list(original_pixels.shape),
               'pixel_values_equal': True, 'encoded_pixel_payload_equal': True,
               'native_geometry_equal': True, 'pixel_representation_and_window_equal': True,
               'deidentification_checked': True, 'header_deidentification_pass': True,
               'deidentification_status': 'HEADER_PASS_PIXEL_PHI_UNKNOWN',
               'BurnedInAnnotation': annotation, 'burned_in_phi_status': 'UNKNOWN',
               'pixel_phi_visual_review': 'NOT_PERFORMED_NO_ABSENCE_CLAIM',
               'upload_eligible': False, 'upload_block_reason': 'PIXEL_PHI_ABSENCE_NOT_VERIFIED',
               'transfer_syntax': str(syntax), 'decoder_available_in_existing_environment': True,
               'lossless_reencoding': False, 'uid_changes': False,
               'operations': ['retained technical header allowlist and original encoded PixelData',
                              'removed all other header elements and original file-meta/preamble',
                              'removed all private elements including nested content',
                              'set PatientIdentityRemoved=YES for header removal',
                              'did not infer BurnedInAnnotation=NO'],
               'removed_standard_keywords': sorted(removed_keywords)}
        rows.append(row)
        del original_pixels, derived_pixels, src, dst, check
        if sha(source) != r['source_ct_sha256']:
            raise ValueError('ORIGINAL_CHANGED')
    ledger = {'schema': 'EPI_NEXT_MVP_DERIVATIVE_DELIVERY_V1',
              'status': 'LOCAL_DERIVATIVES_VERIFIED_UPLOAD_BLOCKED_PIXEL_PHI_UNKNOWN',
              'prepared_delivery_sha256': DELIVERY_SHA, 'owner_scope_sha256': SCOPE_SHA,
              'owner_approval_sha256': OWNER_SHA, 'hospital_display_authorized': False,
              'source_file_count': 3, 'model_calls': 0, 'GT_files_read': 0,
              'records': rows}
    ledger_path = out / 'MVP_THREE_SOP_DERIVATIVE_LEDGER_V1.json'
    with os.fdopen(exclusive(ledger_path), 'wb') as f:
        f.write(encoded(ledger))
        f.flush()
        os.fsync(f.fileno())
    return ledger_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared-delivery', required=True)
    parser.add_argument('--owner-approval', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = derive(args.prepared_delivery, args.owner_approval, args.output)
    print(json.dumps({'ledger_path': str(path.resolve()), 'ledger_sha256': sha(path),
                      'status': 'LOCAL_VERIFIED_UPLOAD_BLOCKED_PIXEL_PHI_UNKNOWN'}))


if __name__ == '__main__':
    main()
