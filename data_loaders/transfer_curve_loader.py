# data_loaders/universal_loader.py
import pandas as pd
import numpy as np
import os
import re

from extractor import DeviceExtractor


def load_transfer_curves(file_path, default_vds=None):
    """
    【万能转移曲线读取器】
    自动识别并处理三种数据格式：
    1. 仪器原生导出的 CSV 日志文件（支持单次测试，以及多次连续 Sweep 的可靠性测试）
    2. 横向多曲线手工汇总的 Excel 表格（支持多 Sheet 遍历）
    3. 纯两列数据的简单表格

    参数:
        file_path (str): 数据文件的绝对路径
        default_vds (float): 如果文件中实在找不到漏源极电压 Vds，用来兜底的默认值

    返回:
        list of dict: 一个包含所有曲线数据的列表。
        每个字典结构为 {'sheet_name': 子表名, 'name': 曲线名, 'vds': 电压值, 'vg': Vg数组, 'id': Id数组}
    """
    print(f"正在读取: {os.path.basename(file_path)}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到文件: {file_path}")

    curves = []

    # =====================================================================
    # 策略 1：原生解析仪器的日志型 CSV (如 Keysight B1500A 导出的原始数据)
    # =====================================================================
    try:
        # 使用 errors='replace' 防止某些特殊编码字符导致读取崩溃
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        # 初始化列索引和数据容器
        vg_idx, id_idx, vds_idx = -1, -1, -1
        current_vg, current_id, current_vds = [], [], []

        in_data_block = False  # 标记当前是否正在读取数据区域
        curve_count = 0  # 记录这是文件里的第几次 Sweep (用于可靠性连扫)

        for line in lines:
            # 当遇到表头标识符时，说明一个新的数据块开始了
            if line.startswith("DataName,"):

                # 🌟 如果上一个数据块已经收集到了数据，先把它“打包”存起来，不要丢弃！
                if in_data_block and len(current_vg) > 10:
                    vds = float(np.median(current_vds)) if current_vds else default_vds
                    curve_count += 1
                    curves.append({
                        'name': f"{os.path.basename(file_path).replace('.csv', '')}_Sweep{curve_count}",
                        'vds': vds,
                        'vg': np.array(current_vg),
                        'id': np.array(current_id)
                    })

                # 重置容器，准备迎接新的数据块
                current_vg, current_id, current_vds = [], [], []
                cols = [c.strip().lower() for c in line.split(",")]

                # 寻找 Vg 和 Id 所在的列号
                if "vg" in cols and "id" in cols:
                    vg_idx = cols.index("vg")
                    id_idx = cols.index("id")

                    # 尝试寻找 Vds，如果没有则为 -1
                    if "vds" in cols:
                        vds_idx = cols.index("vds")
                    elif "vd" in cols:
                        vds_idx = cols.index("vd")
                    else:
                        vds_idx = -1

                    in_data_block = True
                else:
                    in_data_block = False

            # 当遇到数据行时，提取具体数值
            elif line.startswith("DataValue,") and in_data_block:
                vals = line.strip().split(",")
                try:
                    # 将字符串转为浮点数，存入列表
                    current_vg.append(float(vals[vg_idx]))
                    current_id.append(float(vals[id_idx]))
                    if vds_idx >= 0:
                        current_vds.append(float(vals[vds_idx]))
                except (ValueError, IndexError):
                    pass  # 遇到空值或乱码则跳过这一行

        # 🌟 文件读取结束时，别忘了把最后收集到的那一个数据块也打包存入！
        if in_data_block and len(current_vg) > 10:
            vds = float(np.median(current_vds)) if current_vds else default_vds
            curve_count += 1
            curves.append({
                'name': f"{os.path.basename(file_path).replace('.csv', '')}_Sweep{curve_count}",
                'vds': vds,
                'vg': np.array(current_vg),
                'id': np.array(current_id)
            })

        # 如果通过 CSV 解析成功提取到了曲线，做最后的润色：
        if curves:
            # 如果文件里只有一条线（不是连扫），就把 "_Sweep1" 砍掉，保持名字清爽
            if len(curves) == 1:
                curves[0]['name'] = os.path.basename(file_path).replace('.csv', '')
            return curves  # 直接返回，不再执行后续的 Pandas 策略

    except Exception:
        pass  # 如果策略1报错（比如文件不是CSV），默默跳过，交给策略2处理

    # =====================================================================
    # 策略 2 & 3：使用 Pandas 扫描手工汇总的复杂 Excel 表格
    # =====================================================================
    dfs = {}
    file_lower = file_path.lower()

    try:
        # 读取文件：利用 sheet_name=None 一次性读取所有的 Sheet 子表
        if file_lower.endswith('.csv'):
            dfs['Sheet1'] = pd.read_csv(file_path, sep=None, engine='python', on_bad_lines='skip', header=None)
        elif file_lower.endswith(('.xlsx', '.xls')):
            try:
                dfs = pd.read_excel(file_path, engine='openpyxl', header=None, sheet_name=None)
            except:
                dfs = pd.read_excel(file_path, engine='xlrd', header=None, sheet_name=None)
    except Exception as e:
        return []  # 文件彻底损坏或格式不支持，返回空列表

    # 遍历该文件中的每一个子表 (Sheet)
    for sheet_name, df in dfs.items():
        if df is None or df.empty:
            continue

        found_multi_curve = False

        # 在当前子表的前 40 行中寻找 "Vgs" 或 "Vg" 这样的关键表头
        for row in range(min(40, len(df))):
            for col in range(len(df.columns)):
                val = str(df.iat[row, col]).strip().lower()

                # 一旦找到 Vgs 标识
                if val in ['vgs', 'vg', 'gate voltage']:

                    # 策略 2 核心：向右扫描相邻的 5 列，寻找配套的 Vds 或 Id
                    for c2 in range(col + 1, min(col + 6, len(df.columns))):
                        v2 = str(df.iat[row, c2]).strip().lower()

                        # 遇到下一个 Vgs 就停止，防止把下一组器件的数据串台了
                        if v2 in ['vgs', 'vg', 'gate voltage']: break

                        if 'vds' in v2 or 'id' in v2:
                            # 使用正则从 "Vds=0.1V" 这样的表头里抠出数字 0.1
                            match = re.search(r'vds\s*=?\s*([0-9\.]+)', v2)
                            vds = float(match.group(1)) if match else default_vds

                            vg_data, id_data = [], []
                            # 往下遍历每一行提取数字
                            for r2 in range(row + 1, len(df)):
                                try:
                                    vg_float = float(df.iat[r2, col])
                                    id_float = float(df.iat[r2, c2])
                                    if np.isnan(vg_float) or np.isnan(id_float): break
                                    vg_data.append(vg_float)
                                    id_data.append(id_float)
                                except:
                                    break  # 遇到非数字（比如底部的备注）就停止提取

                            # 如果成功抓到一段有效的曲线数据
                            if len(vg_data) > 5:
                                found_multi_curve = True
                                tags = []

                                # 向上追溯 6 行，寻找这组数据的标识标签（比如 "M2 TEG", "#点位1"）
                                for r_up in range(max(0, row - 6), row):
                                    cell_c1 = str(df.iat[r_up, col]).strip()
                                    if cell_c1 and cell_c1 != 'nan' and cell_c1 not in tags: tags.append(cell_c1)
                                for r_up in range(max(0, row - 6), row):
                                    cell_c2 = str(df.iat[r_up, c2]).strip()
                                    if cell_c2 and cell_c2 != 'nan' and cell_c2 not in tags: tags.append(cell_c2)

                                # 把找到的标签拼起来作为曲线的名字，去掉非法字符
                                base_name = "_".join(tags) if tags else f"C{col}_C{c2}"
                                base_name = re.sub(r'[<>:"/\\|?*]+', '_', base_name)

                                curves.append({
                                    'sheet_name': str(sheet_name),
                                    'name': f"{base_name}_Vds{vds}V",
                                    'vds': vds,
                                    'vg': np.array(vg_data),
                                    'id': np.array(id_data)
                                })

    return curves


# =============================================================================
# 以下为批量文件处理引擎，衔接 Loader (读取) 与 Extractor (计算)
# =============================================================================

def process_transfer_files(input_folder, device_config, process_config):
    """
    【批量处理中枢】
    扫描文件夹 -> 调用 load_transfer_curves 读取数据 -> 调用 DeviceExtractor 计算参数

    返回:
        summary_results (list): 用于生成 Excel 的参数汇总表
        all_curves_grouped (dict): 用于送给 Origin 画图的曲线分组字典
    """
    all_curves_grouped = {}
    summary_results = []

    # 1. 过滤文件夹内的有效文件，避开隐藏文件和临时缓存(~$开头)
    target_files = [
        os.path.join(input_folder, file_name)
        for file_name in os.listdir(input_folder)
        if not file_name.startswith("~$")
           and file_name.lower().endswith((".csv", ".xlsx", ".xls"))
    ]

    if not target_files:
        print(f"在 {input_folder} 文件夹下没有找到 CSV 或 Excel 数据文件。")
        return summary_results, all_curves_grouped

    # 2. 遍历每一个有效文件
    for file_path in target_files:
        file_name = os.path.basename(file_path)
        # 砍掉后缀名，用于拼接最终的纯净名字
        file_name_no_ext = re.sub(r"\.(xlsx|xls|csv)$", "", file_name, flags=re.IGNORECASE)

        # 尝试从文件名（如 W80L4）中提取器件的长宽，若没有则用 config 默认值
        match = re.search(r"(?i)W(\d+).*?L(\d+)", file_name)
        if match:
            real_w = float(match.group(1)) * 1e-6
            real_l = float(match.group(2)) * 1e-6
        else:
            real_w = float(device_config["W"])
            real_l = float(device_config["L"])

        # 3. 将文件交给【万能读取器】解析
        curves = load_transfer_curves(
            file_path,
            default_vds=device_config.get("default_vds", 0.1),
        )

        # 4. 遍历提取出来的每一条曲线，进行物理计算
        for curve in curves:
            curve_name = curve["name"]
            sheet_name = curve.get("sheet_name", "Sheet1")

            # 定义分组的 Key，格式为 "文件名_子表名"，防止 Origin 里图例重名冲突
            group_key = f"{file_name_no_ext}_{sheet_name}"

            # 初始化物理参数提取器
            extractor = DeviceExtractor(
                device_config,
                width_m=real_w,
                length_m=real_l,
                drain_voltage=curve["vds"],
            )

            try:
                # 步骤 A：平滑去噪
                vg_proc, id_proc = extractor.preprocess_data(
                    curve["vg"],
                    curve["id"],
                    window_length=process_config["window_length"],
                )
                # 步骤 B：提取阈值电压、迁移率、亚阈值摆幅
                vth = extractor.extract_vth(vg_proc, id_proc)
                mobility, _ = extractor.extract_mobility(vg_proc, id_proc)
                ss, _ = extractor.extract_ss(vg_proc, id_proc)
            except Exception as error:
                print(f"处理曲线 {curve_name} 时发生错误: {error}")
                vg_proc, id_proc = None, None
                vth, mobility, ss = np.nan, np.nan, np.nan

            # 5. 将计算结果录入清单，准备输出到 Excel
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

            # 6. 将处理好的曲线数据装入画图字典，准备送去 Origin
            if vg_proc is not None and id_proc is not None:
                # setdefault 会检查字典里有没有 group_key 这个抽屉，没有就建一个列表，然后存入数据
                all_curves_grouped.setdefault(group_key, []).append({
                    "name": curve_name,
                    "vg": vg_proc,
                    "id": id_proc,
                })

    return summary_results, all_curves_grouped