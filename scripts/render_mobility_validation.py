"""Render a standalone scientific comparison from recorded native results."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def render(source, output):
    report = json.loads(source.read_text())
    rows = report['points']
    x = np.asarray([row['requested_slip_fraction'] for row in rows])
    observed = np.asarray([row['published_traction_slope_deg'] for row in rows])
    modeled = np.asarray([row['mean_traction_slope_deg'] for row in rows])
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), gridspec_kw={'height_ratios': [2.3, 1]}, sharex=True, layout='constrained')
    axes[0].scatter(x, observed, marker='x', color='#17212c', s=40, label='Published NASA Glenn TREC points')
    order = np.argsort(x)
    axes[0].plot(x[order], modeled[order], color='#2166ac', marker='o', markersize=3, lw=1.5, label='MuJoCo rigid plane, declared friction 0.7')
    refinements = report['refinements']
    axes[0].scatter([rows[row['source_index']]['requested_slip_fraction'] for row in refinements], [row['mean_traction_slope_deg'] for row in refinements], marker='+', s=100, color='#b35806', label='Half-step repeats at three fixed slips')
    axes[0].set_ylabel('Traction slope (degrees)')
    axes[0].legend(loc='lower right', fontsize=9, framealpha=.95)
    axes[0].set_title('NASA Glenn wheel comparison - Earth gravity', loc='left', fontsize=14, pad=14)
    axes[1].axhline(0, lw=1, color='#75808b')
    axes[1].scatter(x, modeled-observed, color='#2166ac', s=22)
    axes[1].set_ylabel('Model - published\n(degrees)')
    axes[1].set_xlabel('Driving slip fraction, 1 - v / (omega R)')
    axes[1].set_xlim(-.035, .84)
    for axis in axes:
        axis.grid(True, color='#d9dfe5', lw=.6)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right']].set_visible(False)
    summary = report['summary']
    fig.suptitle(f"RMS discrepancy {summary['traction_rmse_deg']:.2f} degrees | {len(rows)} published points | No lunar calibration", fontsize=10, color='#4f5963')
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    render(args.source, args.output)
