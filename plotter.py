# plotter.py
import os
import originpro as op
import numpy as np
from pathlib import Path  # ✅ 修复1：补上了必备的路径处理库


class OriginPlotter:
    def __init__(self, template_path=None):
        """
        初始化画图模块
        :param template_path: 你的 Origin 模板文件 (.otpu) 的绝对路径
        """
        self.template_path = template_path
        # 让 Origin 在后台默默干活，不弹窗打扰
        op.set_show(False)

    def plot_combined_transfer_curves(self, curves_data: list[dict], output_path):
        """
        把多条曲线画在同一个 Origin 文件的同一张图层上，并打包成组 (Group)
        """
        op.new()

        # 创建一个超级大表，用来并排装下所有的器件数据
        wks = op.new_sheet('w', 'All_TFT_Curves')

        # 如果你有预设模板，直接加载模板
        if self.template_path and os.path.exists(self.template_path):
            graph = op.new_graph(template=self.template_path)
        else:
            graph = op.new_graph()

        gl = graph[0]

        col_idx = 0
        for curve in curves_data:
            # Vg 塞入偶数列，Id 塞入奇数列
            wks.from_list(col_idx, curve['vg'], f"Vg_{curve['name']}", "V")
            wks.from_list(col_idx + 1, np.abs(curve['id']), f"Id_{curve['name']}", "A")

            # 把这组数据作为线图连入图层
            gl.add_plot(wks, coly=col_idx + 1, colx=col_idx, type='line')
            col_idx += 2

        # ==========================================================
        # 一键打包成”
        gl.group()
        # ==========================================================

        # TFT 必备：强制把 Y 轴设为 Log10 对数坐标
        gl.set_int('y.type', 2)
        gl.rescale()

        op.save(str(output_path))
        print(f"🎉 终极合并图已完成！请双击打开 Origin: {output_path}")

    def plot_transfer_curve(self, vg, id_raw, id_proc, vth, output_path):
        """
        将单根器件的数据注入 Origin 并根据模板画图
        """
        op.new()

        # 创建一个工作表 Worksheet，包含3列 (Vg, Raw_Id, Proc_Id)
        wks = op.new_sheet('w', 'TFT_Data')
        wks.from_list(0, vg, 'Gate Voltage', 'V')
        wks.from_list(1, id_raw, 'Raw Drain Current', 'A')
        wks.from_list(2, id_proc, 'Processed Drain Current', 'A')

        if self.template_path and os.path.exists(self.template_path):
            graph = op.new_graph(template=self.template_path)
        else:
            graph = op.new_graph()

        gl = graph[0]
        gl.add_plot(wks, coly=1, colx=0, type='scatter')  # 原始数据画散点
        gl.add_plot(wks, coly=2, colx=0, type='line')  # 平滑数据画线

        # 自动绘制 Vth 红色虚线
        if not np.isnan(vth):
            y_min = float(np.nanmin(np.abs(id_raw)))
            y_max = float(np.nanmax(np.abs(id_raw)))
            v_line = gl.add_line(vth, y_min, vth, y_max)
            v_line.set_int('color', 2)
            v_line.set_int('style', 1)
            v_line.set_float('width', 2.0)

        gl.rescale()

        op.save(str(output_path))
        print(f"✅ 单器件 Origin 工程文件已生成: {output_path}")

    def __del__(self):
        """
        安全机制：当程序运行结束销毁此类时，强制清理 Origin 后台进程释放内存。
        """
        try:
            op.exit()
        except:
            pass