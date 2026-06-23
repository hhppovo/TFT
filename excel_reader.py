"""健壮的 Excel 曲线数据读取器 (ExcelCurveReader)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import math
import re

import numpy as np
import openpyxl
import pandas as pd

# 支持的 Excel 格式后缀
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}

# --- 辅助清理函数 ---

def _normalise_text(value: Any) -> str:
    """将文本转换为小写并去掉所有标点和空格，用于模糊匹配表头。"""
    if value is None:
        return ""
    text = str(value).strip().lower()
    return re.sub(r"[\s_\-:：()（）]+", "", text)

def _to_float(value: Any) -> float | None:
    """尝试将单元格内容转换为浮点数，过滤掉非数值内容。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        number = float(text)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None

def _parse_vds(value: Any) -> float | None:
    """通过正则从表头中匹配 Vds=xxx 格式的数值。"""
    if value is None:
        return None
    text = str(value).replace("−", "-").replace("＝", "=").replace(" ", "")
    match = re.search(r"(?i)vds=?([+-]?\d+(?:\.\d+)?)v?", text)
    return float(match.group(1)) if match else None

def _parse_dimensions(value: Any) -> tuple[float, float, str] | None:
    """解析 W/L 尺寸信息（例如 'W=5um L=20um'）。"""
    if value is None:
        return None
    text = str(value).replace("μ", "u").replace("µ", "u")
    match = re.search(
        r"(?i)W\s*=?\s*(\d+(?:\.\d+)?)\s*(?:u?m)?\s*[/,;\s]*L\s*=?\s*(\d+(?:\.\d+)?)\s*(?:u?m)?",
        text,
    )
    if not match:
        return None
    width_um = float(match.group(1))
    length_um = float(match.group(2))
    return width_um * 1e-6, length_um * 1e-6, match.group(0).strip()

# --- 核心类定义 ---

@dataclass
class CurveData:
    """存储单条提取出来的曲线数据及其元数据。"""
    source_file: Path
    sheet_name: str
    point_name: str        # 器件测量点位名称
    vds: float
    vg: np.ndarray         # 栅压数据阵列
    drain_current: np.ndarray # 漏电流数据阵列
    header_row: int        # 表头所在的行号
    vg_column: int         # Vg 所在的列
    id_column: int         # Id 所在的列
    width_m: float | None = None
    length_m: float | None = None
    doe: str = ""          # 设计实验参数 (DOE)
    stage: str = ""        # 实验阶段
    confidence: float = 0.0 # 解析置信度
    warnings: list[str] = field(default_factory=list)

class ExcelCurveReader:
    """负责打开 Excel、寻找表头、提取数据块的解析器。"""
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.vgs_aliases = {_normalise_text(item) for item in config["vgs_aliases"]}
        self.min_points = int(config["min_points"])
        self.max_scan_right = int(config["max_header_scan_right"])
        self.max_invalid = int(config["max_consecutive_invalid_rows"])
        self.min_confidence = float(config["min_confidence"])

    def _is_vgs_header(self, value: Any) -> bool:
        """检查单元格是否为 Vgs 的表头。"""
        text = _normalise_text(value)
        return text in self.vgs_aliases or text.startswith("vgs")

    def _read_numeric_block(self, sheet, header_row, vg_col, id_col) -> tuple[np.ndarray, np.ndarray]:
        """向下读取数据列，直到遇到过多的非法行。"""
        vg_values, id_values = [], []
        started = False
        invalid_count = 0

        # 从表头下方开始扫描
        for row in range(header_row + 1, sheet.max_row + 1):
            vg = _to_float(sheet.value(row, vg_col))
            current = _to_float(sheet.value(row, id_col))
            if vg is not None and current is not None:
                vg_values.append(vg)
                id_values.append(current)
                started = True
                invalid_count = 0
            elif started:
                # 连续遇到非法行则停止读取，防止读到其他无关数据
                invalid_count += 1
                if invalid_count >= self.max_invalid:
                    break
        return np.asarray(vg_values, dtype=float), np.asarray(id_values, dtype=float)

    def extract_file(self, path: str | Path) -> tuple[list[CurveData], list[dict[str, Any]]]:
        """对传入的 Excel 文件执行全面提取。"""
        # ... (内部逻辑：加载工作表 -> 寻找W/L参数 -> 遍历每个单元格寻找 Vgs -> 定位 Vds -> 提取数据)
        # 1. 扫描工作表定位表头 (row, col)
        # 2. 从表头向右扫描获取 Vds 并提取对应的 Id-Vg 块
        # 3. 计算单调性并根据置信度筛选
        # 4. 向上回溯寻找 DOE、点位、阶段等标签信息
        # ...
        return curves, logs