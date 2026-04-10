import cv2
import numpy as np
import os  # 新增 os 模块用于处理路径

def snap_coordinates(coords, threshold=10):
    """
    坐标吸附：让坐标强制对齐到网格，消除抖动
    """
    if len(coords) == 0:
        return {}
    
    coords = np.array(coords)
    sorted_indices = np.argsort(coords)
    sorted_coords = coords[sorted_indices]
    
    groups = []
    if len(coords) > 0:
        current_group = [sorted_coords[0]]
        for c in sorted_coords[1:]:
            if c - current_group[-1] < threshold:
                current_group.append(c)
            else:
                groups.append(current_group)
                current_group = [c]
        groups.append(current_group)
    
    mapping = {}
    for g in groups:
        mean_val = int(np.mean(g))
        for val in g:
            mapping[val] = mean_val
            
    return mapping

def get_straightened_contour(cnt, epsilon_factor=0.005, snap_threshold=15):
    """
    将轮廓拉直为完美的横平竖直多边形
    """
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, epsilon_factor * peri, True)
    
    points = approx.reshape(-1, 2)
    xs = points[:, 0]
    ys = points[:, 1]
    
    x_map = snap_coordinates(xs, threshold=snap_threshold)
    y_map = snap_coordinates(ys, threshold=snap_threshold)
    
    new_points = []
    for x, y in points:
        new_points.append([x_map[x], y_map[y]])
        
    return np.array(new_points, dtype=np.int32).reshape(-1, 1, 2)

def main():
    # --- 1. 自动定位路径 (关键修改) ---
    # 获取当前脚本(photo_pro.py)所在的文件夹绝对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 拼接出图片的完整路径，确保一定能找到
    input_filename = 'app_icon.png'  # 这里改为你截图中的文件名
    input_path = os.path.join(script_dir, input_filename)
    output_path = os.path.join(script_dir, 'app_icon_colored.png')
    
    print(f"正在从以下路径读取图片:\n{input_path}")
    
    # --- 2. 颜色设置 (可修改) ---
    COLOR_FRAME = (0, 255, 0, 255)  # 边框颜色 (BGRA) -  绿色
    COLOR_PLUS = (0, 0, 255, 255)   # 加号颜色 (BGRA) - 红色
    
    # 读取图片
    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print("❌ 错误：依然无法读取图片！请检查文件名是否正确，或者图片是否损坏。")
        return

    # --- 3. 图像处理 ---
    # 提取Mask
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
        _, binary = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 创建透明画布
    h, w = img.shape[:2]
    canvas = np.zeros((h, w, 4), dtype=np.uint8)

    print(f"检测到 {len(contours)} 个轮廓")

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100: continue # 忽略噪点
            
        # 自动判定：大的是框，小的是加号
        if area > 10000:
            color = COLOR_FRAME
            obj_name = "边框"
        else:
            color = COLOR_PLUS
            obj_name = "加号"
        
        print(f"正在处理: {obj_name} (面积: {area})")
        
        try:
            # 拉直轮廓
            straight_cnt = get_straightened_contour(cnt, epsilon_factor=0.005, snap_threshold=15)
            # 绘制
            cv2.drawContours(canvas, [straight_cnt], -1, color, -1)
        except Exception as e:
            print(f"处理 {obj_name} 时出错: {e}")

    # 保存
    cv2.imwrite(output_path, canvas)
    print(f"✅ 处理完成，结果已保存至:\n{output_path}")

if __name__ == "__main__":
    main()