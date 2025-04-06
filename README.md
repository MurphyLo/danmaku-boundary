# B站慕课视频内课件切换边界标注工具

## 简介

这是一个用于标注B站慕课视频中PPT课件切换边界的工具，基于PyQt5和OpenCV开发。用于标注视频中的直接切换和渐变过渡PPT切换边界，并将标注结果保存为JSON或CSV格式。

## 功能特点

- 视频播放控制（播放、暂停、跳转）
- 两种标注模式：
  - 直接切换（课件直接切换到下一页）
  - 渐变过渡（课件带动画效果的过渡）
- 标注列表管理（添加、删除、清除）
- 键盘快捷键支持
- 标注数据导入导出（JSON/CSV格式）
- 直观的用户界面

## 安装要求

- Python 3.6+
- PyQt5
- OpenCV (cv2)
- NumPy

安装依赖：

```
pip install PyQt5 opencv-python numpy
```

## 使用方法

1. 运行程序：
   ```
   python main.py
   ```

2. 打开视频文件（菜单"文件" -> "打开视频"或点击"打开视频"按钮）

3. 使用播放控制按钮或快捷键浏览视频

4. 标注镜头边界：
   - 直接切换：到达切换点时按Ctrl+1或选择模板1并点击"添加标注"
   - 渐变过渡：在过渡开始处按Ctrl+2，然后在过渡结束处再次按Ctrl+2

5. 保存标注（菜单"文件" -> "保存标注"或点击"保存标注"按钮）

## 快捷键

| 快捷键 | 功能 |
|-------|------|
| 空格 | 播放/暂停 |
| 右箭头 | 前进5秒 |
| 左箭头 | 后退5秒 |
| Alt+右箭头 | 前进1秒 |
| Alt+左箭头 | 后退1秒 |
| Shift+右箭头 | 前进5帧 |
| Shift+左箭头 | 后退5帧 |
| Ctrl+1 | 添加直接切换标注 |
| Ctrl+2 | 添加/完成渐变过渡标注 |
| Delete | 删除选中的标注 |
| Ctrl+O | 打开视频 |
| Ctrl+S | 保存标注 |
| Ctrl+L | 加载标注 |

## 标注格式

### JSON格式

```json
{
  "video_info": {
    "filename": "视频文件名",
    "filepath": "视频文件路径",
    "frame_count": 总帧数,
    "fps": 帧率,
    "duration": "总时长"
  },
  "annotations": [
    {
      "type": "direct_cut",
      "time": "00:00:10",
      "frame": 300
    },
    {
      "type": "gradual",
      "start_time": "00:00:20",
      "start_frame": 600,
      "end_time": "00:00:22",
      "end_frame": 660
    }
  ]
}
```

### CSV格式

CSV文件包含以下列：
- type: 标注类型 (direct_cut 或 gradual)
- start_time: 开始时间
- start_frame: 开始帧
- end_time: 结束时间（渐变过渡）
- end_frame: 结束帧（渐变过渡）

## 代码结构

项目采用模块化设计，分为以下几个主要文件：

### 核心文件

- **main.py**: 应用程序入口，初始化Qt应用和主窗口
- **video_annotator.py**: 主窗口类，整合其他组件并提供用户界面
- **video_player.py**: 封装视频播放相关功能
- **annotation_manager.py**: 处理标注的创建、管理和持久化
- **ui_components.py**: 自定义UI控件

### 模块关系

```
main.py
  └── VideoAnnotator (video_annotator.py)
        ├── VideoPlayer (video_player.py)
        ├── AnnotationManager (annotation_manager.py)
        └── UI Components (ui_components.py)
```

## 开发指南

### 扩展功能

1. **添加新的标注类型**:
   - 在`annotation_manager.py`中扩展标注数据结构
   - 更新UI以支持新的标注类型

2. **自定义UI组件**:
   - 在`ui_components.py`中添加新的控件类
   - 在`video_annotator.py`中使用新组件

3. **增加导出格式**:
   - 在`annotation_manager.py`中添加新的导出方法

### 编码规范

- 使用PEP 8风格指南
- 为所有类和方法编写文档字符串
- 使用有意义的变量名和函数名

### 测试

建议为各个模块编写单元测试，尤其是以下方面：
- 视频加载和处理
- 标注数据的序列化和反序列化
- UI交互

## 许可证

MIT