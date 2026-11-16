const columns = ['East (m)','North (m)','Front left (N)','Front right (N)','Rear left (N)','Rear right (N)'];
export const terrainComparisonMarkup = `<details class="drive-comparison" hidden>
  <summary>Compare terrain surfaces</summary><p>Travel and mean wheel load from 4 to 20 seconds under the same steering command.</p>
  <div><table><thead><tr><th>Surface</th>${columns.map(c=>'<th>'+c+'</th>').join('')}</tr></thead><tbody></tbody></table></div>
  <p>Clone 001 is one NASA reconstruction of possible elevations on the same 5 m grid. Both runs use the same rigid-contact rover model.</p></details>`;

export function renderTerrainComparison(panel, records, realization) {
  const rows = [['Nominal',records.nominal],['Clone 001',records[realization]]];
  const table = panel.querySelector('tbody');
  table.replaceChildren();
  for (const [name, record] of rows) {
    const row=table.insertRow(), header=document.createElement('th');
    header.scope='row'; header.textContent=name; row.append(header);
    for(const v of record.displacement_en_m)row.insertCell().textContent=v.toFixed(3);
    for(const v of record.mean_load_n)row.insertCell().textContent=v.toFixed(1);
  }
}
