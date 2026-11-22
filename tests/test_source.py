import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source import SITES,resolve_site,derive,validate,save,collect,Client

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.sites=[{'id':'L123','key':'west'},{'id':'L456','key':'east'}]
        self.row={'speciesCode':'mallar3','comName':'Mallard','sciName':'Anas platyrhynchos','locId':'L123','obsDt':'2026-02-27 10:30','subId':'S123','howMany':3,'obsValid':True,'obsReviewed':True,'userDisplayName':'DO NOT STORE'}
    def test_exact_hotspot_and_geographic_bounds(self):
        rows=[{'locId':'L123','locName':'Iona Island (General)','lat':49.22,'lng':-123.21}]
        self.assertEqual(resolve_site(rows,SITES[0])['id'],'L123')
        with self.assertRaisesRegex(ValueError,'Resolve'):resolve_site(rows*2,SITES[0])
        rows[0]['lat']=50
        with self.assertRaisesRegex(ValueError,'Resolve'):resolve_site(rows,SITES[0])
    def test_derive_is_latest_by_species_not_total_and_does_not_retain_people(self):
        older=dict(self.row,obsDt='2026-02-20',howMany=100)
        east=dict(self.row,locId='L456',howMany=4)
        records=derive({'west':([older,self.row],[self.row]),'east':([east],[])},self.sites)
        self.assertEqual(len(records),1); self.assertEqual(records[0]['west']['count'],3)
        self.assertTrue(records[0]['west']['notable']);self.assertFalse(records[0]['east']['notable'])
        self.assertNotIn('DO NOT STORE',json.dumps(records))
    def test_foreign_hotspot_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'):derive({'west':([dict(self.row,locId='L999')],[])},self.sites)
    def test_missing_key_does_not_write_or_guess_records(self):
        with patch.dict('os.environ',{},clear=True),self.assertRaisesRegex(RuntimeError,'EBIRD_API_KEY'):collect()
    def test_snapshot_is_immutable_and_index_is_small(self):
        records=derive({'west':([self.row],[]),'east':([],[])},self.sites)
        p={'schema':1,'status':'ready','captured_at':'2026-02-28T12:00:00Z','records':records,'sites':self.sites}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);save(p,root)
            h=json.loads((root/'data/history.json').read_text());raw=(root/h[0]['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),h[0]['sha256'])
            with self.assertRaises(FileExistsError):save(p,root)
            self.assertLess((root/'data/index.json').stat().st_size,2000)
    def test_corrupt_record_validation(self):
        with self.assertRaises(ValueError):validate({'schema':1,'status':'ready','records':[]})
        self.assertEqual(validate({'schema':1,'status':'awaiting_source','records':[]})['records'],[])

if __name__=='__main__':unittest.main()
