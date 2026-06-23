# main.py
# 使用提醒每次使用之前在config文件中，更改相关参数，尤其是电容参数



import pandas as pd
import os

# 导入配置和引擎
from config import DEVICE_CONFIG, PROCESS_CONFIG
from plotter import OriginPlotter
from data_loaders.transfer_curve_loader import process_transfer_files

USE_ORIGIN_TEMPLATE = True


def main():
    input_folder = r"F:\SEU\发表论文\GI3成膜优化"
    save_folder = r"E:\AAAA-MYLAB\TFT\实验结果"

    if USE_ORIGIN_TEMPLATE:
        my_template = r"E:\AAAA-MYLAB\TFT\TFT\template\My_TFT_Template.otpu"
    else:
        my_template = None

    os.makedirs(save_folder, exist_ok=True)

    # ==== 扫描文件、读取曲线、参数提取 ====
    summary_results, all_curves_grouped = process_transfer_files(
        input_folder=input_folder,
        device_config=DEVICE_CONFIG,
        process_config=PROCESS_CONFIG,
    )

    print("\n⏳ 正在生成最终汇总报告...")

    # ==== 导出 Excel ====
    if summary_results:
        df_summary = pd.DataFrame(summary_results)
        excel_path = os.path.join(save_folder, "01_提取结果汇总表.xlsx")
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df_summary.to_excel(writer, index=False, sheet_name="TFT Parameters")
            worksheet = writer.sheets["TFT Parameters"]
            for col_idx, col in enumerate(df_summary.columns, 1):
                col_letter = chr(64 + col_idx)
                max_len = max(df_summary[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.column_dimensions[col_letter].width = min(max_len, 30)
        print(f"✅ Excel 汇总已生成: {excel_path}")

    # ==== 导出 Origin ====
    if all_curves_grouped:
        plotter = OriginPlotter(template_path=my_template)
        combined_opju_path = os.path.join(save_folder, "00_多子表_Curves_Combined.opju")
        plotter.plot_multiple_graphs_in_one_project(
            curves_by_group=all_curves_grouped,
            output_path=combined_opju_path
        )

    print("\n🎉 全部任务圆满完成！")


if __name__ == "__main__":
    main()