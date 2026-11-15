"""Standalone scientific figure preserving the frozen training/holdout split."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def render(directory,output):
    report=json.loads((directory/'campaign.json').read_text())
    source=json.loads((directory/'published-reference.json').read_text())
    points=next(series['points'] for series in source['series'] if series['id']=='trec-grc3-vv')
    best=next(candidate for candidate in report['candidates'] if candidate['index']==report['frozen_selection']['selected_index'])
    training=best['training'];holdout=report['holdout']
    baseline=json.loads((Path(__file__).resolve().parents[1]/'public/data/mobility-validation.json').read_text())
    rigid={row['source_index']:row for row in baseline['points']}
    fig,axes=plt.subplots(2,1,figsize=(10,8),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[2,1]})
    x=np.array([point['slip_fraction'] for point in points]);y=np.array([point['traction_slope_deg'] for point in points])
    order=np.argsort(x)
    axes[0].scatter(x,y,marker='x',color='#17212c',s=42,label='Published NASA Glenn TREC points',zorder=4)
    axes[0].plot(x[order],[rigid[int(i)]['mean_traction_slope_deg'] for i in order],color='#8b949e',lw=1.2,ls='--',label='MuJoCo rigid plane, friction 0.7')
    chosen=sorted(training+holdout,key=lambda row:points[row['source_index']]['slip_fraction'])
    axes[0].plot([points[row['source_index']]['slip_fraction'] for row in chosen],[row['mean_traction_slope_deg'] for row in chosen],color='#2166ac',lw=1.3,label='Frozen Chrono CPU SCM candidate')
    for rows,marker,filled,label in [(training,'o',False,'SCM training points (10)'),(holdout,'s',True,'SCM held-out points (8)')]:
        axes[0].scatter([points[row['source_index']]['slip_fraction'] for row in rows],[row['mean_traction_slope_deg'] for row in rows],marker=marker,s=32,edgecolors='#2166ac',facecolors='#2166ac' if filled else 'white',label=label,zorder=3)
    hindex=[row['source_index'] for row in holdout]
    hx=[points[index]['slip_fraction'] for index in hindex]
    scm_error=np.array([row['mean_traction_slope_deg']-row['published_traction_slope_deg'] for row in holdout])
    rigid_error=np.array([rigid[index]['mean_traction_slope_deg']-points[index]['traction_slope_deg'] for index in hindex])
    axes[1].axhline(0,color='#75808b',lw=1)
    axes[1].scatter(hx,rigid_error,marker='^',color='#8b949e',s=34,label='Rigid baseline on the same 8 points')
    axes[1].scatter(hx,scm_error,marker='s',color='#2166ac',s=30,label='SCM held-out discrepancy')
    axes[0].set_ylabel('Traction slope (degrees)')
    axes[1].set_ylabel('Model - published\n(degrees)')
    axes[1].set_xlabel('Driving slip fraction, 1 - v / (omega R)')
    axes[1].set_xlim(-.035,.84)
    for axis in axes:
        axis.grid(True,color='#d9dfe5',lw=.6);axis.set_axisbelow(True)
        axis.spines[['top','right']].set_visible(False)
        axis.legend(loc='best',fontsize=8.5,framealpha=.95)
    phi=best['parameters']['friction_angle_deg'];janosi=best['parameters']['janosi_m']
    axes[0].set_title('NASA Glenn wheel comparison - Earth gravity',loc='left',fontsize=14,pad=14)
    numerical='passed at three tested slips' if report['numerical_targets_met'] else 'targets not met'
    fig.suptitle(f"8-point held-out RMS: SCM {np.sqrt(np.mean(scm_error**2)):.2f} deg; rigid {np.sqrt(np.mean(rigid_error**2)):.2f} deg\nFrozen friction angle {phi} deg; shear length {janosi} m. No lunar calibration.\nBase SCM grid 10 mm, step 1 ms. Time/grid checks: {numerical}.",fontsize=10,color='#4f5963')
    output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,dpi=180,facecolor='white');plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();render(args.directory,args.output)
