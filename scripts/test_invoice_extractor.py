#!/usr/bin/env python3
"""测试发票信息提取功能"""

import sys
from pathlib import Path

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from invoice_gui_tool import InvoiceOrganizerGUI, InvoiceInfo

def test_extract_invoice_info():
    """测试发票信息提取功能"""
    
    # 创建GUI实例以访问提取方法
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    gui = InvoiceOrganizerGUI(root)
    
    # 测试路径（可以是PDF文件或包含PDF的文件夹）
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
    else:
        test_path = input("请输入PDF发票文件路径或包含发票的文件夹路径: ").strip()
    
    if not test_path:
        print("未提供测试路径")
        return
        
    path = Path(test_path)
    if not path.exists():
        print(f"路径不存在: {path}")
        return
    
    # 如果是文件夹，查找其中的PDF文件
    if path.is_dir():
        pdf_files = list(path.glob("*.pdf"))
        if not pdf_files:
            print(f"文件夹中未找到PDF文件: {path}")
            return
        print(f"找到 {len(pdf_files)} 个PDF文件，将测试第一个文件")
        pdf_path = pdf_files[0]
    else:
        pdf_path = path
        
    try:
        print(f"正在提取发票信息: {pdf_path}")
        info = gui.extract_invoice_info(pdf_path)
        
        print("\n=== 提取结果 ===")
        print(f"发票号码: {info.invoice_number}")
        print(f"开票日期: {info.invoice_date}")
        print(f"价税合计: {info.total_amount}")
        
        # 验证结果完整性
        if info.invoice_number and info.invoice_date and info.total_amount:
            print("\n✅ 提取成功，信息完整")
        else:
            print("\n⚠️  信息不完整")
            if not info.invoice_number:
                print("- 缺少发票号码")
            if not info.invoice_date:
                print("- 缺少开票日期")
            if not info.total_amount:
                print("- 缺少价税合计")
                
    except Exception as e:
        print(f"❌ 提取失败: {e}")
    
    finally:
        root.destroy()

if __name__ == "__main__":
    test_extract_invoice_info()