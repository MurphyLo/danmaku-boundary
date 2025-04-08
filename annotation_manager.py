import json
import csv
import os
from PyQt5.QtWidgets import QListWidget, QMessageBox, QFileDialog

class AnnotationManager:
    def __init__(self, main_window):
        self.main_window = main_window  # Reference to the main VideoAnnotator window
        self.annotations = []
        self.temp_annotation = None

    def sort_annotations(self):
        """
        根据帧号进行排序：direct_cut 使用 frame，gradual 使用 start_frame
        """
        def annotation_sort_key(anno):
            if anno["type"] == "direct_cut":
                return anno["frame"]
            else:  # gradual
                return anno["start_frame"]
        self.annotations.sort(key=annotation_sort_key)

    def refresh_annotation_list(self):
        """
        根据当前 self.annotations 刷新列表显示
        """
        self.main_window.annotation_list.clear()
        for anno in self.annotations:
            if anno["type"] == "direct_cut":
                item_text = f"直接切换于 {anno['time']} (帧 {anno['frame']})"
            else:
                item_text = (
                    f"渐变过渡: {anno['start_time']} - {anno['end_time']} "
                    f"(帧 {anno['start_frame']} - {anno['end_frame']})"
                )
            self.main_window.annotation_list.addItem(item_text)

    def add_annotation_with_template(self, template_index):
        """使用指定模板添加标注"""
        if self.main_window.video_player.cap is None:
            return
        
        self.main_window.template_combo.setCurrentIndex(template_index)
        self.add_annotation()

    def add_annotation(self):
        """添加标注"""
        if self.main_window.video_player.cap is None:
            QMessageBox.warning(self.main_window, "警告", "请先打开视频文件。")
            return
        
        template_index = self.main_window.template_combo.currentIndex()
        current_frame = self.main_window.video_player.current_frame
        current_time = self.main_window.video_player.frame_to_time(current_frame)
        
        if template_index == 0:  # 模板1：直接切换
            annotation = {
                "type": "direct_cut",
                "time": current_time,
                "frame": current_frame
            }
            self.annotations.append(annotation)
            item_text = f"直接切换于 {current_time} (帧 {current_frame})"
            # self.main_window.annotation_list.addItem(item_text) # Handled by refresh
            self.main_window.status_label.setText(f"已添加: {item_text}")

            self.sort_annotations()
            try:
                new_index = self.annotations.index(annotation)
                self.refresh_annotation_list()
                new_item = self.main_window.annotation_list.item(new_index)
                if new_item:
                    self.main_window.annotation_list.setCurrentItem(new_item)
            except ValueError:
                # Should not happen, but refresh anyway
                self.refresh_annotation_list()

        elif template_index == 1:  # 模板2：渐变过渡
            if self.temp_annotation is None:  # 开始标注
                self.temp_annotation = {
                    "type": "gradual",
                    "start_time": current_time,
                    "start_frame": current_frame,
                    "end_time": None,
                    "end_frame": None
                }
                item_text = f"渐变过渡开始于 {current_time} (帧 {current_frame})"
                # Add temporary item to list visually
                self.main_window.annotation_list.addItem(item_text) 
                self.main_window.status_label.setText("已开始渐变过渡标注。请用Ctrl+2标记结束位置。")
            else:  # 结束标注
                if current_frame <= self.temp_annotation["start_frame"]:
                    QMessageBox.warning(self.main_window, "警告", "结束帧必须在开始帧之后。")
                    return
                
                self.temp_annotation["end_time"] = current_time
                self.temp_annotation["end_frame"] = current_frame
                # Store completed annotation before clearing temp
                completed_annotation = self.temp_annotation.copy()
                self.annotations.append(completed_annotation)
                # No need to explicitly remove the temporary item, refresh will handle it
                # self.main_window.annotation_list.takeItem(self.main_window.annotation_list.count() - 1)
                item_text = (f"渐变过渡: {self.temp_annotation['start_time']} - {current_time} "
                           f"(帧 {self.temp_annotation['start_frame']} - {current_frame})")
                # self.main_window.annotation_list.addItem(item_text) # Handled by refresh
                self.main_window.status_label.setText(f"已添加: {item_text}")
                self.temp_annotation = None # Clear temp annotation AFTER adding to list

                self.sort_annotations()
                try:
                    # Find the index of the completed annotation
                    new_index = self.annotations.index(completed_annotation)
                    self.refresh_annotation_list() # Refresh updates the list view
                    new_item = self.main_window.annotation_list.item(new_index)
                    if new_item:
                        self.main_window.annotation_list.setCurrentItem(new_item) # Select the new item
                except ValueError:
                     # Should not happen, but refresh anyway
                    self.refresh_annotation_list()

    def delete_annotation(self):
        """删除选中的标注"""
        current_row = self.main_window.annotation_list.currentRow()
        if current_row == -1:
            QMessageBox.warning(self.main_window, "警告", "请选择要删除的标注。")
            return
        
        # If deleting the temporary gradual annotation start marker
        if self.temp_annotation is not None and current_row == self.main_window.annotation_list.count() - 1:
            self.temp_annotation = None
            self.main_window.status_label.setText("已取消渐变过渡标注")
            self.main_window.annotation_list.takeItem(current_row) # Remove the temporary item
        elif current_row < len(self.annotations): # Make sure index is valid for self.annotations
            deleted_annotation = self.annotations.pop(current_row)
            self.main_window.status_label.setText(f"已删除于 {deleted_annotation.get('time', '') or deleted_annotation.get('start_time', '')} 的标注")
            # self.main_window.annotation_list.takeItem(current_row) # Handled by refresh
            self.sort_annotations()
            self.refresh_annotation_list()
        else:
            # This case should ideally not happen if list and data are in sync
             QMessageBox.warning(self.main_window, "警告", "选择的标注索引无效。")

    def clear_annotations(self):
        """清除所有标注"""
        if not self.annotations and self.temp_annotation is None:
            return
        
        reply = QMessageBox.question(self.main_window, "清除标注", 
                                    "确定要清除所有标注吗？",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.annotations = []
            self.main_window.annotation_list.clear()
            self.temp_annotation = None
            self.main_window.status_label.setText("已清除所有标注")

    def save_annotations(self):
        """保存标注"""
        if not self.annotations and self.temp_annotation is None:
            QMessageBox.warning(self.main_window, "警告", "没有标注可保存。")
            return
        
        if self.temp_annotation is not None:
            reply = QMessageBox.question(self.main_window, "未完成的标注", 
                                        "你有一个未完成的渐变过渡标注。要舍弃它吗？",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        try:
            default_name = ""
            if self.main_window.video_player.video_path:
                base_name = os.path.splitext(os.path.basename(self.main_window.video_player.video_path))[0]
                default_name = f"{base_name}_annotations"
            
            # 使用原生文件对话框
            dialog = QFileDialog(self.main_window, "保存标注", default_name, 
                                "CSV文件 (*.csv);;JSON文件 (*.json)")
            dialog.setOption(QFileDialog.DontUseNativeDialog, False)  # 强制使用原生对话框
            dialog.setAcceptMode(QFileDialog.AcceptSave)
            dialog.setFileMode(QFileDialog.AnyFile)
            dialog.setOption(QFileDialog.ReadOnly, True)  # 只读模式减少文件访问操作
            
            if dialog.exec_() != QFileDialog.Accepted:
                return
                
            file_path = dialog.selectedFiles()[0]
            filter_used = dialog.selectedNameFilter()
            
            if filter_used == "JSON文件 (*.json)" and not file_path.lower().endswith('.json'):
                file_path += '.json'
            elif filter_used == "CSV文件 (*.csv)" and not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.json':
                self.save_as_json(file_path)
            elif file_ext == '.csv':
                self.save_as_csv(file_path)
            else:
                QMessageBox.warning(self.main_window, "警告", "不支持的文件格式。请使用.json或.csv")
                return
            
            QMessageBox.information(self.main_window, "成功", f"标注已保存到 {file_path}")
            self.main_window.status_label.setText(f"已保存{len(self.annotations)}个标注到 {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(self.main_window, "错误", f"保存标注失败: {str(e)}")

    def load_annotations(self):
        """加载标注"""
        # 使用原生文件对话框
        try:
            dialog = QFileDialog(self.main_window, "加载标注", "", 
                               "CSV文件 (*.csv);;JSON文件 (*.json);;所有文件 (*)")
            dialog.setOption(QFileDialog.DontUseNativeDialog, False)  # 强制使用原生对话框
            dialog.setFileMode(QFileDialog.ExistingFile)
            dialog.setOption(QFileDialog.ReadOnly, True)  # 只读模式减少文件访问操作
            
            if dialog.exec_() != QFileDialog.Accepted:
                return
                
            file_path = dialog.selectedFiles()[0]
            
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.json':
                self.load_from_json(file_path)
            elif file_ext == '.csv':
                self.load_from_csv(file_path)
            else:
                QMessageBox.warning(self.main_window, "警告", "不支持的文件格式。请使用.json或.csv")
                return
            
            QMessageBox.information(self.main_window, "成功", f"已从 {file_path} 加载 {len(self.annotations)} 个标注")
            self.main_window.status_label.setText(f"已从 {os.path.basename(file_path)} 加载 {len(self.annotations)} 个标注")
        except Exception as e:
            # 已在load_from_json/csv中处理了错误显示，这里不需要重复显示
            pass

    def save_as_json(self, file_path):
        """将标注保存为JSON格式"""
        if not self.main_window.video_player.video_path:
            raise ValueError("未加载视频")
        
        video_info = {
            "filename": os.path.basename(self.main_window.video_player.video_path),
            "filepath": self.main_window.video_player.video_path,
            "frame_count": self.main_window.video_player.frame_count,
            "fps": self.main_window.video_player.fps,
            "duration": self.main_window.video_player.frame_to_time(self.main_window.video_player.frame_count)
        }
        
        data = {
            "video_info": video_info,
            "annotations": self.annotations # Only save completed annotations
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def save_as_csv(self, file_path):
        """将标注保存为CSV格式"""
        headers = ["type", "start_time", "start_frame", "end_time", "end_frame"]
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for anno in self.annotations: # Only save completed annotations
                row = {}
                if anno["type"] == "direct_cut":
                    row = {
                        "type": "direct_cut",
                        "start_time": anno["time"],
                        "start_frame": anno["frame"],
                        "end_time": "",
                        "end_frame": ""
                    }
                else:  # gradual
                    row = {
                        "type": "gradual",
                        "start_time": anno["start_time"],
                        "start_frame": anno["start_frame"],
                        "end_time": anno["end_time"],
                        "end_frame": anno["end_frame"]
                    }
                writer.writerow(row)

    def load_from_json(self, file_path):
        """从JSON文件加载标注"""
        try:
            # 清除现有标注先，避免文件读取错误时留下部分标注
            self.annotations = []
            self.main_window.annotation_list.clear()
            self.temp_annotation = None
            
            # 使用更高效的方式读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查是否需要加载视频 (不直接调用 open_video，让主窗口处理)
            load_associated_video = False
            associated_video_path = None
            if self.main_window.video_player.cap is None and 'video_info' in data and 'filepath' in data['video_info']:
                video_path_from_json = data['video_info']['filepath']
                if os.path.exists(video_path_from_json):
                    reply = QMessageBox.question(self.main_window, "加载视频", 
                                                f"是否加载关联的视频文件？\n{video_path_from_json}",
                                                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                    if reply == QMessageBox.Yes:
                        load_associated_video = True
                        associated_video_path = video_path_from_json
            
            # 加载标注
            if 'annotations' in data:
                self.annotations = data['annotations']
                
            self.sort_annotations()
            self.refresh_annotation_list()

            # If user agreed, tell main window to load the video AFTER annotations are loaded
            if load_associated_video and associated_video_path:
                 self.main_window.request_open_video(associated_video_path)
        except Exception as e:
            QMessageBox.critical(self.main_window, "错误", f"加载JSON标注失败: {str(e)}")
            # 确保出错时清空标注列表
            self.annotations = []
            self.main_window.annotation_list.clear()
            self.temp_annotation = None
            raise e  # 向上抛出异常以便主函数处理

    def load_from_csv(self, file_path):
        """从CSV文件加载标注"""
        try:
            # 清除现有标注先，避免文件读取错误时留下部分标注
            self.annotations = []
            self.main_window.annotation_list.clear()
            self.temp_annotation = None
            
            # 使用更高效的方式读取CSV
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        if row["type"] == "direct_cut":
                            annotation = {
                                "type": "direct_cut",
                                "time": row["start_time"],
                                "frame": int(row["start_frame"])
                            }
                        elif row["type"] == "gradual": # Check for gradual explicitly
                            annotation = {
                                "type": "gradual",
                                "start_time": row["start_time"],
                                "start_frame": int(row["start_frame"]),
                                "end_time": row["end_time"],
                                "end_frame": int(row["end_frame"])
                            }
                        else:
                            print(f"Skipping unknown annotation type in CSV: {row['type']}")
                            continue # Skip rows with unknown types
                            
                        self.annotations.append(annotation)
                    except KeyError as e:
                        print(f"Skipping row due to missing key: {e} in row {row}")
                    except ValueError as e:
                         print(f"Skipping row due to invalid integer conversion: {e} in row {row}")
            
            self.sort_annotations()
            self.refresh_annotation_list()
        except Exception as e:
            QMessageBox.critical(self.main_window, "错误", f"加载CSV标注失败: {str(e)}")
            # 确保出错时清空标注列表
            self.annotations = []
            self.main_window.annotation_list.clear()
            self.temp_annotation = None
            raise e  # 向上抛出异常以便主函数处理

    def jump_to_annotation(self, item):
        """双击标注项跳转到对应位置"""
        idx = self.main_window.annotation_list.row(item)
        
        if idx < 0 or idx >= len(self.annotations):
             # Check if it's the temporary annotation item
            if self.temp_annotation is not None and idx == self.main_window.annotation_list.count() - 1:
                target_frame = self.temp_annotation["start_frame"]
            else:
                return # Invalid index
        else:
            anno = self.annotations[idx]
            if anno["type"] == "direct_cut":
                target_frame = anno["frame"]
            else:  # gradual
                target_frame = anno["start_frame"]
        
        # Request main window to perform the jump
        self.main_window.seek_to_frame(target_frame)

    def reset(self):
        """ Resets annotations when a new video is loaded or cleared """
        self.annotations = []
        self.temp_annotation = None
        self.main_window.annotation_list.clear()
        # Optionally reset status label or let the main window handle it
        # self.main_window.status_label.setText("Annotations cleared") 