import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile,Workbook} from '@oai/artifact-tool';
const root='/Users/ezagoc/Documents/GitHub/amlo_pressconf';
const out=`${root}/outputs/flagged-outlets-20261026`;
const back=`${root}/recovery/flagged-outlets-20261026`;
const mode=process.argv[2]??'preview';
const patches=JSON.parse(await fs.readFile(`${out}/workbook_patches.json`,'utf8'));
async function render(wb,sheetName,range,name){
 const blob=await wb.render({sheetName,range,scale:1});
 await fs.writeFile(`${out}/${name}.${mode}.png`,new Uint8Array(await blob.arrayBuffer()));
}
for(const [file,p] of Object.entries(patches)){
 const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(`${back}/${file}`));
 if(p.sheet){
  const s=wb.worksheets.getItem(p.sheet);
  if(mode==='edit'){
   for(const [r,c,v] of p.edits){
    s.getCell(r-1,c-1).values=[[v]];
    if(file==='newspaper_metadata.xlsx'&&c===30)s.getRangeByIndexes(r-1,0,1,p.original_cols).format.rowHeight=Math.max(80,Math.ceil(String(v).length/55)*15+12);
   }
   for(let i=0;i<p.append.length;i++){
    const range=s.getRangeByIndexes(p.original_rows+i,0,1,p.original_cols);
    range.copyFrom(s.getRangeByIndexes(p.original_rows-1,0,1,p.original_cols),'all');
    range.values=[p.append[i]];
    range.format.rowHeight=file==='newspaper_metadata.xlsx'?Math.max(80,Math.ceil(String(p.append[i][29]??'').length/55)*15+12):80;
    range.format.wrapText=true;
   }
  }
  const first=file.startsWith('mexican')?'E':'A',last=file.startsWith('mexican')?'G':'C';
  await render(wb,p.sheet,`${first}${p.original_rows-2}:${last}${p.original_rows+(mode==='edit'?3:0)}`,file);
  if(mode==='edit')await render(wb,p.sheet,`${first}${p.original_rows+p.append.length}:${last}${p.original_rows+p.append.length}`,`${file}-last-row`);
  if(mode==='edit'&&file==='newspaper_metadata.xlsx')await render(wb,p.sheet,`AC${p.original_rows+1}:AD${p.original_rows+2}`,'metadata-notes');
 }else{
  if(mode==='edit'){
   for(const [name,changes] of Object.entries(p.sheets)){
    const s=wb.worksheets.getItem(name);
    if(name==='Outlet review'){
     for(let n=201;n<=204;n++){
      const range=s.getRange(`A${n}:R${n}`);range.copyFrom(s.getRange('A200:R200'),'all');range.values=[Array(18).fill(null)];
     }
    }
    for(const [r,c,v] of changes.edits)s.getCell(r-1,c-1).values=[[v]];
   }
   const s=wb.worksheets.getItem('Attendance check');
   for(const n of [8,21]){
    s.getRange(`I${n}:L${n}`).copyFrom(s.getRange(`A${n}:D${n}`),'all');
    s.getRange(`I${n}:L${n}`).values=[['Conference ID','Review status','Missing / sparse roster dates','Review decision and remaining issues']];
   }
   s.getRange('I:I').format.columnWidth=29;s.getRange('J:J').format.columnWidth=34;
   s.getRange('K:K').format.columnWidth=27;s.getRange('L:L').format.columnWidth=86;
   s.getRange('I8:L104').format.wrapText=true;
   s.getRange('I8:L104').format.verticalAlignment='top';
   for(const [r,c,v] of p.sheets['Attendance check'].edits){
    if(c===12){
     const height=Math.max(76,Math.ceil(String(v).length/78)*15+16);
     s.getRange(`A${r}:L${r}`).format.rowHeight=height;
    }
   }
   for(const n of [3,4,5,6,16,19])s.getRange(`A${n}:H${n}`).format.rowHeight=32;
   const r=wb.worksheets.getItem('Outlet review');
   r.getRange('Q8:R8').copyFrom(r.getRange('O8:P8'),'all');
   r.getRange('Q8:R8').values=[['Conference ID','Missing / sparse roster dates']];
   r.getRange('Q:Q').format.columnWidth=30;r.getRange('R:R').format.columnWidth=28;
   r.getRange('Q8:R204').format.wrapText=true;
   r.getRange('J:J').format.columnWidth=86;
   r.getRange('J9:J204').format.wrapText=true;
   for(const [row,col,v] of p.sheets['Outlet review'].edits){
    if(col===10){r.getRange(`A${row}:R${row}`).format.rowHeight=Math.max(76,Math.ceil(String(v).length/78)*15+16);r.getRange(`F${row}`).format.wrapText=true;}
   }
   r.getRange('A5:P5').format.rowHeight=32;
   // These review tables have no formulas or saved filter criteria. Recreate
   // the same named tables over their expanded ranges using their own style.
   for(const [sheet,name,range] of [[s,'FocusAttendance','A8:L13'],[s,'AttendanceGaps','A21:L104'],[r,'OutletReview','A8:R204']]){
    const old=sheet.tables.getItem(name),style=old.style;
    old.delete();const expanded=sheet.tables.add(range,true,name);expanded.style=style;
   }
  }
  await render(wb,'Attendance check','A18:F25','attendance');
  if(mode==='edit')await render(wb,'Attendance check','I38:L43','decisions');
  if(mode==='edit')await render(wb,'Attendance check','I33:L33','lamont-decision');
  await render(wb,'Outlet review','A68:F73','roster');
 }
 if(mode==='edit'){
  wb.recalculate();
  const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:5},summary:'formula errors'});
  await fs.writeFile(`${out}/${file}.errors.json`,errors.ndjson);
  await(await SpreadsheetFile.exportXlsx(wb)).save(`${out}/staged/${file}`);
 }
 console.log(mode,file);
}
if(mode==='edit'){
 const data=JSON.parse(await fs.readFile(`${out}/staged/bridge.json`,'utf8'));
 const wb=Workbook.create(),s=wb.worksheets.add('Sheet1');
 s.getRange(`A1:B${data.length+1}`).values=[['outlet_final','total_attendance'],...data.map(r=>[r.outlet_final,r.total_attendance])];
 s.getRange('A:B').format.columnWidth=40;s.getRange('A1:B1').format.font={bold:true};
 wb.recalculate();await render(wb,'Sheet1','A1:B8','bridge');
 await(await SpreadsheetFile.exportXlsx(wb)).save(`${out}/staged/bridge_outlets.xlsx`);
 console.log('edit bridge_outlets.xlsx');
}
