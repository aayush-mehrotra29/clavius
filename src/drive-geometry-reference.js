import {readDriveSource} from './drive-sunlight.js';

export const geometryReferenceMarkup=`<details class="geometry-reference"><summary>Compare with JPL Horizons</summary>
  <p data-reference-status></p><section hidden><label>Reference epoch (UTC)<select data-reference-epoch></select></label>
  <div><table><thead><tr><th>Target / source</th><th>Azimuth</th><th>Elevation</th><th>Range (km)</th></tr></thead>
  <tbody></tbody></table></div><p data-reference-offset></p></section></details>`;

export function mountGeometryReference(panel, context, signal){
  const status=panel.querySelector('[data-reference-status]'), content=panel.querySelector('section');
  const epoch=panel.querySelector('select'), body=panel.querySelector('tbody');
  let report, pending, displayedSite;
  function render(){
    const {site,name}=context();
    const rows=report.rows.filter(row=>row.site===site && row.utc===epoch.value);
    body.replaceChildren();
    status.textContent=name+' · nominal site origin, 0.5 m above ground. Both sources give geometric center directions before terrain occlusion.';
    const offsets=[];
    for(const row of rows){
      const target=row.target==='sun'?'Sun':'Earth';
      for(const [source,label] of [['clavius','Clavius'],['horizons','JPL']]){
        const tr=body.insertRow(), head=document.createElement('th');
        head.scope='row';head.textContent=target+' / '+label;tr.append(head);
        const reading=row[source];
        for(const value of [reading.azimuth_deg.toFixed(6)+'°',reading.elevation_deg.toFixed(6)+'°',reading.distance_km.toFixed(3)]){
          tr.insertCell().textContent=value;
        }
      }
      offsets.push(target+' '+(row.errors.direction_deg*3600).toFixed(3)+' arcsec');
    }
    panel.querySelector('[data-reference-offset]').textContent='Angular separation · '+offsets.join(' · ');
  }
  async function open(){
    if(!panel.open || signal.aborted)return;
    try{
      if(!report){
        content.hidden=true;status.textContent='Loading recorded JPL comparisons…';
        pending??=fetch('/data/manifest.json',{signal}).then(async response=>{
          if(!response.ok)throw new Error();
          return readDriveSource((await response.json()).horizons_geometry,signal);
        });
        report=await pending;
      }
      if(signal.aborted || !panel.open)return;
      const {site,start}=context();
      if(displayedSite!==site){
        const dates=report.rows.filter(row=>row.site===site && row.target==='sun').map(row=>row.utc);
        if(!dates.length)throw new Error();
        epoch.replaceChildren(...dates.map(utc=>new Option(utc.replace('T',' ').replace(/(?:\.000)?Z$/,''),utc)));
        epoch.value=dates.find(utc=>Date.parse(utc)===Date.parse(start)) ?? dates[0];
        displayedSite=site;
      }
      render();content.hidden=false;
    }catch{
      pending=null;report=null;displayedSite=null;content.hidden=true;
      if(!signal.aborted)status.textContent='The recorded geometry comparison is unavailable.';
    }
  }
  panel.addEventListener('toggle',open,{signal});
  epoch.addEventListener('change',render,{signal});
  return open;
}
