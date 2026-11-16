const names = ['Front left','Front right','Rear left','Rear right'];
export const wheelPanelMarkup = `<details class="drive-wheels" hidden><summary>Wheel slip &amp; ground load</summary>
  <p data-wheel-time></p><div><table><thead><tr><th>Wheel</th><th>Slip</th><th>Load (N)</th><th>Loaded</th>
  <th>Rim (m/s)</th><th>Travel (m/s)</th><th>Lateral (m/s)</th></tr></thead><tbody>
  ${names.map(name=>`<tr><th scope="row">${name}</th>${'<td>—</td>'.repeat(6)}</tr>`).join('')}</tbody></table></div>
  <p>Slip compares forward travel with wheel rotation on rigid ground. Load is the average force perpendicular to the terrain. Speeds use only steps with more than 1 N of load. Slip requires a rim speed above 0.02 m/s.</p></details>`;

export function wheelSample(values, time, minRimSpeed) {
  const frame = Math.max(0,Math.min(400,Math.floor(time*20+1e-10)));
  const rows = names.map((_,i)=>{
    const offset = (4*frame+i)*5;
    const [load, fraction, rim, along, lateral] = values.subarray(offset,offset+5);
    const slip = fraction>0 && Math.abs(rim)>minRimSpeed ? 1-along/rim : NaN;
    return {load, fraction, rim, along, lateral, slip};
  });
  return {frame,rows};
}

function format(value, digits, suffix='') {
  return Number.isFinite(value) ? value.toFixed(digits)+suffix : '—';
}

export function renderWheelSample(panel, values, time, minRimSpeed) {
  const {frame,rows} = wheelSample(values,time,minRimSpeed);
  panel.querySelector('[data-wheel-time]').textContent = frame
    ? 'Average over '+((frame-1)/20).toFixed(2)+'–'+(frame/20).toFixed(2)+' s'
    : 'The first measurement is available at 0.05 s.';
  panel.querySelectorAll('tbody tr').forEach((row,i)=>{
    const {load,fraction,rim,along,lateral,slip} = rows[i];
    const display = [format(slip*100,1,'%'),format(load,1),format(fraction*100,0,'%'),
      format(rim,3),format(along,3),format(lateral,3)];
    row.querySelectorAll('td').forEach((cell,j)=>{ if(cell.textContent!==display[j])cell.textContent=display[j]; });
  });
}
