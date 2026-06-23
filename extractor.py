"""TFT electrical parameter extraction (MATLAB Logic Replica + Extrapolation Fallback)."""
from __future__ import annotations
from typing import Any
import numpy as np
from scipy.signal import savgol_filter

class DeviceExtractor:
    def __init__(
        self, config: dict[str, Any], *, width_m: float | None = None, length_m: float | None = None, drain_voltage: float | None = None,
    ):
        self.L = float(length_m if length_m is not None else config["L"])
        self.W = float(width_m if width_m is not None else config["W"])
        self.Vd = float(drain_voltage if drain_voltage is not None else config["Vd"])

        if self.L <= 0 or self.W <= 0:
            raise ValueError("W 和 L 必须大于 0")

        epsilon0 = 8.854187817e-12
        c_sin = epsilon0 * float(config["eps_SiN"]) / float(config["T_SiN"])
        c_sio = epsilon0 * float(config["eps_SiO"]) / float(config["T_SiO"])
        self.Cox = 1.0 / (1.0 / c_sin + 1.0 / c_sio)
        self.I_target = (self.W / self.L) * float(config["I0_norm"])

    @staticmethod
    def _clean_and_sort(vg: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        vg = np.asarray(vg, dtype=float).reshape(-1)
        current = np.asarray(current, dtype=float).reshape(-1)
        mask = np.isfinite(vg) & np.isfinite(current)
        vg, current = vg[mask], current[mask]

        order = np.argsort(vg, kind="stable")
        vg, current = vg[order], current[order]

        unique_vg, inverse = np.unique(vg, return_inverse=True)
        if len(unique_vg) != len(vg):
            sums = np.zeros_like(unique_vg, dtype=float)
            counts = np.zeros_like(unique_vg, dtype=float)
            np.add.at(sums, inverse, current)
            np.add.at(counts, inverse, 1.0)
            current = sums / counts
            vg = unique_vg
        return vg, current

    def preprocess_data(self, vg: np.ndarray, current: np.ndarray, window_length: int = 7, polyorder: int = 3) -> tuple[np.ndarray, np.ndarray]:
        vg, current = self._clean_and_sort(vg, current)
        current_abs = np.abs(current)
        if len(current_abs) < 3: return vg, current_abs

        window = min(int(window_length), len(current_abs))
        if window % 2 == 0: window -= 1
        positive_floor = 1e-30
        log_current = np.log10(np.maximum(current_abs, positive_floor))
        smoothed = np.power(10.0, savgol_filter(log_current, window, int(polyorder), mode="interp"))
        return vg, np.maximum(smoothed, positive_floor)

    def extract_vth(self, vg: np.ndarray, current: np.ndarray) -> float:
        """提取 Vth：完美复刻 MATLAB 防抖 + 外推法兜底"""
        vg, current = self._clean_and_sort(vg, np.abs(current))
        if len(vg) < 2: return float("nan")

        current_cummax = np.maximum.accumulate(current)
        indices = np.flatnonzero(current_cummax >= self.I_target)


        if len(indices) > 0 and indices[0] > 0:
            k = int(indices[0])
            v1, v2 = vg[k - 1], vg[k]
            i1, i2 = current_cummax[k - 1], current_cummax[k]
            if i2 == i1: return float(v2)
            return float(v1 + (self.I_target - i1) * (v2 - v1) / (i2 - i1))


    def _extract_vg_at_current_log(self, vg, current, v_range, i_target, log_floor=1e-30):
        mask = (vg >= v_range[0]) & (vg <= v_range[1])
        vg_sub, id_sub = vg[mask], current[mask]
        if len(vg_sub) < 2: return float("nan")

        id_cummax = np.maximum.accumulate(id_sub)
        indices = np.flatnonzero(id_cummax >= i_target)
        if len(indices) == 0 or indices[0] == 0: return float("nan")

        k = indices[0]
        v1, v2 = vg_sub[k-1], vg_sub[k]

        log_i1 = np.log10(id_cummax[k-1] + log_floor)
        log_i2 = np.log10(id_cummax[k] + log_floor)
        log_it = np.log10(i_target + log_floor)

        if log_i2 == log_i1: return float(v2)
        return float(v1 + (log_it - log_i1) * (v2 - v1) / (log_i2 - log_i1))

    def extract_ss(self, vg: np.ndarray, current: np.ndarray, vth: float, ss_dvg=(-5.0, 0.0), id1_norm=1e-10, id2_norm=1e-9) -> tuple[float, float]:
        if not np.isfinite(vth): return float("nan"), float("nan")
        vg, current = self._clean_and_sort(vg, np.abs(current))

        i1_target = (self.W / self.L) * id1_norm
        i2_target = (self.W / self.L) * id2_norm
        v_range = (vth + ss_dvg[0], vth + ss_dvg[1])

        vg1 = self._extract_vg_at_current_log(vg, current, v_range, i1_target)
        vg2 = self._extract_vg_at_current_log(vg, current, v_range, i2_target)

        if np.isnan(vg1) or np.isnan(vg2): return float("nan"), float("nan")

        ss_val = abs(vg2 - vg1)
        ss_vg_mid = 0.5 * (vg1 + vg2)
        return ss_val, ss_vg_mid

    # 注意：这里把 dvg_range 的默认值放宽到了 20.0，防止严重漂移的器件找不到峰值
    def extract_mobility(self, vg: np.ndarray, current: np.ndarray, vth: float, dvg_range=(1.0, 20.0), gm_smooth_window=3) -> tuple[float, float]:
        if not np.isfinite(vth) or np.isclose(self.Vd, 0.0): return float("nan"), float("nan")

        vg, current = self._clean_and_sort(vg, np.abs(current))
        mask = (vg >= vth + dvg_range[0]) & (vg <= vth + dvg_range[1])
        vg_sub, current_sub = vg[mask], current[mask]

        if len(vg_sub) < 3: return float("nan"), float("nan")

        gm = np.gradient(current_sub, vg_sub)

        if gm_smooth_window > 1 and len(gm) >= gm_smooth_window:
            window = gm_smooth_window if gm_smooth_window % 2 != 0 else gm_smooth_window + 1
            gm = savgol_filter(gm, window, 1)

        gm_valid = np.where(np.isfinite(gm), gm, -np.inf)
        index = int(np.argmax(gm_valid))
        gm_max = float(gm_valid[index])

        if not np.isfinite(gm_max) or gm_max <= 0: return float("nan"), float("nan")

        mobility_m2 = gm_max / (self.Cox * abs(self.Vd)) * (self.L / self.W)
        return float(mobility_m2 * 1e4), float(vg_sub[index])