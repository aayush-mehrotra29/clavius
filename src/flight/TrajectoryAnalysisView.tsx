// Adapted from prollyAditya/Clavius, TrajectoryAnalysisView.tsx (3f26903).
import React, { useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine
} from 'recharts';
import type {FlightSamples} from './types';

export function TrajectoryAnalysisView({trajData}: {trajData: FlightSamples}) {
  const [activeChart,setActiveChart]=useState('velocity');
  const chartData=useMemo(()=>trajData.times_seconds.map((time,i)=>{
    const position=trajData.spacecraft_coords_km[i], velocity=trajData.spacecraft_velocities_kms[i];
    const range=Math.hypot(...position), speed=Math.hypot(...velocity);
    const moonRange=Math.hypot(...position.map((v,k)=>v-trajData.moon_coords_km[i][k]));
    const energy=speed*speed/2-trajData.earth_mu_km3_s2/range;
    return {time_h:time/3600, velocity_kms:speed,
      velocity_rel_moon_kms:Math.hypot(...velocity.map((v,k)=>v-trajData.moon_velocities_kms[i][k])),
      earth_dist_km:range, moon_dist_km:moonRange, moon_alt_km:moonRange-trajData.lunar_reference_radius_km,
      energy_earth:energy, c3_energy:2*energy};
  }),[trajData]);
  const approachAltitude=chartData[trajData.approach_index].moon_alt_km;
  return (
    <section className="orb-analysis" aria-label="Trajectory analysis">
      <h2>Trajectory analysis</h2>
      <div className="orb-chart-tabs" aria-label="Flight charts">
        {[['velocity','Velocity profile'],['distances','Earth & Moon distance'],['lunar_altitude','Lunar altitude'],['energy','Orbital energy & C3']].map(([id,label])=>
          <button key={id} aria-pressed={activeChart===id} onClick={()=>setActiveChart(id)}>{label}</button>)}
      </div>
        {/* Chart 1: Velocity Profile */}
        {activeChart === 'velocity' && (
          <div className="orb-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="time_h" type="number" domain={[0, 'dataMax']}
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'Flight Time (hours)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'Velocity (km/s)', angle: -90, position: 'insideLeft', offset: 10, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#070c18', borderColor: '#334155', borderRadius: 4, fontFamily: 'monospace', fontSize: 12 }}
                  formatter={(value,name) => [Number(value).toFixed(3)+' km/s', name]}
                />
                <Legend wrapperStyle={{ fontFamily: 'monospace', fontSize: 11, paddingTop: 10 }} />
                <Line
                  type="linear" isAnimationActive={false}
                  dataKey="velocity_kms"
                  name="Inertial Velocity |v|"
                  stroke="#00f0ff"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="linear" isAnimationActive={false}
                  dataKey="velocity_rel_moon_kms"
                  name="Moon-Relative Speed"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Chart 2: Distances from Earth & Moon */}
        {activeChart === 'distances' && (
          <div className="orb-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="time_h" type="number" domain={[0, 'dataMax']}
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'Flight Time (hours)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'Distance (km)', angle: -90, position: 'insideLeft', offset: 0, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#070c18', borderColor: '#334155', borderRadius: 4, fontFamily: 'monospace', fontSize: 12 }}
                  formatter={(value,name) => [Math.round(Number(value)).toLocaleString()+' km', name]}
                />
                <Legend wrapperStyle={{ fontFamily: 'monospace', fontSize: 11, paddingTop: 10 }} />
                <ReferenceLine y={50000} stroke="#f43f5e" strokeDasharray="3 3" label={{ value: 'Patch · 50,000 km', fill: '#f43f5e', fontSize: 10, fontFamily: 'monospace' }} />
                <Line
                  type="linear" isAnimationActive={false}
                  dataKey="earth_dist_km"
                  name="Range from Earth Center"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="linear" isAnimationActive={false}
                  dataKey="moon_dist_km"
                  name="Range from Moon Center"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Chart 3: Lunar-Relative Altitude */}
        {activeChart === 'lunar_altitude' && (
          <div className="orb-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="time_h" type="number" domain={[0, 'dataMax']}
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'Flight Time (hours)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'Above lunar datum (km)', angle: -90, position: 'insideLeft', offset: 0, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#070c18', borderColor: '#334155', borderRadius: 4, fontFamily: 'monospace', fontSize: 12 }}
                  formatter={(value,name) => [Math.round(Number(value)).toLocaleString()+' km', name]}
                />
                <Legend wrapperStyle={{ fontFamily: 'monospace', fontSize: 11, paddingTop: 10 }} />
                <ReferenceLine y={approachAltitude} stroke="#10b981" strokeDasharray="4 4" label={{ value: `Approach: ${approachAltitude.toFixed(1)} km`, fill: '#10b981', fontSize: 10, fontFamily: 'monospace' }} />
                <Line
                  type="linear" isAnimationActive={false}
                  dataKey="moon_alt_km"
                  name="Lunar-Relative Altitude"
                  stroke="#22d3ee"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Chart 4: Orbital Energy & C3 */}
        {activeChart === 'energy' && (
          <div className="orb-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="time_h" type="number" domain={[0, 'dataMax']}
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'Flight Time (hours)', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fontSize: 11, fontFamily: 'monospace' }}
                  label={{ value: 'C3 Energy (km²/s²)', angle: -90, position: 'insideLeft', offset: 0, fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#070c18', borderColor: '#334155', borderRadius: 4, fontFamily: 'monospace', fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontFamily: 'monospace', fontSize: 11, paddingTop: 10 }} />
                <Line
                  type="linear" isAnimationActive={false}
                  dataKey="c3_energy"
                  name="Characteristic Energy C3 (km²/s²)"
                  stroke="#a855f7"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="linear" isAnimationActive={false}
                  dataKey="energy_earth"
                  name="Earth specific energy (km²/s²)"
                  stroke="#10b981"
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
    </section>
  );
}
