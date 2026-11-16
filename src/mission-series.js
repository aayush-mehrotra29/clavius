// Saved traverse energy uses the end-of-interval power sample and elapsed SI seconds.
export function driveTotals(rows) {
  let previous=0, solarWh=0, contactSeconds=0, powerComplete=true, contactComplete=true;
  for(const row of rows){
    const dt=row.t_s-previous;
    if(!Number.isFinite(dt)||dt<0)return {solarWh:null, contactSeconds:null};
    if(Number.isFinite(row.solar_w))solarWh+=row.solar_w*dt/3600;
    else powerComplete=false;
    if(typeof row.earth_visible==='boolean')contactSeconds+=row.earth_visible?dt:0;
    else contactComplete=false;
    previous=row.t_s;
  }
  return {solarWh:rows.length&&powerComplete?solarWh:null, contactSeconds:rows.length&&contactComplete?contactSeconds:null};
}

export function selectedScenario(flight,plan) {
  const s=flight.planning_selection;
  if(!s || plan?.kind!=='landing_plan' || plan.id!==s.plan_id)return null;
  const row=plan.candidates.find(r=>r.key===s.candidate_key);
  const sameTime=Date.parse(row?.landing_utc)===Date.parse(flight.landing.utc);
  if(!row || row.site_id!==flight.landing.site_id || !sameTime ||
     (s.solved_flight_sha256 && row.flight_sha256!==s.solved_flight_sha256))return null;
  return row;
}

// Keep short power spikes and stops visible when several trace samples share a screen pixel.
export function envelope(rows,key,buckets=220) {
  const selected=[];
  for(let start=0;start<rows.length;){
    const end=Math.min(rows.length,start+Math.ceil(rows.length/buckets));
    let low=null,high=null;
    for(let i=start;i<end;i++){
      if(!Number.isFinite(rows[i][key]))continue;
      if(low===null||rows[i][key]<rows[low][key])low=i;
      if(high===null||rows[i][key]>rows[high][key])high=i;
    }
    if(low!==null)selected.push(Math.min(low,high),Math.max(low,high));
    start=end;
  }
  if(Number.isFinite(rows[0]?.[key]))selected.unshift(0);
  if(Number.isFinite(rows.at(-1)?.[key]))selected.push(rows.length-1);
  return [...new Set(selected)].map(i=>rows[i]);
}

export function nextEvent(windows,t,duration,on,off) {
  for(const [a,b] of windows){
    if(t<a)return `${on} in ~${Math.ceil((a-t)/60)} min`;
    if(t<b && b<duration)return `${off} in ~${Math.ceil((b-t)/60)} min`;
  }
  return 'No further crossing in this window';
}
