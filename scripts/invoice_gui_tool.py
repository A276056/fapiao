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
from PyPDF2 import PdfReader
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# 正则表达式模式
INVOICE_DATE_PATTERN = re.compile(r"开票日期[:：]?\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})")
INVOICE_CODE_PATTERN = re.compile(r"发票代码[:：]?\s*(\d{12})")
INVOICE_NUMBER_PATTERN = re.compile(r"发票号码[:：]?\s*(\d{8,20})")
INVOICE_AMOUNT_PATTERN = re.compile(r"合计[:：]?\s*([\d,.]+)")


@dataclass
class InvoiceInfo:
    """保存单份发票提取到的信息。"""

    date: Optional[str]
    code: Optional[str]
    number: Optional[str]
    amount: Optional[str]


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
            self.master.after(0, lambda: messagebox.showerror("处理失败", str(exc)))
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
        seen_keys: Dict[Tuple[str, str], Path] = {}
        duplicates_removed = 0
        renamed_count = 0
        missing_info_count = 0

        for index, pdf_path in enumerate(pdf_files, start=1):
            self._update_progress(index - 1, total_files, f"正在处理：{pdf_path.name}")

            try:
                info = self.extract_invoice_info(pdf_path)
            except Exception:
                info = InvoiceInfo(date=None, code=None, number=None, amount=None)

            if info.code and info.number:
                key = (info.code, info.number)
                if key in seen_keys:
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
                seen_keys[key] = pdf_path

            if info.date and info.code and info.number:
                display_date = self.format_display_date(info.date)
                new_name = f"{display_date}_{info.code}-{info.number}.pdf"
                dest_dir = source_dir / info.date[:6]
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = self._unique_path(dest_dir / new_name)
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
        """从 PDF 文件中提取发票信息。"""

        reader = PdfReader(str(pdf_path))
        text_content = []
        for page in reader.pages:
            try:
                text_content.append(page.extract_text() or "")
            except Exception:
                text_content.append("")
        text = "\n".join(text_content)

        date_match = INVOICE_DATE_PATTERN.search(text)
        code_match = INVOICE_CODE_PATTERN.search(text)
        number_match = INVOICE_NUMBER_PATTERN.search(text)
        amount_match = INVOICE_AMOUNT_PATTERN.search(text)

        normalized_date = self.normalize_date(date_match.group(1) if date_match else None)
        code = code_match.group(1) if code_match else None
        number = number_match.group(1) if number_match else None
        amount = amount_match.group(1) if amount_match else None

        return InvoiceInfo(date=normalized_date, code=code, number=number, amount=amount)

    @staticmethod
    def normalize_date(raw_date: Optional[str]) -> Optional[str]:
        """将日期标准化为 YYYYMMDD 格式。"""

        if not raw_date:
            return None
        cleaned = raw_date.strip()
        cleaned = cleaned.replace("年", "-").replace("月", "-").replace("日", "")
        cleaned = cleaned.replace("/", "-").replace(".", "-")
        parts = re.findall(r"\d+", cleaned)
        if len(parts) != 3:
            return None
        year, month, day = parts
        try:
            year_int = int(year)
            month_int = int(month)
            day_int = int(day)
        except ValueError:
            return None
        if month_int < 1 or month_int > 12 or day_int < 1 or day_int > 31:
            return None
        return f"{year_int:04d}{month_int:02d}{day_int:02d}"

    @staticmethod
    def format_display_date(normalized_date: str) -> str:
        """将 YYYYMMDD 日期格式化为 YYYY年MM月DD日。"""

        if len(normalized_date) != 8 or not normalized_date.isdigit():
            return normalized_date
        return (
            f"{normalized_date[:4]}年"
            f"{normalized_date[4:6]}月"
            f"{normalized_date[6:8]}日"
        )

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
