from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List

import cv2
import numpy as np
from PIL import Image, ImageTk

from pc.training.annotation_store import annotation_store
from pc.training.train_manager import TrainingManager


class TrainingAnnotationPanel:
    def __init__(self) -> None:
        self.manager = TrainingManager()
        self.root = tk.Tk()
        self.root.title("NeuroLab Hub - 图片标注与 YOLO 训练面板")
        self.root.geometry("1360x860")
        self.root.configure(bg="#10161D")

        self.workspace_var = tk.StringVar(value="labdetector_training")
        self.base_weights_var = tk.StringVar(value="yolov8n.pt")
        self.class_var = tk.StringVar(value="observation")
        self.status_var = tk.StringVar(value="等待构建工作区或导入图片")

        self.workspace_dir = ""
        self.items: List[Dict[str, Any]] = []
        self.current_item: Dict[str, Any] = {}
        self.boxes: List[Dict[str, Any]] = []
        self.scale = 1.0
        self.offset = (0, 0)
        self.image_size = (0, 0)
        self.drag_start: tuple[int, int] | None = None
        self.preview_rect: int | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None

        self._build_ui()
        self._ensure_workspace()
        self.refresh_panel()

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=14)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        header = ttk.Frame(shell, padding=12)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="工作区").grid(row=0, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.workspace_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Label(header, text="YOLO 权重").grid(row=0, column=2, sticky="w")
        ttk.Entry(header, textvariable=self.base_weights_var, width=18).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        actions = ttk.Frame(shell, padding=12)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for idx in range(6):
            actions.columnconfigure(idx, weight=1)
        ttk.Button(actions, text="构建工作区", command=self._ensure_workspace).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="导入图片", command=self.import_images).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(actions, text="生成测试图片", command=self.generate_samples).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(actions, text="保存标注", command=self.save_annotations).grid(row=0, column=3, sticky="ew", padx=6)
        ttk.Button(actions, text="删除选中框", command=self.delete_selected_box).grid(row=0, column=4, sticky="ew", padx=6)
        ttk.Button(actions, text="启动 YOLO 训练", command=self.start_training).grid(row=0, column=5, sticky="ew", padx=(6, 0))

        body = ttk.Frame(shell, padding=8)
        body.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=5)
        body.columnconfigure(2, weight=3)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="待标注图片").grid(row=0, column=0, sticky="w")
        self.tree = ttk.Treeview(left, columns=("name", "boxes"), show="headings", height=18)
        self.tree.heading("name", text="图片")
        self.tree.heading("boxes", text="框数")
        self.tree.column("name", width=210, anchor="w")
        self.tree.column("boxes", width=60, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_image)

        center = ttk.Frame(body, padding=10)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)
        ttk.Label(center, text="标注画布（拖拽鼠标创建框）").grid(row=0, column=0, sticky="w")
        self.canvas = tk.Canvas(center, bg="#081018", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.canvas.bind("<Configure>", lambda _event: self.render_image())
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        right = ttk.Frame(body, padding=10)
        right.grid(row=0, column=2, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)
        ttk.Label(right, text="当前类别").grid(row=0, column=0, sticky="w")
        ttk.Entry(right, textvariable=self.class_var).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(right, text="当前图片标注框").grid(row=2, column=0, sticky="w", pady=(12, 0))

        box_wrap = ttk.Frame(right)
        box_wrap.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        box_wrap.columnconfigure(0, weight=1)
        box_wrap.rowconfigure(0, weight=1)
        self.box_tree = ttk.Treeview(box_wrap, columns=("id", "class", "w", "h"), show="headings", height=16)
        for key, label, width in (("id", "#", 36), ("class", "类别", 100), ("w", "宽", 50), ("h", "高", 50)):
            self.box_tree.heading(key, text=label)
            self.box_tree.column(key, width=width, anchor="center" if key != "class" else "w")
        self.box_tree.grid(row=0, column=0, sticky="nsew")
        box_scroll = ttk.Scrollbar(box_wrap, orient="vertical", command=self.box_tree.yview)
        box_scroll.grid(row=0, column=1, sticky="ns")
        self.box_tree.configure(yscrollcommand=box_scroll.set)

        ttk.Label(right, textvariable=self.status_var, wraplength=280, justify="left").grid(row=4, column=0, sticky="ew", pady=(12, 0))

        log_wrap = ttk.Frame(shell, padding=10)
        log_wrap.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(1, weight=1)
        ttk.Label(log_wrap, text="执行日志").grid(row=0, column=0, sticky="w")
        self.log_text = tk.Text(log_wrap, height=10, bg="#0F1720", fg="#DBE6F2", insertbackground="#DBE6F2", relief="flat")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.log_text.configure(state="disabled")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _ensure_workspace(self) -> str:
        if self.workspace_dir and Path(self.workspace_dir).exists():
            return self.workspace_dir
        summary = self.manager.build_training_workspace(self.workspace_var.get().strip())
        self.workspace_dir = str(summary.get("workspace_dir") or "")
        self.status_var.set(f"工作区已就绪: {self.workspace_dir}")
        self.log(f"[workspace] {self.workspace_dir}")
        return self.workspace_dir

    def refresh_panel(self) -> None:
        workspace_dir = self._ensure_workspace()
        self.items = annotation_store.list_images(workspace_dir)
        self.tree.delete(*self.tree.get_children())
        for row in self.items:
            self.tree.insert("", "end", iid=row["name"], values=(row["name"], len(row.get("boxes") or [])))
        classes = annotation_store.get_classes(workspace_dir)
        self.status_var.set(f"当前图片 {len(self.items)} 张 | 类别 {len(classes)} 个")

    def import_images(self) -> None:
        paths = list(
            filedialog.askopenfilenames(
                parent=self.root,
                title="导入待标注图片",
                filetypes=[("图片文件", "*.jpg;*.jpeg;*.png;*.bmp;*.webp"), ("所有文件", "*.*")],
            )
        )
        if not paths:
            return
        summary = annotation_store.import_images(self._ensure_workspace(), paths)
        self.log(f"[import] 导入图片 {summary['imported_count']} 张")
        self.refresh_panel()

    def generate_samples(self) -> None:
        workspace_dir = self._ensure_workspace()
        sample_root = Path(workspace_dir) / "synthetic_samples"
        sample_root.mkdir(parents=True, exist_ok=True)
        generated_paths: List[str] = []
        samples = [
            ("sample_flask.png", "FLASK", (90, 70, 390, 350), (40, 170, 240)),
            ("sample_warning.png", "DANGER", (110, 120, 430, 300), (220, 60, 60)),
            ("sample_screen.png", "OCR", (70, 110, 470, 290), (60, 80, 200)),
            ("sample_triangle.png", "CHEM", (150, 90, 420, 330), (80, 160, 80)),
        ]
        for name, label, rect, color in samples:
            canvas = np.full((420, 560, 3), 255, dtype=np.uint8)
            x1, y1, x2, y2 = rect
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness=-1)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (20, 20, 20), thickness=3)
            cv2.putText(canvas, label, (x1 + 24, y1 + 84), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
            output = sample_root / name
            cv2.imwrite(str(output), canvas)
            generated_paths.append(str(output))
        summary = annotation_store.import_images(workspace_dir, generated_paths)
        self.log(f"[samples] 生成并导入测试图片 {summary['imported_count']} 张")
        self.refresh_panel()

    def on_select_image(self, _event: Any = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        image_name = selection[0]
        for row in self.items:
            if row.get("name") == image_name:
                self.current_item = row
                self.boxes = [dict(item) for item in row.get("boxes") or []]
                self.sync_box_tree()
                self.render_image()
                self.status_var.set(f"已加载图片: {image_name}")
                self.log(f"[select] {image_name}")
                break

    def render_image(self) -> None:
        image_path = str(self.current_item.get("image_path") or "").strip()
        if not image_path:
            self.canvas.delete("all")
            return
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        self.image_size = (width, height)
        canvas_width = max(int(self.canvas.winfo_width() or 760), 320)
        canvas_height = max(int(self.canvas.winfo_height() or 460), 240)
        scale = min(canvas_width / max(width, 1), canvas_height / max(height, 1))
        scale = max(min(scale, 1.8), 0.1)
        preview_width = max(1, int(width * scale))
        preview_height = max(1, int(height * scale))
        offset_x = max((canvas_width - preview_width) // 2, 0)
        offset_y = max((canvas_height - preview_height) // 2, 0)
        preview = image.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.scale = scale
        self.offset = (offset_x, offset_y)
        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, anchor="nw", image=self.preview_photo)
        self.redraw_overlay()

    def redraw_overlay(self) -> None:
        self.canvas.delete("annotation_box")
        offset_x, offset_y = self.offset
        for box in self.boxes:
            x1 = offset_x + float(box.get("x1", 0.0)) * self.scale
            y1 = offset_y + float(box.get("y1", 0.0)) * self.scale
            x2 = offset_x + float(box.get("x2", 0.0)) * self.scale
            y2 = offset_y + float(box.get("y2", 0.0)) * self.scale
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#20C997", width=2, tags=("annotation_box",))
            self.canvas.create_text(
                x1 + 6,
                y1 + 6,
                anchor="nw",
                text=str(box.get("class_name", "")),
                fill="#20C997",
                font=("Microsoft YaHei UI", 10, "bold"),
                tags=("annotation_box",),
            )

    def _canvas_to_image(self, event_x: int, event_y: int) -> tuple[float, float]:
        offset_x, offset_y = self.offset
        scale = max(self.scale, 1e-6)
        width, height = self.image_size
        return (
            max(0.0, min((event_x - offset_x) / scale, float(width))),
            max(0.0, min((event_y - offset_y) / scale, float(height))),
        )

    def on_press(self, event: tk.Event) -> None:
        if not self.current_item:
            return
        self.drag_start = (event.x, event.y)
        if self.preview_rect is not None:
            self.canvas.delete(self.preview_rect)
            self.preview_rect = None

    def on_drag(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        x0, y0 = self.drag_start
        if self.preview_rect is None:
            self.preview_rect = self.canvas.create_rectangle(x0, y0, event.x, event.y, outline="#FFD166", width=2, dash=(4, 2))
        else:
            self.canvas.coords(self.preview_rect, x0, y0, event.x, event.y)

    def on_release(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        if self.preview_rect is not None:
            self.canvas.delete(self.preview_rect)
            self.preview_rect = None
        start_x, start_y = self.drag_start
        self.drag_start = None
        class_name = self.class_var.get().strip()
        if not class_name:
            messagebox.showwarning("NeuroLab Hub", "请先输入当前标注类别。", parent=self.root)
            return
        x1, y1 = self._canvas_to_image(start_x, start_y)
        x2, y2 = self._canvas_to_image(event.x, event.y)
        if abs(x2 - x1) < 4 or abs(y2 - y1) < 4:
            return
        self.boxes.append(
            {
                "class_name": class_name,
                "x1": min(x1, x2),
                "y1": min(y1, y2),
                "x2": max(x1, x2),
                "y2": max(y1, y2),
            }
        )
        self.sync_box_tree()
        self.redraw_overlay()
        self.status_var.set(f"已新增标注框 {len(self.boxes)} 个")

    def sync_box_tree(self) -> None:
        self.box_tree.delete(*self.box_tree.get_children())
        for index, box in enumerate(self.boxes):
            self.box_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    index + 1,
                    box.get("class_name", ""),
                    int(abs(float(box.get("x2", 0.0)) - float(box.get("x1", 0.0)))),
                    int(abs(float(box.get("y2", 0.0)) - float(box.get("y1", 0.0)))),
                ),
            )

    def save_annotations(self) -> None:
        if not self.current_item:
            messagebox.showwarning("NeuroLab Hub", "请先选择一张训练图片。", parent=self.root)
            return
        width, height = self.image_size
        summary = annotation_store.save_annotations(
            self._ensure_workspace(),
            str(self.current_item.get("name") or ""),
            width,
            height,
            self.boxes,
        )
        self.log(f"[save] {summary['image_name']} -> {summary['label_path']}")
        self.status_var.set(f"标注已保存: {summary['image_name']} | 框 {summary['box_count']} 个")
        self.refresh_panel()

    def delete_selected_box(self) -> None:
        selection = self.box_tree.selection()
        if not selection:
            return
        for item in sorted((int(value) for value in selection), reverse=True):
            if 0 <= item < len(self.boxes):
                self.boxes.pop(item)
        self.sync_box_tree()
        self.redraw_overlay()
        self.status_var.set("已删除选中标注框")

    def start_training(self) -> None:
        workspace_dir = self._ensure_workspace()
        dataset_yaml = Path(workspace_dir) / "pi_detector" / "dataset.yaml"
        if not dataset_yaml.exists():
            messagebox.showwarning("NeuroLab Hub", "当前工作区还没有可训练的数据集。", parent=self.root)
            return

        def _runner() -> None:
            try:
                self.root.after(0, lambda: self.log("[train] 正在启动 YOLO 训练任务"))
                result = self.manager.start_pi_job(
                    {
                        "workspace_dir": workspace_dir,
                        "dataset_yaml": str(dataset_yaml),
                        "base_weights": self.base_weights_var.get().strip(),
                    }
                )
                self.root.after(0, lambda: self.log(f"[train] 训练任务已提交: {result.get('job_id', '')}"))
            except Exception as exc:
                self.root.after(0, lambda: self.log(f"[train] 启动失败: {exc}"))
                self.root.after(0, lambda: messagebox.showerror("NeuroLab Hub", str(exc), parent=self.root))

        threading.Thread(target=_runner, daemon=True).start()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    TrainingAnnotationPanel().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
