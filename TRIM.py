import numpy as np
import matplotlib.pyplot as plt
import re
import os

# =========================================================================
# 1. 实验参数设置 (在此处修改)
# =========================================================================
Target_Dose = 1e15  # 注入剂量 (ions/cm^2)

# 结构定义 (nm)
Thick_SiO2 = 300  # 氧化硅层 (阻挡层)
Thick_IGZO = 25  # IGZO层 (目标捕获层)
Thick_BGI = 100  # BGI层 (底层)

# 在这里指定 SRIM 输出文件的绝对路径
File_Range = r'F:\Program Files\SRIM-2013\SRIM Outputs\RANGE.txt'


# =========================================================================
# 2. 读取 RANGE.txt 数据
# =========================================================================
def read_srim_range(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到文件：\n{filepath}\n请检查路径是否正确，或者 SRIM 是否已经成功生成了该文件！")

    depths_ang = []
    probs = []
    start_read = False

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if '-----------' in line:
                start_read = True
                continue
            if start_read:
                line = line.strip()
                if not line:
                    continue
                # 修复 SRIM 科学计数法格式问题 (例如 1.00+01 缺 E)
                line = re.sub(r'(?<=\d)([+-])(?=\d)', r'E\1', line)
                line = line.replace('EE', 'E')

                parts = line.split()
                if len(parts) >= 2:
                    try:
                        # 深度单位是埃 (Angstrom), 概率单位是 (Atoms/cm3)/(Atoms/cm2)
                        depths_ang.append(float(parts[0]))
                        probs.append(float(parts[1]))
                    except ValueError:
                        pass

    return np.array(depths_ang), np.array(probs)


print(f"正在读取文件: {File_Range} ...")
raw_depth_ang, raw_prob = read_srim_range(File_Range)

# =========================================================================
# 3. 数据清洗与插值
# =========================================================================
# 去除可能存在的重复深度点
unique_depths, indices = np.unique(raw_depth_ang, return_index=True)
unique_probs = raw_prob[indices]

# 动态创建统一坐标轴 (nm) - 延长 50nm 作为画图缓冲
max_plot_depth = Thick_SiO2 + Thick_IGZO + Thick_BGI + 50
depth_axis_nm = np.linspace(0, max_plot_depth, 2000)
depth_axis_ang = depth_axis_nm * 10  # 转换为埃用于插值

# 线性插值
prob_interp = np.interp(depth_axis_ang, unique_depths, unique_probs, left=0, right=0)

# =========================================================================
# 4. 核心计算 (绝对离子浓度与截获效率)
# =========================================================================
# 计算绝对体积浓度 (atoms/cm^3) = 概率 * 剂量
vol_concentration = prob_interp * Target_Dose

# 计算 IGZO 层的截获效率
# 找出 IGZO 层对应的索引区间
mask_igzo = (depth_axis_nm > Thick_SiO2) & (depth_axis_nm <= Thick_SiO2 + Thick_IGZO)
# 积分时需将深度从 nm 转换为 cm (乘以 1e-7)，以保持量纲正确
depth_axis_cm = depth_axis_nm * 1e-7
efficiency_pct = np.trapezoid(prob_interp[mask_igzo], depth_axis_cm[mask_igzo]) * 100

print(f"计算完成！IGZO 层截获效率: {efficiency_pct:.2f}%")

# =========================================================================
# 5. 绘图：离子浓度随深度的分布
# =========================================================================
plt.figure(figsize=(10, 6), dpi=120)

# 绘制背景色块，标定不同膜层的位置
plt.axvspan(0, Thick_SiO2, facecolor='#E8F8F5', alpha=0.8, label=f'SiO$_2$ ({Thick_SiO2} nm)')
plt.axvspan(Thick_SiO2, Thick_SiO2 + Thick_IGZO, facecolor='#FDEBD0', alpha=0.8, label=f'IGZO ({Thick_IGZO} nm)')
plt.axvspan(Thick_SiO2 + Thick_IGZO, Thick_SiO2 + Thick_IGZO + Thick_BGI, facecolor='#EBF5FB', alpha=0.8,
            label=f'BGI ({Thick_BGI} nm)')

# 绘制离子浓度曲线
plt.plot(depth_axis_nm, vol_concentration, color='#1F618D', linewidth=2.5, label='Ion Concentration')

# 填充曲线下方区域 (仅为了美观，可选)
plt.fill_between(depth_axis_nm, vol_concentration, color='#1F618D', alpha=0.1)

# 修饰图表
plt.xlabel('Depth (nm)', fontsize=12, fontweight='bold')
plt.ylabel('Absolute Ion Concentration (atoms/cm$^3$)', fontsize=12, fontweight='bold')
plt.title(
    f'Ion Implantation Profile (Dose = {Target_Dose:.0e} ions/cm$^2$)\nCaptured Efficiency in IGZO: {efficiency_pct:.2f}%',
    fontsize=13, fontweight='bold')

# 限制坐标轴范围
plt.xlim(0, max_plot_depth)
plt.ylim(0, max(vol_concentration) * 1.15)

# 若离子浓度跨度非常大，你可以取消下面这行的注释来使用对数坐标轴
# plt.yscale('log')

plt.grid(True, linestyle='--', alpha=0.6)
plt.legend(loc='upper right', framealpha=0.9)
plt.tight_layout()

# 显示图像
plt.show()