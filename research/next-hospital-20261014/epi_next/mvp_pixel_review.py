"""Render local-only full-frame previews; no automated pixel identity verdict."""
import argparse
import base64
import html
import io
import json
import os
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image

from .a0_acquire import exclusive, secure_parent
from .a1_prepare import encoded, sha
from .mvp_three_sop import pixels_sha

LEDGER_SHA = '0000000000000000000000000000000000000000000000000000000000000000'


def save(path, raw):
    with os.fdopen(exclusive(path), 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def prepare(ledger_path, out):
    if sha(ledger_path) != LEDGER_SHA:
        raise ValueError('EXACT_BLOCKED_LEDGER_REQUIRED')
    ledger = json.loads(Path(ledger_path).read_text())
    if [r['case_index'] for r in ledger['records']] != [1, 2, 3]:
        raise ValueError('EXACT_THREE_CASES_REQUIRED')
    out = Path(out)
    secure_parent(out)
    out.mkdir(mode=0o700, exist_ok=False)
    preview_cases, sections = [], []
    for record in ledger['records']:
        path = Path(record['path'])
        if path.stat().st_size > 20 * 1024**2 or sha(path) != record['sha256']:
            raise ValueError('DERIVATIVE_BINDING_OR_SIZE_DRIFT')
        ds = pydicom.dcmread(path)
        raw_pixels = ds.pixel_array
        if raw_pixels.shape != (512, 512) or pixels_sha(raw_pixels) != record['derivative_decoded_pixel_sha256']:
            raise ValueError('FULL_FRAME_PIXEL_BINDING_DRIFT')
        scaled = None
        if 'RescaleSlope' in ds and 'RescaleIntercept' in ds:
            scaled = raw_pixels.astype(np.float64) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)
        if scaled is None or not np.isfinite(scaled).all():
            raise ValueError('FINITE_SOURCE_RESCALE_REQUIRED_NO_INFERRED_TRANSFORM')
        units = str(ds.get('RescaleType', 'UNKNOWN'))
        windows = [('stored_minmax', '原存储值全范围', raw_pixels, float(raw_pixels.min()), float(raw_pixels.max())),
                   ('rescaled_wide', '重标度值固定范围 -1350..150', scaled, -1350., 150.),
                   ('rescaled_narrow', '重标度值固定范围 -160..240', scaled, -160., 240.)]
        previews, panels = [], []
        for name, label, values, low, high in windows:
            gray = np.rint(np.clip((values.astype(np.float64) - low) / max(high - low, 1.), 0., 1.) * 255).astype(np.uint8)
            buffer = io.BytesIO()
            Image.fromarray(gray).save(buffer, format='PNG')
            png = buffer.getvalue()
            png_path = out / f'case-{record["case_index"]}-{name}.png'
            save(png_path, png)
            png_sha = sha(png_path)
            previews.append({'window_id': name, 'path': str(png_path.resolve()), 'sha256': png_sha,
                             'rows': 512, 'columns': 512, 'range_low': low, 'range_high': high,
                             'units': 'STORED_VALUE' if name == 'stored_minmax' else units,
                             'crop': False, 'resize': False})
            label = label + ('；单位 ' + units if name != 'stored_minmax' else '')
            panels.append('<figure><figcaption>' + html.escape(label) + '</figcaption><img width="512" height="512" alt="case_index ' + str(record['case_index']) + ' ' + name + ' full frame" src="data:image/png;base64,' + base64.b64encode(png).decode('ascii') + '"><code>PNG SHA256 ' + png_sha + '</code></figure>')
        preview_cases.append({'case_index': record['case_index'],
                              'source_ct_sha256': record['source_ct_sha256'],
                              'derivative_sha256': record['sha256'],
                              'decoded_pixel_sha256': record['derivative_decoded_pixel_sha256'],
                              'previews': previews})
        index = record['case_index']
        sections.append('<section><h2>case_index ' + str(index) + '</h2><div class="panels">' + ''.join(panels) + '</div><div class="checks"><label><input type="checkbox" id="panels-' + str(index) + '">我已逐张查看此例全部三个窗口</label><label><input type="checkbox" id="edges-' + str(index) + '">我已核查完整图像及四周边缘，未遗漏角落</label><label>发现烧录身份信息：<select id="finding-' + str(index) + '"><option value="">请选择本人结论</option><option value="NO">NO：未发现</option><option value="YES">YES：发现</option><option value="UNCERTAIN">UNCERTAIN：无法确定</option></select></label><label>备注（区域或疑点，勿抄录身份文字）<textarea id="notes-' + str(index) + '"></textarea></label></div></section>')
        del raw_pixels, scaled, ds
    binding = {'schema': 'EPI_NEXT_MVP_PIXEL_REVIEW_PREVIEW_V1',
               'derivative_ledger_path': str(Path(ledger_path).resolve()),
               'derivative_ledger_sha256': LEDGER_SHA,
               'status': 'AWAITING_OWNER_VISUAL_REVIEW',
               'hospital_display_authorized': False, 'external_upload_authorized': False,
               'automatic_pixel_phi_verdict': 'NONE', 'records': preview_cases}
    save(out / 'PREVIEW_BINDING_V1.json', encoded(binding))
    # The exported human record remains pending DATA audit; it never edits the
    # blocked derivative ledger or makes another DICOM version automatically.
    human_binding = {'schema': 'EPI_NEXT_OWNER_PIXEL_VISUAL_REVIEW_V1',
                     'derivative_ledger_sha256': LEDGER_SHA,
                     'preview_binding_sha256': sha(out / 'PREVIEW_BINDING_V1.json'),
                     'status': 'OWNER_RECORD_PENDING_DATA_AUDIT',
                     'records': [{k: v for k, v in r.items() if k != 'previews'} |
                                 {'preview_png_sha256': [p['sha256'] for p in r['previews']]}
                                 for r in preview_cases]}
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'"><title>原三SOP：负责人本机像素复核</title><style>body{font-family:system-ui,sans-serif;margin:24px;background:#fafafa;color:#222}h1{font-size:24px}section{background:white;padding:20px;margin:24px 0;border:1px solid #bbb}.panels{display:flex;flex-wrap:wrap;gap:16px}figure{margin:0;width:512px;max-width:100%}img{display:block;width:100%;height:auto;background:#000}figcaption{min-height:2em}code{display:block;font-size:11px;overflow-wrap:anywhere}.checks{display:grid;gap:12px;margin-top:20px}textarea{display:block;width:95%;height:56px}button,input,select{font:inherit}button{padding:10px;margin:16px 0}#message{color:#a00}</style><h1>原三SOP：负责人本机人工像素复核</h1><p>当前派生物不可上传：烧录身份信息状态 UNKNOWN。此页无外部资源、联网请求或自动图像分析。全部图像为完整512×512，仅灰度映射；未裁剪、缩放源像素或覆盖文字。可使用浏览器缩放核查边缘与角落。</p><p>请本人检查姓名、编号、日期等可能识别身份的烧录文字或图形。自动像素等值QA和来源去标识不代替目视判断。页面导出的记录仍需DATA审核；本页不改当前UNKNOWN，也不生成新派生版本。</p>''' + ''.join(sections) + '''<section><h2>负责人确认</h2><label>本人姓名或负责人账号 <input id="reviewer" autocomplete="off"></label><p><label><input type="checkbox" id="affirmation">以上是本人逐例目视检查的结论</label></p><button id="export" type="button">下载本机人工复核记录 JSON</button><p id="message"></p></section><script>
const bound = ''' + json.dumps(human_binding, ensure_ascii=True) + ''';
document.getElementById('export').onclick = () => {
 const reviewer=document.getElementById('reviewer').value.trim();
 const affirmation=document.getElementById('affirmation').checked;
 const result=JSON.parse(JSON.stringify(bound));
 result.reviewer=reviewer;result.reviewed_at=new Date().toISOString();
 result.browser_time_zone=Intl.DateTimeFormat().resolvedOptions().timeZone;
 result.owner_visual_review_affirmed=affirmation;
 let complete=!!reviewer&&affirmation;
 for (const row of result.records) {
  const id=row.case_index;
  row.all_preview_panels_reviewed=document.getElementById('panels-'+id).checked;
  row.full_frame_including_edges_reviewed=document.getElementById('edges-'+id).checked;
  row.burned_in_identity_information_detected=document.getElementById('finding-'+id).value;
  row.notes=document.getElementById('notes-'+id).value;
  complete=complete&&row.all_preview_panels_reviewed&&row.full_frame_including_edges_reviewed&&!!row.burned_in_identity_information_detected;
 }
 if (!complete) {document.getElementById('message').textContent='请本人完成三例核查、选择结论并确认身份后再导出。';return;}
 const blob=new Blob([JSON.stringify(result,null,2)+'\\n'],{type:'application/json'});
 const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='OWNER_PIXEL_VISUAL_REVIEW_V1.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById('message').textContent='已导出本机人工记录。当前UNKNOWN派生物保持不变；记录交回DATA审核后才决定新版本。';
};</script></html>'''
    page_path = out / 'OWNER_PIXEL_REVIEW_V1.html'
    save(page_path, page.encode('utf-8'))
    return page_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = prepare(args.ledger, args.output)
    print(json.dumps({'review_page': str(path.resolve()), 'sha256': sha(path),
                      'status': 'AWAITING_OWNER_VISUAL_REVIEW'}))


if __name__ == '__main__':
    main()
