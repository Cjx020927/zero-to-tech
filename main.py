"""
打地鼠自动瞄准脚本
- 截屏 -> 模板匹配 -> NMS 去重 -> 模拟点击
- 多目标同时点击（每只地鼠独立冷却）
- 识别窗口实时显示绿色框（看到识别效果）
- 命令行参数：--threshold / --monitor / --start / --no-view
"""
import cv2
import numpy as np
import pyautogui as pa
from mss import mss
import time
import argparse
import sys

# ---- 默认参数 ----
TEMPLATE_PATH = "mouse.png"
DEFAULT_THRESHOLD = 0.75           # 模板匹配置信度阈值
CLICK_COOLDOWN = 0.3               # 同一地鼠点击冷却（秒）
CLICK_DIST_THRESHOLD = 25          # 距离阈值，小于此值视为同一地鼠（用于 NMS/冷却）
# 默认游戏区域（左上角 x,y + 宽高）
DEFAULT_MONITOR = {"top": 149, "left": 36, "width": 675, "height": 675}


def parse_args():
    p = argparse.ArgumentParser(description="打地鼠自动瞄准脚本")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help=f"匹配置信度阈值 (0~1)，默认 {DEFAULT_THRESHOLD}")
    p.add_argument("--monitor", type=str, default=None,
                   help='游戏区域，格式 "left,top,width,height"，例如 "36,149,675,675"'
                        '；不传则使用默认值或自动选择主屏窗口')
    p.add_argument("--start", type=str, default=None,
                   help='开始按钮坐标 "x,y"，脚本启动后自动点击该坐标开始游戏')
    p.add_argument("--no-view", action="store_true",
                   help="不显示识别可视化窗口（更快）")
    p.add_argument("--template", type=str, default=TEMPLATE_PATH,
                   help=f"地鼠模板图片路径，默认 {TEMPLATE_PATH}")
    return p.parse_args()


def nms(points, scores, dist_thresh):
    """简单非极大值抑制：按分数从高到低，剔除距离过近的重复框。
    返回 [(x, y, score), ...]
    """
    if len(points) == 0:
        return []
    order = np.argsort(scores)[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append((int(points[i, 0]), int(points[i, 1]), float(scores[i])))
        if order.size == 1:
            break
        rest = order[1:]
        dx = np.abs(points[rest, 0] - points[i, 0])
        dy = np.abs(points[rest, 1] - points[i, 1])
        mask = (dx < dist_thresh) & (dy < dist_thresh)
        order = rest[~mask]
    return keep


def main():
    args = parse_args()

    # 解析游戏区域
    if args.monitor:
        try:
            left, top, w, h = [int(x) for x in args.monitor.split(",")]
            monitor = {"left": left, "top": top, "width": w, "height": h}
        except Exception:
            print('参数 --monitor 格式错误，应为 "left,top,width,height"')
            sys.exit(1)
    else:
        monitor = DEFAULT_MONITOR.copy()

    # 读取地鼠模板
    template = cv2.imread(args.template, cv2.IMREAD_COLOR)
    if template is None:
        print(f'错误：找不到模板图片 {args.template}！请截图地鼠露头图片放到程序同目录')
        sys.exit(1)
    t_h, t_w = template.shape[:2]
    print(f"模板尺寸: {t_w}x{t_h}")
    print(f"游戏区域: left={monitor['left']}, top={monitor['top']}, "
          f"width={monitor['width']}, height={monitor['height']}")
    print(f"匹配置信度阈值: {args.threshold}")
    print(f"冷却时间: {CLICK_COOLDOWN}s, 距离阈值: {CLICK_DIST_THRESHOLD}px")
    print("程序启动！按键盘 q 退出识别窗口")

    # 自动点击开始按钮
    if args.start:
        try:
            sx, sy = [int(x) for x in args.start.split(",")]
            print(f"点击开始按钮：({sx}, {sy})")
            pa.click(sx, sy)
            time.sleep(1.0)
        except Exception:
            print('参数 --start 格式错误，应为 "x,y"')

    sct = mss()
    # 每只地鼠最近的点击时间记录：坐标 -> 上次点击时间戳
    last_click = []  # 列表项: (x, y, t)
    hit_count = 0
    start_ts = time.time()

    try:
        while True:
            screen_img = np.array(sct.grab(monitor))
            screen_img = cv2.cvtColor(screen_img, cv2.COLOR_BGRA2BGR)

            # 模板匹配
            result = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)
            loc = np.where(result >= args.threshold)

            if len(loc[0]) > 0:
                # 收集候选点（地鼠中心，相对于 monitor 左上）
                pts = np.column_stack((loc[1] + t_w // 2, loc[0] + t_h // 2)).astype(np.int32)
                scores = result[loc]
                # NMS 去除重复框
                moles = nms(pts, scores, CLICK_DIST_THRESHOLD)
            else:
                moles = []

            now = time.time()
            for (mx_rel, my_rel, score) in moles:
                # 转换为屏幕绝对坐标
                abs_x = monitor["left"] + mx_rel
                abs_y = monitor["top"] + my_rel

                # 冷却判断：与最近点击的地鼠坐标比较
                too_soon = False
                for (px, py, pt) in last_click:
                    if (abs(abs_x - px) < CLICK_DIST_THRESHOLD and
                            abs(abs_y - py) < CLICK_DIST_THRESHOLD and
                            now - pt < CLICK_COOLDOWN):
                        too_soon = True
                        break
                if too_soon:
                    continue

                pa.click(abs_x, abs_y)
                last_click.append((abs_x, abs_y, now))
                hit_count += 1
                print(f"[{hit_count:04d}] 点击地鼠：x={abs_x}, y={abs_y}, 置信度={score:.2f}")

            # 清理 2 秒前的冷却记录，避免列表无限增长
            last_click = [rec for rec in last_click if now - rec[2] < 2.0]

            # 识别可视化（绿色矩形 + 中心点）
            if not args.no_view:
                view = screen_img.copy()
                for (mx_rel, my_rel, _score) in moles:
                    cv2.rectangle(view,
                                  (mx_rel - t_w // 2, my_rel - t_h // 2),
                                  (mx_rel + t_w // 2, my_rel + t_h // 2),
                                  (0, 255, 0), 2)
                    cv2.circle(view, (mx_rel, my_rel), 4, (0, 0, 255), -1)
                cv2.putText(view, f"hits:{hit_count}", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imshow("view", view)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        duration = time.time() - start_ts
        rate = hit_count / duration if duration > 0 else 0
        print(f"\n程序结束 - 总点击 {hit_count} 次，运行 {duration:.1f}s，平均 {rate:.2f} 次/秒")


if __name__ == "__main__":
    main()
