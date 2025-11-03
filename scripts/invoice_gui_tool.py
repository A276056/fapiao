#!/usr/bin/env python3
"""带有 Tkinter 图形界面的发票整理工具。"""

from __future__ import annotations

import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pdfplumber
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# 正则表达式模式（根据README要求）
INVOICE_NUMBER_PATTERN = re.compile(r"\d{15,20}")
INVOICE_DATE_PATTERN = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")
INVOICE_AMOUNT_PATTERN = re.compile(r"¥\s*\d+\.\d{2}")


@dataclass
class InvoiceInfo:
    """保存单份发票提取到的信息。"""

    invoice_number: Optional[str]  # 发票号码
    invoice_date: Optional[str]    # 开票日期
    total_amount: Optional[str]    # 价税合计


class InvoiceOrganizerGUI:
    """发票整理与去重 GUI 应用。"""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("发票整理与去重工具")
        self.master.geometry("700x400")
        self.master.resizable(False, False)

        self.folder_var = tk.StringVar()
        self.status_var = tk.StringVar(value="请选择包含 PDF 发票的文件夹。")

        self._build_layout()

    def _build_layout(self) -> None:
        """构建界面布局。"""

        padding_options = {"padx": 20, "pady": 10}

        frame = ttk.Frame(self.master)
        frame.pack(fill=tk.BOTH, expand=True)

        folder_label = ttk.Label(frame, text="发票文件夹：")
        folder_label.grid(row=0, column=0, sticky=tk.W, **padding_options)

        folder_entry = ttk.Entry(frame, textvariable=self.folder_var, width=60)
        folder_entry.grid(row=0, column=1, sticky=tk.W, **padding_options)

        browse_button = ttk.Button(frame, text="浏览", command=self.select_folder)
        browse_button.grid(row=0, column=2, sticky=tk.W, **padding_options)

        self.start_button = ttk.Button(frame, text="开始整理", command=self.start_processing)
        self.start_button.grid(row=1, column=1, sticky=tk.W, **padding_options)

        self.progress = ttk.Progressbar(frame, orient=tk.HORIZONTAL, length=400, mode="determinate")
        self.progress.grid(row=2, column=0, columnspan=3, sticky=tk.W, **padding_options)

        status_label = ttk.Label(frame, textvariable=self.status_var, foreground="#333333")
        status_label.grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=20, pady=(10, 0))

        for child in frame.winfo_children():
            child.grid_configure(padx=10, pady=10)

    def select_folder(self) -> None:
        """打开文件夹选择对话框。"""

        folder_path = filedialog.askdirectory()
        if folder_path:
            self.folder_var.set(folder_path)

    def start_processing(self) -> None:
        """启动整理流程的线程。"""

        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "请先选择发票文件夹。")
            return

        source_dir = Path(folder)
        if not source_dir.exists() or not source_dir.is_dir():
            messagebox.showerror("错误", "选择的路径无效，请重新选择。")
            return

        self.start_button.config(state=tk.DISABLED)
        self._update_progress(0, 1, "正在准备处理文件...")

        thread = threading.Thread(target=self._run_processing, args=(source_dir,), daemon=True)
        thread.start()

    def _run_processing(self, source_dir: Path) -> None:
        """线程执行的实际整理逻辑。"""

        try:
            summary = self.process_invoices(source_dir)
            self._show_completion(summary)
        except Exception as exc:  # pragma: no cover - 运行时保护
            error_message = str(exc)
            self.master.after(
                0, lambda msg=error_message: messagebox.showerror("处理失败", msg)
            )
        finally:
            self.master.after(0, lambda: self.start_button.config(state=tk.NORMAL))

    def process_invoices(self, source_dir: Path) -> str:
        """处理指定目录下的所有 PDF 发票。"""

        pdf_files = sorted(source_dir.rglob("*.pdf"))
        total_files = len(pdf_files)
        if total_files == 0:
            self._update_progress(0, 1, "未找到任何 PDF 文件。")
            return "未找到任何 PDF 文件。"

        records: List[Dict[str, str]] = []
        seen_keys: Dict[str, Path] = {}
        duplicates_removed = 0
        renamed_count = 0
        missing_info_count = 0

        for index, pdf_path in enumerate(pdf_files, start=1):
            self._update_progress(index - 1, total_files, f"正在处理：{pdf_path.name}")

            try:
                info = self.extract_invoice_info(pdf_path)
            except Exception:
                info = InvoiceInfo(invoice_number=None, invoice_date=None, total_amount=None)

            # 按发票号码去重
            if info.invoice_number:
                if info.invoice_number in seen_keys:
                    duplicates_removed += 1
                    self._delete_file(pdf_path)
                    records.append(
                        {
                            "原文件名": pdf_path.name,
                            "新文件名": "",
                            "状态": "删除",
                        }
                    )
                    self._update_progress(index, total_files, f"删除重复：{pdf_path.name}")
                    continue
                seen_keys[info.invoice_number] = pdf_path

            # 检查是否有完整信息
            if info.invoice_number and info.invoice_date and info.total_amount:
                # 仅在原文件名前添加日期
                new_name = f"{info.invoice_date}_{pdf_path.name}"
                dest_path = self._unique_path(source_dir / new_name)
                self._move_file(pdf_path, dest_path)
                renamed_count += 1
                records.append(
                    {
                        "原文件名": pdf_path.name,
                        "新文件名": dest_path.name,
                        "状态": "保留",
                    }
                )
            else:
                missing_info_count += 1
                new_name = f"unmatched_{pdf_path.name}"
                dest_path = self._unique_path(source_dir / new_name)
                self._move_file(pdf_path, dest_path)
                records.append(
                    {
                        "原文件名": pdf_path.name,
                        "新文件名": dest_path.name,
                        "状态": "缺失信息",
                    }
                )

            self._update_progress(index, total_files, f"完成：{pdf_path.name}")

        log_path = source_dir / "rename_log.xlsx"
        df = pd.DataFrame(records, columns=["原文件名", "新文件名", "状态"])
        df.to_excel(log_path, index=False)

        summary = (
            "整理完成 ✅\n"
            f"共处理 {total_files} 份发票\n"
            f"删除重复文件 {duplicates_removed} 份\n"
            f"成功重命名 {renamed_count} 份\n"
            f"缺失信息 {missing_info_count} 份\n"
            "日志文件已保存为 rename_log.xlsx"
        )

        final_status = (
            f"总文件数：{total_files}，删除重复：{duplicates_removed}，"
            f"重命名：{renamed_count}，缺失信息：{missing_info_count}"
        )
        self._update_progress(total_files, total_files, final_status)
        return summary

    def extract_invoice_info(self, pdf_path: Path) -> InvoiceInfo:
        """从 PDF 文件中提取发票信息（增强鲁棒性版本）。"""
        
        text_content = []
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    try:
                        page_text = page.extract_text() or ""
                        text_content.append(page_text)
                    except Exception:
                        text_content.append("")
        except Exception as e:
            raise Exception(f"无法读取PDF文件 {pdf_path.name}: {e}")
        
        # 合并多页文本并按行分割
        full_text = "\n".join(text_content)
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        if not lines:
            return InvoiceInfo(invoice_number=None, invoice_date=None, total_amount=None)
        
        # 1. 提取开票日期（多种方式尝试）
        invoice_date = self._extract_date(lines)
        
        # 2. 提取发票号码（多种策略）
        invoice_number = self._extract_invoice_number(lines, invoice_date)
        
        # 3. 提取价税合计金额（增强匹配）
        total_amount = self._extract_amount(lines)
        
        return InvoiceInfo(
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            total_amount=total_amount
        )
    
    def _extract_date(self, lines):
        """提取开票日期，支持多种格式"""
        # 方式1: 标准格式 "YYYY年MM月DD日"
        for line in lines:
            if "年" in line and "月" in line and "日" in line:
                date_match = INVOICE_DATE_PATTERN.search(line)
                if date_match:
                    return date_match.group(0)
        
        # 方式2: 包含"开票日期"关键字的行
        for line in lines:
            if "开票日期" in line:
                # 尝试从该行提取日期
                date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', line)
                if date_match:
                    raw_date = date_match.group(1)
                    # 标准化为YYYY年MM月DD日格式
                    if '-' in raw_date or '/' in raw_date:
                        return raw_date.replace('-', '年').replace('/', '月') + '日'
                    else:
                        return raw_date
        
        # 方式3: 任何包含年月日的行
        for line in lines:
            if re.search(r'\d{4}.*年.*\d{1,2}.*月.*\d{1,2}.*日', line):
                date_match = re.search(r'(\d{4}.*年.*\d{1,2}.*月.*\d{1,2}.*日)', line)
                if date_match:
                    return date_match.group(1)
        
        return None
    
    def _extract_invoice_number(self, lines, invoice_date):
        """提取发票号码，使用多种策略"""
        
        # 策略1: 如果有日期，查找日期行附近的数字
        if invoice_date:
            for i, line in enumerate(lines):
                if invoice_date in line:
                    # 查找上一行
                    if i > 0:
                        prev_line = lines[i-1]
                        number_match = INVOICE_NUMBER_PATTERN.search(prev_line)
                        if number_match:
                            return number_match.group(0)
                    
                    # 查找下一行
                    if i < len(lines) - 1:
                        next_line = lines[i+1]
                        number_match = INVOICE_NUMBER_PATTERN.search(next_line)
                        if number_match:
                            return number_match.group(0)
        
        # 策略2: 查找包含发票号码关键字的行
        for line in lines:
            if any(keyword in line for keyword in ["发票号码", "号码", "发票编号", "Invoice Number"]):
                number_match = INVOICE_NUMBER_PATTERN.search(line)
                if number_match:
                    return number_match.group(0)
                # 如果没有找到长数字，尝试提取冒号后面的数字
                colon_match = re.search(r'[：:]\s*(\d{8,})', line)
                if colon_match:
                    return colon_match.group(1)
        
        # 策略3: 查找所有长数字，选择最可能是发票号码的
        long_numbers = []
        for line in lines:
            matches = INVOICE_NUMBER_PATTERN.findall(line)
            long_numbers.extend(matches)
        
        if long_numbers:
            # 优先选择长度最长的数字
            return max(long_numbers, key=len)
        
        return None
    
    def _extract_amount(self, lines):
        """提取价税合计金额，增强匹配"""
        # 优先级顺序：从高到低
        keywords_priority = [
            ["价税合计"],
            ["圆整"],
            ["合计"],
            ["金额"],
            ["总计"],
            ["应收"]
        ]
        
        for keywords in keywords_priority:
            for line in lines:
                if any(keyword in line for keyword in keywords):
                    # 查找金额模式（保留负号）
                    amount_match = re.search(r'¥\s*(-?\d+\.\d{2})', line)
                    if amount_match:
                        return amount_match.group(1)
                    
                    # 如果没找到¥符号，尝试查找纯数字金额（支持负号）
                    amount_match = re.search(r'(-?\d+\.\d{2})', line)
                    if amount_match:
                        return amount_match.group(1)
        
        # 最后尝试：查找任何包含货币符号的行（保留负号）
        for line in lines:
            if "¥" in line or "￥ " in line:
                # 保留负号：¥-323460.00 → -323460.00
                amount_match = re.search(r'¥\s*(-?\d+\.\d{2})', line)
                if amount_match:
                    return amount_match.group(1)  # 直接返回包含负号的金额
        
        return None

    
    def _update_progress(self, value: int, maximum: int, message: str) -> None:
        """线程安全地更新进度条和状态信息。"""

        def callback() -> None:
            self.progress.config(maximum=maximum if maximum else 1)
            self.progress.config(value=value)
            self.status_var.set(message)

        self.master.after(0, callback)

    def _show_completion(self, summary: str) -> None:
        """在处理结束后显示弹窗。"""

        def callback() -> None:
            messagebox.showinfo("整理完成", summary)

        self.master.after(0, callback)

    @staticmethod
    def _unique_path(target: Path) -> Path:
        """生成不与现有文件冲突的目标路径。"""

        if not target.exists():
            return target
        counter = 1
        while True:
            new_name = f"{target.stem}_{counter}{target.suffix}"
            candidate = target.with_name(new_name)
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _move_file(src: Path, dest: Path) -> None:
        """移动或重命名文件到目标路径。"""

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

    @staticmethod
    def _delete_file(path: Path) -> None:
        """删除重复文件。"""

        try:
            path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            if path.exists():
                path.unlink()


def main() -> None:
    root = tk.Tk()
    InvoiceOrganizerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
