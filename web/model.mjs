export const TERMS='https://www.birds.cornell.edu/home/ebird-data-access-terms-of-use/';
export const COLUMNS=['species_code','common_name','scientific_name','west_date','west_count','west_checklist','west_notable','east_date','east_count','east_checklist','east_notable','captured_at','source','terms'];
export function validate(data){
  if(!data||data.schema!==1||!Array.isArray(data.records)||data.records.length>2000||!Array.isArray(data.sites)||data.sites.length!==2)throw Error('Choose a Hotspot Ledger JSON snapshot or exported CSV.');
  if(data.status!=='ready'&&data.status!=='awaiting_source')throw Error('Unknown dataset status.');
  const seen=new Set();
  for(const r of data.records){
    if(!/^[a-z0-9]{3,20}$/.test(r.id)||seen.has(r.id)||typeof r.name!=='string'||!r.name||typeof r.scientific_name!=='string'||!r.scientific_name)throw Error('The file contains an invalid or duplicate species.');seen.add(r.id);
    if(!r.west&&!r.east)throw Error('Each species needs a source observation.');
    for(const side of ['west','east']){const o=r[side];if(!o)continue;
      if(!/^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$/.test(o.date)||!Number.isFinite(Date.parse(o.date.slice(0,10)+'T12:00:00Z'))||!/^https:\/\/ebird\.org\/checklist\/S\d+$/.test(o.checklist))throw Error('Invalid observation date or eBird checklist link.');
      if(o.count!==null&&(!Number.isInteger(o.count)||o.count<0))throw Error('Observation count must be a nonnegative whole number or blank.');
      if(typeof o.notable!=='boolean')throw Error('Notable flags must be true or false.');
    }
  }
  if(data.status==='ready'&&!Number.isFinite(Date.parse(data.captured_at)))throw Error('The snapshot needs a valid collection timestamp.');
  return data;
}
export function windowRows(data,days=30){
  const anchor=Date.parse((data.captured_at||new Date().toISOString()).slice(0,10)+'T23:59:59Z');
  return data.records.map(r=>({...r,...Object.fromEntries(['west','east'].map(side=>{const o=r[side];return [side,o&&anchor-Date.parse(o.date.slice(0,10)+'T00:00:00Z')<days*86400000?o:null];}))})).filter(r=>r.west||r.east);
}
export function summarize(rows){return{west:rows.filter(r=>r.west).length,east:rows.filter(r=>r.east).length,shared:rows.filter(r=>r.west&&r.east).length,notable:rows.filter(r=>r.west?.notable||r.east?.notable).length};}
export function filterRows(data,{days=30,query='',scope='all',sort='name'}={}){
  const q=query.trim().toLowerCase();let rows=windowRows(data,Number(days)).filter(r=>(r.name+' '+r.scientific_name).toLowerCase().includes(q));
  rows=rows.filter(r=>scope==='shared'?r.west&&r.east:scope==='west'?r.west&&!r.east:scope==='east'?r.east&&!r.west:scope==='notable'?r.west?.notable||r.east?.notable:true);
  return rows.sort((a,b)=>sort==='recent'?[b.west?.date||'',b.east?.date||''].sort().at(-1).localeCompare([a.west?.date||'',a.east?.date||''].sort().at(-1))||a.name.localeCompare(b.name):a.name.localeCompare(b.name));
}
export function csvCell(value){const s=String(value??'');return '"'+s.replaceAll('"','""').replace(/^[=+@-]/,"'$&")+'"';}
export function toCSV(rows,data){return[COLUMNS.map(csvCell).join(','),...rows.map(r=>[r.id,r.name,r.scientific_name,...['west','east'].flatMap(s=>[r[s]?.date,r[s]?.count,r[s]?.checklist,r[s]?String(r[s].notable):'']),data.captured_at,'eBird.org / Cornell Lab of Ornithology / contributors',TERMS].map(csvCell).join(','))].join('\r\n');}
export function parseCSV(text){
  const rows=[];let row=[],value='',quoted=false;
  for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){value+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(value);value='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(value);if(row.some(Boolean))rows.push(row);row=[];value='';}else value+=c;}
  if(quoted)throw Error('Unclosed CSV quote.');row.push(value);if(row.some(Boolean))rows.push(row);
  if(rows.shift()?.join(',')!==COLUMNS.join(','))throw Error('CSV columns must match a Hotspot Ledger export.');
  return rows.map(values=>{if(values.length!==COLUMNS.length)throw Error('CSV row has the wrong number of columns.');return Object.fromEntries(COLUMNS.map((c,i)=>[c,values[i]]));});
}
export function importText(text,filename,base){
  if(text.length>5_000_000)throw Error('Choose a file smaller than 5 MB.');
  if(!filename.toLowerCase().endsWith('.csv'))return validate(JSON.parse(text));
  const raw=parseCSV(text);if(!raw.length)throw Error('CSV has no observations.');const stamps=new Set(raw.map(r=>r.captured_at));if(stamps.size!==1)throw Error('CSV mixes different collection times.');
  const records=raw.map(r=>({id:r.species_code,name:r.common_name,scientific_name:r.scientific_name,...Object.fromEntries(['west','east'].map(side=>[side,r[side+'_date']?{date:r[side+'_date'],count:r[side+'_count']===''?null:Number(r[side+'_count']),checklist:r[side+'_checklist'],notable:r[side+'_notable']==='true',reviewed:false,valid:true}:null]))}));
  return validate({...base,status:'ready',captured_at:raw[0].captured_at,records,warnings:['Locally imported derived CSV. Its provenance has not been verified by this website.']});
}
