# config.py

# 器件物理参数配置
DEVICE_CONFIG = {
    'L': 4e-6,  # 沟道长度 (m)
    'W': 80e-6,  # 沟道宽度 (m)
    'default_vds': 0.1,  # 漏极电压 (V)
    'I0_norm': 1e-8,  # 归一化目标电流 (A)

    # 栅介质层参数 (用于计算电容)：双栅就把厚度*2
    'T_SiN': 50e-9,  # 氮化硅厚度 (m)
    'eps_SiN': 7.5,  # 氮化硅相对介电常数
    'T_SiO': 50e-9,  # 氧化硅厚度 (m)
    'eps_SiO': 3.9  # 氧化硅相对介电常数
}

# 数据处理相关的参数
PROCESS_CONFIG = {
    "window_length": 7,   # Savitzky-Golay 平滑滤波窗口大小 (必须是奇数)
    "polyorder": 3,       # 平滑滤波的多项式阶数
    "smooth_log_current": True, # 是否在对数坐标下进行平滑，对 TFT 曲线提取更稳健
    "dVg_range": [1.0, 6.0],    # 提取迁移率时，Vg 相对于 Vth 的计算范围
    "mobility_max_abs_vds": 1.0,# 只有当漏压低于此值时，才计算线性区迁移率
}

# 提取文件中数据的参数
READER_CONFIG = {
    "vgs_aliases": ["Vgs", "Vg", "Gate Voltage", "GateVoltage"], # 自动识别表头的别名
    "min_points": 10,     # 单条曲线至少需要多少数据点，少于此数则拒绝识别
    "max_header_scan_right": 6,  # 向右扫描表头查找 Vds 的最大范围
    "max_consecutive_invalid_rows": 3, # 遇到多少行空值则认为曲线结束
    "min_confidence": 0.75, # 置信度阈值，低于此值则跳过不处理
}

# 输出结果的参数
OUTPUT_CONFIG = {
    "output_folder_name": "实验结果",
    "save_png": True,     # 是否保存 PNG 图
    "save_curve_csv": False,
    "enable_origin": False, # 是否启动 Origin 自动化
    "origin_template": r"E:\AAAA-MYLAB\TFT\My_TFT_Template.otpu",
}