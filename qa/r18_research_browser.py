"""Headless generated-page regression only. Never opens a real research page."""
import argparse
import json
from pathlib import Path

from epilocate_next.r18_research_artifact import validate_artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    html = args.page.read_text()
    raw = html.split('<script id="artifact" type="application/json">', 1)[1].split('</script>', 1)[0]
    a = validate_artifact(json.loads(raw))
    if a.evidence != 'GENERATED' or any(not c.source_group.startswith('GENERATED-') for c in a.cases):
        raise ValueError('GENERATED_PAGE_ONLY_NO_REAL_BROWSER_ACCEPTANCE')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    from playwright.sync_api import sync_playwright
    errors, external = [], []
    checks = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            args=['--disable-background-networking', '--disable-component-update', '--disable-sync'])
        try:
            page = browser.new_page(viewport=dict(width=1280, height=1000))
            uri = args.page.resolve().as_uri()
            def route(r):
                if r.request.url == uri:
                    r.continue_()
                else:
                    external.append(r.request.url);r.abort()
            page.route('**/*', route)
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.goto(uri, wait_until='networkidle')
            assert page.locator('#group option').count() == 5
            assert page.locator('#rows tr').count() == 8
            assert 'GENERATED' in page.locator('#kind').inner_text()
            checks['generated_and_eight_rows'] = 'PASS'
            page.locator('#group').select_option('GENERATED-COVID-FN')
            first = page.locator('#rows tr').first.locator('td')
            assert first.nth(3).inner_text() == '0.250000'
            original = page.locator('#summary').inner_text()
            page.locator('#unit').select_option('component')
            assert first.nth(3).inner_text() == '1.250000'
            assert '八片均值' in page.locator('#unit-note').inner_text()
            assert page.locator('#summary').inner_text() == original
            checks['weighted_vs_bias_included_component'] = 'PASS'
            page.locator('#display').select_option('positive')
            assert all(float(x) >= 0 for x in page.locator('#rows tr td:nth-child(4)').all_text_contents())
            assert page.locator('#summary').inner_text() == original
            checks['positive_display_never_reconstructs'] = 'PASS'
            page.locator('#display').select_option('signed')
            assert any(float(x) < 0 for x in page.locator('#rows tr td:nth-child(4)').all_text_contents())
            page.locator('#errors').check()
            assert page.locator('#group option').count() == 1
            assert page.locator('#group').input_value() == 'GENERATED-COVID-FN'
            checks['source_label_error_filter'] = 'PASS'
            page.locator('#errors').uncheck()
            page.locator('#group').select_option('GENERATED-TIE')
            assert '预测类别 0' in page.locator('#summary').inner_text()
            page.locator('#group').select_option('GENERATED-PREDICTION-ONLY')
            assert not page.locator('#components').is_visible()
            assert 'NOT_RUN' in page.locator('#component-missing').inner_text()
            assert 'NOT_RUN' in page.locator('#spatial').inner_text()
            assert page.locator('img,canvas,iframe').count() == 0
            checks['tie_missing_contribution_and_no_fake_cam'] = 'PASS'
            page.locator('#group').select_option('GENERATED-COVID-FN')
            page.locator('summary').click()
            assert 'geometry' in page.locator('#provenance').inner_text()
            assert 'pretraining_overlap' in page.locator('#provenance').inner_text()
            page.locator('summary').click()
            page.screenshot(path=str(args.output/'generated-desktop.png'), full_page=True)
            page.set_viewport_size(dict(width=390, height=844))
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(args.output/'generated-mobile.png'), full_page=True)
            checks['provenance_and_mobile_layout'] = 'PASS'
            assert not errors and not external
        finally:
            browser.close()
    result = dict(status='PASS_GENERATED_UI_ONLY', checks=checks, page_errors=errors,
        page_external_requests=external, browser_closed=True, real_pages_opened=0,
        medical_pixels_read=0, medical_map_assets_read=0, model_calls=0,
        screenshots='GENERATED_ONLY', services_started=0)
    with (args.output/'result.json').open('x') as f:
        json.dump(result, f, indent=2);f.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
