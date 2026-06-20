import sys
import traceback
import matplotlib
matplotlib.use("TkAgg")
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import io
import numpy as np

# ==========================================
# Gaussian B3LYP/6-31G
# ==========================================
csv_data = """Substrate,Substituent,Halogen,Position,Catalyst,R_Hartree,TS_Hartree,P_Hartree,Note
Benzene,None,Cl2,-,None,-1152.602145,-1152.540790,-1152.642304,无催化基准
Benzene,None,Br2,-,None,-5380.855412,-5380.781786,-5380.870551,溴代
Benzene,None,I2,-,None,-14067.221055,-14067.133724,-14067.210218,碘代
Toluene,Methyl,Cl2,Ortho,None,-1191.923560,-1191.869058,-1191.965154,甲苯邻位
Toluene,Methyl,Cl2,Para,None,-1191.923560,-1191.870811,-1191.965791,甲苯对位
Toluene,Methyl,Cl2,Meta,None,-1191.923560,-1191.863321,-1191.964198,甲苯间位
Phenol,-OH,Cl2,Para,None,-1227.810550,-1227.774693,-1227.858518,苯酚
Nitrobenzene,-NO2,Cl2,Meta,None,-1357.108845,-1357.031554,-1357.146295,硝基苯间位
Nitrobenzene,-NO2,Cl2,Para,None,-1357.108845,-1357.025817,-1357.145179,硝基苯对位
Benzene,None,Cl2,-,AlCl3,-2775.654210,-2775.634290,-2775.694369,AlCl3催化
"""

# 尝试导入 scipy
try:
    from scipy.interpolate import make_interp_spline

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("提示: 未检测到 scipy，曲线将显示为折线")


class ReactionPlotterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EAS Reaction Energy Profile (Gaussian Data Processor)")
        self.root.geometry("1280x720")
        try:
            self.df = pd.read_csv(io.StringIO(csv_data), skipinitialspace=True)
        except Exception as e:
            messagebox.showerror("数据错误", f"读取CSV数据失败: {e}")
            return

        # 布局
        self.create_widgets()

    def create_widgets(self):
        # --- 左侧面板 ---
        left_panel = tk.Frame(self.root, width=450, bg="#f0f0f0")
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        title_lbl = tk.Label(left_panel, text="计算结果数据表 (单位: Hartree)", bg="#f0f0f0",
                             font=("Arial", 11, "bold"))
        title_lbl.pack(pady=5)

        # 表格配置
        cols = ("Substrate", "Halogen", "Pos", "R_E", "TS_E")
        self.tree = ttk.Treeview(left_panel, columns=cols, show='headings', selectmode="extended")

        self.tree.heading("Substrate", text="底物")
        self.tree.column("Substrate", width=70)
        self.tree.heading("Halogen", text="X2")
        self.tree.column("Halogen", width=40)
        self.tree.heading("Pos", text="位")
        self.tree.column("Pos", width=40)
        self.tree.heading("R_E", text="Reactant (Ha)")
        self.tree.column("R_E", width=100)
        self.tree.heading("TS_E", text="TS (Ha)")
        self.tree.column("TS_E", width=100)

        for index, row in self.df.iterrows():
            self.tree.insert("", tk.END, iid=index, values=(
                row['Substrate'], row['Halogen'], row['Position'],
                f"{row['R_Hartree']:.6f}", f"{row['TS_Hartree']:.6f}"
            ))

        self.tree.pack(fill=tk.BOTH, expand=True)

        tk.Label(left_panel, text="提示: 表格显示绝对能量(Hartree)\n绘图自动转换为相对能量(kcal/mol)", bg="#f0f0f0",
                 fg="#555").pack(pady=5)

        btn_frame = tk.Frame(left_panel, bg="#f0f0f0")
        btn_frame.pack(pady=10, fill=tk.X)

        tk.Button(btn_frame, text="绘制相对能量曲线 (按住Ctrl多选)", command=self.plot_selected, bg="#2196F3",
                  fg="white", font=("Arial", 12)).pack(fill=tk.X, pady=4)
        tk.Button(btn_frame, text="清空画布", command=self.clear_plot).pack(fill=tk.X, pady=2)

        # --- 右侧面板 ---
        right_panel = tk.Frame(self.root)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.setup_plot_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=right_panel)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, right_panel)
        toolbar.update()

    def setup_plot_axes(self):
        self.ax.set_title("Reaction Coordinate Diagram (B3LYP/6-31G*)")
        self.ax.set_xlabel("Reaction Coordinate")
        self.ax.set_ylabel("Relative Energy (kcal/mol)")
        self.ax.axhline(0, color='black', linewidth=0.8, linestyle='--')
        self.ax.grid(True, linestyle=':', alpha=0.6)

    def get_smooth_curve(self, y_points):
        x_key = np.array([0.0, 0.2, 1.0, 1.8, 2.0])
        y_key = np.array([y_points[0], y_points[0], y_points[1], y_points[2], y_points[2]])
        if SCIPY_AVAILABLE:
            x_smooth = np.linspace(0, 2, 300)
            try:
                spl = make_interp_spline(x_key, y_key, k=3, bc_type=([(1, 0.0)], [(1, 0.0)]))
                return x_smooth, spl(x_smooth)
            except Exception:
                return x_key, y_key  # 降级处理
        else:
            return x_key, y_key

    def plot_selected(self):
        try:
            selected_items = self.tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请选择至少一条反应路径！")
                return

            self.ax.clear()
            self.setup_plot_axes()

            for iid in selected_items:
                row = self.df.loc[int(iid)]
                r_abs, ts_abs, p_abs = row['R_Hartree'], row['TS_Hartree'], row['P_Hartree']
                rel_ts = (ts_abs - r_abs) * 627.509
                rel_p = (p_abs - r_abs) * 627.509
                energies = [0.0, rel_ts, rel_p]

                label_text = f"{row['Substrate']} + {row['Halogen']}"
                if row['Position'] != "-": label_text += f" ({row['Position']})"
                if row['Catalyst'] != "None": label_text += f" / {row['Catalyst']}"

                x_vals, y_vals = self.get_smooth_curve(energies)
                line, = self.ax.plot(x_vals, y_vals, label=label_text, linewidth=2)

                self.ax.scatter([1.0], [rel_ts], color=line.get_color(), zorder=5)
                self.ax.text(1.0, rel_ts + 1.5, f"{rel_ts:.1f}", ha='center', va='bottom', fontsize=9,
                             color=line.get_color(), fontweight='bold')

            self.ax.legend(loc='upper right')
            self.canvas.draw()
        except Exception as e:
            messagebox.showerror("绘图错误", f"绘图时发生错误: {e}")
            print(traceback.format_exc())

    def clear_plot(self):
        self.ax.clear()
        self.setup_plot_axes()
        self.canvas.draw()


# --- 3. 主程序入口 ---
if __name__ == "__main__":
    try:
        print("正在启动图形界面...")
        root = tk.Tk()
        try:
            root.state('zoomed')
        except:
            root.geometry("1280x720")

        app = ReactionPlotterApp(root)
        print("图形界面启动成功！")
        root.mainloop()
    except Exception as e:
        print("\n" + "!!!" * 10)
        print("程序发生严重错误！")
        print(traceback.format_exc())
        print("!!!" * 10)
        input("按回车键退出...")