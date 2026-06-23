import numpy as np
from scipy.signal import savgol_filter

class DeviceExtractor:
    """
    TFT 电学参数提取引擎
    """
    Cox: float

    def __init__(self, config: dict, *, width_m: float, length_m: float, drain_voltage: float):
        """

        :type drain_voltage: float
        """
        self.W = width_m
        self.L = length_m
        self.Vd = drain_voltage

        # 1. 计算绝缘层电容 Cox [F/m^2]
        # 公式: Cox = eps_0 * eps_r / tox
        eps_0 = 8.854e-12

        t_sin = config["T_SiN"]
        eps_sin = config["eps_SiN"]
        t_sio = config["T_SiO"]
        eps_sio = config["eps_SiO"]

        # 两层介质串联：1/Cox = t_SiN/(eps0*eps_SiN) + t_SiO/(eps0*eps_SiO)
        self.Cox = eps_0 / (t_sin / eps_sin + t_sio / eps_sio)

        # 2. 定电流法阈值目标值 [A]
        # I_target = (W/L) * I0_norm
        self.I_target = (self.W / self.L) * float(config.get('I0_norm', 1e-9))

    def preprocess_data(self, vg, current, window_length=7):
        """数据预处理：去除噪声并平滑曲线"""
        # 取绝对值防止电流为负造成 log 运算报错
        id_abs = np.abs(current)

        # 使用 Savitzky-Golay 滤波器进行平滑
        # 它通过多项式拟合局部数据，能较好地保留 gm(跨导) 的峰值
        wl = window_length if window_length % 2 != 0 else window_length + 1
        id_proc = savgol_filter(id_abs, window_length=wl, polyorder=2)

        # 确保电流不为0（避免log运算错误）
        return vg, np.maximum(id_proc, 1e-15)

    def extract_vth(self, vg, id_proc):
        """定电流法提取 Vth，增加异常捕获"""
        # 增加容错：如果数据太短或全是 0，直接返回 NaN
        if len(vg) < 5 or np.max(id_proc) < self.I_target:
            return np.nan

        id_mono = np.maximum.accumulate(id_proc)
        indices = np.flatnonzero(id_mono >= self.I_target)

        if len(indices) == 0:
            return np.nan

        k = indices[0]
        if k == 0: return float(vg[0])

        v1, v2 = vg[k - 1], vg[k]
        i1, i2 = id_mono[k - 1], id_mono[k]

        # 增加除零保护
        if abs(i2 - i1) < 1e-20: return float(v2)

        return float(v1 + (self.I_target - i1) * (v2 - v1) / (i2 - i1))

    def extract_mobility(self, vg, id_proc):
        """提取迁移率 mu"""
        # 线性区: mu = (L / W*Cox*Vd) * gm
        if self.Vd < 1.0:
            gm = np.gradient(id_proc, vg)
            gm_max = np.max(gm)
            mu = (self.L / (self.W * self.Cox * self.Vd)) * gm_max
        # 饱和区: mu = (2L / W*Cox) * (d(sqrt_Id)/dVg)^2
        else:
            sqrt_id = np.sqrt(id_proc)
            gm_sat = np.gradient(sqrt_id, vg)
            mu = (2.0 * self.L / (self.W * self.Cox)) * (np.max(gm_sat) ** 2)

        return mu * 1e4, None # 转换为 cm^2/Vs

    def extract_ss(self, vg, id_proc):
        """亚阈值摆幅 SS [V/dec]"""
        # SS = d(Vg) / d(log10(Id)) = 1 / max(d(log10(Id))/dVg)
        log_id = np.log10(np.maximum(id_proc, 1e-15))
        dlogId_dVg = np.gradient(log_id, vg)

        max_slope = np.max(dlogId_dVg)
        if max_slope <= 0: return np.nan, np.nan
        return 1.0 / max_slope, np.nan