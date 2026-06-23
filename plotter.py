# plotter.py
import os
import originpro as op
import numpy as np
from pathlib import Path  # 必备的路径处理库


class OriginPlotter:
    def __init__(self, template_path=None):
        """
        初始化画图模块
        :param template_path: 你的 Origin 模板文件 (.otpu) 的绝对路径
        """
        self.template_path = template_path
        # 让 Origin 在后台默默干活，不弹窗打扰
        op.set_show(False)

    # =====================================================================
    # 🌟 按子表分类，在同一个 Origin 文件里生成多个 Graph 窗口
    # =====================================================================
    def plot_multiple_graphs_in_one_project(self, curves_by_group: dict, output_path):
        """
        把多组数据放入同一个 Origin 工程中，每组数据独立占用一个图表(Graph)
        :param curves_by_group: 字典结构，{"组名(例如子表名)": [曲线数据1, 曲线数据2...]}
        """
        op.new()  # 新建一个空白工程

        graph_count = 0
        for group_name, curves in curves_by_group.items():
            if not curves:
                continue

            graph_count += 1
            # 给工作表起个安全的英文短名字 (Origin 对短名字有限制，长名字放 lname 里)
            wks = op.new_sheet('w', f'Data_{graph_count}')
            wks.lname = group_name

            # 加载模板
            if self.template_path and os.path.exists(self.template_path):
                graph = op.new_graph(template=self.template_path)
            else:
                graph = op.new_graph()

            # 将 Graph 窗口的标签名也改成子表的名字，方便你在 Origin 里寻找！
            graph.lname = group_name
            gl = graph[0]

            col_idx = 0
            for curve in curves:
                wks.from_list(col_idx, curve['vg'], f"Vg_{curve['name']}", "V")
                wks.from_list(col_idx + 1, np.abs(curve['id']), f"Id_{curve['name']}", "A")
                gl.add_plot(wks, coly=col_idx + 1, colx=col_idx, type='line')
                col_idx += 2

            # 一键打包成组并设置对数坐标
            gl.group()
            gl.set_int('y.type', 2)
            gl.rescale()

        op.save(str(output_path))
        print(f"🎉 聚合 Origin 工程已生成，内含 {graph_count} 张子图: {output_path}")

    # =====================================================================
    # 🌟 多个文件在一个文件夹，每一个文件里一条曲线使用
    # =====================================================================
    def plot_combined_transfer_curves(self, curves_data: list[dict], output_path):
        """
        把多条曲线画在同一个 Origin 文件的【同一张图层上】，并打包成组 (Group)
        """
        op.new()
        wks = op.new_sheet('w', 'All_TFT_Curves')

        if self.template_path and os.path.exists(self.template_path):
            graph = op.new_graph(template=self.template_path)
        else:
            graph = op.new_graph()

        gl = graph[0]
        col_idx = 0
        for curve in curves_data:
            wks.from_list(col_idx, curve['vg'], f"Vg_{curve['name']}", "V")
            wks.from_list(col_idx + 1, np.abs(curve['id']), f"Id_{curve['name']}", "A")
            gl.add_plot(wks, coly=col_idx + 1, colx=col_idx, type='line')
            col_idx += 2

        gl.group()
        gl.set_int('y.type', 2)
        gl.rescale()

        op.save(str(output_path))
        print(f"🎉 终极合并图已完成！请双击打开 Origin: {output_path}")

    def plot_transfer_curve(self, vg, id_raw, id_proc, vth, output_path):
        """
        将【单根器件】的数据注入 Origin 并根据模板画图
        """
        op.new()
        wks = op.new_sheet('w', 'TFT_Data')
        wks.from_list(0, vg, 'Gate Voltage', 'V')
        wks.from_list(1, id_raw, 'Raw Drain Current', 'A')
        wks.from_list(2, id_proc, 'Processed Drain Current', 'A')

        if self.template_path and os.path.exists(self.template_path):
            graph = op.new_graph(template=self.template_path)
        else:
            graph = op.new_graph()

        gl = graph[0]
        gl.add_plot(wks, coly=1, colx=0, type='scatter')
        gl.add_plot(wks, coly=2, colx=0, type='line')

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