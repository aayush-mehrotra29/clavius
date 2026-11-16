// FlightSimulator3D and TrajectoryAnalysisView are adapted from Aditya's Clavius.
// https://github.com/prollyAditya/Clavius/tree/3f26903fad64ae961b1464597d83d3a86ef02663/frontend/src/components/views
import React, {Component, lazy, Suspense, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {FlightSimulator3D} from './FlightSimulator3D';
import type {FlightSamples} from './types';
import './viewer.css';

const Analysis = lazy(()=>import('./TrajectoryAnalysisView').then(module=>({default:module.TrajectoryAnalysisView})));

class SceneBoundary extends Component<{children:React.ReactNode}, {failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<p className="orb-message">The 3D view needs WebGL. Open Charts to inspect this flight.</p>:this.props.children;}
}

function FlightViewer({data}: {data: FlightSamples}){
  const [view,setView]=useState('path');
  return <>
    <div className="orb-view-switch" aria-label="Flight visualization">
      <button aria-pressed={view==='path'} onClick={()=>setView('path')}>Flight path</button>
      <button aria-pressed={view==='charts'} onClick={()=>setView('charts')}>Charts</button>
    </div>
    <div hidden={view!=='path'}><SceneBoundary><FlightSimulator3D trajData={data} active={view==='path'}/></SceneBoundary></div>
    {view==='charts' &&
      <Suspense fallback={<p className="orb-message">Loading charts…</p>}><Analysis trajData={data}/></Suspense>}
  </>;
}

export function mountFlightViewer(host:HTMLElement,data:FlightSamples){
  const root=createRoot(host);
  root.render(<FlightViewer data={data}/>);
  return ()=>root.unmount();
}
