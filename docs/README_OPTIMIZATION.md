# 项目优化说明

## 已完成的优化

### 1. ✅ 清理缓存文件
- 删除所有 `__pycache__` 目录
- 删除所有 `.pyc` 编译文件
- 减小项目体积，避免版本冲突

### 2. ✅ 添加 .gitignore
- 防止提交 Python 缓存文件
- 排除大型模型权重文件（.pt, .pth）
- 排除运行结果目录（runs/, result/）
- 排除 IDE 配置文件

### 3. ✅ 优化 requirements.txt
- 添加版本约束（使用 >= 确保兼容性）
- 分类整理依赖（核心、PyTorch、GUI、工具等）
- 添加注释说明各依赖用途

### 4. ✅ 重构 main.py
- **字体加载优化**：提取重复的 try-except 为 `load_chinese_font()` 函数
- **错误处理改进**：所有异常都显示异常类型，便于调试
- **模块导入优化**：ImportError 显示具体错误信息
- **代码可维护性**：提取魔法数字为常量（FONT_SIZE, FONT_PATHS）

## 代码改进详情

### 字体加载优化（第 83-98 行）
**优化前**：嵌套的 try-except 块，重复代码
```python
try:
    font = ImageFont.truetype("simhei.ttf", 20, encoding="utf-8")
except:
    try:
        font = ImageFont.truetype("/usr/share/fonts/...", 20)
    except:
        ...
```

**优化后**：提取为独立函数，配置驱动
```python
def load_chinese_font(size=FONT_SIZE):
    for font_path in FONT_PATHS:
        try:
            return ImageFont.truetype(font_path, size, encoding="utf-8")
        except (OSError, IOError):
            continue
    return ImageFont.load_default()
```

### 错误处理优化
**改进点**：
- 捕获具体的 `ImportError` 而不是裸 `except`
- 显示异常类型 `e.__class__.__name__`
- 提供更详细的错误上下文

## 建议进一步优化

### 1. 配置管理（可选）
可以将 CONFIG 字典移到独立的配置文件：
```
config/
  ├── default.json  # 默认配置
  └── local.json    # 本地覆盖（已在 .gitignore 中）
```

### 2. 日志系统（可选）
替换 print 为 logging 模块：
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

### 3. 类型注解（可选）
为关键函数添加类型提示，提高代码可读性：
```python
def load_chinese_font(size: int = FONT_SIZE) -> ImageFont.FreeTypeFont:
    ...
```

### 4. 单元测试（推荐）
为核心功能添加测试：
- 字体加载测试
- 配置解析测试
- 数据传输测试

### 5. 性能优化（如需要）
- 使用 `@lru_cache` 缓存字体加载
- 优化帧处理频率
- 使用线程池处理 HTTP 请求

## 项目结构说明

- `main.py` (566 行) - 主入口，PyQt5 GUI + 检测线程
- `apprcc_rc.py` (194K 行) - PyQt5 自动生成的资源文件（图标等）
- `transport/` - 数据传输模块（串口、HTTP、RTMP）
- `models/` - YOLO 模型定义
- `utils/` - 工具函数
- `pt/` - 模型权重文件目录

## 使用建议

1. **环境设置**：
   ```bash
   pip install -r requirements.txt
   ```

2. **配置修改**：
   在 `main.py` 顶部的 CONFIG 字典中修改参数

3. **运行程序**：
   ```bash
   python main.py
   # 或带参数运行
   python main.py --source 0 --auto-start
   ```

4. **Git 初始化**（如果还没有）：
   ```bash
   git init
   git add .
   git commit -m "优化项目结构和代码质量"
   ```
