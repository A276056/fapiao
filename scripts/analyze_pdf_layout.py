#!/usr/bin/env python3
"""分析PDF发票的排版特征和内容结构"""

import sys
import re
from pathlib import Path
import pdfplumber

def analyze_pdf_structure(pdf_path):
    """分析PDF文件的结构特征"""
    
    print(f"\n=== 分析文件: {pdf_path.name} ===")
    
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"\n--- 第 {page_num} 页 ---")
                text = page.extract_text()
                if not text:
                    print("  无文本内容")
                    continue
                
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                print(f"  总行数: {len(lines)}")
                
                # 分析关键内容所在的行
                print("\n  关键内容分析:")
                for i, line in enumerate(lines):
                    line_lower = line.lower()
                    markers = []
                    
                    if "年" in line and "月" in line and "日" in line:
                        markers.append("日期")
                    if any(keyword in line for keyword in ["发票号码", "号码", "number"]):
                        markers.append("发票号码关键词")
                    if re.search(r'\d{15,20}', line):
                        markers.append("长数字(可能是发票号码)")
                    if any(keyword in line for keyword in ["圆整", "价税合计", "合计", "金额"]):
                        markers.append("金额关键词")
                    if "¥" in line or "￥ " in line:
                        markers.append("货币符号")
                    if re.search(r'¥\s*\d+\.\d{2}', line):
                        markers.append("完整金额格式")
                    
                    if markers:
                        print(f"    行 {i+1:2d}: [{', '.join(markers)}] {line}")
                
                # 如果行数不多，显示所有内容
                if len(lines) <= 20:
                    print("\n  完整内容:")
                    for i, line in enumerate(lines):
                        print(f"    {i+1:2d}: {line}")
                else:
                    print("\n  前10行和后10行:")
                    for i, line in enumerate(lines[:10]):
                        print(f"    {i+1:2d}: {line}")
                    print("    ...")
                    for i, line in enumerate(lines[-10:], len(lines)-9):
                        print(f"    {i:2d}: {line}")
                        
    except Exception as e:
        print(f"  ❌ 分析失败: {e}")

def main():
    """主函数"""
    
    test_path = input("请输入PDF文件路径或包含PDF的文件夹路径: ").strip()
    if not test_path:
        print("未提供路径")
        return
        
    path = Path(test_path)
    if not path.exists():
        print(f"路径不存在: {path}")
        return
    
    # 获取要分析的PDF文件列表
    if path.is_dir():
        pdf_files = list(path.glob("*.pdf"))[:5]  # 最多分析5个文件
        if not pdf_files:
            print("文件夹中未找到PDF文件")
            return
        print(f"将分析 {len(pdf_files)} 个PDF文件")
    else:
        pdf_files = [path]
    
    # 分析每个文件
    for pdf_file in pdf_files:
        analyze_pdf_structure(pdf_file)
    
    print("\n" + "="*50)
    print("分析完成！请查看上述输出来了解不同PDF的排版特征。")

if __name__ == "__main__":
    main()