import test from 'node:test';import assert from 'node:assert/strict';import {validate,filterRows,summarize,toCSV,importText,parseCSV,csvCell} from '../web/model.mjs';
const obs=(date,count=2,notable=false)=>({date,count,notable,checklist:'https://ebird.org/checklist/S123',reviewed:true,valid:true});
const data={schema:1,status:'ready',captured_at:'2026-02-28T12:00:00Z',sites:[{key:'west'},{key:'east'}],records:[{id:'mallar3',name:'Mallard',scientific_name:'Anas platyrhynchos',west:obs('2026-02-27 08:00'),east:obs('2026-02-20',null)},{id:'sposan',name:'Spotted Sandpiper',scientific_name:'Actitis macularius',west:null,east:obs('2026-02-25',1,true)},{id:'amecro',name:'American Crow',scientific_name:'Corvus brachyrhynchos',west:obs('2026-02-01'),east:null}]};
test('matching compares species codes and shorter windows change shared status',()=>{assert.deepEqual(summarize(filterRows(data)),{west:2,east:2,shared:1,notable:1});assert.equal(filterRows(data,{scope:'shared'}).length,1);assert.equal(filterRows(data,{scope:'shared',days:7}).length,0);assert.equal(filterRows(data,{scope:'west',days:7})[0].id,'mallar3');});
test('the full source window retains a local-date boundary report without recomputing the API cutoff',()=>{
  const boundary={...data,window_days:30,captured_at:'2026-11-22T15:17:58Z',records:[{id:'eurwig',name:'Eurasian Wigeon',scientific_name:'Mareca penelope',west:obs('2026-10-23 12:36'),east:null}]};
  assert.deepEqual(filterRows(boundary),boundary.records);
  assert.deepEqual(summarize(filterRows(boundary)),{west:1,east:0,shared:0,notable:0});
  assert.equal(filterRows(boundary,{days:14}).length,0);
});
test('shorter windows use the stated number of calendar dates ending on the capture date',()=>{
  const boundary={...data,window_days:30,records:[{...data.records[0],west:obs('2026-02-22 00:00'),east:obs('2026-02-21 23:59')}]};
  const rows=filterRows(boundary,{days:7});
  assert.equal(rows[0].west.date,'2026-02-22 00:00');
  assert.equal(rows[0].east,null);
});
test('notable flags come from the source and text search supports scientific names',()=>{assert.equal(filterRows(data,{scope:'notable'})[0].id,'sposan');assert.equal(filterRows(data,{query:'ANAS'})[0].id,'mallar3');assert.equal(filterRows(data,{query:'nothing'}).length,0);});
test('derived CSV retains null counts, flags, sources and collection date on round trip',()=>{const csv=toCSV(data.records,data);assert.ok(csv.includes('ebird-data-access-terms-of-use'));assert.equal(parseCSV(csv).length,3);const result=importText(csv,'view.csv',data);assert.deepEqual(result.records.map(r=>[r.id,r.west?.count,r.east?.count]),data.records.map(r=>[r.id,r.west?.count,r.east?.count]));assert.equal(result.records[1].east.notable,true);});
test('import rejects duplicate identities, unsafe links, and invalid counts',()=>{assert.throws(()=>validate({...data,records:[data.records[0],data.records[0]]}),/duplicate/);assert.throws(()=>validate({...data,records:[{...data.records[0],west:{...obs('2026-02-27'),checklist:'javascript:alert(1)'}}]}),/checklist/);assert.throws(()=>validate({...data,records:[{...data.records[0],west:obs('2026-02-27',-1)}]}),/count/);});
test('CSV handles quotes/newlines and neutralizes spreadsheet formulas',()=>{assert.equal(csvCell('=CMD()'),'"\'=CMD()"');const r={...data.records[0],name:'A "quoted",\nname'};assert.equal(importText(toCSV([r],data),'x.csv',data).records[0].name,r.name);assert.throws(()=>parseCSV('"bad'),/quote/);});
test('uncollected dataset is explicit and stays empty',()=>{const d={...data,status:'awaiting_source',captured_at:null,records:[]};assert.equal(validate(d).records.length,0);assert.equal(filterRows(d).length,0);});
