"""CI-only Chromium acceptance flow using explicitly synthetic local-import test data."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
import threading
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
    def end_headers(self):
        # Reproduce the legacy module cache lifetime; all primer assets are temporary.
        if self.path.split('?')[0] in ('/hotspotledger/app.mjs','/hotspotledger/model.mjs'):
            self.send_header('Cache-Control','public, max-age=600, immutable')
        else:
            self.send_header('Cache-Control','no-store')
        super().end_headers()

def synthetic_snapshot():
    """Independent test data: never inherits source-capture metadata or scope."""
    return {
        'schema':1,'status':'ready','captured_at':'2026-02-28T12:00:00Z','window_days':30,
        'sites':[
            {'key':'west','name':'Synthetic west test location','url':'https://ebird.org/hotspot/L1'},
            {'key':'east','name':'Synthetic east test location','url':'https://ebird.org/hotspot/L2'},
        ],
        'sources':[],'coverage':'Synthetic browser-test fixture only; not source observations.',
        'warnings':['Synthetic test data, used only by CI.'],
        'records':[
            {'id':'testone','name':'Test Shared Bird','scientific_name':'Testus communis','west':{'date':'2026-02-27','count':2,'notable':False,'checklist':'https://ebird.org/checklist/S1'},'east':{'date':'2026-02-26','count':None,'notable':True,'checklist':'https://ebird.org/checklist/S2'}},
            # A rolling-window boundary report must survive the full-source view.
            {'id':'testtwo','name':'<img src=x onerror=alert(1)>','scientific_name':'Testus localis','west':{'date':'2026-01-29 12:36','count':1,'notable':False,'checklist':'https://ebird.org/checklist/S3'},'east':None},
        ],
    }


def main():
    from playwright.sync_api import sync_playwright, expect
    screenshots=ROOT/'browser-checks';screenshots.mkdir(exist_ok=True)
    sample=synthetic_snapshot()
    with tempfile.TemporaryDirectory() as temp:
        site=Path(temp)/'hotspotledger';shutil.copytree(ROOT/'dist',site)
        # Cache a deliberately obsolete module graph at the former unversioned URLs.
        # This primer and its sentinel modules are never placed in dist/ or published.
        (site/'cache-primer.html').write_text('<!doctype html><html><head><title>CI cache primer</title></head><body><script type="module" src="./app.mjs"></script></body></html>')
        (site/'model.mjs').write_text('globalThis.__hotspotLegacyModel = true; export const legacy = true;')
        (site/'app.mjs').write_text("import './model.mjs'; globalThis.__hotspotLegacyApp = true;")
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=temp));threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                base=f'http://127.0.0.1:{server.server_port}/hotspotledger/'
                page.goto(base+'cache-primer.html')
                page.wait_for_function('globalThis.__hotspotLegacyApp === true && globalThis.__hotspotLegacyModel === true')
                # The server now has fresh unversioned sources, while this same browser
                # context still holds the cacheable legacy responses from the primer.
                shutil.copyfile(ROOT/'web/app.mjs',site/'app.mjs')
                shutil.copyfile(ROOT/'web/model.mjs',site/'model.mjs')
                cached=page.evaluate("Promise.all(['app.mjs','model.mjs'].map(async file => (await (await fetch('./'+file,{cache:'force-cache'})).text()).includes('__hotspotLegacy')))")
                assert cached==[True,True], 'Legacy app and model responses were not primed in the browser cache'
                page.goto(base)
                expect(page.locator('#status')).not_to_contain_text('Loading')
                assert page.evaluate('globalThis.__hotspotLegacyApp === undefined && globalThis.__hotspotLegacyModel === undefined'), 'The built page reused a legacy unversioned module'
                assert not errors,errors
                page.locator('#import-file').set_input_files({'name':'synthetic-test-only.json','mimeType':'application/json','buffer':json.dumps(sample).encode()})
                expect(page.locator('#import-status')).to_contain_text('Opened synthetic-test-only.json')
                expect(page.locator('#status')).to_contain_text('LOCAL FILE')
                assert page.locator('#rows tr').count()==2
                expect(page.locator('#rows')).to_contain_text('2026-01-29 12:36')
                assert page.locator('#shared-total').inner_text()=='1'
                assert page.locator('#rows img').count()==0
                page.locator('#scope').select_option('notable');assert page.locator('#rows tr').count()==1
                page.locator('#query').fill('no match');assert page.locator('#empty').is_visible()
                page.locator('#reset').click();assert page.locator('#rows tr').count()==2
                page.locator('#days').select_option('7');assert page.locator('#rows tr').count()==1
                with page.expect_download() as info:page.locator('#export-csv').click()
                downloaded=Path(temp)/'derived.csv';info.value.save_as(downloaded)
                assert 'ebird-data-access-terms-of-use' in downloaded.read_text()
                page.locator('#import-file').set_input_files(str(downloaded));expect(page.locator('#import-status')).to_contain_text('Opened derived.csv');assert page.locator('#rows tr').count()==1
                page.locator('#import-file').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':b'{"schema":999}'})
                expect(page.locator('#import-status')).to_contain_text('Could not open file')
                assert page.locator('#rows tr').count()==1
                with page.expect_download() as info:page.locator('#export-json').click()
                assert info.value.suggested_filename=='hotspotledger-snapshot.json'
                page.screenshot(path=str(screenshots/'desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(screenshots/'mobile.png'),full_page=True)
                page.locator('#restore').click();assert 'LOCAL FILE' not in page.locator('#status').inner_text();assert page.locator('#restore').is_hidden()
                assert not errors,errors;browser.close()
            print('Browser acceptance passed: same-context legacy module cache, full-source boundary report, published data, local JSON/CSV roundtrip, filters, export, invalid import, safe text and mobile.')
        finally:server.shutdown()
if __name__=='__main__':main()
