"""Reuse the local Playwright runtime; generated scalar pages only."""
import argparse
import json
from pathlib import Path

from epilocate_next.r103_research_metadata import validate_metadata
from epilocate_next.r103_research_review import render_metadata_review


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifact',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    artifact=validate_metadata(json.loads(a.artifact.read_text()))
    if artifact.evidence!='GENERATED':raise ValueError('GENERATED_ONLY')
    page_html=render_metadata_review(artifact)
    a.output.mkdir(mode=0o700,parents=True,exist_ok=False);page_path=a.output/'generated.html'
    with page_path.open('x') as f:f.write(page_html)
    from playwright.sync_api import sync_playwright
    checks={};external=[];errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args=['--disable-background-networking','--disable-component-update','--disable-sync'])
        try:
            page=browser.new_page(viewport=dict(width=1280,height=900));uri=page_path.resolve().as_uri()
            def route(r):
                if r.request.url==uri:r.continue_()
                else:external.append(r.request.url);r.abort()
            page.route('**/*',route);page.on('pageerror',lambda exc:errors.append(str(exc)));page.goto(uri,wait_until='networkidle')
            assert page.locator('#cases tbody tr').count()==1
            text=page.locator('#cases').inner_text();assert ('Normal_SOURCE' if artifact.kind=='CONDITIONAL_BAG' else 'COVID-19_OR_CAP_SOURCE') in text and 'BAG' in text and 'UNKNOWN' in text
            checks['normal_target_reference_unknown']='PASS'
            assert 'UNKNOWN' in page.locator('#cases tbody tr td').last.inner_text()
            checks['empty_candidate_not_absence']='PASS'
            if artifact.kind=='CONDITIONAL_BAG':
                assert page.locator('#responses tbody tr').count()==19
                assert page.locator('#responses tbody tr').first.locator('td').nth(6).inner_text()=='0.25'
                assert page.locator('#responses tbody tr').first.locator('td').nth(7).inner_text()=='16.0'
                assert 'NO_CALIBRATED_RELIABILITY_RULE' in text
                checks['separate_bag_component_units']='PASS'
            else:
                assert page.locator('#slices tbody tr').count()==8
                assert any(float(v)<0 for v in page.locator('#slices tbody tr td:nth-child(6)').all_text_contents())
                assert 'REFERENCES_ONLY_NOT_READ' in text and 'AVAILABLE_SAVED_GAP_SCALARS' in text
                checks['signed_slice_scalars_and_unread_spatial_refs']='PASS'
            assert 'positive = max(signed margin, 0)' in page.locator('#semantics').inner_text()
            assert page.locator('img,canvas,iframe,a,script').count()==0
            checks['no_medical_assets_or_scripts']='PASS'
            page.locator('summary').click();assert 'GENERATED' in page.locator('#provenance').inner_text() and artifact.source.path in page.locator('#provenance').inner_text()
            page.screenshot(path=str(a.output/'generated-desktop.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=844));assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(a.output/'generated-mobile.png'),full_page=True)
            checks['provenance_mobile']='PASS'
            assert not external and not errors
        finally:browser.close()
    result=dict(status='PASS_GENERATED_METADATA_UI_ONLY',checks=checks,external_requests=external,page_errors=errors,browser_closed=True,real_pages_opened=0,external_array_files_opened=0,models=0,services=0)
    with (a.output/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':main()
