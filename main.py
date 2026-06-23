# main.py
import numpy as np
import pandas as pd
import os
import glob
import re

# 导入配置和引擎
from config import DEVICE_CONFIG, PROCESS_CONFIG
from extractor import DeviceExtractor
from plotter import OriginPlotter

# ==================== 0. 全局控制开关 ====================
# 想用模板就设为 True，不想用就设为 False (注意首字母大写)
USE_ORIGIN_TEMPLATE = True


# =========================================================

# ==================== 1. 数据读取模块 ====================
def load_single_excel(file_path):
    print(f"正在读取: {os.path.basename(file_path)}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到文件: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        vg_idx, id_idx = -1, -1
        current_vg, current_id = [], []
        in_data_block = False

        for line in lines:
            if line.startswith("DataName,"):
                cols = [c.strip().lower() for c in line.split(',')]
                if 'vg' in cols and 'id' in cols:
                    vg_idx = cols.index('vg')
                    id_idx = cols.index('id')
                    in_data_block = True
                else:
                    in_data_block = False
            elif line.startswith("DataValue,") and in_data_block:
                vals = line.split(',')
                try:
                    current_vg.append(float(vals[vg_idx]))
                    current_id.append(float(vals[id_idx]))
                except (ValueError, IndexError):
                    pass
            else:
                if in_data_block and len(current_vg) > 10:
                    break

        if len(current_vg) > 10:
            return np.array(current_vg), np.array(current_id)
    except Exception:
        pass

    df = None
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
    except:
        try:
            df = pd.read_excel(file_path, engine='xlrd')
        except:
            try:
                df = pd.read_csv(file_path, sep=None, engine='python', on_bad_lines='skip')
            except Exception as e:
                raise ValueError(f"文件格式完全无法识别！报错信息: {e}")

    if df is not None:
        df = df.dropna(subset=[df.columns[0], df.columns[1]])
        df.iloc[:, 0] = pd.to_numeric(df.iloc[:, 0], errors='coerce')
        df.iloc[:, 1] = pd.to_numeric(df.iloc[:, 1], errors='coerce')
        df = df.dropna(subset=[df.columns[0], df.columns[1]])
        Id_raw = df.iloc[:, 0].values
        Vg_raw = df.iloc[:, 1].values
        return Vg_raw, Id_raw


# ==================== 2. 主循环控制台 ====================
def main():
    # 1. 文件夹路径设置
    input_folder = r"E:\桌面\621\ald100"
    save_folder = r"E:\AAAA-MYLAB\TFT\实验结果"

    # 根据开关决定是否加载模板路径
    if USE_ORIGIN_TEMPLATE:
        my_template = r"E:\AAAA-MYLAB\TFT\My_TFT_Template.otpu"
    else:
        my_template = None
        print("ℹ️ 提示：未启用 Origin 模板，将使用默认样式绘图。")

    if not os.path.exists(save_folder):
        os.makedirs(save_folder)

    # 准备两个空盒子：一个装画图数据，一个装 Excel 汇总数据
    all_curves_for_plot = []
    summary_results = []

    csv_files = glob.glob(os.path.join(input_folder, "*.csv"))
    if not csv_files:
        print("❌ 在该文件夹下没有找到任何 .csv 文件！")
        return

    print(f"\n🔍 找到 {len(csv_files)} 个数据文件，准备批量提取...")

    # ==================== 批量处理循环 ====================
    for file_path in csv_files:
        file_name = os.path.basename(file_path)
        curve_name = file_name.replace('.csv', '')

        # 自动从文件名中识别 W 和 L (例如 W10L3 -> W=10, L=3)
        match = re.search(r'(?i)W(\d+).*?L(\d+)', file_name)
        if match:
            real_w = float(match.group(1)) * 1e-6
            real_l = float(match.group(2)) * 1e-6
        else:
            real_w = float(DEVICE_CONFIG['W'])
            real_l = float(DEVICE_CONFIG['L'])

        # 初始化提参引擎
        extractor = DeviceExtractor(
            DEVICE_CONFIG,
            width_m=real_w,
            length_m=real_l,
            drain_voltage=0.1
        )

        # 读取并处理数据
        try:
            Vg_raw, Id_raw = load_single_excel(file_path)
            Vg_proc, Id_proc = extractor.preprocess_data(
                Vg_raw, Id_raw,
                window_length=PROCESS_CONFIG['window_length']
            )

            # 提取核心参数

            Vth = extractor.extract_vth(Vg_proc, Id_proc)
            Mobility, _ = extractor.extract_mobility(Vg_proc, Id_proc, Vth, dvg_range=(1.0, 6.0))

            # ========================================================
            # 计算亚阈值摆幅 SS，对应 MATLAB 里的相对 Vth 查找范围
            SS, SS_Vg = extractor.extract_ss(Vg_proc, Id_proc, Vth, ss_dvg=(-5.0, 0.0), id1_norm=1e-8, id2_norm=1e-7)
            # ========================================================
        except Exception as e:
            print(f"⚠️ 处理 {file_name} 时发生错误: {e}")
            Vg_proc, Id_proc, Vth, Mobility = None, None, np.nan, np.nan

        # 1. 把参数记录到 Excel 汇总盒子里
        # 新增了 W 和 L 字段，方便你在 Excel 里直接核对
        summary_results.append({
            "文件名": file_name,
            "W (μm)": real_w * 1e6,  # 转换回微米单位显示
            "L (μm)": real_l * 1e6,  # 转换回微米单位显示
            "Vd (V)": 0.1,
            "阈值电压 Vth (V)": round(Vth, 3) if not np.isnan(Vth) else "提取失败",
            "亚阈值摆幅 SS (V/dec)": round(SS, 3) if not np.isnan(SS) else "提取失败",
            "迁移率 Mobility (cm2/Vs)": round(Mobility, 3) if not np.isnan(Mobility) else "提取失败"
        })

        # 2. 把处理好的数据装进画图盒子里
        if Vg_proc is not None and Id_proc is not None:
            all_curves_for_plot.append({
                'name': curve_name,
                'vg': Vg_proc,
                'id': Id_proc
            })

    # ==================== 终极导出阶段 ====================
    print("\n⏳ 正在生成最终汇总报告...")

    # 导出 1：生成 Excel 汇总表
    if summary_results:
        df_summary = pd.DataFrame(summary_results)
        excel_path = os.path.join(save_folder, "01_提取结果汇总表.xlsx")
        # 自动调整列宽以适应中文内容，使用 openpyxl 引擎写入
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df_summary.to_excel(writer, index=False, sheet_name="TFT Parameters")

            # 简单排版：设置一下列宽，让表格看起来更舒服
            worksheet = writer.sheets["TFT Parameters"]
            for col_idx, col in enumerate(df_summary.columns, 1):
                col_letter = chr(64 + col_idx)  # A, B, C...
                max_len = max(df_summary[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.column_dimensions[col_letter].width = min(max_len, 30)

        print(f"✅ Excel 汇总已生成: {excel_path}")

    # 导出 2：生成 Origin
    if all_curves_for_plot:
        plotter = OriginPlotter(template_path=my_template)
        combined_opju_path = os.path.join(save_folder, "00_All_Curves_Combined.opju")
        plotter.plot_combined_transfer_curves(
            curves_data=all_curves_for_plot,
            output_path=combined_opju_path
        )

    print("\n🎉 全部任务圆满完成！可以去实验结果文件夹验收了。")


if __name__ == "__main__":
    main()