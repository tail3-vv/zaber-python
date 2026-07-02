from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pickle

from scipy.signal import find_peaks, savgol_filter
from scipy.interpolate import UnivariateSpline


class PSCurveBenchmark:
    """
    Protocol implementation:
      1. Generate n_curves synthetic P.S. curves with known peaks,
         varying amplitude and width to model sensor variance.
      2. Add Gaussian noise once per curve (one noisy copy per curve).
      3. Apply four smoothing techniques n_reps times each to the
         same noisy curve to measure reproducibility.
      4. Compute phase shift, peak attenuation, and reproducibility.
      5. Expose best_smoother() for use by EMAnalysis.
    """

    SMOOTHER_NAMES = ['MA_100', 'MA_200', 'SavGol', 'CubicSpline']

    def __init__(
        self,
        path: str,
        n_curves: int = 10,
        n_reps: int = 3,
        noise_fraction: float = 0.15,
        random_seed: int = 42,
    ):
        """
        Parameters
        ----------
        path             Output directory for all benchmark figures and tables.
        n_curves         Number of synthetic curves to generate (default 10).
        n_reps           Times each smoother is applied to the same noisy curve.
                         For a deterministic filter, all n_reps outputs are
                         identical — this confirms reproducibility std == 0.
        noise_fraction   Noise std as a fraction of each curve's peak amplitude.
        random_seed      Seed for reproducible noise generation.
        """
        self.path = Path(path)
        self.n_curves = n_curves
        self.n_reps = n_reps
        self.noise_fraction = noise_fraction
        self.rng = np.random.default_rng(random_seed)

        # x-axis: 0–45 kPa at 1 000 points — matches real EMAnalysis data density
        self.x_kpa = np.linspace(0, 45, 1000)

        # Internal storage
        self.curves: list[dict] = []
        self.noisy_curves: list[np.ndarray] = []
        # smoothed[name][curve_idx][rep_idx] -> 1-D smoothed array
        self.smoothed: dict[str, list[list[np.ndarray]]] = {}
        self.metrics: dict[str, dict] = {}

        # Run the full benchmark pipeline
        self._generate_curves()
        self._add_noise()
        self._apply_smoothers()
        self._compute_metrics()
        self._plot_per_curve()
        self._plot_summary()
        self._save_results()

    # ── 1. Synthetic curve generation ────────────────────────────────────────

    def _gaussian_ps_curve(
        self, amplitude: float, peak_kpa: float, width: float
    ) -> np.ndarray:
        """
        Gaussian bell curve centred at peak_kpa.
        Mimics the shape of a real P.S. curve peak.
        """
        return amplitude * np.exp(
            -0.5 * ((self.x_kpa - peak_kpa) / width) ** 2
        )

    def _generate_curves(self):
        """
        Generate n_curves synthetic P.S. curves.
        Amplitude, peak location, and width vary linearly across curves
        to represent the sensor variance described in the protocol.
        """
        for i in range(self.n_curves):
            amplitude = 0.40 + i * 0.08   # 0.40 → 1.12 pF/kPa
            peak_kpa  = 14.0 + i * 1.80   # 14.0 → 30.2 kPa
            width     = 3.50 + i * 0.25   # 3.50 → 5.75 kPa

            self.curves.append({
                'y':         self._gaussian_ps_curve(amplitude, peak_kpa, width),
                'amplitude': amplitude,   # true peak value (Gaussian max == amplitude)
                'peak_kpa':  peak_kpa,    # true peak location — ground truth
                'width':     width,
            })

    # ── 2. Noise ──────────────────────────────────────────────────────────────

    def _add_noise(self):
        """
        Add Gaussian noise once per curve.
        The same noisy array is reused for all smoothing reps (per protocol).
        """
        for c in self.curves:
            sigma = self.noise_fraction * c['amplitude']
            self.noisy_curves.append(
                c['y'] + self.rng.normal(0.0, sigma, len(self.x_kpa))
            )

    # ── 3. Smoothers ─────────────────────────────────────────────────────────

    @staticmethod
    def _apply_ma(y: np.ndarray, window: int) -> np.ndarray:
        """
        Causal rolling mean — intentionally matches the original
        EMAnalysis implementation so benchmark results transfer directly.
        Note: causal MA introduces a phase lag proportional to window/2.
        """
        return pd.Series(y).rolling(window, min_periods=1).mean().to_numpy()

    @staticmethod
    def _apply_savgol(y: np.ndarray) -> np.ndarray:
        """
        Savitzky-Golay filter (zero phase shift by design).
        window_length=101 and polyorder=2 chosen to match typical PS curve density.
        """
        return savgol_filter(y, window_length=101, polyorder=2)

    @staticmethod
    def _apply_cubic_spline(y: np.ndarray) -> np.ndarray:
        """
        Smoothing cubic spline via UnivariateSpline.
        The smoothing factor s scales with signal length and noise variance —
        adjust the multiplier (default 5) based on empirical results.
        """
        x = np.arange(len(y))
        noise_std = np.std(np.diff(y))
        s = len(y) * (noise_std ** 2) * 5
        try:
            spl = UnivariateSpline(x, y, s=s, k=3)
            return spl(x)
        except Exception as e:
            print(f"CubicSpline fallback to MA_100: {e}")
            return pd.Series(y).rolling(100, min_periods=1).mean().to_numpy()

    def _apply_smoothers(self):
        """
        For each smoother apply it n_reps times to every noisy curve.
        All reps receive the exact same noisy array — output variance
        across reps directly measures filter reproducibility.
        """
        dispatch = {
            'MA_100':      lambda y: self._apply_ma(y, 100),
            'MA_200':      lambda y: self._apply_ma(y, 200),
            'SavGol':      self._apply_savgol,
            'CubicSpline': self._apply_cubic_spline,
        }

        for name, fn in dispatch.items():
            self.smoothed[name] = [
                [fn(noisy) for _ in range(self.n_reps)]
                for noisy in self.noisy_curves
            ]

    # ── 4. Metrics ────────────────────────────────────────────────────────────

    def _find_peak(self, y: np.ndarray) -> tuple[float, float]:
        """
        Return (peak_kpa, peak_value) for the tallest prominent peak.
        Returns (nan, nan) when no peak is detected.
        """
        threshold = 0.01 * max(float(np.nanmax(np.abs(y))), 1e-9)
        peaks, _ = find_peaks(y, prominence=threshold)
        if len(peaks) == 0:
            return np.nan, np.nan
        best = peaks[np.argmax(y[peaks])]
        return float(self.x_kpa[best]), float(y[best])

    def _compute_metrics(self):
        """
        Per smoother, compute across all curves and reps:

        phase_shift      (n_curves × n_reps)
            detected_kpa − true_kpa
            Positive = peak shifted right (higher kPa than true location).
            Ideal = 0.

        attenuation      (n_curves × n_reps)
            100 × (true_peak_val − detected_peak_val) / true_peak_val  [%]
            Ideal = 0 (no flattening).

        reproducibility  (n_curves,)
            std of phase_shift across n_reps for each curve.
            Ideal = 0 (identical output every time).
        """
        for name in self.SMOOTHER_NAMES:
            phase_shifts = np.full((self.n_curves, self.n_reps), np.nan)
            attenuations = np.full((self.n_curves, self.n_reps), np.nan)

            for ci, c in enumerate(self.curves):
                true_kpa = c['peak_kpa']
                true_val = c['amplitude']

                for ri, rep_arr in enumerate(self.smoothed[name][ci]):
                    det_kpa, det_val = self._find_peak(rep_arr)
                    phase_shifts[ci, ri] = det_kpa - true_kpa
                    if not np.isnan(det_val) and true_val > 0:
                        attenuations[ci, ri] = (
                            100.0 * (true_val - det_val) / true_val
                        )

            reproducibility = np.nanstd(phase_shifts, axis=1, ddof=0)

            self.metrics[name] = {
                'phase_shift':          phase_shifts,
                'attenuation':          attenuations,
                'reproducibility':      reproducibility,
                'mean_phase_shift':     float(np.nanmean(phase_shifts)),
                'mean_attenuation':     float(np.nanmean(attenuations)),
                'mean_reproducibility': float(np.nanmean(reproducibility)),
            }

    # ── 5. Plots ──────────────────────────────────────────────────────────────

    def _plot_per_curve(self):
        """
        One figure per synthetic curve — 2×2 grid, one panel per smoother.
        Each panel shows the noisy input, the true curve, all n_reps smoothed
        outputs with their detected peaks, and the true peak as a reference line.
        Phase shift, attenuation, and reproducibility are printed in each title.
        """
        rep_colors = ['tab:blue', 'tab:orange', 'tab:green']
        self.path.mkdir(parents=True, exist_ok=True)

        for ci, c in enumerate(self.curves):
            fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
            fig.suptitle(
                f'Synthetic Curve {ci + 1}  |  '
                f'True peak: {c["peak_kpa"]:.1f} kPa  |  '
                f'Amplitude: {c["amplitude"]:.2f} pF/kPa  |  '
                f'Width: {c["width"]:.2f} kPa',
                fontsize=12, fontweight='bold',
            )

            for ax, name in zip(axes.flatten(), self.SMOOTHER_NAMES):
                # Background: noisy signal and true curve
                ax.plot(self.x_kpa, self.noisy_curves[ci],
                        color='lightgray', linewidth=1, label='Noisy input', zorder=1)
                ax.plot(self.x_kpa, c['y'],
                        'k--', linewidth=1.8, label='True curve', zorder=2)
                ax.axvline(c['peak_kpa'], color='black', linestyle=':',
                           linewidth=1.2, label=f'True peak ({c["peak_kpa"]:.1f} kPa)')

                # Overlay all reps for this smoother
                for ri, rep_arr in enumerate(self.smoothed[name][ci]):
                    det_kpa, _ = self._find_peak(rep_arr)
                    ax.plot(self.x_kpa, rep_arr,
                            color=rep_colors[ri], linewidth=1.5,
                            alpha=0.85, label=f'Rep {ri + 1}', zorder=3)
                    if not np.isnan(det_kpa):
                        ax.axvline(det_kpa, color=rep_colors[ri],
                                   linestyle='--', linewidth=1.0, alpha=0.55)

                m = self.metrics[name]
                mean_ps = np.nanmean(m['phase_shift'][ci])
                mean_at = np.nanmean(m['attenuation'][ci])
                repro   = m['reproducibility'][ci]
                ax.set_title(
                    f'{name}  |  Phase shift: {mean_ps:+.2f} kPa  |  '
                    f'Attenuation: {mean_at:.1f}%  |  Repro std: {repro:.4f}',
                    fontsize=9,
                )
                ax.set_xlabel('Pressure (kPa)', fontsize=10)
                ax.set_ylabel('P.S. (pF/kPa)', fontsize=10)
                ax.legend(fontsize=7, loc='upper right')
                ax.grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(
                self.path / f'PS_benchmark_curve_{ci + 1}.png',
                dpi=150, bbox_inches='tight',
            )
            plt.close(fig)

    def _plot_summary(self):
        """
        Side-by-side bar chart for all three metrics across all four smoothers.
        Lower is better for every metric.
        """
        metric_specs = [
            ('mean_phase_shift',     '|Mean Phase Shift| (kPa)',        'tab:blue'),
            ('mean_attenuation',     'Mean Peak Attenuation (%)',        'tab:orange'),
            ('mean_reproducibility', 'Mean Reproducibility Std (kPa)',   'tab:green'),
        ]

        x = np.arange(len(self.SMOOTHER_NAMES))
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        fig.suptitle(
            'Smoothing Technique Benchmark — Summary  (lower = better)',
            fontsize=14, fontweight='bold',
        )

        for ax, (key, label, color) in zip(axes, metric_specs):
            values = [abs(self.metrics[n][key]) for n in self.SMOOTHER_NAMES]
            bars = ax.bar(x, values, color=color, alpha=0.75,
                          edgecolor='black', width=0.5)
            ax.set_xticks(x)
            ax.set_xticklabels(self.SMOOTHER_NAMES, rotation=20,
                               ha='right', fontsize=10)
            ax.set_ylabel(label, fontsize=11)
            ax.set_title(label, fontsize=11)
            ax.grid(True, axis='y', alpha=0.3)
            for bar, val in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.01,
                    f'{val:.4f}', ha='center', va='bottom', fontsize=9,
                )

        plt.tight_layout()
        plt.savefig(
            self.path / 'PS_benchmark_summary.png',
            dpi=150, bbox_inches='tight',
        )
        plt.close(fig)

    # ── 6. Save ───────────────────────────────────────────────────────────────

    def _save_results(self):
        """Print summary table to console, save Excel summary and pickle."""
        rows = [
            {
                'Smoother':               name,
                'Mean Phase Shift (kPa)': round(self.metrics[name]['mean_phase_shift'], 4),
                'Mean Attenuation (%)':   round(self.metrics[name]['mean_attenuation'], 4),
                'Mean Repro Std (kPa)':   round(self.metrics[name]['mean_reproducibility'], 6),
            }
            for name in self.SMOOTHER_NAMES
        ]

        df = pd.DataFrame(rows)
        print('\n── Benchmark Results ──────────────────────────────────────────')
        print(df.to_string(index=False))
        print('────────────────────────────────────────────────────────────────\n')

        self.path.mkdir(parents=True, exist_ok=True)
        df.to_excel(self.path / 'PS_benchmark_summary.xlsx', index=False)

        with open(self.path / 'PS_benchmark_results.pkl', 'wb') as f:
            pickle.dump({
                'metrics':      self.metrics,
                'curves':       self.curves,
                'noisy_curves': self.noisy_curves,
            }, f)

        print(f'Benchmark complete. All outputs saved to: {self.path}')

    # ── 7. Public API ─────────────────────────────────────────────────────────

    def best_smoother(
        self,
        weight_phase: float = 1.0,
        weight_attenuation: float = 1.0,
        weight_repro: float = 1.0,
    ) -> str:
        """
        Return the name of the smoother with the lowest weighted composite score.
        All three metrics are equally weighted by default — adjust the weights to
        prioritise what matters most for your specific use case.

        Parameters
        ----------
        weight_phase       Weight for absolute mean phase shift.
        weight_attenuation Weight for mean peak attenuation (%).
        weight_repro       Weight for mean reproducibility std.
        """
        scores = {
            name: (
                weight_phase       * abs(self.metrics[name]['mean_phase_shift'])
                + weight_attenuation * abs(self.metrics[name]['mean_attenuation'])
                + weight_repro       * self.metrics[name]['mean_reproducibility']
            )
            for name in self.SMOOTHER_NAMES
        }

        best = min(scores, key=scores.get)
        print(f'\nBest smoother (weighted composite score): {best}')
        for n, s in scores.items():
            print(f'  {n:12s}: {s:.4f}')
        return best