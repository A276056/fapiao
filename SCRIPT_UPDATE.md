# 发票信息提取脚本更新说明

## 更新内容

根据README.md文档的要求，重新编写了发票信息提取逻辑，主要变更如下：

### 1. PDF文本提取库变更
- **原实现**: 使用 `PyPDF2` 库
- **新实现**: 使用 `pdfplumber` 库
- **优势**: pdfplumber提供更准确的文本提取和更好的布局保持

### 2. 信息提取逻辑变更
- **原实现**: 基于正则表达式关键字匹配
- **新实现**: 基于行号定位的语义特征识别

#### 具体提取流程：
1. **开票日期**: 查找包含"年""月""日"的行，使用正则 `r"\d{4}年\d{1,2}月\d{1,2}日"` 提取
2. **发票号码**: 取开票日期行的上一行，使用正则 `r"\d{15,20}"` 提取15-20位数字
3. **价税合计**: 搜索包含"圆整"或"价税合计"的行，使用正则 `r"¥\s*\d+\.\d{2}"` 提取金额

### 3. 数据结构变更
```python
# 原数据结构
@dataclass
class InvoiceInfo:
    date: Optional[str]      # 开票日期
    code: Optional[str]      # 发票代码  
    number: Optional[str]    # 发票号码
    amount: Optional[str]    # 金额

# 新数据结构
@dataclass  
class InvoiceInfo:
    invoice_number: Optional[str]  # 发票号码
    invoice_date: Optional[str]    # 开票日期
    total_amount: Optional[str]    # 价税合计
```

### 4. 去重逻辑变更
- **原实现**: 按发票代码+号码组合去重
- **新实现**: 仅按发票号码去重

### 5. 文件命名变更
- **原实现**: `{日期}_{代码}-{号码}.pdf`
- **新实现**: `{日期}_{号码}.pdf`

## 依赖要求

新版本需要以下Python包：
```
pdfplumber>=0.5.28
pandas>=1.3.0  
openpyxl>=3.0.9
```

安装命令：
```bash
pip install -r requirements.txt
```

## 测试方法

使用提供的测试脚本验证新功能：
```bash
python scripts/test_invoice_extractor.py
```

## 兼容性说明

- 保持原有的GUI界面不变
- 保持原有的文件组织结构（按月份分文件夹）
- 保持原有的Excel日志输出格式
- 新实现与README文档描述的流程完全一致