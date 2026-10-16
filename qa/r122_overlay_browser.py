"""Small generated-only DOM/canvas check; no server, screenshot or recording."""
import argparse
import json

from pathlib import Path
from epilocate_next.r122_spatial_overlay import generate_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args = parser.parse_args()
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    generate_demo(args.output/'with-cam');generate_demo(args.output/'missing-cam',without_cam=True)
    from playwright.sync_api import sync_playwright
    checks = {};requests = [];errors = []
    uris = [(args.output/x/'overlay.html').resolve().as_uri() for x in ['with-cam','missing-cam']]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            args=['--disable-background-networking','--disable-component-update','--disable-sync','--disable-gpu','--renderer-process-limit=1'])
        try:
            page = browser.new_page(viewport=dict(width=1000,height=850))
            def route(r):
                if r.request.url in uris:r.continue_()
                else:requests.append(r.request.url);r.abort()
            page.route('**/*',route);page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.goto(uris[0],wait_until='networkidle')
            assert page.locator('#status-CT').inner_text().find('PASS') >= 0
            assert page.locator('#status-GT').inner_text().find('PASS') >= 0
            assert page.locator('#status-CAM').inner_text().find('PASS') >= 0
            assert 'UNKNOWN' in page.locator('#qualification').inner_text()
            actual = page.evaluate('coordinates(2,3,2)')
            assert actual['native_xyz'] == [1,3,1] and actual['world_LPS_mm'] == [-14,27,46]
            checks['generated_same_space_and_world_coordinates'] = 'PASS'
            page.locator('#mask').uncheck();page.locator('#cam').uncheck()
            base = page.evaluate("Array.from(ctx.getImageData(2,3,1,1).data)")
            page.locator('#mask').check()
            masked = page.evaluate("Array.from(ctx.getImageData(2,3,1,1).data)")
            assert masked != base and masked[0] > base[0]
            page.locator('#cam').check()
            assert page.evaluate("Array.from(ctx.getImageData(2,3,1,1).data)") != masked
            checks['native_mask_and_signed_cam_same_pixel'] = 'PASS'
            page.goto(uris[1],wait_until='networkidle')
            assert 'UNKNOWN' in page.locator('#status-CAM').inner_text() and page.locator('#cam').is_disabled()
            assert not page.locator('#cam').is_checked() and page.evaluate('payload.arrays.CAM') is None
            checks['missing_cam_unknown_without_fabrication'] = 'PASS'
            assert not requests and not errors
        finally:browser.close()
    result = dict(status='PASS_SMALL_GENERATED_OVERLAY_ONLY',checks=checks,external_requests=requests,page_errors=errors,
                  browser_closed=True,services=0,screenshots=0,recordings=0,real_medical_reads=0,models=0)
    with (args.output/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':main()
