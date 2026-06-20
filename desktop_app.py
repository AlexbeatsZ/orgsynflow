from __future__ import annotations

import tkinter as tk
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.route_layout import layout_route
from services.workbench import (
    analyze_target,
    explain_single_reaction,
    gaussian_status,
    make_gaussian_input,
    run_local_gaussian,
)


class OrgSynFlowDesktop(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OrgSyn Flow 有机合成工作台 V6")
        self.geometry("1120x760")
        self.minsize(960, 640)

        self.smiles_var = tk.StringVar(value="CC(=O)Oc1ccccc1C(=O)O")
        self.target_var = tk.StringVar(value="Aspirin")
        self.use_aizynth_var = tk.BooleanVar(value=False)
        self.report_markdown = ""
        self.last_result: dict[str, object] | None = None

        self._build_layout()

    def _build_layout(self) -> None:
        top = ttk.Frame(self, padding=12)
        top.pack(fill=tk.X)

        ttk.Label(top, text="目标分子 SMILES").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(top, textvariable=self.smiles_var, width=58).grid(row=0, column=1, padx=8, sticky=tk.EW)
        ttk.Label(top, text="演示目标").grid(row=0, column=2, padx=(12, 0), sticky=tk.W)
        ttk.Combobox(
            top,
            textvariable=self.target_var,
            values=["Aspirin", "Paracetamol"],
            width=16,
            state="readonly",
        ).grid(row=0, column=3, padx=8)
        ttk.Checkbutton(top, text="尝试 AiZynthFinder", variable=self.use_aizynth_var).grid(row=0, column=4)
        ttk.Button(top, text="分析路线", command=self.analyze).grid(row=0, column=5, padx=(8, 0))
        top.columnconfigure(1, weight=1)

        progress_frame = ttk.Frame(self, padding=(12, 0, 12, 8))
        progress_frame.pack(fill=tk.X)
        self.progress = ttk.Progressbar(progress_frame, maximum=100, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(progress_frame, textvariable=self.status_var, width=42).pack(side=tk.LEFT, padx=(10, 0))

        tabs = ttk.Notebook(self)
        tabs.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.summary_text = self._make_text_tab(tabs, "路线分析")
        self.route_canvas = self._make_canvas_tab(tabs, "路线图")
        self.reaction_text = self._make_text_tab(tabs, "反应解释")
        self.gaussian_text = self._make_text_tab(tabs, "Gaussian 计算")
        self.report_text = self._make_text_tab(tabs, "报告")

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.pack(fill=tk.X)
        ttk.Button(bottom, text="导出 Markdown 报告", command=self.export_report).pack(side=tk.LEFT)
        ttk.Button(bottom, text="生成 Gaussian 输入", command=self.generate_gaussian).pack(side=tk.LEFT, padx=8)
        ttk.Button(bottom, text="运行本机 Gaussian", command=self.run_gaussian).pack(side=tk.LEFT)
        ttk.Button(bottom, text="退出", command=self.destroy).pack(side=tk.RIGHT)

    def _make_text_tab(self, tabs: ttk.Notebook, title: str) -> tk.Text:
        frame = ttk.Frame(tabs, padding=8)
        text = tk.Text(frame, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tabs.add(frame, text=title)
        return text

    def _make_canvas_tab(self, tabs: ttk.Notebook, title: str) -> tk.Canvas:
        frame = ttk.Frame(tabs, padding=8)
        canvas = tk.Canvas(frame, bg="white", scrollregion=(0, 0, 1400, 900))
        x_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=canvas.xview)
        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tabs.add(frame, text=title)
        return canvas

    def analyze(self) -> None:
        try:
            self._set_progress(10, "读取目标分子与路线数据...")
            result = analyze_target(
                self.smiles_var.get().strip(),
                demo_target=self.target_var.get(),
                use_aizynth=self.use_aizynth_var.get(),
            )
            self._set_progress(65, "生成路线图与反应解释...")
        except Exception as exc:
            self._set_progress(0, "分析失败")
            messagebox.showerror("分析失败", str(exc))
            return

        self.last_result = result
        self.report_markdown = str(result["report_markdown"])
        self._set_text(self.summary_text, self._format_summary(result))
        self._set_text(self.reaction_text, self._format_reactions(result))
        self._set_text(self.report_text, self.report_markdown)
        self._draw_route_graph(result)
        self._set_progress(100, "分析完成")

    def generate_gaussian(self) -> None:
        gjf = make_gaussian_input(
            {
                "smiles": self.smiles_var.get().strip(),
                "title": f"{self.target_var.get()} opt freq",
                "job_type": "opt freq",
            }
        )
        self._set_text(self.gaussian_text, gjf)
        self._set_progress(100, "已生成 Gaussian 输入文件文本；尚未运行 Gaussian。")

    def run_gaussian(self) -> None:
        self.generate_gaussian()
        status = gaussian_status()
        if not status["available"]:
            messagebox.showerror("Gaussian 不可用", "未检测到 g16/g09，请确认 Gaussian 已安装并加入 PATH。")
            return
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status_var.set(f"正在调用本机 Gaussian：{status['executable']}")
        thread = threading.Thread(target=self._run_gaussian_worker, daemon=True)
        thread.start()

    def _run_gaussian_worker(self) -> None:
        try:
            result = run_local_gaussian(
                {
                    "smiles": self.smiles_var.get().strip(),
                    "title": f"{self.target_var.get()} opt freq",
                    "job_type": "opt freq",
                    "timeout_seconds": 3600,
                }
            )
            output = self.gaussian_text.get("1.0", tk.END)
            output += "\n\n=== 本机 Gaussian 运行结果 ===\n"
            output += f"成功：{result['success']}\n"
            output += f"可执行文件：{result['executable']}\n"
            output += f"输入文件：{result['input_path']}\n"
            output += f"输出 log：{result['log_path']}\n"
            output += f"消息：{result['message']}\n"
            output += f"解析结果：{result['parsed_result']}\n"
            self.after(0, lambda: self._finish_gaussian_run(output, bool(result["success"])))
        except Exception as exc:
            self.after(0, lambda: self._finish_gaussian_run(f"Gaussian 运行失败：{exc}", False))

    def _finish_gaussian_run(self, output: str, success: bool) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self._set_text(self.gaussian_text, output)
        self._set_progress(100 if success else 0, "Gaussian 计算完成" if success else "Gaussian 计算未正常完成")

    def export_report(self) -> None:
        if not self.report_markdown:
            self.analyze()
        path = filedialog.asksaveasfilename(
            title="保存报告",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
            initialfile="orgsynflow_route_report.md",
        )
        if not path:
            return
        Path(path).write_text(self.report_markdown, encoding="utf-8")
        messagebox.showinfo("已导出", f"报告已保存到：\n{path}")

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, value)

    def _format_summary(self, result: dict[str, object]) -> str:
        lines = [f"状态：{result['status']}", "", "目标分子："]
        target = result["target"]
        if isinstance(target, dict):
            lines.extend(f"- {key}: {value}" for key, value in target.items())
        lines.append("")
        lines.append("候选路线：")
        routes = result["routes"]
        scores = result["route_scores"]
        feasibility = result["feasibility"]
        if isinstance(routes, list) and isinstance(scores, dict) and isinstance(feasibility, dict):
            for route in routes:
                route_id = route["id"]
                score = scores[route_id]
                feas = feasibility[route_id]
                lines.append(
                    f"- {route['title']}：综合分 {score['route_score']}，"
                    f"规则可行性 {feas['route_feasibility_score']}，规则估计总收率 {feas['estimated_overall_yield_percent']}%"
                )
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _format_reactions(self, result: dict[str, object]) -> str:
        lines: list[str] = []
        routes = result["routes"]
        if not isinstance(routes, list):
            return ""
        for route in routes:
            lines.append(f"路线：{route['title']}")
            for step in route["steps"]:
                detail = explain_single_reaction(step.get("reaction_smiles") or "", step.get("template"))
                lines.append(f"  {step['id']} {detail['reaction_type']}")
                lines.append(f"  反应中心：{'、'.join(detail['reaction_center'])}")
                lines.append(f"  解释：{detail['summary']}")
                lines.append(f"  规则估计产率：{detail['yield_estimate']['predicted_yield_percent']}%")
                lines.append(f"  说明：{detail['yield_estimate']['note']}")
            lines.append("")
        return "\n".join(lines)

    def _draw_route_graph(self, result: dict[str, object]) -> None:
        self.route_canvas.delete("all")
        routes = result.get("routes")
        if not isinstance(routes, list) or not routes:
            return
        route_payload = routes[0]
        from core.route import route_from_dict

        route = route_from_dict(route_payload, source=str(route_payload.get("source", "demo")))
        graph = layout_route(route)
        for edge in graph.edges:
            source = graph.nodes[edge.source_id]
            target = graph.nodes[edge.target_id]
            self.route_canvas.create_line(source.x + 180, source.y + 35, target.x, target.y + 35, arrow=tk.LAST, width=2, arrowshape=(8,10,3))
            self.route_canvas.create_text(
                (source.x + target.x) // 2 + 90,
                (source.y + target.y) // 2 + 10,
                text=edge.label,
                fill="#334155",
                font=("Microsoft YaHei UI", 9),
            )
        for node in graph.nodes.values():
            fill = "#dcfce7" if node.in_stock else "#dbeafe"
            outline = "#16a34a" if node.in_stock else "#2563eb"
            self.route_canvas.create_rectangle(node.x, node.y, node.x + 180, node.y + 70, fill=fill, outline=outline, width=2)
            self.route_canvas.create_text(
                node.x + 90,
                node.y + 35,
                text=node.label,
                width=165,
                font=("Microsoft YaHei UI", 9),
            )

    def _set_progress(self, value: int, message: str) -> None:
        self.progress.configure(mode="determinate")
        self.progress["value"] = value
        self.status_var.set(message)
        self.update_idletasks()


def main() -> None:
    app = OrgSynFlowDesktop()
    app.analyze()
    app.generate_gaussian()
    app.mainloop()


if __name__ == "__main__":
    main()
