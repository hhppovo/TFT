# data_loaders/universal_loader.py
import pandas as pd
import numpy as np
import os
import re

from extractor import DeviceExtractor


def load_transfer_curves(file_path, default_vds=None):
    """
    自动识别：1. 仪器原生CSV 2. 横向多曲线手工汇总表 3. 纯两列数据
    返回: list of dict, 每个 dict 包含 {'name', 'vds', 'vg', 'id'}
    """
    print(f"正在读取: {os.path.basename(file_path)}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到文件: {file_path}")

    curves = []

    # === 策略 1：原生解析仪器的日志型 CSV  ===
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        vg_idx, id_idx, vds_idx = -1, -1, -1
        current_vg, current_id, current_vds = [], [], []
        in_data_block = False

        for line in lines:
            if line.startswith("DataName,"):
                cols = [c.strip().lower() for c in line.split(",")]

                if "vg" in cols and "id" in cols:
                    vg_idx = cols.index("vg")
                    id_idx = cols.index("id")

                    if "vds" in cols:
                        vds_idx = cols.index("vds")
                    elif "vd" in cols:
                        vds_idx = cols.index("vd")
                    else:
                        vds_idx = -1

                    in_data_block = True
                else:
                    in_data_block = False

            elif line.startswith("DataValue,") and in_data_block:
                vals = line.strip().split(",")

                try:
                    current_vg.append(float(vals[vg_idx]))
                    current_id.append(float(vals[id_idx]))

                    if vds_idx >= 0:
                        current_vds.append(float(vals[vds_idx]))

                except (ValueError, IndexError):
                    pass

            elif in_data_block and len(current_vg) > 10:
                break
        vds = float(np.median(current_vds)) if current_vds else default_vds
        if len(current_vg) > 10:
            curves.append({
                'name': os.path.basename(file_path).replace('.csv', ''),
                'vds': vds,
                'vg': np.array(current_vg),
                'id': np.array(current_id)
            })
            return curves
    except Exception:
        pass

    # === 策略 2 & 3：使用 Pandas 扫描横向多曲线表  ===
    dfs = {}
    file_lower = file_path.lower()

    try:
        if file_lower.endswith('.csv'):
            # CSV 没有子表的概念，直接作为一个名叫 Sheet1 的表存起来
            dfs['Sheet1'] = pd.read_csv(file_path, sep=None, engine='python', on_bad_lines='skip', header=None)
        elif file_lower.endswith(('.xlsx', '.xls')):
            # 【终极奥义】：sheet_name=None 会把 Excel 里所有的表都读出来，变成字典！
            try:
                dfs = pd.read_excel(file_path, engine='openpyxl', header=None, sheet_name=None)
            except:
                dfs = pd.read_excel(file_path, engine='xlrd', header=None, sheet_name=None)
    except Exception as e:
        return []

    # 遍历这个文件里的每一个子表
    for sheet_name, df in dfs.items():
        if df is None or df.empty:
            continue

        found_multi_curve = False

        # === 策略 2：在当前子表中寻找 Vgs 表头 ===
        for row in range(min(40, len(df))):
            for col in range(len(df.columns)):
                val = str(df.iat[row, col]).strip().lower()
                if val in ['vgs', 'vg', 'gate voltage']:

                    # 找到 Vgs 后，向右扫描相邻的列找 Vds
                    for c2 in range(col + 1, min(col + 6, len(df.columns))):
                        v2 = str(df.iat[row, c2]).strip().lower()

                        # 遇到下一个 Vgs 就停止，防止跨到下一组器件
                        if v2 in ['vgs', 'vg', 'gate voltage']: break

                        if 'vds' in v2 or 'id' in v2:
                            match = re.search(r'vds\s*=?\s*([0-9\.]+)', v2)
                            vds = float(match.group(1)) if match else default_vds

                            vg_data, id_data = [], []
                            for r2 in range(row + 1, len(df)):
                                try:
                                    vg_float = float(df.iat[r2, col])
                                    id_float = float(df.iat[r2, c2])
                                    if np.isnan(vg_float) or np.isnan(id_float): break
                                    vg_data.append(vg_float)
                                    id_data.append(id_float)
                                except:
                                    break

                            # 如果成功抓到数据，向上追溯查找表头标签
                            if len(vg_data) > 5:
                                found_multi_curve = True
                                tags = []
                                for r_up in range(max(0, row - 6), row):
                                    cell_c1 = str(df.iat[r_up, col]).strip()
                                    if cell_c1 and cell_c1 != 'nan' and cell_c1 not in tags: tags.append(cell_c1)
                                for r_up in range(max(0, row - 6), row):
                                    cell_c2 = str(df.iat[r_up, c2]).strip()
                                    if cell_c2 and cell_c2 != 'nan' and cell_c2 not in tags: tags.append(cell_c2)

                                base_name = "_".join(tags) if tags else f"C{col}_C{c2}"
                                base_name = re.sub(r'[<>:"/\\|?*]+', '_', base_name)

                                curves.append({
                                    'sheet_name': str(sheet_name),  # ⚠️ 这里记录了曲线来自哪个子表
                                    'name': f"{base_name}_Vds{vds}V",
                                    'vds': vds,
                                    'vg': np.array(vg_data),
                                    'id': np.array(id_data)
                                })

    return curves

def process_transfer_files(input_folder, device_config, process_config):
    """扫描文件夹，并批量提取所有转移曲线的参数。"""
    all_curves_grouped = {}
    summary_results = []

    target_files = [
        os.path.join(input_folder, file_name)
        for file_name in os.listdir(input_folder)
        if not file_name.startswith("~$")
        and file_name.lower().endswith((".csv", ".xlsx", ".xls"))
    ]

    if not target_files:
        print(f"在 {input_folder} 文件夹下没有找到 CSV 或 Excel 数据文件。")
        return summary_results, all_curves_grouped

    for file_path in target_files:
        file_name = os.path.basename(file_path)
        file_name_no_ext = re.sub(
            r"\.(xlsx|xls|csv)$", "", file_name, flags=re.IGNORECASE
        )

        match = re.search(r"(?i)W(\d+).*?L(\d+)", file_name)
        if match:
            real_w = float(match.group(1)) * 1e-6
            real_l = float(match.group(2)) * 1e-6
        else:
            real_w = float(device_config["W"])
            real_l = float(device_config["L"])

        curves = load_transfer_curves(
            file_path,
            default_vds=device_config["default_vds"],
        )

        for curve in curves:
            curve_name = curve["name"]
            sheet_name = curve.get("sheet_name", "Sheet1")
            group_key = f"{file_name_no_ext}_{sheet_name}"

            extractor = DeviceExtractor(
                device_config,
                width_m=real_w,
                length_m=real_l,
                drain_voltage=curve["vds"],
            )

            try:
                vg_proc, id_proc = extractor.preprocess_data(
                    curve["vg"],
                    curve["id"],
                    window_length=process_config["window_length"],
                )
                vth = extractor.extract_vth(vg_proc, id_proc)
                mobility, _ = extractor.extract_mobility(vg_proc, id_proc)
                ss, _ = extractor.extract_ss(vg_proc, id_proc)
            except Exception as error:
                print(f"处理曲线 {curve_name} 时发生错误: {error}")
                vg_proc, id_proc = None, None
                vth, mobility, ss = np.nan, np.nan, np.nan

            summary_results.append({
                "所属文件": file_name_no_ext,
                "数据来源子表": sheet_name,
                "曲线位置名称": curve_name,
                "W (μm)": real_w * 1e6,
                "L (μm)": real_l * 1e6,
                "Vd (V)": curve["vds"],
                "阈值电压 Vth (V)": round(vth, 3) if not np.isnan(vth) else "提取失败",
                "亚阈值摆幅 SS (V/dec)": round(ss, 3) if not np.isnan(ss) else "提取失败",
                "迁移率 Mobility (cm2/Vs)": round(mobility, 3) if not np.isnan(mobility) else "提取失败",
            })

            if vg_proc is not None and id_proc is not None:
                all_curves_grouped.setdefault(group_key, []).append({
                    "name": curve_name,
                    "vg": vg_proc,
                    "id": id_proc,
                })

    return summary_results, all_curves_grouped