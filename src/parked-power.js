import {Matrix4, Quaternion, Vector3} from 'three';
import {arrayPower} from './viper-array.js';

// Heading increases clockwise from north in the fixed site ENU basis.
export function parkedAttitude(headingDeg, dzDe, dzDn) {
  const angle = headingDeg * Math.PI / 180;
  const east = Math.sin(angle), north = Math.cos(angle);
  const forward = new Vector3(east, north, east*dzDe+north*dzDn).normalize();
  const up = new Vector3(-dzDe, -dzDn, 1).normalize();
  const left = new Vector3().crossVectors(up, forward).normalize();
  return new Quaternion().setFromRotationMatrix(new Matrix4().makeBasis(forward,left,up));
}

// Array and load share the bus. Integrate each surplus or deficit segment
// separately so reaching full/empty before a sign reversal cannot erase losses.
export function batteryBudget(power, {capacity, initialPct, load, chargeEfficiency, dischargeEfficiency}) {
  if (!(capacity>0 && initialPct>=0 && initialPct<=100 && load>=0 &&
        chargeEfficiency>0 && chargeEfficiency<=1 && dischargeEfficiency>0 && dischargeEfficiency<=1)) {
    throw new Error('Invalid battery scenario inputs.');
  }
  let stored = capacity*initialPct/100;
  let minimum=stored, generated=0, curtailed=0, unmet=0, losses=0, firstUnmet=null;
  const timeline = [[0,stored,power[0][1]]];
  function segment(t,dt,w0,w1) {
    const netWh=(w0+w1)*dt/7200;
    if (netWh>=0) {
      const accepted=Math.min(netWh,(capacity-stored)/chargeEfficiency);
      stored = accepted<netWh ? capacity : Math.min(capacity,stored+accepted*chargeEfficiency);
      curtailed+=netWh-accepted;
      losses+=accepted*(1-chargeEfficiency);
    } else {
      const deliverable=stored*dischargeEfficiency;
      const served=Math.min(-netWh,deliverable);
      if (-netWh>deliverable && firstUnmet===null) {
        // Solve the integral of a linear, nonnegative demand for the empty time.
        const required=deliverable*3600;
        const rate=-w0, acceleration=(w0-w1)/dt;
        const endRate=Math.sqrt(Math.max(0,rate*rate+2*acceleration*required));
        firstUnmet=t+(required===0?0:2*required/(rate+endRate));
      }
      stored = served===deliverable ? 0 : stored-served/dischargeEfficiency;
      unmet+=-netWh-served;
      losses+=served*(1/dischargeEfficiency-1);
    }
    minimum=Math.min(minimum,stored);
  }
  for(let i=1;i<power.length;i++){
    const [t0,p0]=power[i-1], [t1,p1]=power[i], dt=t1-t0;
    if (!(dt>0 && p0>=0 && p1>=0 && Number.isFinite(p0+p1))) throw new Error('Invalid solar time series.');
    generated+=(p0+p1)*dt/7200;
    const n0=p0-load,n1=p1-load;
    if(n0*n1<0){
      const cross=dt*n0/(n0-n1);
      segment(t0,cross,n0,0);
      timeline.push([t0+cross,stored,load]);
      segment(t0+cross,dt-cross,0,n1);
    }else segment(t0,dt,n0,n1);
    timeline.push([t1,stored,p1]);
  }
  return {end:stored,minimum,generated,curtailed,unmet,losses,firstUnmet,timeline,
    demand:load*(power.at(-1)[0]-power[0][0])/3600};
}

export function parkedBudget(environment, hardware, scenario) {
  const rotation=parkedAttitude(scenario.heading,environment.dz_de,environment.dz_dn);
  const duration=scenario.hours*3600;
  const power=[];
  for(const [time,e,n,u,distance,fraction] of environment.rows){
    if(time>duration)break;
    const sample={sun_site_enu:[e,n,u],sun_distance_km:distance,disk_fraction:fraction};
    power.push([time,arrayPower(hardware,sample,rotation).total]);
  }
  if(power[0]?.[0]!==0 || power.at(-1)?.[0]!==duration)throw new Error('Incomplete sunlight coverage.');
  return batteryBudget(power,scenario);
}
