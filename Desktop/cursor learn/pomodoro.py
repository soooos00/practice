#!/usr/bin/env python3
"""
番茄钟 (Pomodoro Timer) - 桌面番茄钟应用
==========================================
纯 Python + tkinter 实现，零外部依赖。
功能：25分钟专注 / 5分钟短休息 / 15分钟长休息
     + 系统托盘 + 声音提醒
"""

import tkinter as tk
from tkinter import ttk
import winsound
import ctypes
from ctypes import wintypes
import threading
import queue
import time

# ═══════════════════════════════════════════════════════════════
# Windows 系统托盘 (ctypes + Shell_NotifyIcon)
# ═══════════════════════════════════════════════════════════════

# Win32 常量
WM_APP = 0x8000
WM_TRAY_CALLBACK = WM_APP + 100
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_LBUTTONUP = 0x0202
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_STATE = 0x00000008
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001
NIS_HIDDEN = 0x00000001
NIS_SHAREDICON = 0x00000002
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
TPM_LEFTALIGN = 0x0000
WM_COMMAND = 0x0111
ID_TRAY_SHOW = 1001
ID_TRAY_QUIT = 1002
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
WS_OVERLAPPED = 0x00000000
WS_POPUP = 0x80000000
CW_USEDEFAULT = 0x80000000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_USER = 0x0400
WM_CREATE = 0x0001
COLOR_WINDOW = 5
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001

# 结构体定义
class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]

# 加载 Windows API
shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

# 窗口过程回调原型 (LRESULT = LONG_PTR, 在64位上为c_longlong)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM)

# 显式设置 DefWindowProcW 的参数/返回值类型
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_longlong


def create_tomato_icon():
    """用 GDI 创建一个番茄色圆形图标 (32x32)"""
    hdc = user32.GetDC(0)

    # 颜色位图
    hdc_color = gdi32.CreateCompatibleDC(hdc)
    hbm_color = gdi32.CreateCompatibleBitmap(hdc, 32, 32)
    gdi32.SelectObject(hdc_color, hbm_color)

    # 画番茄红色圆形
    # 主体红色
    hbr_red = gdi32.CreateSolidBrush(0x003366FF)  # 番茄红 (BGR)
    gdi32.SelectObject(hdc_color, hbr_red)
    gdi32.Ellipse(hdc_color, 3, 3, 29, 29)

    # 顶部绿色小叶子 (用一个小椭圆)
    hbr_green = gdi32.CreateSolidBrush(0x0033AA44)
    gdi32.SelectObject(hdc_color, hbr_green)
    gdi32.Ellipse(hdc_color, 13, 1, 19, 8)

    # 掩码位图 (AND mask, 全白 = 完全不透明)
    hdc_mask = gdi32.CreateCompatibleDC(hdc)
    hbm_mask = gdi32.CreateBitmap(32, 32, 1, 1, None)
    gdi32.SelectObject(hdc_mask, hbm_mask)

    hbr_white = gdi32.CreateSolidBrush(0x00FFFFFF)
    gdi32.SelectObject(hdc_mask, hbr_white)
    gdi32.Ellipse(hdc_mask, 3, 3, 29, 29)
    gdi32.SelectObject(hdc_mask, hbr_white)
    gdi32.Ellipse(hdc_mask, 13, 1, 19, 8)

    # 创建图标
    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    ii = ICONINFO()
    ii.fIcon = True
    ii.xHotspot = 16
    ii.yHotspot = 16
    ii.hbmMask = hbm_mask
    ii.hbmColor = hbm_color

    hicon = user32.CreateIconIndirect(ctypes.byref(ii))

    # 清理 GDI 资源 (CreateIconIndirect 会复制位图)
    gdi32.DeleteObject(hbr_red)
    gdi32.DeleteObject(hbr_green)
    gdi32.DeleteObject(hbr_white)
    gdi32.DeleteObject(hbm_color)
    gdi32.DeleteObject(hbm_mask)
    gdi32.DeleteDC(hdc_color)
    gdi32.DeleteDC(hdc_mask)
    user32.ReleaseDC(0, hdc)

    return hicon


class SystemTray:
    """Windows 系统托盘管理，运行在独立线程中。
    通过 queue.Queue 安全地与主线程通信，避免跨线程 tkinter 调用。"""

    EVENT_SHOW = "show"
    EVENT_QUIT = "quit"

    def __init__(self, event_queue):
        self.event_queue = event_queue  # 线程安全队列，向主线程发送事件
        self.hwnd = None
        self.hicon = None
        self.thread = None
        self.running = False
        self._wndproc_ref = None  # 防止 GC 回收回调

    def start(self):
        """启动系统托盘线程"""
        self.running = True
        self.hicon = create_tomato_icon()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        """停止系统托盘"""
        self.running = False
        if self.hwnd:
            shell32.Shell_NotifyIconW(NIM_DELETE,
                ctypes.byref(self._build_nid(uFlags=0)))
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self.hicon:
            user32.DestroyIcon(self.hicon)
            self.hicon = None

    def update_tooltip(self, text):
        """更新托盘提示文字"""
        if self.hwnd and self.running:
            nid = self._build_nid(uFlags=NIF_TIP)
            nid.szTip = text
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def show_balloon(self, title, text):
        """显示气泡通知"""
        if self.hwnd and self.running:
            nid = self._build_nid(uFlags=NIF_INFO)
            nid.szInfoTitle = title
            nid.szInfo = text
            nid.dwInfoFlags = NIIF_INFO
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _build_nid(self, uFlags=None):
        """构建 NOTIFYICONDATA 结构"""
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uCallbackMessage = WM_TRAY_CALLBACK
        nid.hIcon = self.hicon
        nid.szTip = "番茄钟"
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        if uFlags is not None:
            nid.uFlags = uFlags
        return nid

    def _run(self):
        """在独立线程中运行消息循环"""
        hinstance = kernel32.GetModuleHandleW(None)

        # 注册窗口类
        class_name = "PomodoroTrayClass"
        self._wndproc_ref = WNDPROC(self._wndproc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = hinstance
        wc.hCursor = user32.LoadCursorW(0, 32512)  # IDC_ARROW
        wc.hbrBackground = ctypes.cast(COLOR_WINDOW + 1, wintypes.HBRUSH)
        wc.lpszClassName = class_name

        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if atom == 0:
            err = kernel32.GetLastError()
            print(f"RegisterClassExW 失败: {err}")
            return

        # 创建隐藏窗口
        self.hwnd = user32.CreateWindowExW(
            0, class_name, "PomodoroTray", WS_POPUP,
            0, 0, 0, 0, 0, 0, hinstance, 0
        )

        if not self.hwnd:
            err = kernel32.GetLastError()
            print(f"CreateWindowExW 失败: {err}")
            return

        # 添加托盘图标
        nid = self._build_nid()
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        # 设置版本 4 (Win2K+) 以获得更好的气泡通知支持
        nid.uVersion = 4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))

        # 消息循环
        msg = wintypes.MSG()
        while self.running:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # 清理
        if self.hwnd:
            shell32.Shell_NotifyIconW(NIM_DELETE,
                ctypes.byref(self._build_nid(uFlags=0)))
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        user32.UnregisterClassW(class_name, hinstance)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        """窗口消息处理（运行在托盘线程）"""
        if msg == WM_TRAY_CALLBACK:
            if lparam == WM_LBUTTONDBLCLK or lparam == WM_LBUTTONUP:
                self.event_queue.put(self.EVENT_SHOW)
            elif lparam == WM_RBUTTONUP:
                self._show_context_menu()
        elif msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == ID_TRAY_SHOW:
                self.event_queue.put(self.EVENT_SHOW)
            elif cmd == ID_TRAY_QUIT:
                self.event_queue.put(self.EVENT_QUIT)
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_context_menu(self):
        """显示右键上下文菜单"""
        hmenu = user32.CreatePopupMenu()
        user32.AppendMenuW(hmenu, 0x00000000, ID_TRAY_SHOW, "显示番茄钟")
        user32.AppendMenuW(hmenu, 0x00000800, 0, "")  # 分隔线
        user32.AppendMenuW(hmenu, 0x00000000, ID_TRAY_QUIT, "退出")

        # 获取光标位置
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        # 确保菜单正确显示
        user32.SetForegroundWindow(self.hwnd)
        user32.TrackPopupMenu(
            hmenu,
            TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_LEFTALIGN,
            pt.x, pt.y, 0, self.hwnd, 0
        )
        user32.PostMessageW(self.hwnd, 0, 0, 0)  # 使菜单正常关闭
        user32.DestroyMenu(hmenu)


# ═══════════════════════════════════════════════════════════════
# 番茄钟应用主类
# ═══════════════════════════════════════════════════════════════

class PomodoroApp:
    # 默认时长（秒）
    WORK_TIME = 25 * 60       # 25 分钟
    SHORT_BREAK = 5 * 60      # 5 分钟
    LONG_BREAK = 15 * 60      # 15 分钟
    LONG_BREAK_INTERVAL = 4   # 每 4 个番茄后长休息

    # 颜色主题
    COLOR_WORK = "#E74C3C"       # 专注 - 红色
    COLOR_SHORT_BREAK = "#2ECC71"  # 短休息 - 绿色
    COLOR_LONG_BREAK = "#3498DB"   # 长休息 - 蓝色
    COLOR_BG = "#1E1E2E"          # 深色背景
    COLOR_SURFACE = "#2D2D3F"     # 卡片背景
    COLOR_TEXT = "#ECF0F1"        # 浅色文字
    COLOR_TEXT_SECONDARY = "#95A5A6"  # 次要文字
    COLOR_BUTTON_START = "#2ECC71"
    COLOR_BUTTON_PAUSE = "#F39C12"
    COLOR_BUTTON_RESET = "#95A5A6"
    COLOR_BUTTON_SKIP = "#3498DB"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🍅 番茄钟")
        self.root.geometry("360x480")
        self.root.resizable(True, True)
        self.root.minsize(320, 420)
        self.root.configure(bg=self.COLOR_BG)

        # 状态变量
        self.mode = "work"           # work / short_break / long_break
        self.remaining = self.WORK_TIME
        self.total_seconds = self.WORK_TIME
        self.running = False
        self.pomodoro_count = 0      # 完成的番茄数
        self._after_id = None

        # 线程安全事件队列（托盘线程 → 主线程）
        self._tray_queue = queue.Queue()

        # 系统托盘
        self.tray = SystemTray(event_queue=self._tray_queue)
        self.tray.start()

        # 构建 UI
        self._create_widgets()
        self._update_display()

        # 窗口事件
        self.root.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)

        # 键盘快捷键
        self.root.bind('<space>', lambda e: self.toggle_timer())
        self.root.bind('<Escape>', lambda e: self.minimize_to_tray())
        self.root.bind('<Control-r>', lambda e: self.reset_timer())

        # 窗口居中
        self._center_window()

        # 启动托盘事件轮询（每 200ms 检查队列）
        self._poll_tray_events()

    # ── UI 构建 ──────────────────────────────────────────────

    def _create_widgets(self):
        """构建所有 UI 组件"""

        # 主容器
        main_frame = tk.Frame(self.root, bg=self.COLOR_BG)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 标题
        self.title_label = tk.Label(
            main_frame, text="🍅 番茄钟",
            font=("Segoe UI", 20, "bold"),
            bg=self.COLOR_BG, fg=self.COLOR_TEXT
        )
        self.title_label.pack(pady=(0, 5))

        # 模式指示器
        self.mode_label = tk.Label(
            main_frame, text="专注工作",
            font=("Segoe UI", 12),
            bg=self.COLOR_BG, fg=self.COLOR_WORK
        )
        self.mode_label.pack(pady=(0, 15))

        # ── 计时器圆形显示区域 ──
        timer_frame = tk.Frame(main_frame, bg=self.COLOR_BG)
        timer_frame.pack(pady=10)

        # 计时器背景画布（圆形视觉效果）
        self.canvas_size = 220
        self.canvas = tk.Canvas(
            timer_frame,
            width=self.canvas_size, height=self.canvas_size,
            bg=self.COLOR_BG, highlightthickness=0
        )
        self.canvas.pack()

        # 进度环和文字
        self._draw_timer_ring(1.0)

        # 会话计数
        count_frame = tk.Frame(main_frame, bg=self.COLOR_BG)
        count_frame.pack(pady=(10, 15))

        self.count_label = tk.Label(
            count_frame, text="🍅 × 0",
            font=("Segoe UI", 11),
            bg=self.COLOR_BG, fg=self.COLOR_TEXT_SECONDARY
        )
        self.count_label.pack()

        # ── 按钮区域 ──
        btn_frame = tk.Frame(main_frame, bg=self.COLOR_BG)
        btn_frame.pack(pady=5)

        # 开始/暂停按钮（主按钮，大）
        self.start_btn = tk.Button(
            btn_frame, text="▶  开 始",
            font=("Segoe UI", 13, "bold"),
            bg=self.COLOR_BUTTON_START, fg="white",
            activebackground="#27AE60", activeforeground="white",
            relief=tk.FLAT, cursor="hand2",
            padx=30, pady=8,
            command=self.toggle_timer
        )
        self.start_btn.pack(pady=5)

        # 次要按钮行
        sub_btn_frame = tk.Frame(main_frame, bg=self.COLOR_BG)
        sub_btn_frame.pack(pady=5)

        self.reset_btn = tk.Button(
            sub_btn_frame, text="↺ 重置",
            font=("Segoe UI", 10),
            bg=self.COLOR_BUTTON_RESET, fg="white",
            activebackground="#7F8C8D", activeforeground="white",
            relief=tk.FLAT, cursor="hand2",
            padx=14, pady=5,
            command=self.reset_timer
        )
        self.reset_btn.pack(side=tk.LEFT, padx=5)

        self.skip_btn = tk.Button(
            sub_btn_frame, text="⏭ 跳过",
            font=("Segoe UI", 10),
            bg=self.COLOR_BUTTON_SKIP, fg="white",
            activebackground="#2980B9", activeforeground="white",
            relief=tk.FLAT, cursor="hand2",
            padx=14, pady=5,
            command=self.skip_phase
        )
        self.skip_btn.pack(side=tk.LEFT, padx=5)

        # ── 底部提示 ──
        tip_frame = tk.Frame(main_frame, bg=self.COLOR_BG)
        tip_frame.pack(side=tk.BOTTOM, pady=(10, 0))

        tips = [
            "空格=开始/暂停  ·  Esc=最小化托盘  ·  Ctrl+R=重置",
        ]
        for tip in tips:
            tk.Label(
                tip_frame, text=tip,
                font=("Segoe UI", 8),
                bg=self.COLOR_BG, fg=self.COLOR_TEXT_SECONDARY
            ).pack()

    def _draw_timer_ring(self, progress):
        """绘制圆形进度环和倒计时文字"""
        self.canvas.delete("all")
        w, h = self.canvas_size, self.canvas_size
        cx, cy = w // 2, h // 2
        r = 85
        ring_width = 8

        # 当前模式颜色
        color = self._get_mode_color()

        # 背景圆环
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=self.COLOR_SURFACE,
            width=ring_width
        )

        # 进度圆环（从顶部开始逆时针）
        if progress > 0:
            # tkinter canvas 的 arc 从右侧(3点钟)顺时针绘制
            # 我们需要从顶部(12点钟)逆时针，即角度 90° → 90° - progress*360
            start_angle = 90  # 顶部
            extent = -progress * 360  # 负值为逆时针
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=start_angle, extent=extent,
                outline=color, width=ring_width,
                style="arc"
            )

        # 中心计时文字
        mins, secs = divmod(self.remaining, 60)
        time_str = f"{mins:02d}:{secs:02d}"

        self.canvas.create_text(
            cx, cy - 8,
            text=time_str,
            font=("Segoe UI", 36, "bold"),
            fill=self.COLOR_TEXT,
            anchor="center"
        )

        # 秒数小字
        self.canvas.create_text(
            cx, cy + 30,
            text=f"{self.remaining} 秒",
            font=("Segoe UI", 10),
            fill=self.COLOR_TEXT_SECONDARY,
            anchor="center"
        )

    def _get_mode_color(self):
        """获取当前模式对应的颜色"""
        if self.mode == "work":
            return self.COLOR_WORK
        elif self.mode == "short_break":
            return self.COLOR_SHORT_BREAK
        else:
            return self.COLOR_LONG_BREAK

    def _get_mode_text(self):
        """获取当前模式的中文描述"""
        if self.mode == "work":
            return "🔴 专注工作"
        elif self.mode == "short_break":
            return "🟢 短休息"
        else:
            return "🔵 长休息"

    # ── 计时逻辑 ────────────────────────────────────────────

    def toggle_timer(self):
        """切换开始/暂停"""
        if self.running:
            self._pause()
        else:
            self._start()

    def _start(self):
        """开始计时"""
        self.running = True
        self.start_btn.config(
            text="⏸  暂 停",
            bg=self.COLOR_BUTTON_PAUSE,
            activebackground="#E67E22"
        )
        self._tick()
        self.tray.update_tooltip(f"🍅 番茄钟 - {self._get_mode_text()} - 运行中")

    def _pause(self):
        """暂停计时"""
        self.running = False
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.start_btn.config(
            text="▶  开 始",
            bg=self.COLOR_BUTTON_START,
            activebackground="#27AE60"
        )
        self.tray.update_tooltip(f"🍅 番茄钟 - {self._get_mode_text()} - 已暂停")

    def reset_timer(self):
        """重置当前计时"""
        self._pause()
        self.remaining = self.total_seconds
        self._update_display()
        self.tray.update_tooltip(f"🍅 番茄钟 - {self._get_mode_text()}")

    def skip_phase(self):
        """跳过当前阶段"""
        self._pause()
        self._play_notification()
        self._switch_mode()

    def _tick(self):
        """每秒执行的计时核心"""
        if not self.running:
            return

        if self.remaining > 0:
            self.remaining -= 1
            self._update_display()

        if self.remaining <= 0:
            # 时间到！
            self.running = False
            self._play_notification()
            self._switch_mode()

        if self.running:
            self._after_id = self.root.after(1000, self._tick)

    def _switch_mode(self):
        """切换到下一个模式"""
        self._pause()

        if self.mode == "work":
            # 完成一个番茄
            self.pomodoro_count += 1
            if self.pomodoro_count % self.LONG_BREAK_INTERVAL == 0:
                self.mode = "long_break"
                self.remaining = self.LONG_BREAK
                self.total_seconds = self.LONG_BREAK
            else:
                self.mode = "short_break"
                self.remaining = self.SHORT_BREAK
                self.total_seconds = self.SHORT_BREAK

            # 托盘通知
            self.tray.show_balloon(
                "🍅 专注时间结束！",
                f"已完成 {self.pomodoro_count} 个番茄，该休息一下了~"
            )

        else:  # 休息结束 → 开始工作
            self.mode = "work"
            self.remaining = self.WORK_TIME
            self.total_seconds = self.WORK_TIME
            self.tray.show_balloon(
                "⏰ 休息时间结束！",
                "该开始下一个番茄钟了，加油！"
            )

        self._update_display()
        self.tray.update_tooltip(f"🍅 番茄钟 - {self._get_mode_text()}")

    def _play_notification(self):
        """播放声音提醒（在独立线程中运行，不阻塞 UI）"""
        def _play():
            try:
                # 播放三声提示音
                for _ in range(3):
                    winsound.Beep(880, 200)   # A5 音
                    time.sleep(0.1)
                winsound.Beep(1200, 400)      # 更高音，延长
            except Exception:
                # 备用方案：系统消息提示音
                try:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass
        threading.Thread(target=_play, daemon=True).start()

    # ── 显示更新 ────────────────────────────────────────────

    def _update_display(self):
        """刷新所有显示元素"""
        progress = self.remaining / self.total_seconds if self.total_seconds > 0 else 0
        self._draw_timer_ring(progress)

        # 模式标签
        mode_color = self._get_mode_color()
        self.mode_label.config(
            text=self._get_mode_text(),
            fg=mode_color
        )

        # 计数
        self.count_label.config(text=f"🍅 × {self.pomodoro_count}")

    # ── 窗口管理 ────────────────────────────────────────────

    def minimize_to_tray(self, event=None):
        """最小化到系统托盘"""
        self.root.withdraw()  # 隐藏窗口

    def restore_window(self):
        """从托盘恢复窗口"""
        self.root.deiconify()    # 显示窗口
        self.root.lift()         # 提到最前
        self.root.focus_force()  # 获取焦点

    def quit_app(self):
        """退出应用"""
        self._pause()
        self.tray.stop()
        self.root.destroy()

    def _center_window(self):
        """窗口居中"""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _poll_tray_events(self):
        """轮询托盘事件队列（主线程安全）"""
        try:
            while True:
                event = self._tray_queue.get_nowait()
                if event == SystemTray.EVENT_SHOW:
                    self.restore_window()
                elif event == SystemTray.EVENT_QUIT:
                    self.quit_app()
        except queue.Empty:
            pass
        # 每 200ms 轮询一次
        self.root.after(200, self._poll_tray_events)

    def run(self):
        """启动应用主循环"""
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = PomodoroApp()
    app.run()
