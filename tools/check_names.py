import torch
# 加载你的权重文件（对应你项目中的pt/best.pt）
model = torch.load('./pt/best.pt', map_location='cpu')
# 提取类别名称
if 'model' in model.keys():
    # 新版YOLOv5权重格式
    names = model['model'].names if hasattr(model['model'], 'names') else model['model'].module.names
else:
    # 旧版格式（备用）
    names = model.get('names', [])

# 打印类别名称（就是你界面上显示的病虫害名称）
print("你的模型类别名称列表：")
for idx, name in enumerate(names):
    print(f"类别ID {idx}：{name}")