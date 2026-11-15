"""Render scientific comparison figures from hash-verified validation samples.

Optional authoring dependency: Matplotlib. It is not part of the app runtime.
"""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/validation"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source = DIRECTORY / "observed-shadow-comparison.json"
    report = json.loads(source.read_text())
    regional, local = [], []
    for scene in report["scenes"]:
        derivative = next(d for d in report["sample_derivatives"] if d["file"].startswith(scene["scene_id"]))
        path = DIRECTORY / derivative["file"]
        if digest(path) != derivative["sha256"]:
            raise ValueError("Sample derivative differs from recorded comparison")
        with np.load(path) as archive:
            arrays = {k: archive[k] for k in archive.files}
        date = scene["cameras"]["LE"]["midpoint_utc"][:10]
        if scene["grid"]["assessed_samples"]:
            regional.append((scene["scene_id"] + " · " + date + " · regional 80 m", scene, arrays, arrays["clavius_visible_fraction"], np.isfinite(arrays["observed_if"])))
        for case in scene["local_site_comparisons"]:
            site = case["site_id"]
            title = site.replace("-", " ").title() + " · " + date + " · local 5 m + regional 80 m"
            local.append((title, case, arrays, arrays[site + "_visible_fraction"], arrays[site + "_domain_mask"]))
    outputs = []
    colors = ["#c1c8ce", "#e5b74e", "#c53637", "#2879b0", "#71717b"]
    for name, rows in [("observed-shadows-regional.png", regional), ("observed-shadows-sites.png", local)]:
        fig, axes = plt.subplots(len(rows), 3, figsize=(11, 4.2 * len(rows)), squeeze=False, constrained_layout=True)
        fig.set_constrained_layout_pads(hspace=.12, wspace=.04)
        for i, (title, case, arrays, predicted, domain) in enumerate(rows):
            observed = np.where(domain, arrays["observed_if"], np.nan)
            covered = np.isfinite(observed)
            rr, cc = np.where(covered)
            crop = np.s_[rr.min():rr.max() + 1, cc.min():cc.max() + 1]
            x = arrays["x_centers_m"][cc.min():cc.max() + 1]
            y = arrays["y_centers_m"][rr.min():rr.max() + 1]
            extent = [(x[0] - 100) / 1000, (x[-1] + 100) / 1000, (y[-1] - 100) / 1000, (y[0] + 100) / 1000]
            obs_dark, obs_lit = observed <= .001, observed >= .005
            pred_dark, pred_lit = predicted <= .05, predicted >= .95
            classes = np.where(covered, 0., np.nan)
            classes[covered & (~(obs_dark | obs_lit) | ~(pred_dark | pred_lit))] = 1
            classes[covered & obs_dark & pred_lit] = 2
            classes[covered & obs_lit & pred_dark] = 3
            classes[covered & ~np.isfinite(predicted)] = 4
            displayed = [(observed, "Observed NAC I/F\n(display clipped at 0.02)", "gray", 0, .02), (np.where(covered, predicted, np.nan), "Clavius visible\nsolar-disk fraction", "gray", 0, 1), (classes, "Predeclared\nthreshold comparison", ListedColormap(colors), -.5, 4.5)]
            for j, (values, subtitle, cmap, low, high) in enumerate(displayed):
                ax = axes[i, j]
                ax.set_facecolor("#f1f2f3")
                picture = ax.imshow(values[crop], extent=extent, origin="upper", interpolation="nearest", aspect="equal", cmap=cmap, vmin=low, vmax=high)
                ax.set_title(subtitle, fontsize=9)
                ax.set_xlabel("Polar X (km)", fontsize=8)
                ax.set_ylabel("Polar Y (km)", fontsize=8)
                ax.tick_params(labelsize=8)
                if (extent[1] - extent[0]) / (extent[3] - extent[2]) < .3:
                    ax.set_xticks([round((extent[0] + extent[1]) / 2, 1)])
                if j < 2:
                    fig.colorbar(picture, ax=ax, orientation="horizontal", fraction=.045, pad=.1, shrink=.7)
            primary = case["observed_proxy_comparisons"][0]
            sun = 100 * primary["false_sunlit_fraction"]
            shadow = 100 * primary["false_shadow_fraction"]
            axes[i, 1].set_title(title + "\n\nClavius visible\nsolar-disk fraction", fontsize=9, weight="bold", pad=8)
            axes[i, 2].set_xlabel(f"Polar X (km)\n\nFalse sunlit: {sun:.2f}% of dark proxy\nFalse shadow: {shadow:.2f}% of lit proxy", fontsize=8)
        fig.legend(handles=[Patch(color=c, label=s) for c, s in zip(colors, ["Confident classes agree", "Ambiguous / partial", "False sunlit", "False shadow", "Prediction unknown"])], loc="outside lower center", ncol=5, fontsize=8, frameon=False)
        fig.suptitle("LROC observed-shadow screening · 200 m lattice · no fitted registration\nReflectance proxies: dark ≤ 0.001 I/F; lit ≥ 0.005 I/F. One observed epoch at the local sites; no operational error bound.", fontsize=10)
        output = DIRECTORY / name
        fig.savefig(output, dpi=160, facecolor="white")
        plt.close(fig)
        outputs.append({"file": name, "sha256": digest(output), "bytes": output.stat().st_size})
    provenance = {"comparison_sha256": digest(source), "renderer_sha256": digest(Path(__file__)), "matplotlib": matplotlib.__version__, "figures": outputs}
    (DIRECTORY / "observed-shadow-figures.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
