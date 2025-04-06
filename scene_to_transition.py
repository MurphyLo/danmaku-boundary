import os
import glob
import csv
import datetime
import re
import argparse

def extract_bvid_idx(filename):
    """从文件名中提取BV号和索引"""
    base_name = os.path.basename(filename)
    match = re.match(r'(BV[0-9a-zA-Z]+)_(\d+)_scenes\.txt', base_name)
    if match:
        return match.group(1), match.group(2)
    return base_name.replace('_scenes.txt', ''), ''

def process_scenes_file(file_path, frame_gap_threshold=1):
    """处理场景文件，将镜头边界转换为转场信息"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    transitions = []
    scenes = []
    
    # 跳过头部信息，寻找场景列表
    start_idx = 0
    for i, line in enumerate(lines):
        if "场景列表" in line:
            start_idx = i + 1
            break
    
    print(f"开始提取场景信息，从第 {start_idx} 行开始")
    
    # 提取场景信息
    for i in range(start_idx, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        
        parts = line.split(',')
        if len(parts) == 2:
            start_frame = int(parts[0].strip())
            end_frame = int(parts[1].strip())
            scenes.append((start_frame, end_frame))
    
    print(f"共提取到 {len(scenes)} 个场景")
    
    # 转换为转场信息
    for i in range(len(scenes) - 1):
        current_end = scenes[i][1]
        next_start = scenes[i+1][0]
        
        frame_gap = next_start - current_end - 1
        
        if frame_gap <= frame_gap_threshold:
            # 直接切换 - 不需要结束帧
            transitions.append(("direct_cut", current_end, None))
            print(f"场景 {i} 到 {i+1} 的过渡为直接切换，间隔 {frame_gap} 帧")
        else:
            # 渐变过渡 - 需要开始和结束帧
            transitions.append(("gradual", current_end, next_start))
            print(f"场景 {i} 到 {i+1} 的过渡为渐变过渡，间隔 {frame_gap} 帧")
    
    print(f"共生成 {len(transitions)} 个转场记录")
    return transitions

def frame_to_time(frame, fps=24):
    """将帧数转换为时间格式 (HH:MM:SS)"""
    total_seconds = frame / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}"

def save_annotations(transitions, output_path, fps=24):
    """保存转场信息到CSV文件"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['type', 'start_time', 'start_frame', 'end_time', 'end_frame'])
        
        for transition in transitions:
            transition_type, start_frame, end_frame = transition
            
            # 对于直接切换，只有开始时间和帧数
            if transition_type == "direct_cut":
                writer.writerow([
                    transition_type,
                    frame_to_time(start_frame, fps),
                    start_frame,
                    "",
                    ""
                ])
            # 对于渐变过渡，有开始和结束时间与帧数
            else:
                writer.writerow([
                    transition_type,
                    frame_to_time(start_frame, fps),
                    start_frame,
                    frame_to_time(end_frame, fps),
                    end_frame
                ])
    
    print(f"已将转场信息保存到: {output_path}")

def find_scenes_files(directory):
    """在指定目录中查找所有_scenes.txt文件"""
    pattern = os.path.join(directory, "**", "*_scenes.txt")
    return glob.glob(pattern, recursive=True)

def main():
    # 获取当前时间作为时间戳，格式为mmdd_hhmm
    timestamp = datetime.datetime.now().strftime("%m%d_%H%M")
    default_output_dir = os.path.join("annotations", timestamp)
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="将场景边界文件转换为转场标注文件")
    parser.add_argument("--fps", type=float, default=24.0, help="视频的帧率，默认为24.0")
    parser.add_argument("--gap", type=int, default=1, help="判断是否为直接切换的帧间隔阈值，默认为1")
    parser.add_argument("--output", type=str, default=default_output_dir, help=f"输出目录，默认为{default_output_dir}")
    parser.add_argument("--input", type=str, nargs="+", help="输入的_scenes.txt文件路径，不指定则搜索指定目录下的所有文件")
    parser.add_argument("--dir", type=str, default=".", help="要搜索的目录，默认为当前目录")
    args = parser.parse_args()
    
    # 使用指定的输出目录
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取场景文件列表
    if args.input:
        # 如果指定了具体文件，则使用这些文件
        scenes_files = args.input
    else:
        # 否则搜索指定目录下的所有_scenes.txt文件
        scenes_files = find_scenes_files(args.dir)
    
    if not scenes_files:
        print(f"在目录 '{args.dir}' 下没有找到任何_scenes.txt文件，请确保文件存在")
        return
    
    print(f"找到 {len(scenes_files)} 个场景文件: {scenes_files}")
    print(f"使用帧率: {args.fps}, 直接切换帧间隔阈值: {args.gap}")
    print(f"输出目录: {output_dir}")
    
    for file_path in scenes_files:
        print(f"\n处理文件: {file_path}")
        
        # 从文件名中提取BV号和索引
        bvid, idx = extract_bvid_idx(file_path)
        print(f"提取到BV号: {bvid}, 索引: {idx}")
        
        # 生成输出文件名
        if idx:
            output_filename = f"{bvid}_{idx}_annotations.csv"
        else:
            output_filename = f"{bvid}_annotations.csv"
        
        output_path = os.path.join(output_dir, output_filename)
        
        # 处理场景文件并保存结果
        transitions = process_scenes_file(file_path, frame_gap_threshold=args.gap)
        save_annotations(transitions, output_path, fps=args.fps)
        
        print(f"文件 {file_path} 处理完成，结果保存到 {output_path}")

if __name__ == "__main__":
    main() 