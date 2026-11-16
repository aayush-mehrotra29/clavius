"""Score a freshly reproduced NAC comparison against two explicit baselines.

Use the existing three I/F threshold pairs and every archived scope. On finite,
confident cells compare center-above-horizon decisions with a flat horizon.
Separately compare any visible disk with positive published rendered irradiance.
Keep separate masks for these two comparisons. Return null for missing classes.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def classification(truth, prediction, valid):
    dark = valid & ~truth
    lit = valid & truth
    false_sun = int(np.sum(prediction & dark))
    false_shadow = int(np.sum(~prediction & lit))
    dark_count, lit_count = int(dark.sum()), int(lit.sum())
    balanced = None
    if dark_count and lit_count:
        balanced = 1 - .5*(false_sun/dark_count + false_shadow/lit_count)
    return dict(dark_count=dark_count,lit_count=lit_count,false_sunlit=false_sun,
                false_shadow=false_shadow,balanced_accuracy=balanced)


def compare(report_path):
    report = json.loads(report_path.read_text())
    protocol = report['protocol']
    proxy = protocol['reflectance_proxy']
    records = []
    for artifact in report['sample_derivatives']:
        path=report_path.parent/artifact['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact['sha256']:
            raise ValueError('Sample digest mismatch: '+path.name)
        with np.load(path) as arr:
            obs=arr['observed_if']
            flux=arr['nasa_model_w_m2']
            for scope in ['regional',*protocol['sites']]:
                prefix='' if scope=='regional' else scope+'_'
                height_key=prefix+'solar_elevation_deg'
                if height_key not in arr:
                    continue
                fraction=arr[prefix+'visible_fraction' if prefix else 'clavius_visible_fraction']
                solar=arr[height_key]
                common=np.isfinite(fraction)&np.isfinite(solar)&np.isfinite(obs)
                for thresholds in [proxy['primary'],*proxy['sensitivity']]:
                    truth=obs>=thresholds['lit_at_least']
                    confident=common & (truth | (obs<=thresholds['dark_at_most']))
                    positive_flux=confident & np.isfinite(flux) & (flux>=0)
                    records.append(dict(scene=path.name.split('-')[0],scope=scope,thresholds=thresholds,
                        flat_horizon=dict(clavius=classification(truth,fraction>=.5,confident),
                                          baseline=classification(truth,solar>=0,confident)),
                        published_rendering=dict(clavius=classification(truth,fraction>0,positive_flux),
                                                 baseline=classification(truth,flux>0,positive_flux))))
    return dict(source=report['source_manifest_section']['source_page'],
                observation="NAC reflectance I/F thresholds from the source protocol; ambiguous cells excluded.",
                measure="Mean of lit recall and dark recall on the joint valid cells of each pair.",
                flat_horizon="Clavius disk fraction >= 0.5 versus geometric solar elevation >= 0 degrees.",
                published_rendering="Clavius disk fraction > 0 versus PGDA rendered irradiance > 0 W/m².",
                protocol_sha256=report['protocol_sha256'],samples=report['sample_derivatives'],rows=records)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    print(json.dumps(compare(args.report),indent=2,allow_nan=False))
