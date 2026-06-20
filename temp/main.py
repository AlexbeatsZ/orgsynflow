# -*- coding: utf-8 -*-
"""
过渡态搜索 - Gradio 交互式界面 v3
模块1: 配置与预览 (含扫描设置和历史项目加载)
模块2: 任务队列+执行+结果 (合并)
"""

import os
import sys
import json
import re
import copy
import shutil
import datetime
import glob
import base64
import io
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum

# 添加AI分析相关导入
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

# 导入内置数据 (直接定义，避免导入data.py)
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

# 设置Gaussian环境
gaussian_root = r"C:\Program Files\G16W"
os.environ['g16root'] = gaussian_root
os.environ['GAUSS_EXEDIR'] = gaussian_root
os.environ['PATH'] = gaussian_root + os.pathsep + os.environ.get('PATH', '')

# 工作目录 - 放在gaussian目录下
SCRIPT_DIR = Path(__file__).parent.resolve()
OUT_DIR = SCRIPT_DIR / "out"
OUT_DIR.mkdir(exist_ok=True)

from ts_search_lib import *

try:
    import gradio as gr
except ImportError:
    print("请安装gradio: pip install gradio")
    sys.exit(1)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# RDKit可视化
try:
    from rdkit.Chem import Draw
    from rdkit.Chem.Draw import rdMolDraw2D
    HAS_RDKIT_DRAW = True
except:
    HAS_RDKIT_DRAW = False


# =============================================================================
# 任务类型定义
# =============================================================================

class TaskType(Enum):
    INITIAL_OPT = "initial_opt"
    SCAN = "scan"
    TS_OPT = "ts_opt"
    TS_FIX = "ts_fix"  # 新增: TS修复
    REFINE_SCAN = "refine_scan"  # 新增: 精细扫描
    REACTANT_ENERGY = "reactant_energy"  # 新增: 反应物能量
    PRODUCT_ENERGY = "product_energy"  # 新增: 产物能量

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    """任务定义"""
    task_id: str
    task_type: TaskType
    status: TaskStatus
    distance: Optional[float] = None
    description: str = ""
    method: str = ""
    result: Optional[dict] = None
    log_file: Optional[str] = None
    chk_file: Optional[str] = None
    gjf_file: Optional[str] = None
    energy: Optional[float] = None
    frequencies: Optional[list] = None
    imag_freqs: Optional[list] = None
    convergence_count: int = 0  # 收敛表格数量
    
    def __lt__(self, other):
        type_order = {TaskType.INITIAL_OPT: 0, TaskType.REACTANT_ENERGY: 1, TaskType.SCAN: 2, TaskType.REFINE_SCAN: 3, TaskType.TS_OPT: 4, TaskType.TS_FIX: 5, TaskType.PRODUCT_ENERGY: 6}
        if self.task_type != other.task_type:
            return type_order[self.task_type] < type_order[other.task_type]
        if self.distance is not None and other.distance is not None:
            return self.distance > other.distance
        return False


# =============================================================================
# 项目配置类
# =============================================================================

@dataclass
class ProjectConfig:
    """项目配置 - 保存到config.json"""
    aromatic_smiles: str = "c1ccccc1"
    aromatic_name: str = "Benzene"
    halogen_preset: str = "Br2"
    scheme_name: str = "fast_wB97XD"
    solvent: str = "Dichloromethane"
    solvent_model: str = "SMD"
    c_x_distance: float = 3.0
    c_x_x_angle: float = 175.0
    ipso_carbon: int = 1
    enable_symmetry: bool = True
    opt_mode: str = "CalcFC"
    nproc: int = 18
    memory: str = "20GB"
    scan_start: float = 3.0
    scan_end: float = 1.9
    step_size: float = 0.1
    auto_stop: bool = True
    energy_threshold: float = 0.5
    # 新增: 反应物和产物能量计算选项
    calc_reactant_energy: bool = True
    calc_product_energy: bool = True
    reactant_opt_before_sp: bool = True  # 优化后再计算单点
    product_opt_before_sp: bool = True
    
    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}
    
    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
    
    def save(self, work_dir):
        path = Path(work_dir) / "config.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, work_dir):
        path = Path(work_dir) / "config.json"
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return cls.from_dict(json.load(f))
        return None


# =============================================================================
# 应用状态管理
# =============================================================================

class AppState:
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.project_config: Optional[ProjectConfig] = None
        self.work_dir: Optional[str] = None
        self.complex_mol = None
        self.scan_pair = None
        self.is_running = False
        self.stop_requested = False
        self.all_tasks: List[Task] = []  # 所有任务(含已完成)
        self.scan_results: List[dict] = []
        self.ts_guess_idx: Optional[int] = None
        self.log_messages = []
        self.current_task_idx: int = -1
        self.initial_mol = None
        self.optimized_mol = None
        self.is_loaded_project = False  # 是否是加载的历史项目
        # 新增: 反应物、TS、产物能量 (用于能量图)
        self.reactant_energy: Optional[float] = None
        self.ts_energy: Optional[float] = None
        self.product_energy: Optional[float] = None
        self.reactant_mol = None
        self.product_mol = None
        self.running_processes: List[subprocess.Popen] = []  # 正在运行的进程
        # TS和对称性设置
        self.auto_ts_calc: bool = True
        self.symmetry_offset: float = 0.05
    
    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_messages.append(f"[{ts}] {msg}")
        if len(self.log_messages) > 500:
            self.log_messages = self.log_messages[-500:]
    
    def get_log_text(self):
        return "\n".join(self.log_messages[-100:])
    
    def add_scan_result(self, distance, energy, geometry, mol):
        self.scan_results.append({
            'distance': distance, 'energy': energy,
            'geometry': geometry, 'mol': copy.deepcopy(mol) if mol else None
        })
        self.scan_results.sort(key=lambda x: x['distance'], reverse=True)
    
    def get_pending_tasks(self):
        return [t for t in self.all_tasks if t.status == TaskStatus.PENDING]
    
    def get_next_task(self):
        for t in self.all_tasks:
            if t.status == TaskStatus.PENDING:
                return t
        return None

state = AppState()


# =============================================================================
# RDKit可视化
# =============================================================================

def mol_to_image_base64(mol, size=(400, 300)):
    """将RDKit分子转为Base64图片"""
    if mol is None or not HAS_RDKIT_DRAW:
        return None
    try:
        drawer = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
        drawer.drawOptions().addStereoAnnotation = True
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        img_data = drawer.GetDrawingText()
        return base64.b64encode(img_data).decode('utf-8')
    except:
        return None

def mol_to_image_html(mol, size=(400, 300)):
    """生成可嵌入的HTML图片"""
    b64 = mol_to_image_base64(mol, size)
    if b64:
        return f'<img src="data:image/png;base64,{b64}" />'
    return "<p>无法生成结构图</p>"

def mol_to_xyz(mol):
    """RDKit分子转XYZ格式"""
    if mol is None:
        return ""
    try:
        conf = mol.GetConformer()
        lines = [str(mol.GetNumAtoms()), ""]
        for i in range(mol.GetNumAtoms()):
            a = mol.GetAtomWithIdx(i)
            p = conf.GetAtomPosition(i)
            lines.append(f"{a.GetSymbol()} {p.x:.6f} {p.y:.6f} {p.z:.6f}")
        return "\n".join(lines)
    except:
        return ""


def generate_structure_preview(aromatic_smiles, aromatic_name, halogen_preset,
                              c_x_distance, c_x_x_angle, ipso_carbon, enable_symmetry):
    """生成结构预览"""
    try:
        # 获取卤素预设
        halogen = HALOGEN_PRESETS[halogen_preset]
        
        # 生成分子
        mol = generate_endon_complex(
            aromatic_smiles, 
            halogen.smiles,
            ipso_carbon - 1,  # 转换为0-based
            c_x_distance,
            c_x_x_angle,
            halogen.xx_bond_length,
            enable_symmetry
        )
        
        if mol is None:
            return "❌ 结构生成失败", "<p>无法生成分子结构</p>"
        
        # 生成3D视图
        html_3d = view_3d_structure(mol, "预览结构")
        
        # 信息文本
        info = f"✅ 结构生成成功\n"
        info += f"芳香族: {aromatic_name} ({aromatic_smiles})\n"
        info += f"卤素: {halogen_preset}\n"
        info += f"初始距离: {c_x_distance} Å\n"
        info += f"角度: {c_x_x_angle}°\n"
        info += f"进攻碳: C{ipso_carbon}\n"
        info += f"对称性: {'启用' if enable_symmetry else '禁用'}\n"
        info += f"原子数: {mol.GetNumAtoms()}"
        
        return info, html_3d
        
    except Exception as e:
        return f"❌ 错误: {str(e)}", f"<p>生成失败: {e}</p>"


# =============================================================================
# 收敛表格解析
# =============================================================================

def parse_all_convergence_tables(log_file):
    """解析log文件中的所有收敛表格"""
    if not log_file or not os.path.exists(log_file):
        return []
    
    tables = []
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 更健壮的匹配模式 - 匹配完整的收敛表格块
        pattern = r'Item\s+Value\s+Threshold\s+Converged\?\s*\n\s*' \
                  r'Maximum Force\s+(\S+)\s+(\S+)\s+(YES|NO)\s*\n\s*' \
                  r'RMS\s+Force\s+(\S+)\s+(\S+)\s+(YES|NO)\s*\n\s*' \
                  r'Maximum Displacement\s+(\S+)\s+(\S+)\s+(YES|NO)\s*\n\s*' \
                  r'RMS\s+Displacement\s+(\S+)\s+(\S+)\s+(YES|NO)'
        
        matches = list(re.finditer(pattern, content))
        
        for i, match in enumerate(matches):
            table_data = [
                {'item': 'Maximum Force', 'value': match.group(1), 'threshold': match.group(2), 'converged': '✅' if match.group(3) == 'YES' else '❌'},
                {'item': 'RMS Force', 'value': match.group(4), 'threshold': match.group(5), 'converged': '✅' if match.group(6) == 'YES' else '❌'},
                {'item': 'Maximum Displacement', 'value': match.group(7), 'threshold': match.group(8), 'converged': '✅' if match.group(9) == 'YES' else '❌'},
                {'item': 'RMS Displacement', 'value': match.group(10), 'threshold': match.group(11), 'converged': '✅' if match.group(12) == 'YES' else '❌'},
            ]
            tables.append({'index': i + 1, 'data': table_data})
    except Exception as e:
        print(f"解析收敛表格出错: {e}")
    
    return tables

def format_convergence_table(table_data):
    """格式化单个收敛表格为Markdown"""
    if not table_data:
        return "无数据"
    
    lines = ["| 项目 | 值 | 阈值 | 收敛 |", "|------|-----|------|------|"]
    for row in table_data:
        lines.append(f"| {row['item']} | {row['value']} | {row['threshold']} | {row['converged']} |")
    return "\n".join(lines)

def get_log_files_in_workdir():
    """获取工作目录中的所有log文件"""
    if not state.work_dir:
        return []
    log_files = glob.glob(os.path.join(state.work_dir, "*.log"))
    return [os.path.basename(f) for f in sorted(log_files)]


def parse_scf_cycles(log_file):
    """解析log文件中的SCF循环信息"""
    if not log_file or not os.path.exists(log_file):
        return []
    
    scf_cycles = []
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 匹配SCF循环: "SCF Done:  E(RwB97XD) =  -5380.85541200     A.U. after   12 cycles"
        pattern = r'SCF Done:\s+E\((\w+)\)\s*=\s*([-\d.]+)\s+A\.U\.\s+after\s+(\d+)\s+cycles'
        matches = re.finditer(pattern, content)
        
        for match in matches:
            scf_cycles.append({
                'method': match.group(1),
                'energy': float(match.group(2)),
                'cycles': int(match.group(3))
            })
        
        # 匹配正在进行的SCF: "Cycle   5  Pass 1  IDiag  1: E= -5380.8522..."
        current_pattern = r'Cycle\s+(\d+)\s+Pass\s+\d+.*?E=\s*([-\d.E+]+)'
        current_matches = list(re.finditer(current_pattern, content))
        
        if current_matches:
            last_match = current_matches[-1]
            scf_cycles.append({
                'method': 'In Progress',
                'energy': float(last_match.group(2)),
                'cycles': int(last_match.group(1)),
                'in_progress': True
            })
    except Exception as e:
        print(f"解析SCF循环出错: {e}")
    
    return scf_cycles


def parse_warnings_errors(log_file):
    """解析log文件中的所有警告和错误"""
    if not log_file or not os.path.exists(log_file):
        return {'warnings': [], 'errors': []}
    
    warnings = []
    errors = []
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # 警告匹配
            if 'warning' in line_lower or 'warning!' in line_lower:
                warnings.append({'line': i+1, 'text': line.strip()})
            
            # 错误匹配
            if 'error' in line_lower and 'error termination' not in line_lower:
                errors.append({'line': i+1, 'text': line.strip()})
            
            # Gaussian特定警告
            if 'small imaginary frequenc' in line_lower:
                warnings.append({'line': i+1, 'text': line.strip()})
            if 'eigenvalue problem' in line_lower:
                warnings.append({'line': i+1, 'text': line.strip()})
            if 'convergence failure' in line_lower:
                errors.append({'line': i+1, 'text': line.strip()})
            if 'imaginary frequenc' in line_lower and 'ts' not in line_lower:
                warnings.append({'line': i+1, 'text': line.strip()})
            
            # 错误终止
            if 'error termination' in line_lower:
                # 获取前几行作为上下文
                context_start = max(0, i-3)
                context = ''.join(lines[context_start:i+1])
                errors.append({'line': i+1, 'text': f"错误终止:\n{context.strip()}"})
            
            # Link死亡
            if 'galloc' in line_lower or 'out-of-memory' in line_lower:
                errors.append({'line': i+1, 'text': line.strip()})
    
    except Exception as e:
        print(f"解析警告/错误出错: {e}")
    
    return {'warnings': warnings, 'errors': errors}


def get_scf_status_text():
    """获取当前SCF状态的文本描述"""
    if not state.work_dir:
        return "无工作目录"
    
    log_files = glob.glob(os.path.join(state.work_dir, "*.log"))
    if not log_files:
        return "无log文件"
    
    latest_log = max(log_files, key=os.path.getmtime)
    scf_cycles = parse_scf_cycles(latest_log)
    
    if not scf_cycles:
        return f"**{os.path.basename(latest_log)}**\n\n等待SCF开始..."
    
    lines = [f"**{os.path.basename(latest_log)}**\n"]
    
    # 显示已完成的SCF
    completed = [s for s in scf_cycles if not s.get('in_progress')]
    if completed:
        lines.append(f"✅ 已完成 {len(completed)} 个SCF计算")
        last_done = completed[-1]
        lines.append(f"   最近: {last_done['cycles']}轮 → E = {last_done['energy']:.6f} Ha")
    
    # 显示正在进行的SCF
    in_progress = [s for s in scf_cycles if s.get('in_progress')]
    if in_progress:
        current = in_progress[-1]
        lines.append(f"\n🔄 **正在进行**: 第{current['cycles']}轮")
        lines.append(f"   当前E = {current['energy']:.6f} Ha")
    
    return "\n".join(lines)


def get_all_warnings_errors():
    """获取所有log文件的警告和错误"""
    if not state.work_dir:
        return "无工作目录"
    
    log_files = glob.glob(os.path.join(state.work_dir, "*.log"))
    if not log_files:
        return "无log文件"
    
    all_warnings = []
    all_errors = []
    
    for log_file in sorted(log_files, key=os.path.getmtime, reverse=True):
        basename = os.path.basename(log_file)
        result = parse_warnings_errors(log_file)
        
        for w in result['warnings']:
            all_warnings.append(f"[{basename}:{w['line']}] {w['text']}")
        for e in result['errors']:
            all_errors.append(f"[{basename}:{e['line']}] {e['text']}")
    
    lines = []
    
    if all_errors:
        lines.append(f"## ❌ 错误 ({len(all_errors)})")
        for e in all_errors[:20]:  # 最多显示20个
            lines.append(f"- {e}")
        if len(all_errors) > 20:
            lines.append(f"... 还有 {len(all_errors)-20} 个错误")
        lines.append("")
    
    if all_warnings:
        lines.append(f"## ⚠️ 警告 ({len(all_warnings)})")
        for w in all_warnings[:30]:  # 最多显示30个
            lines.append(f"- {w}")
        if len(all_warnings) > 30:
            lines.append(f"... 还有 {len(all_warnings)-30} 个警告")
    
    if not lines:
        return "✅ 无警告或错误"
    
    return "\n".join(lines)


# =============================================================================
# 数据分析功能 (重新设计)
# =============================================================================

def get_available_data_series():
    """获取所有可用的数据系列 - 包括所有out文件夹项目和内置数据"""
    series_list = []
    
    # 1. 当前项目数据
    if state.scan_results:
        series_list.append("Current-Scan")
    
    has_reactant = False
    has_ts = False
    has_product = False
    
    for task in state.all_tasks:
        if task.status == TaskStatus.COMPLETED and task.energy:
            if task.task_type == TaskType.REACTANT_ENERGY or task.task_type == TaskType.INITIAL_OPT:
                has_reactant = True
            elif task.task_type == TaskType.TS_OPT:
                has_ts = True
            elif task.task_type == TaskType.PRODUCT_ENERGY:
                has_product = True
    
    if has_reactant or has_ts or has_product:
        series_list.append("Current-Energy")
    
    # 2. 扫描所有out文件夹中的项目
    if OUT_DIR.exists():
        for project_dir in sorted(OUT_DIR.iterdir(), reverse=True):
            if project_dir.is_dir():
                project_name = project_dir.name
                # 跳过当前加载的项目
                if state.work_dir and Path(state.work_dir).name == project_name:
                    continue
                
                # 检查是否有normal_data.txt或log文件
                normal_data_file = project_dir / "normal_data.txt"
                has_scan_logs = bool(glob.glob(str(project_dir / "*_scan_*.log")))
                has_ts_logs = bool(glob.glob(str(project_dir / "*_TS*.log")) or glob.glob(str(project_dir / "*_ts_*.log")))
                
                if normal_data_file.exists():
                    # 读取normal_data检查内容
                    try:
                        mock_data = read_normal_data_file(str(project_dir))
                        if mock_data.get('scans'):
                            series_list.append(f"Project:{project_name}-Scan")
                        if mock_data.get('reactant') or mock_data.get('ts') or mock_data.get('product'):
                            series_list.append(f"Project:{project_name}-Energy")
                    except:
                        pass
                elif has_scan_logs or has_ts_logs:
                    series_list.append(f"Project:{project_name}-Logs")
    
    # 3. 内置数据集
    import pandas as pd
    from io import StringIO
    try:
        df_builtin = pd.read_csv(StringIO(csv_data), skipinitialspace=True)
        for idx, row in df_builtin.iterrows():
            label = f"{row['Substrate']}-{row['Halogen']}"
            if row['Position'] != '-':
                label += f"-{row['Position']}"
            if row['Catalyst'] != 'None':
                label += f"-{row['Catalyst']}"
            series_list.append(f"Builtin:{label}")
    except Exception as e:
        print(f"Failed to load builtin data: {e}")
    
    return series_list

def plot_selected_series(selected_series, plot_type):
    """绘制选中的数据系列"""
    if not selected_series:
        return None, "Please select at least one data series"
    
    import pandas as pd
    from io import StringIO
    
    fig, ax = plt.subplots(figsize=(12, 7))
    analysis_text = ""
    
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    color_idx = 0
    
    def plot_scan_data(distances, energies, label):
        nonlocal color_idx, analysis_text
        if not distances or not energies:
            return
        sorted_data = sorted(zip(distances, energies))
        distances = [d for d, e in sorted_data]
        energies = [e for d, e in sorted_data]
        
        min_energy = min(energies)
        rel_energies = [(e - min_energy) * 2625.5 for e in energies]
        
        ax.plot(distances, rel_energies, 'o-', linewidth=2.5, markersize=6,
               label=label, color=colors[color_idx % 10])
        color_idx += 1
        
        max_idx = rel_energies.index(max(rel_energies))
        ax.annotate(f'{rel_energies[max_idx]:.1f}',
                   (distances[max_idx], rel_energies[max_idx]),
                   textcoords="offset points", xytext=(0, 8), ha='center',
                   fontsize=9, fontweight='bold', color=colors[color_idx-1])
        
        analysis_text += f"{label}:\n"
        analysis_text += f"  Scan points: {len(distances)}\n"
        analysis_text += f"  Distance range: {min(distances):.2f} - {max(distances):.2f} A\n"
        analysis_text += f"  Energy range: {min(rel_energies):.1f} - {max(rel_energies):.1f} kJ/mol\n\n"
    
    def plot_energy_profile(r_e, ts_e, p_e, label):
        nonlocal color_idx, analysis_text
        energies_dict = {}
        if r_e: energies_dict['R'] = r_e
        if ts_e: energies_dict['TS'] = ts_e
        if p_e: energies_dict['P'] = p_e
        
        if len(energies_dict) < 2:
            return
        
        ref_e = energies_dict.get('R', min(energies_dict.values()))
        x_pos, y_values = [], []
        
        if 'R' in energies_dict:
            x_pos.append(0)
            y_values.append((energies_dict['R'] - ref_e) * 2625.5)
        if 'TS' in energies_dict:
            x_pos.append(1)
            y_values.append((energies_dict['TS'] - ref_e) * 2625.5)
        if 'P' in energies_dict:
            x_pos.append(2)
            y_values.append((energies_dict['P'] - ref_e) * 2625.5)
        
        ax.plot(x_pos, y_values, 'o-', linewidth=2.5, markersize=10,
               label=label, color=colors[color_idx % 10])
        color_idx += 1
        
        analysis_text += f"{label}:\n"
        if 'R' in energies_dict and 'TS' in energies_dict:
            ea = (energies_dict['TS'] - energies_dict['R']) * 2625.5
            analysis_text += f"  Ea: {ea:.1f} kJ/mol ({ea/4.184:.1f} kcal/mol)\n"
        if 'R' in energies_dict and 'P' in energies_dict:
            dh = (energies_dict['P'] - energies_dict['R']) * 2625.5
            analysis_text += f"  dH: {dh:.1f} kJ/mol ({dh/4.184:.1f} kcal/mol)\n"
        analysis_text += "\n"
    
    if plot_type == "Scan":
        analysis_text = "PES Scan Analysis:\n\n"
        
        for series_name in selected_series:
            if series_name == "Current-Scan":
                if state.scan_results:
                    distances = [r['distance'] for r in state.scan_results]
                    energies = [r['energy'] for r in state.scan_results]
                    plot_scan_data(distances, energies, "Current Project")
            
            elif series_name.startswith("Project:") and series_name.endswith("-Scan"):
                project_name = series_name.replace("Project:", "").replace("-Scan", "")
                project_dir = OUT_DIR / project_name
                try:
                    mock_data = read_normal_data_file(str(project_dir))
                    if mock_data.get('scans'):
                        distances = [s['distance'] for s in mock_data['scans']]
                        energies = [s['energy'] for s in mock_data['scans']]
                        plot_scan_data(distances, energies, project_name)
                except Exception as e:
                    print(f"Failed to load {project_name}: {e}")
        
        ax.set_xlabel('Distance (A)', fontsize=12)
        ax.set_ylabel('Relative Energy (kJ/mol)', fontsize=12)
        ax.set_title('PES Scan Energy Profile', fontsize=14, fontweight='bold')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        
    else:  # Reaction Energy Profile
        analysis_text = "Reaction Energy Analysis:\n\n"
        
        for series_name in selected_series:
            if series_name == "Current-Energy":
                r_e, ts_e, p_e = None, None, None
                for task in state.all_tasks:
                    if task.status == TaskStatus.COMPLETED and task.energy:
                        if task.task_type in [TaskType.REACTANT_ENERGY, TaskType.INITIAL_OPT]:
                            r_e = task.energy
                        elif task.task_type == TaskType.TS_OPT:
                            ts_e = task.energy
                        elif task.task_type == TaskType.PRODUCT_ENERGY:
                            p_e = task.energy
                plot_energy_profile(r_e, ts_e, p_e, "Current Project")
            
            elif series_name.startswith("Project:") and series_name.endswith("-Energy"):
                project_name = series_name.replace("Project:", "").replace("-Energy", "")
                project_dir = OUT_DIR / project_name
                try:
                    mock_data = read_normal_data_file(str(project_dir))
                    r_e = mock_data.get('reactant', {}).get('energy')
                    ts_e = mock_data.get('ts', {}).get('energy')
                    p_e = mock_data.get('product', {}).get('energy')
                    plot_energy_profile(r_e, ts_e, p_e, project_name)
                except Exception as e:
                    print(f"Failed to load {project_name}: {e}")
            
            elif series_name.startswith("Builtin:"):
                label_part = series_name.replace("Builtin:", "")
                try:
                    df_builtin = pd.read_csv(StringIO(csv_data), skipinitialspace=True)
                    for idx, row in df_builtin.iterrows():
                        row_label = f"{row['Substrate']}-{row['Halogen']}"
                        if row['Position'] != '-':
                            row_label += f"-{row['Position']}"
                        if row['Catalyst'] != 'None':
                            row_label += f"-{row['Catalyst']}"
                        
                        if row_label == label_part:
                            plot_energy_profile(row['R_Hartree'], row['TS_Hartree'], 
                                              row['P_Hartree'], row_label)
                            break
                except Exception as e:
                    print(f"Failed to load builtin: {e}")
        
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(['Reactant (R)', 'TS', 'Product (P)'])
        ax.set_ylabel('Relative Energy (kJ/mol)', fontsize=12)
        ax.set_title('Reaction Energy Profile', fontsize=14, fontweight='bold')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
    
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if not analysis_text.strip():
        analysis_text = "No data available for analysis"
    
    return fig, analysis_text

def analyze_with_ai_enhanced(data_description, analysis_results, user_prompt="", backend="本地Ollama", ollama_model="llama2"):
    """增强版AI分析 - 支持本地Ollama和OpenAI API"""
    if not (HAS_OLLAMA or HAS_REQUESTS):
        return "需要安装ollama或requests库进行AI分析\n\npip install ollama  # 本地Ollama\npip install requests  # API调用"
    
    prompt = f"""
请分析以下计算化学数据和分析结果：

数据描述: {data_description}

分析结果: {analysis_results}

用户问题: {user_prompt if user_prompt else "请提供详细的科学分析和解释"}

请从以下方面进行分析：
1. 数据趋势和特征分析
2. 化学机理解释
3. 与已知文献的比较
4. 实验建议和进一步计算方向
5. 潜在的异常或值得注意的点

请用专业但易懂的语言回答。
"""
    
    try:
        if backend == "本地Ollama":
            if not HAS_OLLAMA:
                return "未安装ollama库，请运行: pip install ollama"
            
            response = ollama.chat(model=ollama_model, messages=[{'role': 'user', 'content': prompt}])
            return response['message']['content']
        
        elif backend == "OpenAI API":
            if not HAS_REQUESTS:
                return "未安装requests库，请运行: pip install requests"
            
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                return "请设置OPENAI_API_KEY环境变量\n\n在Windows上设置:\nset OPENAI_API_KEY=your_api_key_here\n\n或在Python中:\nimport os\nos.environ['OPENAI_API_KEY'] = 'your_api_key_here'"
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            data = {
                'model': 'gpt-3.5-turbo',
                'messages': [{'role': 'user', 'content': prompt}]
            }
            response = requests.post('https://api.openai.com/v1/chat/completions', 
                                   headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"API调用失败: {response.status_code}\n{response.text}"
        
        else:
            return f"未知的AI后端: {backend}"
    
    except Exception as e:
        import traceback
        return f"AI分析出错: {str(e)}\n\n{traceback.format_exc()}"


# =============================================================================
# TS修复功能 - 沿虚频方向调整原子
# =============================================================================

def parse_vibration_displacement(log_file, freq_index=0):
    """解析虚频的原子位移向量"""
    if not os.path.exists(log_file):
        return None
    
    displacements = []
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 找到频率部分
        freq_sections = re.findall(r'Frequencies --\s+([-\d.]+)\s+([-\d.]+)?\s*([-\d.]+)?.*?(?=Frequencies --|Thermochemistry|$)', 
                                   content, re.DOTALL)
        
        # 简化实现：返回None表示暂不支持
        # 完整实现需要解析Gaussian输出中的原子位移向量
        return None
    except:
        return None

def fix_ts_along_imaginary_mode(mol, log_file, displacement_scale=0.1):
    """沿虚频方向调整结构以消除小虚频"""
    # 这是一个占位实现
    # 完整实现需要：
    # 1. 解析log中最小绝对值虚频的位移向量
    # 2. 将原子沿该方向移动
    return None, "TS修复功能开发中，需要解析Gaussian振动模式输出"


# =============================================================================
# 普通格式数据文件读取功能
# =============================================================================

def read_mock_data_file(work_dir):
    """兼容旧接口：读取普通格式数据文件。"""
    return read_normal_data_file(work_dir)


def read_normal_data_file(work_dir):
    """
    从工作目录读取统一的普通格式数据文件 normal_data.txt
    
    文件格式示例:
    # 普通格式数据文件 - 用于导入非脚本计算数据与测试功能
    # 普通格式数据与Gaussian log文件可混合使用
    
    [INITIAL_OPT]
    ENERGY: -1152.602145
    FREQUENCIES: 50.2, 100.3, 200.4, 350.5
    
    [REACTANT_ENERGY]
    ENERGY: -1152.602145
    
    [SCAN]
    DISTANCE: 3.0
    ENERGY: -1152.580000
    
    [SCAN]
    DISTANCE: 2.9
    ENERGY: -1152.570000
    
    [TS_OPT]
    ENERGY: -1152.540790
    FREQUENCIES: -456.7, 50.2, 100.3, 200.4
    
    [PRODUCT_ENERGY]
    ENERGY: -1152.642304
    """
    if not work_dir:
        return {}
    
    # 寻找所有匹配的普通格式数据文件
    import glob
    normal_files = glob.glob(os.path.join(work_dir, "normal_data*.txt"))
    mock_files = glob.glob(os.path.join(work_dir, "mock_data*.txt"))
    
    candidate_files = normal_files + mock_files
    if not candidate_files:
        return {}
    
    # 优先选择normal_data.txt，如果没有则选择第一个找到的文件
    data_file = None
    for file_path in candidate_files:
        if os.path.basename(file_path) == "normal_data.txt":
            data_file = file_path
            break
    if not data_file:
        data_file = candidate_files[0]
    
    mock_data = {
        'initial_opt': [],
        'reactant_energy': [],
        'scan': [],
        'ts_opt': [],
        'product_energy': [],
        'refine_scan': [],
        'ts_fix': []
    }
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 按section解析
        current_section = None
        current_data = {}
        
        for line in content.split('\n'):
            line = line.strip()
            
            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue
            
            # 检测section标记
            if line.startswith('[') and line.endswith(']'):
                # 保存之前的section
                if current_section and current_data:
                    section_key = current_section.lower()
                    if section_key in mock_data:
                        mock_data[section_key].append(current_data.copy())
                
                # 开始新section
                current_section = line[1:-1].strip()
                current_data = {'type': current_section}
                continue
            
            # 解析数据行
            if ':' in line and current_section:
                key, value = line.split(':', 1)
                key = key.strip().upper()
                value = value.strip()
                
                if key == 'ENERGY':
                    current_data['energy'] = float(value)
                elif key == 'DISTANCE':
                    current_data['distance'] = float(value)
                elif key == 'FREQUENCIES':
                    current_data['frequencies'] = [float(f.strip()) for f in value.split(',') if f.strip()]
                elif key == 'CONVERGED':
                    current_data['converged'] = value.upper() in ['YES', 'TRUE', '1']
        
        # 保存最后一个section
        if current_section and current_data:
            section_key = current_section.lower()
            if section_key in mock_data:
                mock_data[section_key].append(current_data.copy())
        
        return mock_data
    
    except Exception as e:
        print(f"读取普通格式数据文件失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


def create_mock_data_template(work_dir, aromatic_name, halogen_name):
    """兼容旧接口：创建普通格式数据文件模板。"""
    return create_normal_data_template(work_dir, aromatic_name, halogen_name)


def create_normal_data_template(work_dir, aromatic_name, halogen_name):
    """创建普通格式数据文件模板"""
    mock_file = os.path.join(work_dir, "normal_data.txt")
    
    with open(mock_file, 'w', encoding='utf-8') as f:
        f.write("# 普通格式数据文件 - 用于演示、导入与测试\n")
        f.write(f"# 项目: {aromatic_name} + {halogen_name}\n")
        f.write("# 普通格式数据与Gaussian log数据可混合使用\n")
        f.write("# 如果某个任务有真实log文件，会优先使用log数据\n\n")
        
        f.write("[INITIAL_OPT]\n")
        f.write("ENERGY: -1152.602145\n")
        f.write("FREQUENCIES: 50.2, 100.3, 200.4, 350.5\n\n")
        
        f.write("[REACTANT_ENERGY]\n")
        f.write("ENERGY: -1152.602145\n\n")
        
        # 扫描点
        scan_energies = [
            (3.0, -1152.580),
            (2.9, -1152.570),
            (2.8, -1152.555),
            (2.7, -1152.545),
            (2.6, -1152.538),
            (2.5, -1152.535),
            (2.4, -1152.540),
            (2.3, -1152.550),
            (2.2, -1152.565),
            (2.1, -1152.580),
            (2.0, -1152.600),
        ]
        
        for dist, energy in scan_energies:
            f.write("[SCAN]\n")
            f.write(f"DISTANCE: {dist:.2f}\n")
            f.write(f"ENERGY: {energy:.6f}\n\n")
        
        f.write("[TS_OPT]\n")
        f.write("ENERGY: -1152.540790\n")
        f.write("FREQUENCIES: -456.7, 50.2, 100.3, 200.4\n\n")
        
        f.write("[PRODUCT_ENERGY]\n")
        f.write("ENERGY: -1152.642304\n")
    
    return mock_file


def export_calculation_to_normal_data(work_dir=None):
    """
    导出当前计算数据为normal_data.txt格式
    从state中的任务和扫描结果导出
    """
    if work_dir is None:
        work_dir = state.work_dir
    
    if not work_dir:
        return None, "没有工作目录"
    
    output_file = os.path.join(work_dir, "normal_data_exported.txt")
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 普通格式数据文件 - 从计算结果导出\n")
            f.write(f"# 导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if state.project_config:
                f.write(f"# 项目: {state.project_config.aromatic_name} + {state.project_config.halogen_preset}\n")
            f.write("\n")
            
            # 导出初始优化/反应物能量
            reactant_energy = None
            reactant_frequencies = []
            for task in state.all_tasks:
                if task.task_type == TaskType.INITIAL_OPT and task.status == TaskStatus.COMPLETED and task.energy:
                    reactant_energy = task.energy
                    reactant_frequencies = task.frequencies or []
                    break
            
            if reactant_energy:
                f.write("[INITIAL_OPT]\n")
                f.write(f"ENERGY: {reactant_energy:.6f}\n")
                if reactant_frequencies:
                    freq_str = ', '.join([f"{freq:.1f}" for freq in reactant_frequencies[:6]])
                    f.write(f"FREQUENCIES: {freq_str}\n")
                f.write("\n")
                
                f.write("[REACTANT_ENERGY]\n")
                f.write(f"ENERGY: {reactant_energy:.6f}\n\n")
            
            # 导出反应物能量任务
            for task in state.all_tasks:
                if task.task_type == TaskType.REACTANT_ENERGY and task.status == TaskStatus.COMPLETED and task.energy:
                    if task.energy != reactant_energy:
                        f.write("[REACTANT_ENERGY]\n")
                        f.write(f"ENERGY: {task.energy:.6f}\n\n")
                    break
            
            # 导出扫描数据
            scan_count = 0
            for result in sorted(state.scan_results, key=lambda x: -x['distance']):
                f.write("[SCAN]\n")
                f.write(f"DISTANCE: {result['distance']:.2f}\n")
                f.write(f"ENERGY: {result['energy']:.6f}\n\n")
                scan_count += 1
            
            # 从任务中导出扫描数据（如果scan_results为空）
            if scan_count == 0:
                for task in sorted(state.all_tasks, key=lambda t: -(t.distance or 0)):
                    if task.task_type == TaskType.SCAN and task.status == TaskStatus.COMPLETED and task.energy and task.distance:
                        f.write("[SCAN]\n")
                        f.write(f"DISTANCE: {task.distance:.2f}\n")
                        f.write(f"ENERGY: {task.energy:.6f}\n\n")
                        scan_count += 1
            
            # 导出TS优化
            for task in state.all_tasks:
                if task.task_type == TaskType.TS_OPT and task.status == TaskStatus.COMPLETED and task.energy:
                    f.write("[TS_OPT]\n")
                    f.write(f"ENERGY: {task.energy:.6f}\n")
                    if task.frequencies:
                        freq_str = ', '.join([f"{freq:.1f}" for freq in task.frequencies[:6]])
                        f.write(f"FREQUENCIES: {freq_str}\n")
                    f.write("\n")
                    break
            
            # 导出产物能量
            for task in state.all_tasks:
                if task.task_type == TaskType.PRODUCT_ENERGY and task.status == TaskStatus.COMPLETED and task.energy:
                    f.write("[PRODUCT_ENERGY]\n")
                    f.write(f"ENERGY: {task.energy:.6f}\n")
                    break
        
        state.log(f"📤 已导出计算数据到: {output_file}")
        return output_file, f"已导出 {scan_count} 个扫描点和其他数据到:\n{output_file}"
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"导出失败: {str(e)}"


def supplement_normal_data_from_scan(work_dir=None):
    if work_dir is None:
        work_dir = state.work_dir

    if not work_dir:
        return None, "没有工作目录"

    # 只补缺失，不覆盖已有任务/能量
    has_scan = bool(state.scan_results)
    if not has_scan:
        return None, "没有扫描数据，无法从扫描补全"

    def _has_completed_task(task_type: "TaskType") -> bool:
        for t in state.all_tasks:
            if t.task_type == task_type and t.status == TaskStatus.COMPLETED and t.energy is not None:
                return True
        return False

    # 估算能量点（保持与扫描同一基准）
    scan_sorted = sorted(
        [(float(r['distance']), float(r['energy'])) for r in state.scan_results if r.get('distance') is not None and r.get('energy') is not None],
        key=lambda x: x[0]
    )
    if not scan_sorted:
        return None, "扫描数据为空，无法补全"

    dist_min, e_min = min(scan_sorted, key=lambda x: x[1])
    dist_max = max(scan_sorted, key=lambda x: x[0])[0]
    e_r = next((e for d, e in reversed(scan_sorted) if abs(d - dist_max) < 1e-6), scan_sorted[-1][1])
    e_ts = max(scan_sorted, key=lambda x: x[1])[1]
    e_p = e_min

    output_file = os.path.join(work_dir, "normal_data.txt")

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# normal_data.txt (补全缺失能量点)\n")
            if state.project_config:
                f.write(f"# 项目: {state.project_config.aromatic_name} + {state.project_config.halogen_preset}\n")
            f.write(f"# 导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            wrote_any = False

            if not _has_completed_task(TaskType.REACTANT_ENERGY):
                f.write("[REACTANT_ENERGY]\n")
                f.write(f"ENERGY: {e_r:.6f}\n\n")
                wrote_any = True

            if not _has_completed_task(TaskType.TS_OPT):
                f.write("[TS_OPT]\n")
                f.write(f"ENERGY: {e_ts:.6f}\n")
                f.write("FREQUENCIES: -450.0, 40.0, 100.0, 180.0, 250.0, 320.0\n\n")
                wrote_any = True

            if not _has_completed_task(TaskType.PRODUCT_ENERGY):
                f.write("[PRODUCT_ENERGY]\n")
                f.write(f"ENERGY: {e_p:.6f}\n")
                wrote_any = True

        if not wrote_any:
            return output_file, "无需补全：反应物/TS/产物能量点均已存在"

        return output_file, f"已补全缺失能量点到:\n{output_file}"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"补全失败: {str(e)}"


def export_from_log_files(work_dir=None):
    """
    从log文件中读取真实数据并导出为normal_data.txt格式
    """
    if work_dir is None:
        work_dir = state.work_dir
    
    if not work_dir:
        return None, "没有工作目录"
    
    output_file = os.path.join(work_dir, "normal_data_from_logs.txt")
    
    try:
        log_prefix = ""
        try:
            if state.project_config and state.project_config.aromatic_name and state.project_config.halogen_preset:
                halogen_obj = HALOGEN_PRESETS.get(state.project_config.halogen_preset)
                halogen_name = halogen_obj.name if halogen_obj else state.project_config.halogen_preset
                log_prefix = f"{state.project_config.aromatic_name}_{halogen_name}_"
        except Exception:
            log_prefix = ""

        if log_prefix:
            log_files = glob.glob(os.path.join(work_dir, f"{log_prefix}*.log"))
        else:
            log_files = glob.glob(os.path.join(work_dir, "*.log"))
        if not log_files:
            return None, "没有找到log文件"
        
        data = {
            'initial_opt': None,
            'scans': [],
            'ts_opt': None,
            'product': None
        }
        
        for log_file in sorted(log_files):
            basename = os.path.basename(log_file)
            result = read_gaussian16_output_opt(log_file)
            
            if not result or not result.get('energy'):
                continue
            
            if 'initial_opt' in basename.lower() or ('opt' in basename.lower() and 'ts' not in basename.lower()):
                if not data['initial_opt']:
                    data['initial_opt'] = result
            
            elif 'scan_step' in basename:
                step_match = re.search(r'step_(\d+)', basename)
                step = int(step_match.group(1)) if step_match else len(data['scans']) + 1
                # 估算距离（假设从3.0开始，步长0.1）
                distance = 3.0 - (step - 1) * 0.1
                result['distance'] = distance
                result['step'] = step
                data['scans'].append(result)
            
            elif 'ts_opt' in basename.lower() or 'ts' in basename.lower():
                data['ts_opt'] = result
            
            elif 'product' in basename.lower():
                data['product'] = result
        
        # 按步骤排序扫描
        data['scans'].sort(key=lambda x: x.get('step', 0))
        
        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 普通格式数据文件 - 从log文件导出\n")
            f.write(f"# 导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 源目录: {work_dir}\n\n")
            
            if data['initial_opt']:
                f.write("[INITIAL_OPT]\n")
                f.write(f"ENERGY: {data['initial_opt']['energy']:.6f}\n")
                if data['initial_opt'].get('frequencies'):
                    freq_str = ', '.join([f"{freq:.1f}" for freq in data['initial_opt']['frequencies'][:6]])
                    f.write(f"FREQUENCIES: {freq_str}\n")
                f.write("\n")
                
                f.write("[REACTANT_ENERGY]\n")
                f.write(f"ENERGY: {data['initial_opt']['energy']:.6f}\n\n")
            
            for scan in data['scans']:
                f.write("[SCAN]\n")
                f.write(f"DISTANCE: {scan['distance']:.2f}\n")
                f.write(f"ENERGY: {scan['energy']:.6f}\n\n")
            
            if data['ts_opt']:
                f.write("[TS_OPT]\n")
                f.write(f"ENERGY: {data['ts_opt']['energy']:.6f}\n")
                if data['ts_opt'].get('frequencies'):
                    freq_str = ', '.join([f"{freq:.1f}" for freq in data['ts_opt']['frequencies'][:6]])
                    f.write(f"FREQUENCIES: {freq_str}\n")
                f.write("\n")
            
            if data['product']:
                f.write("[PRODUCT_ENERGY]\n")
                f.write(f"ENERGY: {data['product']['energy']:.6f}\n")
        
        scan_count = len(data['scans'])
        state.log(f"📤 已从log文件导出数据到: {output_file}")
        return output_file, f"已从log文件导出 {scan_count} 个扫描点到:\n{output_file}"
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"导出失败: {str(e)}"


def load_mock_data_from_workdir(work_dir):
    """从工作目录加载普通格式数据并创建相应任务"""
    if not work_dir:
        return

    mock_data = read_normal_data_file(work_dir)
    if not mock_data:
        return

    def _has_completed_task(task_type: "TaskType") -> bool:
        for t in state.all_tasks:
            if t.task_type == task_type and t.status == TaskStatus.COMPLETED and t.energy is not None:
                return True
        return False

    def _has_scan_at_distance(dist: float, tol: float = 1e-3) -> bool:
        # 1) scan_results 去重
        for r in state.scan_results:
            try:
                if abs(float(r.get('distance', 0.0)) - dist) <= tol:
                    return True
            except Exception:
                continue
        # 2) all_tasks 去重
        for t in state.all_tasks:
            if t.task_type == TaskType.SCAN and t.distance is not None:
                try:
                    if abs(float(t.distance) - dist) <= tol:
                        return True
                except Exception:
                    continue
        return False

    # 为普通数据创建任务
    created_tasks = []

    # 初始优化任务
    if mock_data.get('initial_opt') and not _has_completed_task(TaskType.INITIAL_OPT):
        data = mock_data['initial_opt'][0]
        if data.get('energy'):
            task = Task(
                task_id="initial_opt_mock",
                task_type=TaskType.INITIAL_OPT,
                status=TaskStatus.COMPLETED,
                description="初始结构优化 (普通数据)",
                energy=data['energy'],
                frequencies=data.get('frequencies', [])
            )
            state.all_tasks.append(task)
            created_tasks.append("初始优化")
            if state.reactant_energy is None:
                state.reactant_energy = data['energy']  # 设置反应物能量

    # 反应物能量任务
    if mock_data.get('reactant_energy') and not _has_completed_task(TaskType.REACTANT_ENERGY):
        data = mock_data['reactant_energy'][0]
        if data.get('energy'):
            task = Task(
                task_id="reactant_energy_mock",
                task_type=TaskType.REACTANT_ENERGY,
                status=TaskStatus.COMPLETED,
                description="反应物能量计算 (普通数据)",
                energy=data['energy']
            )
            state.all_tasks.append(task)
            created_tasks.append("反应物能量")
            if state.reactant_energy is None:
                state.reactant_energy = data['energy']

    # TS优化任务
    if mock_data.get('ts_opt') and not _has_completed_task(TaskType.TS_OPT):
        data = mock_data['ts_opt'][0]
        if data.get('energy'):
            task = Task(
                task_id="ts_opt_mock",
                task_type=TaskType.TS_OPT,
                status=TaskStatus.COMPLETED,
                description="TS优化 (普通数据)",
                energy=data['energy'],
                frequencies=data.get('frequencies', [])
            )
            state.all_tasks.append(task)
            created_tasks.append("TS优化")
            if state.ts_energy is None:
                state.ts_energy = data['energy']

    # 产物能量任务
    if mock_data.get('product_energy') and not _has_completed_task(TaskType.PRODUCT_ENERGY):
        data = mock_data['product_energy'][0]
        if data.get('energy'):
            task = Task(
                task_id="product_energy_mock",
                task_type=TaskType.PRODUCT_ENERGY,
                status=TaskStatus.COMPLETED,
                description="产物能量计算 (普通数据)",
                energy=data['energy']
            )
            state.all_tasks.append(task)
            created_tasks.append("产物能量")
            if state.product_energy is None:
                state.product_energy = data['energy']

    # 扫描点任务
    if mock_data.get('scan'):
        for i, scan_data in enumerate(mock_data['scan']):
            dist = scan_data.get('distance')
            energy = scan_data.get('energy')
            if dist and energy:
                if _has_scan_at_distance(dist):
                    continue
                # 创建扫描任务
                task = Task(
                    task_id=f"scan_mock_{i}",
                    task_type=TaskType.SCAN,
                    status=TaskStatus.COMPLETED,
                    distance=dist,
                    description=f"扫描 d={dist:.2f}Å (普通数据)",
                    energy=energy
                )
                state.all_tasks.append(task)

                # 添加到扫描结果
                state.scan_results.append({
                    'distance': dist,
                    'energy': energy,
                    'geometry': None,
                    'mol': None
                })

        if mock_data['scan']:
            created_tasks.append(f"{len(mock_data['scan'])}个扫描点")

    state.all_tasks.sort()

    if created_tasks:
        state.log(f"📋 从普通数据创建任务: {', '.join(created_tasks)}")


# =============================================================================
# 产物结构生成
# =============================================================================

def generate_product_structure(aromatic_smiles, halogen_preset, ipso_carbon):
    """
    生成EAS反应产物结构:
    1. 卤代芳烃 (ArX)
    2. HX (卤化氢)
    
    Args:
        aromatic_smiles: 芳香族SMILES
        halogen_preset: 卤素预设名称
        ipso_carbon: 被进攻碳的位置 (1-based)
    
    Returns:
        product_mol: 产物分子 (卤代芳烃 + HX)
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem
    
    try:
        halogen = HALOGEN_PRESETS[halogen_preset]
        hal_symbol = halogen.symbol
        
        # 生成卤代芳烃
        # 将芳香环上的H替换为卤素
        ar_mol = Chem.MolFromSmiles(aromatic_smiles)
        if ar_mol is None:
            return None
        
        # 简单方法: 直接构建卤代苯的SMILES
        # 对于苯: c1ccccc1 -> c1ccc(X)cc1
        if aromatic_smiles == "c1ccccc1":  # 苯
            if hal_symbol == 'Cl':
                product_smiles = "Clc1ccccc1"
                hx_smiles = "Cl"
            elif hal_symbol == 'Br':
                product_smiles = "Brc1ccccc1"
                hx_smiles = "Br"
            elif hal_symbol == 'I':
                product_smiles = "Ic1ccccc1"
                hx_smiles = "I"
            elif hal_symbol == 'F':
                product_smiles = "Fc1ccccc1"
                hx_smiles = "F"
            else:
                return None
        else:
            # 通用方法: 在指定位置添加卤素
            # 这里简化处理，实际需要更复杂的化学转换
            product_smiles = f"{hal_symbol}{aromatic_smiles}"
            hx_smiles = hal_symbol
        
        # 生成产物分子
        arx_mol = Chem.AddHs(Chem.MolFromSmiles(product_smiles))
        hx_mol = Chem.AddHs(Chem.MolFromSmiles(hx_smiles))
        
        if arx_mol is None or hx_mol is None:
            return None
        
        # 生成3D结构
        AllChem.EmbedMolecule(arx_mol, randomSeed=42)
        AllChem.MMFFOptimizeMolecule(arx_mol)
        
        AllChem.EmbedMolecule(hx_mol, randomSeed=42)
        AllChem.MMFFOptimizeMolecule(hx_mol)
        
        # 合并分子并分离
        combined = Chem.CombineMols(arx_mol, hx_mol)
        
        # 移动HX使其与ArX分离
        conf = combined.GetConformer()
        n_arx = arx_mol.GetNumAtoms()
        
        # 将HX移动到ArX的上方，分离5Å
        for i in range(n_arx, combined.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            conf.SetAtomPosition(i, Point3D(pos.x, pos.y, pos.z + 5.0))
        
        return combined
        
    except Exception as e:
        print(f"生成产物结构失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# =============================================================================
# 能量-反应进程图
# =============================================================================

def create_reaction_profile_plot():
    """创建能量-反应进程图 (R → TS → P)"""
    # 检查是否有足够数据
    r_energy = state.reactant_energy
    ts_energy = state.ts_energy
    p_energy = state.product_energy
    
    # 尝试从任务结果获取能量
    for task in state.all_tasks:
        if task.status == TaskStatus.COMPLETED and task.energy:
            if task.task_type == TaskType.REACTANT_ENERGY:
                r_energy = task.energy
            elif task.task_type == TaskType.TS_OPT:
                ts_energy = task.energy
            elif task.task_type == TaskType.PRODUCT_ENERGY:
                p_energy = task.energy
    
    # 如果初始优化完成且没有单独的反应物能量，使用初始优化的能量
    if r_energy is None:
        for task in state.all_tasks:
            if task.task_type == TaskType.INITIAL_OPT and task.status == TaskStatus.COMPLETED and task.energy:
                r_energy = task.energy
                break
    
    # 如果TS能量为空，尝试从扫描结果获取最高能量点
    if ts_energy is None and state.scan_results:
        max_e_result = max(state.scan_results, key=lambda x: x['energy'])
        ts_energy = max_e_result['energy']
    
    has_data = any([r_energy, ts_energy, p_energy])
    if not has_data:
        return None
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 设置参考能量
    ref_energy = r_energy if r_energy else (ts_energy if ts_energy else p_energy)
    
    # 转换为相对能量 (kJ/mol)
    energies = []
    labels = []
    x_positions = []
    
    if r_energy:
        rel_r = (r_energy - ref_energy) * 2625.5
        energies.append(rel_r)
        labels.append(f'Reactant\n{rel_r:.1f} kJ/mol')
        x_positions.append(0)
    
    if ts_energy:
        rel_ts = (ts_energy - ref_energy) * 2625.5
        energies.append(rel_ts)
        labels.append(f'TS\n{rel_ts:.1f} kJ/mol')
        x_positions.append(1)
    
    if p_energy:
        rel_p = (p_energy - ref_energy) * 2625.5
        energies.append(rel_p)
        labels.append(f'Product\n{rel_p:.1f} kJ/mol')
        x_positions.append(2)
    
    if len(energies) < 2:
        # Need at least 2 points
        ax.text(0.5, 0.5, "Need more data points\n(Reactant/TS/Product)", 
                ha='center', va='center', fontsize=14, transform=ax.transAxes)
        ax.set_xlim(-0.5, 2.5)
        ax.set_ylim(-10, 10)
    else:
        # 绘制能量曲线
        try:
            from scipy.interpolate import make_interp_spline
            
            # 创建平滑曲线的关键点
            x_key = []
            y_key = []
            
            for i, (x, e) in enumerate(zip(x_positions, energies)):
                # 添加平台区域
                x_key.extend([x - 0.15, x, x + 0.15])
                y_key.extend([e, e, e])
            
            x_key = np.array(x_key)
            y_key = np.array(y_key)
            
            # 排序
            sort_idx = np.argsort(x_key)
            x_key = x_key[sort_idx]
            y_key = y_key[sort_idx]
            
            # 插值
            x_smooth = np.linspace(x_key.min(), x_key.max(), 300)
            spl = make_interp_spline(x_key, y_key, k=min(3, len(x_key)-1))
            y_smooth = spl(x_smooth)
            
            ax.plot(x_smooth, y_smooth, 'b-', lw=2.5)
        except:
            # 降级为折线
            ax.plot(x_positions, energies, 'b-', lw=2.5)
        
        # 绘制数据点
        colors = ['green', 'red', 'blue']
        for i, (x, e, label) in enumerate(zip(x_positions, energies, labels)):
            color = colors[i] if i < len(colors) else 'gray'
            ax.scatter([x], [e], c=color, s=200, zorder=5)
            ax.annotate(
                label,
                (x, e),
                textcoords="offset points",
                xytext=(0, 12),
                ha='center',
                fontsize=11,
                fontweight='bold',
                clip_on=True,
            )
        
        # 计算活化能
        if r_energy and ts_energy:
            ea = (ts_energy - r_energy) * 2625.5
            ax.annotate(f'Ea = {ea:.1f} kJ/mol', 
                       xy=(0.5, (rel_ts + (rel_r if r_energy else 0)) / 2),
                       fontsize=12, color='red', ha='center', fontweight='bold')
        
        # 计算反应焓变
        if r_energy and p_energy:
            delta_h = (p_energy - r_energy) * 2625.5
            ax.annotate(f'ΔH = {delta_h:.1f} kJ/mol', 
                       xy=(1.5, (rel_p + (rel_r if r_energy else 0)) / 2),
                       fontsize=12, color='blue', ha='center', fontweight='bold')
    
    ax.set_xlabel('Reaction Coordinate', fontsize=12)
    ax.set_ylabel('Relative Energy (kJ/mol)', fontsize=12)
    ax.set_title('Reaction Energy Profile', fontsize=12, fontweight='bold')
    ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
    ax.grid(True, alpha=0.3)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(['Reactant (R)', 'TS', 'Product (P)'])

    # 避免标注超出图表：给Y轴留白
    try:
        y_min, y_max = min(energies), max(energies)
        pad = max(5.0, (y_max - y_min) * 0.15)
        ax.set_ylim(y_min - pad, y_max + pad)
    except Exception:
        pass
    
    plt.tight_layout()
    return fig


# =============================================================================
# 核心功能函数
# =============================================================================

def mol_to_3d_file(mol, filename="temp_structure"):
    """将RDKit分子保存为3D可视化文件"""
    if mol is None:
        return None
    try:
        from rdkit import Chem
        temp_file = os.path.join(SCRIPT_DIR, f"{filename}.mol")
        Chem.MolToMolFile(mol, temp_file)
        return temp_file
    except Exception as e:
        print(f"保存mol文件失败: {e}")
        return None


def geometry_to_xyz_file(geometry, filename="temp_structure"):
    """将几何结构转换为XYZ文件"""
    if not geometry:
        return None
    try:
        temp_file = os.path.join(SCRIPT_DIR, f"{filename}.xyz")
        with open(temp_file, 'w') as f:
            f.write(f"{len(geometry)}\n")
            f.write("Generated structure\n")
            for atom in geometry:
                f.write(f"{atom['element']} {atom['x']:.6f} {atom['y']:.6f} {atom['z']:.6f}\n")
        return temp_file
    except Exception as e:
        print(f"保存xyz文件失败: {e}")
        return None


def get_scan_point_choices():
    """获取可用的扫描点选择"""
    if not state.scan_results:
        return []
    choices = []
    for i, r in enumerate(state.scan_results):
        e_rel = 0
        if state.scan_results:
            min_e = min(sr['energy'] for sr in state.scan_results)
            e_rel = (r['energy'] - min_e) * 627.5
        marker = "⭐" if i == state.ts_guess_idx else ""
        choices.append(f"{i}: d={r['distance']:.2f}Å ({e_rel:+.2f} kcal/mol) {marker}")
    return choices


def generate_structure_preview(aromatic_smiles, aromatic_name, halogen_preset,
                               c_x_distance, c_x_x_angle, ipso_carbon, enable_symmetry):
    """生成初始结构并预览"""
    try:
        halogen = HALOGEN_PRESETS[halogen_preset]
        mol = generate_endon_complex(
            aromatic_smiles, halogen.smiles,
            int(ipso_carbon) - 1,
            float(c_x_distance),
            float(c_x_x_angle),
            halogen.xx_bond_length,
            enable_symmetry
        )
        
        if mol is None:
            return "❌ 结构生成失败", ""
        
        state.initial_mol = mol
        state.complex_mol = mol
        
        # 检测扫描坐标
        conf = mol.GetConformer()
        c_idx = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == 'C']
        x_idx = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == halogen.symbol]
        
        min_d = float('inf')
        for ci in c_idx:
            for xi in x_idx:
                d = conf.GetAtomPosition(ci).Distance(conf.GetAtomPosition(xi))
                if d < min_d:
                    min_d = d
                    state.scan_pair = (ci + 1, xi + 1)
        
        info = f"✅ T型构型生成成功\n"
        info += f"扫描坐标: C{state.scan_pair[0]} - {halogen.symbol}{state.scan_pair[1]}\n"
        info += f"当前距离: {min_d:.3f} Å\n"
        info += f"原子数: {mol.GetNumAtoms()}"
        
        # 生成3D结构用于预览
        img_html = view_3d_structure(mol, "初始结构预览")
        
        return info, img_html
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 错误: {str(e)}", ""


def get_available_projects():
    """获取可用的历史项目"""
    projects = []
    if OUT_DIR.exists():
        for d in OUT_DIR.iterdir():
            if d.is_dir():
                projects.append(d.name)
    return sorted(projects, reverse=True)


def detect_calculation_method_from_gjf(work_dir):
    """从工作目录中的.gjf文件自动检测计算方法"""
    import glob
    
    # 查找所有.gjf文件
    gjf_files = glob.glob(str(work_dir / "*.gjf"))
    if not gjf_files:
        return None
    
    # 尝试读取第一个.gjf文件
    try:
        with open(gjf_files[0], 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 查找方法行 (通常以#开头)
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                method_line = line[1:].strip()  # 去掉#
                
                # 提取方法和基组
                # 格式通常是: method/basis opt ...
                parts = method_line.split()
                if parts:
                    method_basis = parts[0]
                    
                    # 分离方法和基组
                    if '/' in method_basis:
                        method, basis = method_basis.split('/', 1)
                    else:
                        method = method_basis
                        basis = None
                    
                    # 尝试匹配到已知的计算方案
                    for scheme_name, scheme_config in CALCULATION_SCHEMES.items():
                        if scheme_config['method'].lower() == method.lower():
                            if basis and scheme_config.get('basis', '').lower() == basis.lower():
                                return scheme_name
                            elif not basis and not scheme_config.get('basis'):
                                return scheme_name
                    
                    # 如果没找到完全匹配，尝试部分匹配
                    method_lower = method.lower()
                    for scheme_name, scheme_config in CALCULATION_SCHEMES.items():
                        if scheme_config['method'].lower() in method_lower:
                            return scheme_name
                    
                    # 如果还是没找到，返回通用配置
                    return {
                        'method': method,
                        'basis': basis,
                        'scheme_name': 'custom'
                    }
    
    except Exception as e:
        print(f"读取.gjf文件失败: {e}")
    
    return None


def load_project(project_name):
    """加载历史项目"""
    if not project_name:
        return "请选择项目", None, None, None, gr.update(), gr.update()
    
    work_dir = OUT_DIR / project_name
    state.reset()
    state.work_dir = str(work_dir)
    state.is_loaded_project = True
    
    # 尝试加载配置
    config = ProjectConfig.load(work_dir)
    config_info = ""
    
    if config:
        state.project_config = config
        config_info = f"**已加载配置:**\n"
        config_info += f"- 反应物: {config.aromatic_name} + {config.halogen_preset}\n"
        config_info += f"- 方法: {config.scheme_name}\n"
        config_info += f"- 扫描: {config.scan_start}Å → {config.scan_end}Å (步长{config.step_size}Å)\n"
    else:
        config_info = "⚠️ 无配置文件(旧版项目)，正在自动检测计算方法..."
        state.project_config = ProjectConfig()
        
        # 自动检测计算方法
        detected_method = detect_calculation_method_from_gjf(work_dir)
        if detected_method:
            if isinstance(detected_method, str):
                # 匹配到预定义方案
                state.project_config.scheme_name = detected_method
                config_info += f"\n✅ 检测到计算方案: {detected_method}"
            else:
                # 自定义方法
                state.project_config.scheme_name = detected_method.get('scheme_name', 'custom')
                config_info += f"\n✅ 检测到自定义方法: {detected_method['method']}"
                if detected_method['basis']:
                    config_info += f"/{detected_method['basis']}"
        else:
            config_info += "\n⚠️ 无法自动检测计算方法，请手动设置"

    # 生成当前项目的log文件前缀，用于过滤同目录下可能存在的其它反应log
    log_prefix = ""
    try:
        if state.project_config and state.project_config.aromatic_name and state.project_config.halogen_preset:
            halogen_obj = HALOGEN_PRESETS.get(state.project_config.halogen_preset)
            halogen_name = halogen_obj.name if halogen_obj else state.project_config.halogen_preset
            log_prefix = f"{state.project_config.aromatic_name}_{halogen_name}_"
    except Exception:
        log_prefix = ""

    # 如果没有配置文件导致无法得到前缀，则从log文件名“投票”推断最可能的前缀，避免串入其它反应
    if not log_prefix:
        try:
            candidates = []
            for p in ["*_scan_d*.log", "*_scan_step_*.log", "*_TS*.log", "*_ts_*.log"]:
                candidates.extend(glob.glob(str(work_dir / p)))

            def _infer_prefix(path: str) -> str:
                base = os.path.basename(path)
                for token in ["_scan_d", "_scan_step_", "_scan_refine_", "_TS", "_ts_"]:
                    idx = base.find(token)
                    if idx > 0:
                        return base[:idx + 1]  # 保留末尾下划线，形成统一前缀
                return ""

            freq = {}
            for fp in candidates:
                pref = _infer_prefix(fp)
                if pref:
                    freq[pref] = freq.get(pref, 0) + 1

            if freq:
                log_prefix = max(freq.items(), key=lambda kv: kv[1])[0]
        except Exception:
            log_prefix = ""
    
    # 加载扫描结果
    json_path = work_dir / "scan_results.json"
    if json_path.exists():
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            state.scan_results = [
                {'distance': r['distance'], 'energy': r['energy'], 'geometry': None, 'mol': None}
                for r in data.get('scan_results', [])
            ]
            state.ts_guess_idx = data.get('ts_guess_idx')
        except:
            pass
    
    # 从log文件重建任务列表 - 支持多种文件名格式
    state.all_tasks = []
    
    # 优先仅加载符合当前项目前缀的log，避免混入其它反应的log
    scan_d_patterns = []
    if log_prefix:
        scan_d_patterns.append(str(work_dir / f"{log_prefix}scan_d*.log"))
    scan_d_patterns.append(str(work_dir / "*_scan_d*.log"))

    # 格式1: *_scan_d2.90.log (新版距离格式)
    scan_d_files = []
    for p in scan_d_patterns:
        scan_d_files = glob.glob(p)
        if scan_d_files:
            break

    for log_file in scan_d_files:
        m = re.search(r'_d([\d.]+)\.log', log_file)
        if m:
            dist = float(m.group(1))
            res = read_scan_output_robust(log_file)
            status = TaskStatus.COMPLETED if res else TaskStatus.FAILED
            
            task = Task(
                task_id=f"loaded_{dist}",
                task_type=TaskType.SCAN,
                status=status,
                distance=dist,
                description=f"扫描 d={dist:.2f}Å",
                log_file=log_file
            )
            if res:
                task.energy = res[-1]['energy']
                task.convergence_count = len(parse_all_convergence_tables(log_file))
                if dist not in [r['distance'] for r in state.scan_results]:
                    state.add_scan_result(dist, res[-1]['energy'], res[-1]['geometry'], None)
            
            state.all_tasks.append(task)
    
    scan_step_patterns = []
    if log_prefix:
        scan_step_patterns.append(str(work_dir / f"{log_prefix}scan_step_*.log"))
    scan_step_patterns.append(str(work_dir / "*_scan_step_*.log"))

    # 格式2: *_scan_step_N.log (旧版步骤格式)
    scan_step_files = []
    for p in scan_step_patterns:
        scan_step_files = glob.glob(p)
        if scan_step_files:
            break

    for log_file in scan_step_files:
        m = re.search(r'_scan_step_(\d+)\.log', log_file)
        if m:
            step_num = int(m.group(1))
            res = read_scan_output_robust(log_file)
            status = TaskStatus.COMPLETED if res else TaskStatus.FAILED
            
            # 从log文件读取实际距离
            dist = None
            if res and res[-1].get('geometry'):
                # 尝试从几何结构推断距离
                pass
            
            task = Task(
                task_id=f"loaded_step_{step_num}",
                task_type=TaskType.SCAN,
                status=status,
                distance=dist,
                description=f"扫描 步骤{step_num}",
                log_file=log_file
            )
            if res:
                task.energy = res[-1]['energy']
                task.convergence_count = len(parse_all_convergence_tables(log_file))
                # 旧格式没有距离信息，用步骤号作为伪距离
                pseudo_dist = 3.0 - (step_num - 1) * 0.1
                if pseudo_dist not in [r['distance'] for r in state.scan_results]:
                    state.add_scan_result(pseudo_dist, res[-1]['energy'], res[-1]['geometry'], None)
                task.distance = pseudo_dist
            
            state.all_tasks.append(task)
    
    scan_refine_patterns = []
    if log_prefix:
        scan_refine_patterns.append(str(work_dir / f"{log_prefix}scan_refine_*.log"))
    scan_refine_patterns.append(str(work_dir / "*_scan_refine_*.log"))

    # 格式3: *_scan_refine_*.log (精细扫描格式)
    scan_refine_files = []
    for p in scan_refine_patterns:
        scan_refine_files = glob.glob(p)
        if scan_refine_files:
            break

    for log_file in scan_refine_files:
        m = re.search(r'_scan_refine_\d+_(\d+)\.log', log_file)
        if m:
            dist_int = int(m.group(1))
            dist = dist_int / 100.0  # 假设是厘埃转埃
            res = read_scan_output_robust(log_file)
            status = TaskStatus.COMPLETED if res else TaskStatus.FAILED
            
            task = Task(
                task_id=f"loaded_refine_{dist:.2f}",
                task_type=TaskType.SCAN,
                status=status,
                distance=dist,
                description=f"精细扫描 d={dist:.2f}Å",
                log_file=log_file
            )
            if res:
                task.energy = res[-1]['energy']
                task.convergence_count = len(parse_all_convergence_tables(log_file))
                if dist not in [r['distance'] for r in state.scan_results]:
                    state.add_scan_result(dist, res[-1]['energy'], res[-1]['geometry'], None)
            
            state.all_tasks.append(task)
    
    # 检查TS优化结果 - 支持多种命名（并去重，避免同一log被重复加入）
    ts_patterns = []
    if log_prefix:
        ts_patterns.extend([
            str(work_dir / f"{log_prefix}TS*.log"),
            str(work_dir / f"{log_prefix}ts_*.log"),
            str(work_dir / f"{log_prefix}ts*.log"),
        ])
    ts_patterns.extend([
        str(work_dir / "*_TS*.log"),
        str(work_dir / "*_ts_*.log"),
    ])

    ts_log_files = []
    for p in ts_patterns:
        ts_log_files.extend(glob.glob(p))
    ts_log_files = sorted(set(ts_log_files))

    for log_file in ts_log_files:
        res = read_gaussian16_output_opt(log_file)
        status = TaskStatus.COMPLETED if res else TaskStatus.FAILED
        
        task = Task(
            task_id=f"loaded_ts_{Path(log_file).stem}",
            task_type=TaskType.TS_OPT,
            status=status,
            description="TS优化",
            log_file=log_file
        )
        if res:
            task.energy = res.get('energy')
            freqs = get_last_frequencies_robust(log_file)
            if freqs:
                task.frequencies = freqs
                task.imag_freqs = [f for f in freqs if f < 0]
        
        state.all_tasks.append(task)
    
    state.all_tasks.sort()
    
    # 加载普通格式数据（如果存在）
    load_mock_data_from_workdir(str(work_dir))
    
    # 从TS任务获取TS能量
    for task in state.all_tasks:
        if task.task_type == TaskType.TS_OPT and task.status == TaskStatus.COMPLETED and task.energy:
            state.ts_energy = task.energy
            break
    
    # 如果没有TS能量，从扫描结果获取最高点
    if state.ts_energy is None and state.scan_results:
        max_e_result = max(state.scan_results, key=lambda x: x['energy'])
        state.ts_energy = max_e_result['energy']
        state.ts_guess_idx = state.scan_results.index(max_e_result)
    
    # 生成任务列表HTML
    task_html = generate_task_table_md()
    
    # 生成能量图
    fig = create_energy_plot()
    
    return (f"✅ 已加载: {project_name}\n{config_info}", 
            task_html, fig, state.get_log_text(),
            gr.update(interactive=False),  # 配置变灰
            gr.update(interactive=False))


def generate_task_table_md():
    """生成任务列表表格Markdown"""
    if not state.all_tasks:
        return "无任务"
    
    lines = ["| # | 状态 | 类型 | 距离 | 能量(Ha) | 虚频 | 描述 |"]
    lines.append("|---|------|------|------|----------|------|------|")
    
    for i, task in enumerate(state.all_tasks):
        # 状态
        status_map = {
            TaskStatus.COMPLETED: "✅完成",
            TaskStatus.RUNNING: "🔄运行",
            TaskStatus.FAILED: "❌失败",
            TaskStatus.PENDING: "⏳待执行",
            TaskStatus.CANCELLED: "⏸️取消"
        }
        status = status_map.get(task.status, "?")
        
        # 类型
        type_map = {"initial_opt": "优化", "scan": "扫描", "refine_scan": "精细", "ts_opt": "TS", "ts_fix": "修复",
                    "reactant_energy": "反应物", "product_energy": "产物"}
        type_str = type_map.get(task.task_type.value, "?")
        
        # 距离
        dist_str = f"{task.distance:.2f}" if task.distance else "-"
        
        # 能量
        energy_str = f"{task.energy:.6f}" if task.energy else "-"
        
        # 虚频
        imag_str = "-"
        if task.imag_freqs:
            if len(task.imag_freqs) == 1:
                imag_str = f"{task.imag_freqs[0]:.0f}"
            else:
                imag_str = f"{len(task.imag_freqs)}个"
        
        lines.append(f"| {i} | {status} | {type_str} | {dist_str} | {energy_str} | {imag_str} | {task.description[:20]} |")
    
    return "\n".join(lines)


def create_energy_plot():
    """创建能量曲线图 (使用kJ/mol)"""
    if not state.scan_results:
        return None
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    dists = [r['distance'] for r in state.scan_results]
    min_e = min(r['energy'] for r in state.scan_results)
    rel_e = [(r['energy'] - min_e) * 2625.5 for r in state.scan_results]  # kJ/mol
    
    ax.plot(dists, rel_e, 'bo-', lw=2, ms=8)
    
    if state.ts_guess_idx is not None and state.ts_guess_idx < len(dists):
        ax.plot(dists[state.ts_guess_idx], rel_e[state.ts_guess_idx],
               'r*', ms=20, label=f'TS Guess ({dists[state.ts_guess_idx]:.2f}A, {rel_e[state.ts_guess_idx]:.1f} kJ/mol)')
        ax.legend()
    
    # 标注最高点
    max_idx = rel_e.index(max(rel_e))
    ax.annotate(f'{rel_e[max_idx]:.1f}', 
               (dists[max_idx], rel_e[max_idx]),
               textcoords="offset points", xytext=(0, 8), ha='center',
               fontsize=10, fontweight='bold', color='red')
    
    ax.set_xlabel('C-X Distance (\u00c5)', fontsize=11)
    ax.set_ylabel('Relative Energy (kJ/mol)', fontsize=11)
    ax.set_title('PES Scan Energy Profile', fontsize=12, fontweight='bold')
    ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
    ax.grid(True, alpha=0.3)
    ax.invert_xaxis()
    plt.tight_layout()
    return fig


def build_initial_tasks(config: ProjectConfig, extra_dists_str="", enable_initial_opt=True,
                        calc_reactant_energy=True, calc_product_energy=True, auto_ts_calc=True):
    """根据配置构建初始任务队列"""
    state.all_tasks = []
    state.project_config = config
    
    halogen = HALOGEN_PRESETS[config.halogen_preset]
    scheme = CALCULATION_SCHEMES[config.scheme_name]
    method_basis = f"{scheme['method']}/{scheme['basis']}" if scheme['basis'] else scheme['method']
    
    base_method = f"# {method_basis}"
    if scheme.get('disp'):
        base_method += f" {scheme['disp']}"
    if config.solvent and config.solvent != "None":
        base_method += f" SCRF=({config.solvent_model},Solvent={config.solvent})"
    
    # 初始结构优化任务
    if enable_initial_opt:
        opt_method = f"{base_method} opt freq nosymm"
        initial_opt_task = Task(
            task_id="initial_opt",
            task_type=TaskType.INITIAL_OPT,
            status=TaskStatus.PENDING,
            description="初始结构优化",
            method=opt_method
        )
        state.all_tasks.append(initial_opt_task)
    
    # 反应物能量计算任务 (初始结构优化自动包含此功能，或单独计算)
    if calc_reactant_energy and not enable_initial_opt:
        reactant_method = f"{base_method} opt freq nosymm"
        reactant_task = Task(
            task_id="reactant_energy",
            task_type=TaskType.REACTANT_ENERGY,
            status=TaskStatus.PENDING,
            description="反应物能量计算",
            method=reactant_method
        )
        state.all_tasks.append(reactant_task)
    
    # 生成扫描距离
    distances = []
    current = config.scan_start
    while current > config.scan_end - 0.001:
        distances.append(round(current, 3))
        current -= config.step_size
    
    # 额外距离
    if extra_dists_str:
        for d in extra_dists_str.replace(',', ' ').split():
            try:
                d = float(d.strip())
                if d not in distances:
                    distances.append(d)
            except:
                pass
    
    distances.sort(reverse=True)
    
    # 创建扫描任务
    for i, dist in enumerate(distances):
        opt_cmd = f"ModRedundant,{config.opt_mode}" if config.opt_mode else "ModRedundant"
        method = f"{base_method} opt({opt_cmd}) nosymm"
        
        task = Task(
            task_id=f"scan_{i}",
            task_type=TaskType.SCAN,
            status=TaskStatus.PENDING,
            distance=dist,
            description=f"扫描 d={dist:.2f}Å",
            method=method
        )
        state.all_tasks.append(task)
    
    # TS优化任务 (仅在auto_ts_calc为True时添加)
    if auto_ts_calc:
        ts_method = f"{base_method} opt=(TS,CalcFC,NoEigen) Freq nosymm"
        ts_task = Task(
            task_id="ts_auto",
            task_type=TaskType.TS_OPT,
            status=TaskStatus.PENDING,
            description="TS Opt (auto)",
            method=ts_method
        )
        state.all_tasks.append(ts_task)
    
    # 产物能量计算任务
    if calc_product_energy:
        product_method = f"{base_method} opt freq nosymm"
        product_task = Task(
            task_id="product_energy",
            task_type=TaskType.PRODUCT_ENERGY,
            status=TaskStatus.PENDING,
            description="产物能量计算",
            method=product_method
        )
        state.all_tasks.append(product_task)
    
    state.all_tasks.sort()
    return generate_task_table_md()


def delete_task(task_index):
    """删除任务"""
    try:
        idx = int(task_index)
        if 0 <= idx < len(state.all_tasks):
            task = state.all_tasks[idx]
            if task.status == TaskStatus.PENDING:
                state.all_tasks.pop(idx)
                return f"✅ 已删除任务", generate_task_table_md()
            else:
                return f"⚠️ 只能删除待执行任务", generate_task_table_md()
    except:
        pass
    return "❌ 删除失败", generate_task_table_md()


def add_task(task_type_str, distance, method_override, scan_point_idx=None):
    """添加新任务"""
    config = state.project_config or ProjectConfig()
    scheme = CALCULATION_SCHEMES[config.scheme_name]
    method_basis = f"{scheme['method']}/{scheme['basis']}" if scheme['basis'] else scheme['method']
    
    base_method = f"# {method_basis}"
    if scheme.get('disp'):
        base_method += f" {scheme['disp']}"
    if config.solvent and config.solvent != "None":
        base_method += f" SCRF=({config.solvent_model},Solvent={config.solvent})"
    
    if task_type_str == "scan":
        try:
            dist = float(distance)
        except:
            return "❌ 无效距离", generate_task_table_md()
        
        # 检查重复
        for t in state.all_tasks:
            if t.task_type == TaskType.SCAN and t.distance and abs(t.distance - dist) < 0.001:
                return f"⚠️ 距离 {dist:.2f}Å 已存在", generate_task_table_md()
        
        opt_cmd = f"ModRedundant,{config.opt_mode}" if config.opt_mode else "ModRedundant"
        method = method_override if method_override else f"{base_method} opt({opt_cmd}) nosymm"
        
        task = Task(
            task_id=f"scan_new_{int(datetime.datetime.now().timestamp()*1000)}",
            task_type=TaskType.SCAN,
            status=TaskStatus.PENDING,
            distance=dist,
            description=f"扫描 d={dist:.2f}Å (新增)",
            method=method
        )
        state.all_tasks.append(task)
        state.all_tasks.sort()
        return f"✅ 已添加扫描任务 d={dist:.2f}Å", generate_task_table_md()
    
    elif task_type_str == "ts":
        method = method_override if method_override else f"{base_method} opt=(TS,CalcFC,NoEigen) Freq nosymm"
        
        # 确定使用哪个扫描点
        ts_idx = None
        ts_dist = None
        if scan_point_idx is not None and scan_point_idx >= 0:
            try:
                ts_idx = int(scan_point_idx)
                if ts_idx < len(state.scan_results):
                    ts_dist = state.scan_results[ts_idx]['distance']
            except:
                pass
        
        desc = "TS优化"
        if ts_dist:
            desc = f"TS优化 (d={ts_dist:.2f}Å)"
            state.ts_guess_idx = ts_idx  # 设置选中的扫描点
        elif state.ts_guess_idx is not None and state.ts_guess_idx < len(state.scan_results):
            ts_dist = state.scan_results[state.ts_guess_idx]['distance']
            desc = f"TS优化 (自动: d={ts_dist:.2f}Å)"
        else:
            desc = "TS优化 (自动选点)"
        
        task = Task(
            task_id=f"ts_new_{int(datetime.datetime.now().timestamp()*1000)}",
            task_type=TaskType.TS_OPT,
            status=TaskStatus.PENDING,
            description=desc,
            method=method,
            distance=ts_dist
        )
        state.all_tasks.append(task)
        state.all_tasks.sort()
        return f"✅ 已添加TS优化任务 {desc}", generate_task_table_md()
    
    elif task_type_str == "ts_fix":
        task = Task(
            task_id=f"ts_fix_{int(datetime.datetime.now().timestamp()*1000)}",
            task_type=TaskType.TS_FIX,
            status=TaskStatus.PENDING,
            description="TS修复 (消除多余虚频)",
            method=""
        )
        state.all_tasks.append(task)
        return "✅ 已添加TS修复任务", generate_task_table_md()
    
    elif task_type_str == "refine_scan":
        task = Task(
            task_id=f"refine_scan_{int(datetime.datetime.now().timestamp()*1000)}",
            task_type=TaskType.REFINE_SCAN,
            status=TaskStatus.PENDING,
            description="精细扫描 (极大值附近)",
            method=""
        )
        state.all_tasks.append(task)
        return "✅ 已添加精细扫描任务", generate_task_table_md()
    
    elif task_type_str == "reactant_energy":
        method = method_override if method_override else f"{base_method} opt freq nosymm"
        task = Task(
            task_id=f"reactant_energy_{int(datetime.datetime.now().timestamp()*1000)}",
            task_type=TaskType.REACTANT_ENERGY,
            status=TaskStatus.PENDING,
            description="反应物能量计算",
            method=method
        )
        state.all_tasks.append(task)
        state.all_tasks.sort()
        return "✅ 已添加反应物能量计算任务", generate_task_table_md()
    
    elif task_type_str == "product_energy":
        method = method_override if method_override else f"{base_method} opt freq nosymm"
        task = Task(
            task_id=f"product_energy_{int(datetime.datetime.now().timestamp()*1000)}",
            task_type=TaskType.PRODUCT_ENERGY,
            status=TaskStatus.PENDING,
            description="产物能量计算",
            method=method
        )
        state.all_tasks.append(task)
        state.all_tasks.sort()
        return "✅ 已添加产物能量计算任务", generate_task_table_md()
    
    return "❌ 未知任务类型", generate_task_table_md()


def get_task_details(task_index):
    """获取任务详情"""
    try:
        idx = int(task_index)
        if 0 <= idx < len(state.all_tasks):
            task = state.all_tasks[idx]
            
            details = f"## 任务详情 #{idx}\n\n"
            details += f"**类型**: {task.task_type.value}\n"
            details += f"**状态**: {task.status.value}\n"
            details += f"**描述**: {task.description}\n"
            
            if task.distance:
                details += f"**距离**: {task.distance:.3f} Å\n"
            if task.energy:
                # 计算相对能量
                rel_e = 0
                if state.scan_results:
                    min_e = min(r['energy'] for r in state.scan_results)
                    rel_e = (task.energy - min_e) * 627.5
                details += f"**能量**: {task.energy:.6f} Ha ({rel_e:+.2f} kcal/mol)\n"
            if task.method:
                details += f"**方法**: `{task.method}`\n"
            if task.log_file:
                details += f"**Log文件**: `{os.path.basename(task.log_file)}`\n"
            if task.convergence_count:
                details += f"**收敛步数**: {task.convergence_count}\n"
            
            # 频率信息
            if task.frequencies:
                details += f"\n### 频率分析\n"
                details += f"总频率数: {len(task.frequencies)}\n"
                if task.imag_freqs:
                    details += f"**虚频**: {[f'{f:.1f}' for f in task.imag_freqs]} cm⁻¹\n"
                    if len(task.imag_freqs) == 1 and abs(task.imag_freqs[0]) > 50:
                        details += "✅ 正确的过渡态 (单个大虚频)\n"
                    elif len(task.imag_freqs) > 1:
                        details += "⚠️ 多个虚频，可能需要修复\n"
                else:
                    details += "无虚频 (极小值点)\n"
            
            # 结构可视化 - 从scan_results或log文件获取
            img_html = ""
            mol_for_view = None
            
            # 尝试从scan_results获取结构
            if task.task_type == TaskType.SCAN and task.distance:
                for sr in state.scan_results:
                    if sr['distance'] and abs(sr['distance'] - task.distance) < 0.01:
                        mol_for_view = sr.get('mol')
                        break
            
            # 尝试从log文件读取并创建mol
            if not mol_for_view and task.log_file and os.path.exists(task.log_file):
                res = read_scan_output_robust(task.log_file)
                if res:
                    geometry = res[-1].get('geometry')
                    if geometry:
                        mol_for_view = create_mol_from_geometry(geometry)
                else:
                    res = read_gaussian16_output_opt(task.log_file)
                    if res and 'geometry' in res:
                        mol_for_view = create_mol_from_geometry(res['geometry'])
            
            # 生成3D结构图像
            if mol_for_view:
                img_html = view_3d_structure(mol_for_view, f"任务{idx}结构")
            else:
                img_html = "<p>无法生成结构视图</p>"
            
            return details, img_html
    except Exception as e:
        import traceback
        traceback.print_exc()
    return "无法获取任务详情", ""


def get_latest_convergence():
    """获取最新的收敛表格"""
    if not state.work_dir:
        return "无工作目录"
    
    # 找到最新修改的log文件
    log_files = glob.glob(os.path.join(state.work_dir, "*.log"))
    if not log_files:
        return "无log文件"
    
    latest_log = max(log_files, key=os.path.getmtime)
    tables = parse_all_convergence_tables(latest_log)
    
    if not tables:
        return f"文件: {os.path.basename(latest_log)}\n\n无收敛数据"
    
    last = tables[-1]
    header = f"**{os.path.basename(latest_log)}** 步骤 {last['index']}/{len(tables)}\n\n"
    return header + format_convergence_table(last['data'])


def execute_all_tasks(run_name):
    """执行所有待执行任务"""
    if state.is_running:
        return "⚠️ 已有任务在运行", state.get_log_text(), generate_task_table_md(), None
    
    pending = state.get_pending_tasks()
    if not pending:
        return "无待执行任务", state.get_log_text(), generate_task_table_md(), None
    
    if state.complex_mol is None and not state.is_loaded_project:
        return "❌ 请先生成初始结构", state.get_log_text(), generate_task_table_md(), None
    
    state.is_running = True
    state.stop_requested = False
    state.running_processes.clear()  # 清理之前的进程列表
    
    # 设置工作目录
    if not state.work_dir:
        if not run_name:
            run_name = f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        state.work_dir = str(OUT_DIR / run_name)
    
    os.makedirs(state.work_dir, exist_ok=True)
    
    # 保存配置
    if state.project_config:
        state.project_config.save(state.work_dir)
    
    config = state.project_config or ProjectConfig()
    halogen = HALOGEN_PRESETS[config.halogen_preset]
    
    # 定义base_method用于TS修复任务
    scheme = CALCULATION_SCHEMES[config.scheme_name]
    method_basis = f"{scheme['method']}/{scheme['basis']}" if scheme['basis'] else scheme['method']
    
    base_method = f"# {method_basis}"
    if scheme.get('disp'):
        base_method += f" {scheme['disp']}"
    if config.solvent and config.solvent != "None":
        base_method += f" SCRF=({config.solvent_model},Solvent={config.solvent})"
    
    state.log(f"📂 工作目录: {state.work_dir}")
    state.log(f"🧪 反应: {config.aromatic_name} + {config.halogen_preset}")
    
    current_mol = copy.deepcopy(state.complex_mol) if state.complex_mol else None
    prev_chk = None
    highest_e, highest_idx = -float('inf'), -1
    e_threshold = config.energy_threshold / 627.5
    
    try:
        while not state.stop_requested:
            task = state.get_next_task()
            if not task:
                break
            
            task.status = TaskStatus.RUNNING
            state.log(f"▶️ 开始: {task.description}")
            
            if task.task_type == TaskType.INITIAL_OPT:
                # 初始结构优化任务
                filename = f"{config.aromatic_name}_{halogen.name}_initial_opt"
                gjf = os.path.join(state.work_dir, f"{filename}.gjf")
                log_file = gjf.replace('.gjf', '.log')
                chk = gjf.replace('.gjf', '.chk')
                
                task.gjf_file = gjf
                task.log_file = log_file
                task.chk_file = chk
                
                # 检查已完成（真实log文件）
                if os.path.exists(log_file):
                    res = read_gaussian16_output_opt(log_file)
                    if res and 'energy' in res:
                        state.log(f"  ✅ 已有真实结果，跳过")
                        task.energy = res['energy']
                        state.reactant_energy = res['energy']  # 初始优化等同于反应物能量
                        task.status = TaskStatus.COMPLETED
                        task.convergence_count = len(parse_all_convergence_tables(log_file))
                        # 更新分子结构
                        if current_mol:
                            current_mol = update_mol_coordinates(current_mol, res)
                        continue
                
                # 检查普通格式数据
                mock_data_dict = read_normal_data_file(state.work_dir)
                if mock_data_dict.get('initial_opt'):
                    mock_entry = mock_data_dict['initial_opt'][0]
                    if mock_entry.get('energy'):
                        task.energy = mock_entry['energy']
                        state.reactant_energy = mock_entry['energy']
                        task.status = TaskStatus.COMPLETED
                        state.log(f"  ✅ 使用普通格式初始优化能量: {mock_entry['energy']:.6f} Ha")
                        continue
                
                # 生成输入文件
                create_gaussian_input(current_mol, gjf, task.method, filename, config.nproc, config.memory, chk)
                
                state.log(f"  运行初始结构优化: {filename}")
                process = run_gaussian_job(gjf, run_dir=state.work_dir)
                
                if process:
                    state.running_processes.append(process)
                    state.log(f"  📊 PID: {process.pid}")
                    
                    # 等待进程完成
                    return_code = process.wait()
                    state.running_processes.remove(process)
                    
                    if return_code == 0:
                        res = read_gaussian16_output_opt(log_file)
                        if res and 'energy' in res:
                            task.energy = res['energy']
                            task.status = TaskStatus.COMPLETED
                            task.convergence_count = len(parse_all_convergence_tables(log_file))
                            # 更新分子结构
                            if current_mol:
                                current_mol = update_mol_coordinates(current_mol, res)
                            state.log(f"  ✅ 初始优化完成 E={res['energy']:.6f} Ha")
                        else:
                            task.status = TaskStatus.FAILED
                            state.log(f"  ❌ 无法读取结果")
                    else:
                        task.status = TaskStatus.FAILED
                        state.log(f"  ❌ 计算失败 (返回码: {return_code})")
                else:
                    task.status = TaskStatus.FAILED
                    state.log(f"  ❌ 无法启动进程")
            
            elif task.task_type == TaskType.SCAN:
                dist = task.distance
                
                if current_mol:
                    mol_adjusted = set_fragment_distance(current_mol, state.scan_pair[0], state.scan_pair[1], dist)
                else:
                    mol_adjusted = None
                
                step_name = f"{config.aromatic_name}_{halogen.name}_scan_d{dist:.2f}"
                gjf = os.path.join(state.work_dir, f"{step_name}.gjf")
                log_file = gjf.replace('.gjf', '.log')
                chk = gjf.replace('.gjf', '.chk')
                
                task.gjf_file = gjf
                task.log_file = log_file
                task.chk_file = chk
                
                # 检查已完成（真实log文件）
                if os.path.exists(log_file):
                    res = read_scan_output_robust(log_file)
                    if res:
                        state.log(f"  ✅ 已有真实结果，跳过")
                        last = res[-1]
                        task.energy = last['energy']
                        task.status = TaskStatus.COMPLETED
                        task.convergence_count = len(parse_all_convergence_tables(log_file))
                        state.add_scan_result(dist, last['energy'], last['geometry'], mol_adjusted)
                        if current_mol and mol_adjusted:
                            current_mol = update_mol_coordinates(mol_adjusted, {'geometry': last['geometry']})
                        prev_chk = chk
                        
                        if last['energy'] > highest_e:
                            highest_e, highest_idx = last['energy'], len(state.scan_results) - 1
                        continue
                
                # 检查普通格式数据
                mock_data_dict = read_mock_data_file(state.work_dir)
                if mock_data_dict.get('scan'):
                    for scan_entry in mock_data_dict['scan']:
                        if scan_entry.get('distance') and abs(scan_entry['distance'] - dist) < 0.01:
                            if scan_entry.get('energy'):
                                task.energy = scan_entry['energy']
                                task.status = TaskStatus.COMPLETED
                                state.add_scan_result(dist, scan_entry['energy'], None, mol_adjusted)
                                state.log(f"  ✅ 使用普通格式扫描数据: d={dist:.2f}Å E={scan_entry['energy']:.6f} Ha")
                                
                                if scan_entry['energy'] > highest_e:
                                    highest_e, highest_idx = scan_entry['energy'], len(state.scan_results) - 1
                                break
                    
                    if task.status == TaskStatus.COMPLETED:
                        continue
                
                # 寻找附近chk
                use_guess = False
                nearby_chk = find_nearby_chk(state.work_dir, dist)
                if nearby_chk:
                    try:
                        shutil.copy2(nearby_chk, chk)
                        use_guess = True
                        state.log(f"  📂 已就近读取chk文件: {os.path.basename(nearby_chk)}")
                    except:
                        pass
                elif prev_chk and os.path.exists(prev_chk):
                    try:
                        shutil.copy2(prev_chk, chk)
                        use_guess = True
                        state.log(f"  📂 已就近读取chk文件")
                    except:
                        pass
                
                method = task.method
                if use_guess:
                    method += " Guess=Read"
                
                if mol_adjusted:
                    scan_constraint = f"{state.scan_pair[0]} {state.scan_pair[1]} F"
                    create_scan_input(mol_adjusted, gjf, scan_constraint, method, config.nproc, config.memory, chk)
                    
                    process = run_gaussian_job(gjf, run_dir=state.work_dir)
                    
                    if process:
                        state.running_processes.append(process)
                        state.log(f"  📊 PID: {process.pid}")
                        
                        return_code = process.wait()
                        state.running_processes.remove(process)
                        
                        if return_code == 0:
                            res = read_scan_output_robust(log_file)
                            if res:
                                last = res[-1]
                                task.energy = last['energy']
                                task.status = TaskStatus.COMPLETED
                                task.convergence_count = len(parse_all_convergence_tables(log_file))
                                state.add_scan_result(dist, last['energy'], last['geometry'], mol_adjusted)
                                current_mol = update_mol_coordinates(mol_adjusted, {'geometry': last['geometry']})
                                prev_chk = chk
                                
                                rel_e = 0
                                if state.scan_results:
                                    min_e = min(r['energy'] for r in state.scan_results)
                                    rel_e = (last['energy'] - min_e) * 627.5
                                state.log(f"  ✅ 步骤{task.convergence_count}步完成 E={last['energy']:.6f} Ha ({rel_e:+.2f} kcal/mol)")
                                
                                # TS检测
                                if last['energy'] > highest_e:
                                    highest_e, highest_idx = last['energy'], len(state.scan_results) - 1
                                elif config.auto_stop and highest_idx >= 0:
                                    drop = highest_e - last['energy']
                                    if drop > e_threshold:
                                        state.log(f"🎯 检测到TS极值点!")
                                        state.ts_guess_idx = highest_idx
                                        # 取消后续扫描
                                        for t in state.all_tasks:
                                            if t.task_type == TaskType.SCAN and t.status == TaskStatus.PENDING:
                                                t.status = TaskStatus.CANCELLED
                            else:
                                task.status = TaskStatus.FAILED
                                state.log(f"  ❌ 无法读取结果")
                        else:
                            task.status = TaskStatus.FAILED
                            state.log(f"  ❌ 计算失败 (返回码: {return_code})")
                    else:
                        task.status = TaskStatus.FAILED
                        state.log(f"  ❌ 无法启动进程")
                else:
                    task.status = TaskStatus.FAILED
                    state.log(f"  ❌ 无分子结构")
            
            elif task.task_type == TaskType.TS_OPT:
                # 检查普通格式数据
                mock_data_dict = read_mock_data_file(state.work_dir)
                if mock_data_dict.get('ts_opt'):
                    mock_entry = mock_data_dict['ts_opt'][0]
                    if mock_entry.get('energy'):
                        task.energy = mock_entry['energy']
                        state.ts_energy = mock_entry['energy']
                        task.status = TaskStatus.COMPLETED
                        if mock_entry.get('frequencies'):
                            task.frequencies = mock_entry['frequencies']
                            task.imag_freqs = [f for f in mock_entry['frequencies'] if f < 0]
                            state.log(f"  ✅ 使用普通格式TS能量: {mock_entry['energy']:.6f} Ha, 虚频:{len(task.imag_freqs)}个")
                        else:
                            state.log(f"  ✅ 使用普通格式TS能量: {mock_entry['energy']:.6f} Ha")
                        continue
                
                if not state.scan_results:
                    state.log("  ⚠️ 无扫描结果，跳过TS优化")
                    task.status = TaskStatus.CANCELLED
                    continue
                
                # 选择最高能量点
                if state.ts_guess_idx is None:
                    energies = [r['energy'] for r in state.scan_results]
                    state.ts_guess_idx = energies.index(max(energies))
                
                ts_data = state.scan_results[state.ts_guess_idx]
                ts_dist = ts_data['distance']
                ts_mol = ts_data['mol'] if ts_data['mol'] else current_mol
                
                state.log(f"  使用 d={ts_dist:.2f}Å 进行TS优化")
                
                ts_name = f"{config.aromatic_name}_{halogen.name}_TS"
                gjf = os.path.join(state.work_dir, f"{ts_name}.gjf")
                log_file = gjf.replace('.gjf', '.log')
                chk = gjf.replace('.gjf', '.chk')
                
                task.gjf_file = gjf
                task.log_file = log_file
                task.chk_file = chk
                
                # 复制扫描chk
                scan_chk = os.path.join(state.work_dir, f"{config.aromatic_name}_{halogen.name}_scan_d{ts_dist:.2f}.chk")
                use_guess = False
                if os.path.exists(scan_chk):
                    try:
                        shutil.copy2(scan_chk, chk)
                        use_guess = True
                        state.log(f"  📂 已就近读取chk文件")
                    except:
                        pass
                
                method = task.method
                if use_guess:
                    method += " Guess=Read"
                
                if ts_mol:
                    create_gaussian_input(ts_mol, gjf, method, "TS Optimization", config.nproc, config.memory, chk)
                    process = run_gaussian_job(gjf, run_dir=state.work_dir)
                    
                    if process:
                        state.running_processes.append(process)
                        state.log(f"  📊 PID: {process.pid}")
                        
                        return_code = process.wait()
                        state.running_processes.remove(process)
                        
                        if return_code == 0:
                            res = read_gaussian16_output_opt(log_file)
                            if res:
                                task.energy = res.get('energy')
                                task.status = TaskStatus.COMPLETED
                                task.convergence_count = len(parse_all_convergence_tables(log_file))
                                
                                freqs = get_last_frequencies_robust(log_file)
                                if freqs:
                                    task.frequencies = freqs
                                    task.imag_freqs = [f for f in freqs if f < 0]
                                    state.log(f"  ✅ 步骤{task.convergence_count}步完成 E={task.energy:.6f} Ha, 虚频:{len(task.imag_freqs)}个")
                                    
                                    # 检查虚频，如果不理想，自动添加修复任务
                                    cat, desc, details = analyze_frequencies(freqs)
                                    if cat in [0, 3, 4, 1]:  # 不理想的情况
                                        state.log(f"  ⚠️ 虚频分析: {desc}")
                                        state.log("  🔧 自动添加TS修复任务")
                                        # 添加ts_fix任务
                                        fix_task = Task(
                                            task_id=f"ts_fix_auto_{int(datetime.datetime.now().timestamp()*1000)}",
                                            task_type=TaskType.TS_FIX,
                                            status=TaskStatus.PENDING,
                                            description="TS修复 (自动)",
                                            method="",
                                            log_file=log_file  # 传递之前的log文件
                                        )
                                        state.all_tasks.append(fix_task)
                                        state.all_tasks.sort()
                                        state.log("  ✅ 已自动添加TS修复任务")
                                else:
                                    state.log(f"  ✅ 步骤{task.convergence_count}步完成 E={task.energy:.6f} Ha")
                            else:
                                task.status = TaskStatus.FAILED
                                state.log(f"  ❌ 无法读取结果")
                        else:
                            task.status = TaskStatus.FAILED
                            state.log(f"  ❌ 计算失败 (返回码: {return_code})")
                    else:
                        task.status = TaskStatus.FAILED
                        state.log(f"  ❌ 无法启动进程")
                else:
                    task.status = TaskStatus.FAILED
            
            elif task.task_type == TaskType.REFINE_SCAN:
                # 精细扫描任务
                if not state.scan_results:
                    state.log("  ❌ 精细扫描失败：无扫描结果")
                    task.status = TaskStatus.FAILED
                    continue
                
                if not state.scan_pair:
                    state.log("  ❌ 精细扫描失败：无扫描坐标")
                    task.status = TaskStatus.FAILED
                    continue
                
                # 找到峰值
                peak_idx = state.ts_guess_idx if state.ts_guess_idx is not None else 0
                if peak_idx >= len(state.scan_results):
                    peak_idx = len(state.scan_results) - 1
                
                # 准备scan_history格式
                scan_history = []
                for r in state.scan_results:
                    scan_history.append({
                        'energy': r['energy'],
                        'geometry': r['geometry'],
                        'mol': r['mol'],
                        'step': -1  # 标记为原始扫描
                    })
                
                # 调用精细化扫描
                try:
                    new_mol, new_e, updated_history = refine_scan_peak(
                        scan_history, peak_idx, state.scan_pair,
                        state.work_dir, f"{config.aromatic_name}_{halogen.name}",
                        base_method, config.nproc, config.memory
                    )
                    
                    # 检查返回值
                    if new_mol is None or updated_history is None:
                        state.log("  ❌ 精细扫描失败：函数返回无效结果")
                        task.status = TaskStatus.FAILED
                        continue
                    
                    # 更新扫描结果
                    state.scan_results = []
                    for h in updated_history:
                        if h['step'] != -1:  # 只添加精细化结果
                            state.scan_results.append({
                                'distance': get_atom_distance(h['mol'], state.scan_pair[0], state.scan_pair[1]),
                                'energy': h['energy'],
                                'geometry': h['geometry'],
                                'mol': h['mol']
                            })
                    
                    # 重新排序
                    state.scan_results.sort(key=lambda x: x['distance'], reverse=True)
                    
                    # 更新峰值索引
                    max_e = max(r['energy'] for r in state.scan_results)
                    state.ts_guess_idx = next(i for i, r in enumerate(state.scan_results) if r['energy'] == max_e)
                    
                    state.log(f"  ✅ 精细扫描完成，新峰值E={new_e:.6f} Ha")
                    task.status = TaskStatus.COMPLETED
                    
                except Exception as e:
                    state.log(f"  ❌ 精细扫描失败: {str(e)}")
                    task.status = TaskStatus.FAILED
            
            elif task.task_type == TaskType.TS_FIX:
                # TS修复任务
                if not task.log_file or not os.path.exists(task.log_file):
                    state.log("  ❌ TS修复失败：无有效的log文件")
                    task.status = TaskStatus.FAILED
                    continue
                
                # 读取之前的TS结果
                prev_results = read_gaussian16_output_opt(task.log_file)
                if not prev_results or 'geometry' not in prev_results:
                    state.log("  ❌ TS修复失败：无法读取之前的几何结构")
                    task.status = TaskStatus.FAILED
                    continue
                
                # 更新分子结构
                current_mol = update_mol_coordinates(state.complex_mol, prev_results)
                
                # 根据描述决定修复类型
                fix_type = "hard_push"  # 默认
                if "虚频" in task.description:
                    fix_type = "imaginary_mode"
                
                if fix_type == "hard_push":
                    # Hard Push: 强制调整距离和移动H原子
                    state.log("  🔧 应用Hard Push修复策略")
                    
                    if not state.scan_pair:
                        state.log("  ❌ 无法应用Hard Push：无扫描坐标")
                        task.status = TaskStatus.FAILED
                        continue
                    
                    c_idx_1b, x_idx_1b = state.scan_pair
                    
                    # 智能计算目标距离
                    target_dist = 2.0
                    if state.scan_results:
                        # 使用峰值附近的距离
                        peak_idx = state.ts_guess_idx if state.ts_guess_idx is not None else len(state.scan_results) // 2
                        if peak_idx < len(state.scan_results):
                            mol_peak = state.scan_results[peak_idx]['mol']
                            if mol_peak:
                                p1 = mol_peak.GetConformer().GetAtomPosition(c_idx_1b - 1)
                                p2 = mol_peak.GetConformer().GetAtomPosition(x_idx_1b - 1)
                                dist_peak = p1.Distance(p2)
                                target_dist = dist_peak - 0.1
                    
                    state.log(f"  强制调整C-X距离: {c_idx_1b}-{x_idx_1b} -> {target_dist:.3f} Å")
                    current_mol = set_fragment_distance(current_mol, c_idx_1b, x_idx_1b, target_dist)
                    
                    # H原子大幅度翘起
                    conf = current_mol.GetConformer()
                    c_atom = current_mol.GetAtomWithIdx(c_idx_1b - 1)
                    h_neighbors = [n for n in c_atom.GetNeighbors() if n.GetSymbol() == 'H']
                    
                    if h_neighbors:
                        target_h = h_neighbors[0]
                        target_h_idx = target_h.GetIdx()
                        
                        p_h = conf.GetAtomPosition(target_h_idx)
                        p_x = conf.GetAtomPosition(x_idx_1b - 1)
                        vec_x = p_h.x - p_x.x
                        vec_y = p_h.y - p_x.y
                        vec_z = p_h.z - p_x.z
                        norm = (vec_x**2 + vec_y**2 + vec_z**2)**0.5
                        if norm > 0.01:
                            push_dist = 0.5
                            scale = push_dist / norm
                            p_new = Point3D(p_h.x + vec_x * scale, p_h.y + vec_y * scale, p_h.z + vec_z * scale)
                            conf.SetAtomPosition(target_h_idx, p_new)
                            state.log(f"  H原子大幅移动 {push_dist} Å")
                    
                elif fix_type == "imaginary_mode":
                    # 沿虚频方向调整
                    state.log("  🔧 应用虚频方向修复策略")
                    fixed_mol, msg = fix_ts_along_imaginary_mode(current_mol, task.log_file)
                    if fixed_mol:
                        current_mol = fixed_mol
                    else:
                        state.log(f"  ⚠️ 虚频修复失败: {msg}")
                        task.status = TaskStatus.FAILED
                        continue
                
                # 准备新的TS优化
                filename = f"{task.task_id}_fix"
                gjf_file = os.path.join(state.work_dir, f"{filename}.gjf")
                log_file = os.path.join(state.work_dir, f"{filename}.log")
                chk_file = os.path.join(state.work_dir, f"{filename}.chk")
                
                # 使用与之前相同的TS方法
                method = task.method if task.method else f"{base_method} opt(ts,calcall,noeigentest) nosymm freq"
                
                create_gaussian_input(current_mol, gjf_file, method, filename, config.nproc, config.memory, chk_file)
                
                state.log(f"  运行TS修复优化: {filename}")
                process = run_gaussian_job(gjf_file, run_dir=state.work_dir)
                
                if process:
                    state.running_processes.append(process)
                    state.log(f"  📊 PID: {process.pid}")
                    
                    return_code = process.wait()
                    state.running_processes.remove(process)
                    
                    if return_code == 0:
                        results = read_gaussian16_output_opt(log_file)
                        freqs = get_last_frequencies_robust(log_file) if results else []
                        
                        if results and freqs:
                            results['frequencies'] = freqs
                            task.result = results
                            task.energy = results.get('energy')
                            task.frequencies = freqs
                            task.imag_freqs = [f for f in freqs if f < 0]
                            task.log_file = log_file
                            task.chk_file = chk_file
                            task.gjf_file = gjf_file
                            
                            # 分析结果
                            cat, desc, details = analyze_frequencies(freqs)
                            state.log(f"  修复后频率分析: {desc}")
                            
                            if cat in [0, 3, 4]:
                                state.log("  ⚠️ 修复后虚频依然不理想")
                            else:
                                state.log("  ✅ 修复成功")
                            
                            task.status = TaskStatus.COMPLETED
                        else:
                            task.status = TaskStatus.FAILED
                            state.log("  ❌ 修复计算完成但无法读取结果")
                    else:
                        task.status = TaskStatus.FAILED
                        state.log(f"  ❌ 计算失败 (返回码: {return_code})")
                else:
                    task.status = TaskStatus.FAILED
                    state.log(f"  ❌ 无法启动进程")
            
            elif task.task_type == TaskType.REACTANT_ENERGY:
                # 反应物能量计算任务
                # 首先检查是否有普通格式数据
                mock_data_dict = read_mock_data_file(state.work_dir)
                if mock_data_dict.get('reactant_energy'):
                    mock_entry = mock_data_dict['reactant_energy'][0]
                    if mock_entry.get('energy'):
                        task.energy = mock_entry['energy']
                        state.reactant_energy = mock_entry['energy']
                        task.status = TaskStatus.COMPLETED
                        state.log(f"  ✅ 使用普通格式反应物能量: {mock_entry['energy']:.6f} Ha")
                        continue
                
                filename = f"{config.aromatic_name}_{halogen.name}_reactant"
                gjf = os.path.join(state.work_dir, f"{filename}.gjf")
                log_file = gjf.replace('.gjf', '.log')
                chk = gjf.replace('.gjf', '.chk')
                
                task.gjf_file = gjf
                task.log_file = log_file
                task.chk_file = chk
                
                # 检查已完成
                if os.path.exists(log_file):
                    res = read_gaussian16_output_opt(log_file)
                    if res and 'energy' in res:
                        state.log(f"  ✅ 已有结果，跳过")
                        task.energy = res['energy']
                        state.reactant_energy = res['energy']
                        task.status = TaskStatus.COMPLETED
                        continue
                
                # 使用初始结构（芳香环 + X2复合物）
                reactant_mol = state.complex_mol if state.complex_mol else current_mol
                if reactant_mol:
                    create_gaussian_input(reactant_mol, gjf, task.method, filename, config.nproc, config.memory, chk)
                    
                    state.log(f"  运行反应物能量计算: {filename}")
                    process = run_gaussian_job(gjf, run_dir=state.work_dir)
                    
                    if process:
                        state.running_processes.append(process)
                        state.log(f"  📊 PID: {process.pid}")
                        
                        return_code = process.wait()
                        state.running_processes.remove(process)
                        
                        if return_code == 0:
                            res = read_gaussian16_output_opt(log_file)
                            if res and 'energy' in res:
                                task.energy = res['energy']
                                state.reactant_energy = res['energy']
                                task.status = TaskStatus.COMPLETED
                                state.log(f"  ✅ 反应物能量计算完成 E={res['energy']:.6f} Ha")
                            else:
                                task.status = TaskStatus.FAILED
                                state.log(f"  ❌ 无法读取结果")
                        else:
                            task.status = TaskStatus.FAILED
                            state.log(f"  ❌ 计算失败 (返回码: {return_code})")
                    else:
                        task.status = TaskStatus.FAILED
                        state.log(f"  ❌ 无法启动进程")
                else:
                    task.status = TaskStatus.FAILED
                    state.log(f"  ❌ 无分子结构")
            
            elif task.task_type == TaskType.PRODUCT_ENERGY:
                # 产物能量计算任务
                # 首先检查是否有普通格式数据
                mock_data_dict = read_mock_data_file(state.work_dir)
                if mock_data_dict.get('product_energy'):
                    mock_entry = mock_data_dict['product_energy'][0]
                    if mock_entry.get('energy'):
                        task.energy = mock_entry['energy']
                        state.product_energy = mock_entry['energy']
                        task.status = TaskStatus.COMPLETED
                        state.log(f"  ✅ 使用普通格式产物能量: {mock_entry['energy']:.6f} Ha")
                        continue
                
                filename = f"{config.aromatic_name}_{halogen.name}_product"
                gjf = os.path.join(state.work_dir, f"{filename}.gjf")
                log_file = gjf.replace('.gjf', '.log')
                chk = gjf.replace('.gjf', '.chk')
                
                task.gjf_file = gjf
                task.log_file = log_file
                task.chk_file = chk
                
                # 检查已完成
                if os.path.exists(log_file):
                    res = read_gaussian16_output_opt(log_file)
                    if res and 'energy' in res:
                        state.log(f"  ✅ 已有结果，跳过")
                        task.energy = res['energy']
                        state.product_energy = res['energy']
                        task.status = TaskStatus.COMPLETED
                        continue
                
                # 生成产物结构
                product_mol = generate_product_structure(
                    config.aromatic_smiles, 
                    config.halogen_preset, 
                    config.ipso_carbon
                )
                
                if product_mol:
                    state.product_mol = product_mol
                    create_gaussian_input(product_mol, gjf, task.method, filename, config.nproc, config.memory, chk)
                    
                    state.log(f"  运行产物能量计算: {filename}")
                    process = run_gaussian_job(gjf, run_dir=state.work_dir)
                    
                    if process:
                        state.running_processes.append(process)
                        state.log(f"  📊 PID: {process.pid}")
                        
                        return_code = process.wait()
                        state.running_processes.remove(process)
                        
                        if return_code == 0:
                            res = read_gaussian16_output_opt(log_file)
                            if res and 'energy' in res:
                                task.energy = res['energy']
                                state.product_energy = res['energy']
                                task.status = TaskStatus.COMPLETED
                                state.log(f"  ✅ 产物能量计算完成 E={res['energy']:.6f} Ha")
                            else:
                                task.status = TaskStatus.FAILED
                                state.log(f"  ❌ 无法读取结果")
                        else:
                            task.status = TaskStatus.FAILED
                            state.log(f"  ❌ 计算失败 (返回码: {return_code})")
                    else:
                        task.status = TaskStatus.FAILED
                        state.log(f"  ❌ 无法启动进程")
                else:
                    task.status = TaskStatus.FAILED
                    state.log(f"  ❌ 无法生成产物结构")
        
        # 保存结果
        save_scan_results()
        
        fig = create_energy_plot()
        return "✅ 执行完成", state.get_log_text(), generate_task_table_md(), fig
    
    except Exception as e:
        state.log(f"❌ 错误: {str(e)}")
        return f"❌ 错误: {str(e)}", state.get_log_text(), generate_task_table_md(), None
    
    finally:
        state.is_running = False


def find_nearby_chk(work_dir, target_dist):
    """寻找附近的chk文件"""
    best_chk = None
    best_diff = float('inf')
    
    for chk in glob.glob(os.path.join(work_dir, "*_scan_d*.chk")):
        log = chk.replace('.chk', '.log')
        if os.path.exists(log):
            try:
                with open(log, 'r') as f:
                    if 'Normal termination' in f.read():
                        m = re.search(r'_d([\d.]+)\.chk', chk)
                        if m:
                            d = float(m.group(1))
                            if d >= target_dist - 0.01:
                                diff = abs(d - target_dist)
                                if diff < best_diff:
                                    best_diff = diff
                                    best_chk = chk
            except:
                pass
    return best_chk


def save_scan_results():
    """保存扫描结果"""
    if not state.work_dir:
        return
    
    data = {
        'scan_results': [{'distance': r['distance'], 'energy': r['energy']} for r in state.scan_results],
        'ts_guess_idx': state.ts_guess_idx
    }
    
    path = os.path.join(state.work_dir, "scan_results.json")
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def stop_execution():
    """停止执行"""
    state.stop_requested = True
    state.log("⏹️ 用户请求停止...")
    
    # 终止所有正在运行的进程
    if state.running_processes:
        state.log(f"🔪 终止 {len(state.running_processes)} 个正在运行的进程...")
        for process in state.running_processes[:]:  # 复制列表以避免修改时迭代问题
            try:
                process.terminate()  # 首先尝试优雅终止
                try:
                    process.wait(timeout=5)  # 等待5秒
                except subprocess.TimeoutExpired:
                    process.kill()  # 如果没响应，强制杀死
                    process.wait()
                state.log(f"✅ 已终止进程 PID: {process.pid}")
            except Exception as e:
                state.log(f"❌ 终止进程 PID {process.pid} 失败: {e}")
        state.running_processes.clear()
        state.log("🧹 已清理所有进程")
    
    return "正在停止..."


def refresh_status():
    """刷新状态"""
    log_files = get_log_files_in_workdir()
    fig = create_energy_plot()
    return state.get_log_text(), generate_task_table_md(), fig, gr.update(choices=log_files)


def open_log_file(task_index):
    """打开任务的log文件"""
    try:
        idx = int(task_index)
        if 0 <= idx < len(state.all_tasks):
            task = state.all_tasks[idx]
            if task.log_file and os.path.exists(task.log_file):
                os.startfile(task.log_file)
                return f"已打开: {task.log_file}"
    except:
        pass
    return "无法打开log文件"


# =============================================================================
# Gradio界面
# =============================================================================

def auto_refresh():
    """自动刷新状态"""
    # 只在有任务正在运行时刷新
    if any(task.status == TaskStatus.RUNNING for task in state.all_tasks):
        fig = create_energy_plot()
        return (state.get_log_text(), generate_task_table_md(), get_latest_convergence(), 
                get_scf_status_text(), fig)
    else:
        # 没有运行任务时，不刷新，保持当前值
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update()


def create_ui():
    """创建Gradio界面"""
    
    with gr.Blocks(title="过渡态搜索 v3") as app:
        gr.Markdown("# 🧪 过渡态搜索 v3")
        
        with gr.Tabs():
            # ==================== Tab 1: 配置与预览 ====================
            with gr.Tab("① 配置与预览"):
                # --- 加载历史 ---
                gr.Markdown("### 📂 加载历史项目")
                with gr.Row():
                    project_dropdown = gr.Dropdown(
                        label="选择项目", choices=get_available_projects(), scale=4
                    )
                    refresh_projects_btn = gr.Button("🔄", scale=1)
                    load_project_btn = gr.Button("📂 加载", variant="primary", scale=1)
                load_status = gr.Textbox(label="状态", interactive=False, lines=2)
                
                gr.Markdown("---")
                
                # --- 反应物配置 | 结构预览 ---
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 🧪 反应物配置")
                        aromatic_smiles = gr.Textbox(label="芳香族SMILES", value="c1ccccc1")
                        aromatic_name = gr.Textbox(label="名称", value="Benzene")
                        halogen_preset = gr.Dropdown(
                            label="卤素", choices=["F2", "Cl2", "Br2", "I2"], value="Br2"
                        )
                        
                        gr.Markdown("### 📐 几何构型")
                        c_x_distance = gr.Number(label="C-X初始距离(Å)", value=3.0)
                        c_x_x_angle = gr.Number(label="C-X-X角度(°)", value=175.0)
                        ipso_carbon = gr.Number(label="被进攻碳(1-based)", value=1)
                        generate_btn = gr.Button("🔬 生成初始结构", variant="primary")
                    
                    with gr.Column(scale=1):
                        gr.Markdown("### 👁️ 结构预览")
                        structure_info = gr.Textbox(label="信息", lines=4, interactive=False)
                        structure_html = gr.HTML(label="结构图像")
                
                gr.Markdown("---")
                
                # --- 计算设置 | 扫描设置 ---
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### ⚙️ 计算设置")
                        scheme_name = gr.Dropdown(
                            label="计算方案", choices=list(CALCULATION_SCHEMES.keys()), value="fast_wB97XD"
                        )
                        with gr.Row():
                            solvent = gr.Dropdown(
                                label="溶剂", choices=["None", "Dichloromethane", "Water", "Acetonitrile", "THF"],
                                value="Dichloromethane"
                            )
                            solvent_model = gr.Dropdown(label="溶剂模型", choices=["SMD", "PCM"], value="SMD")
                        with gr.Row():
                            opt_mode = gr.Dropdown(label="优化模式", choices=["CalcFC", "CalcAll", ""], value="CalcFC")
                            nproc = gr.Number(label="CPU核数", value=18)
                            memory = gr.Textbox(label="内存", value="20GB")
                        enable_initial_opt = gr.Checkbox(label="进行初始结构优化", value=True)
                        
                        gr.Markdown("### 🔋 能量计算")
                        calc_reactant_energy = gr.Checkbox(label="自动计算反应物单点能", value=True)
                        calc_product_energy = gr.Checkbox(label="自动计算产物单点能", value=True)
                    
                    with gr.Column(scale=1):
                        gr.Markdown("### 📊 扫描设置")
                        with gr.Row():
                            scan_start = gr.Number(label="起点(Å)", value=3.0)
                            scan_end = gr.Number(label="终点(Å)", value=1.9)
                            step_size = gr.Number(label="步长(Å)", value=0.1)
                        extra_distances = gr.Textbox(
                            label="额外扫描点(空格分隔)", placeholder="2.35 2.15", value=""
                        )
                        with gr.Row():
                            auto_stop = gr.Checkbox(label="自动极值点停止", value=True)
                            energy_threshold = gr.Number(label="阈值(kcal/mol)", value=0.5)
                        
                        gr.Markdown("### 🔧 TS计算设置")
                        auto_ts_calc = gr.Checkbox(label="扫描后自动计算TS", value=True)
                        enable_symmetry = gr.Checkbox(label="打破对称性 (TS计算需要)", value=True)
                        symmetry_offset = gr.Number(label="对称性偏移量(Å)", value=0.05, 
                                                   info="移动H原子的距离以打破对称性")
                        
                        run_name = gr.Textbox(label="项目名称(留空自动)", value="")
                
                build_tasks_btn = gr.Button("📝 生成任务队列 →", variant="primary", size="lg")
            
            # ==================== Tab 2: 任务与执行 ====================
            with gr.Tab("② 任务与执行"):
                # 控制按钮行
                with gr.Row():
                    execute_btn = gr.Button("🚀 开始执行", variant="primary", scale=2)
                    stop_btn = gr.Button("⏹️ 停止", variant="stop", scale=1)
                    refresh_btn = gr.Button("🔄 刷新", scale=1)
                exec_status = gr.Textbox(label="执行状态", interactive=False, lines=1)
                
                # --- 任务队列 | 日志 ---
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 📋 任务队列")
                        task_list_md = gr.Markdown(value="请先在配置页生成任务")
                    
                    with gr.Column(scale=1):
                        gr.Markdown("### 📜 执行日志")
                        log_output = gr.Textbox(label="", lines=10, interactive=False, max_lines=12)
                
                # --- 任务详情 | 收敛状态 ---
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 🎯 任务详情")
                        with gr.Row():
                            task_detail_idx = gr.Number(label="任务#", value=0, scale=1)
                            view_detail_btn = gr.Button("查看", scale=1)
                            open_log_btn = gr.Button("📄 打开Log", scale=1)
                        task_detail_md = gr.Markdown()
                        task_detail_html = gr.HTML()  # 结构显示
                    
                    with gr.Column(scale=1):
                        gr.Markdown("### 📊 收敛状态 (最新)")
                        convergence_md = gr.Markdown(value="等待计算...")
                        
                        gr.Markdown("### 🔄 SCF状态")
                        scf_status_md = gr.Markdown(value="等待计算...")
                
                # --- 警告/错误框 ---
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### ⚠️ 警告与错误")
                        warnings_errors_md = gr.Markdown(value="✅ 无警告或错误", elem_id="warnings-box")
                        refresh_warnings_btn = gr.Button("🔄 刷新警告/错误", size="sm")
                
                # --- 新增任务 | 能量曲线 ---
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### ➕ 新增扫描任务")
                        with gr.Row():
                            new_scan_dist = gr.Number(label="距离(Å)", value=2.35)
                            add_scan_btn = gr.Button("➕ 添加扫描")
                        
                        gr.Markdown("### ➕ 新增TS任务")
                        ts_scan_point = gr.Dropdown(label="选择扫描点", choices=[], allow_custom_value=True)
                        ts_custom_method = gr.Textbox(label="自定义方法(可选)", value="", lines=1)
                        with gr.Row():
                            refresh_scan_pts_btn = gr.Button("🔄 刷新扫描点")
                            add_ts_btn = gr.Button("➕ 添加TS优化", variant="primary")
                        
                        gr.Markdown("### 🔧 新增修复任务")
                        with gr.Row():
                            add_ts_fix_btn = gr.Button("🔧 添加TS修复")
                            add_refine_scan_btn = gr.Button("🔍 添加精细扫描")
                        
                        gr.Markdown("### � 新增能量计算任务")
                        with gr.Row():
                            add_reactant_energy_btn = gr.Button("⚛️ 反应物能量")
                            add_product_energy_btn = gr.Button("⚛️ 产物能量")
                        
                        gr.Markdown("### 🗑️ 删除任务")
                        with gr.Row():
                            task_to_delete = gr.Number(label="任务#", value=0)
                            delete_task_btn = gr.Button("🗑️ 删除")
                        task_action_status = gr.Textbox(label="操作状态", interactive=False)
                        
                        gr.Markdown("### 📤 导出数据")
                        with gr.Row():
                            export_from_state_btn = gr.Button("📤 导出计算数据")
                            export_from_logs_btn = gr.Button("📄 从Log导出")
                            supplement_from_scan_btn = gr.Button("🧩 从扫描补全能量点")
                        export_status_text = gr.Textbox(label="导出状态", interactive=False, lines=2)
                    
                    with gr.Column(scale=1):
                        gr.Markdown("### 📈 能量曲线 (PES扫描)")
                        energy_plot = gr.Plot()
                        gr.Markdown("### 📊 反应能量图 (R→TS→P)")
                        reaction_profile_plot = gr.Plot()
                        refresh_profile_btn = gr.Button("🔄 刷新反应能量图")
                
                # 10秒自动刷新
                timer = gr.Timer(value=10)
                timer.tick(
                    fn=auto_refresh,
                    outputs=[log_output, task_list_md, convergence_md, scf_status_md, energy_plot]
                )
            
            # ==================== Tab 3: 数据分析 ====================
            with gr.Tab("③ 数据分析"):
                gr.Markdown("### 📊 数据分析与可视化")
                
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("#### 📋 数据系列选择")
                        data_series_list = gr.CheckboxGroup(
                            label="选择要绘制的数据系列（可多选）",
                            choices=[],
                            value=[]
                        )
                        refresh_series_btn = gr.Button("🔄 刷新数据列表", variant="secondary")
                    
                    with gr.Column(scale=2):
                        gr.Markdown("#### 📈 可视化图表")
                        # 图表类型选择
                        plot_type = gr.Radio(
                            label="Chart Type",
                            choices=["Scan", "Energy Profile"],
                            value="Scan"
                        )
                        analysis_plot = gr.Plot(label="分析图表")
                        generate_plot_btn = gr.Button("📊 生成图表", variant="primary", size="lg")
                
                # 分析结果
                gr.Markdown("#### 🔬 分析结果")
                analysis_result = gr.Textbox(label="分析报告", lines=6, interactive=False)
                
                # AI分析
                with gr.Accordion("🤖 AI智能分析", open=False):
                    gr.Markdown("支持本地Ollama或API调用进行数据分析")
                    with gr.Row():
                        ai_backend = gr.Radio(
                            label="AI后端",
                            choices=["本地Ollama", "OpenAI API"],
                            value="本地Ollama"
                        )
                        ollama_model = gr.Textbox(
                            label="Ollama模型名称",
                            value="llama2",
                            placeholder="例如: llama2, mistral"
                        )
                    ai_prompt = gr.Textbox(
                        label="分析提示", 
                        placeholder="请输入您想让AI分析的问题，例如：这个反应的机理是什么？活化能是否合理？",
                        lines=3
                    )
                    ai_analyze_btn = gr.Button("🧠 AI分析", variant="primary")
                    ai_analysis_result = gr.Textbox(label="AI分析结果", lines=12, interactive=False)
                
                # 控制按钮
                with gr.Row():
                    export_data_btn = gr.Button("💾 导出数据", variant="secondary")
                    export_status = gr.Textbox(label="导出状态", interactive=False, scale=2)
        
        # ==================== 事件绑定 ====================
        
        # 刷新项目列表
        refresh_projects_btn.click(
            fn=lambda: gr.update(choices=get_available_projects()),
            outputs=[project_dropdown]
        )
        
        # 加载项目
        def on_load_project(project_name):
            result = load_project(project_name)
            # 返回: status, task_md, plot, log, smiles_update, halogen_update
            return result[0], result[1], result[2], result[3]
        
        load_project_btn.click(
            fn=on_load_project,
            inputs=[project_dropdown],
            outputs=[load_status, task_list_md, energy_plot, log_output]
        )
        
        # 生成结构
        generate_btn.click(
            fn=generate_structure_preview,
            inputs=[aromatic_smiles, aromatic_name, halogen_preset,
                   c_x_distance, c_x_x_angle, ipso_carbon, enable_symmetry],
            outputs=[structure_info, structure_html]
        )
        
        # 初始结构优化勾选时强制勾选反应物能量
        def on_initial_opt_change(enable_init):
            if enable_init:
                return gr.update(value=True, interactive=False)
            else:
                return gr.update(interactive=True)
        
        enable_initial_opt.change(
            fn=on_initial_opt_change,
            inputs=[enable_initial_opt],
            outputs=[calc_reactant_energy]
        )
        
        # 生成任务队列
        def on_build_tasks(ar_smiles, ar_name, hal, scheme, sol, sol_model, opt_m,
                          np, mem, s_start, s_end, s_step, extra, auto_s, e_thresh, 
                          enable_init_opt, calc_r_energy, calc_p_energy, auto_ts, sym_offset):
            # 重要：新建任务时重置work_dir，确保创建新的时间戳文件夹
            state.work_dir = None
            state.is_loaded_project = False
            state.scan_results = []
            
            config = ProjectConfig(
                aromatic_smiles=ar_smiles, aromatic_name=ar_name, halogen_preset=hal,
                scheme_name=scheme, solvent=sol, solvent_model=sol_model, opt_mode=opt_m,
                nproc=int(np), memory=mem, scan_start=s_start, scan_end=s_end,
                step_size=s_step, auto_stop=auto_s, energy_threshold=e_thresh,
                calc_reactant_energy=calc_r_energy, calc_product_energy=calc_p_energy
            )
            # 保存TS和对称性设置到state
            state.auto_ts_calc = auto_ts
            state.symmetry_offset = sym_offset
            md = build_initial_tasks(config, extra, enable_init_opt, calc_r_energy, calc_p_energy, auto_ts)
            return md, f"✅ Generated {len(state.all_tasks)} tasks (new folder will be created)"
        
        build_tasks_btn.click(
            fn=on_build_tasks,
            inputs=[aromatic_smiles, aromatic_name, halogen_preset, scheme_name,
                   solvent, solvent_model, opt_mode, nproc, memory,
                   scan_start, scan_end, step_size, extra_distances, auto_stop, energy_threshold, 
                   enable_initial_opt, calc_reactant_energy, calc_product_energy,
                   auto_ts_calc, symmetry_offset],
            outputs=[task_list_md, exec_status]
        )
        
        # 添加扫描任务
        def on_add_scan(dist):
            return add_task("scan", dist, "")
        
        add_scan_btn.click(
            fn=on_add_scan,
            inputs=[new_scan_dist],
            outputs=[task_action_status, task_list_md]
        )
        
        # 刷新扫描点列表
        def on_refresh_scan_pts():
            choices = get_scan_point_choices()
            return gr.update(choices=choices, value=choices[0] if choices else None)
        
        refresh_scan_pts_btn.click(
            fn=on_refresh_scan_pts,
            outputs=[ts_scan_point]
        )
        
        # 添加TS任务 - 支持选择扫描点和自定义方法
        def on_add_ts(scan_point_str, custom_method):
            # 解析扫描点索引
            scan_idx = None
            if scan_point_str:
                try:
                    scan_idx = int(scan_point_str.split(":")[0])
                except:
                    pass
            return add_task("ts", 0, custom_method, scan_idx)
        
        add_ts_btn.click(
            fn=on_add_ts,
            inputs=[ts_scan_point, ts_custom_method],
            outputs=[task_action_status, task_list_md]
        )
        
        # 添加TS修复任务
        add_ts_fix_btn.click(
            fn=lambda: add_task("ts_fix", 0, ""),
            outputs=[task_action_status, task_list_md]
        )
        
        # 添加精细扫描任务
        add_refine_scan_btn.click(
            fn=lambda: add_task("refine_scan", 0, ""),
            outputs=[task_action_status, task_list_md]
        )
        
        # 添加反应物能量计算任务
        add_reactant_energy_btn.click(
            fn=lambda: add_task("reactant_energy", 0, ""),
            outputs=[task_action_status, task_list_md]
        )
        
        # 添加产物能量计算任务
        add_product_energy_btn.click(
            fn=lambda: add_task("product_energy", 0, ""),
            outputs=[task_action_status, task_list_md]
        )
        
        # 刷新反应能量图
        def on_refresh_profile():
            fig = create_reaction_profile_plot()
            return fig
        
        refresh_profile_btn.click(
            fn=on_refresh_profile,
            outputs=[reaction_profile_plot]
        )
        
        # 删除任务
        delete_task_btn.click(
            fn=delete_task,
            inputs=[task_to_delete],
            outputs=[task_action_status, task_list_md]
        )
        
        # 导出计算数据
        def on_export_from_state():
            _, msg = export_calculation_to_normal_data()
            return msg
        
        export_from_state_btn.click(
            fn=on_export_from_state,
            outputs=[export_status_text]
        )
        
        # 从Log文件导出
        def on_export_from_logs():
            _, msg = export_from_log_files()
            return msg
        
        export_from_logs_btn.click(
            fn=on_export_from_logs,
            outputs=[export_status_text]
        )

        # 从扫描补全缺失能量点（只补缺失，不覆盖已有log任务）
        def on_supplement_from_scan():
            _, msg = supplement_normal_data_from_scan()
            return msg

        supplement_from_scan_btn.click(
            fn=on_supplement_from_scan,
            outputs=[export_status_text]
        )
        
        # 查看任务详情 - 同时显示结构
        def on_view_detail(idx):
            details, html = get_task_details(idx)
            return details, html
        
        view_detail_btn.click(
            fn=on_view_detail,
            inputs=[task_detail_idx],
            outputs=[task_detail_md, task_detail_html]
        )
        
        # 打开log文件
        open_log_btn.click(
            fn=open_log_file,
            inputs=[task_detail_idx],
            outputs=[task_action_status]
        )
        
        # 执行任务
        def on_execute(rn):
            result = execute_all_tasks(rn)
            return result[0], result[1], result[2], result[3]
        
        execute_btn.click(
            fn=on_execute,
            inputs=[run_name],
            outputs=[exec_status, log_output, task_list_md, energy_plot]
        )
        
        # 停止执行
        stop_btn.click(fn=stop_execution, outputs=[exec_status])
        
        # 手动刷新
        refresh_btn.click(
            fn=auto_refresh,
            outputs=[log_output, task_list_md, convergence_md, scf_status_md, energy_plot]
        )
        
        # 刷新警告/错误
        refresh_warnings_btn.click(
            fn=get_all_warnings_errors,
            outputs=[warnings_errors_md]
        )
        
        # ==================== 数据分析事件 ====================
        
        # 刷新数据系列列表
        def refresh_series_list():
            series = get_available_data_series()
            return gr.update(choices=series, value=[])
        
        refresh_series_btn.click(
            fn=refresh_series_list,
            outputs=[data_series_list]
        )
        
        # 生成图表
        generate_plot_btn.click(
            fn=plot_selected_series,
            inputs=[data_series_list, plot_type],
            outputs=[analysis_plot, analysis_result]
        )
        
        # AI分析
        def perform_ai_analysis(selected_series, plot_type_choice, user_prompt, backend, ollama_model):
            if not selected_series:
                return "请先选择数据系列并生成图表"
            
            # 生成数据描述
            data_desc = f"选中的数据系列: {', '.join(selected_series)}\n"
            data_desc += f"图表类型: {plot_type_choice}"
            
            # 生成分析结果
            fig, analysis_text = plot_selected_series(selected_series, plot_type_choice)
            
            if analysis_text:
                analysis_results = analysis_text
            else:
                analysis_results = "无分析结果"
            
            result = analyze_with_ai_enhanced(data_desc, analysis_results, user_prompt, backend, ollama_model)
            return result
        
        ai_analyze_btn.click(
            fn=perform_ai_analysis,
            inputs=[data_series_list, plot_type, ai_prompt, ai_backend, ollama_model],
            outputs=[ai_analysis_result]
        )
        
        # 导出数据
        def export_analysis_data(selected_series, plot_type_choice):
            if not selected_series:
                return "请先选择数据系列"
            
            import pandas as pd
            from io import StringIO
            
            export_data = []
            
            # 导出选中的数据
            for series_name in selected_series:
                if series_name == "当前项目-扫描数据":
                    for r in state.scan_results:
                        export_data.append({
                            'Series': series_name,
                            'Type': 'Scan',
                            'Distance': r['distance'],
                            'Energy': r['energy']
                        })
                
                elif series_name == "当前项目-能量点":
                    for task in state.all_tasks:
                        if task.status == TaskStatus.COMPLETED and task.energy:
                            if task.task_type == TaskType.REACTANT_ENERGY or task.task_type == TaskType.INITIAL_OPT:
                                export_data.append({
                                    'Series': series_name,
                                    'Type': 'Reactant',
                                    'Energy': task.energy
                                })
                            elif task.task_type == TaskType.TS_OPT:
                                export_data.append({
                                    'Series': series_name,
                                    'Type': 'TS',
                                    'Energy': task.energy
                                })
                            elif task.task_type == TaskType.PRODUCT_ENERGY:
                                export_data.append({
                                    'Series': series_name,
                                    'Type': 'Product',
                                    'Energy': task.energy
                                })
                
                elif series_name.startswith("内置数据-"):
                    try:
                        df_builtin = pd.read_csv(StringIO(csv_data), skipinitialspace=True)
                        label_part = series_name.replace("内置数据-", "")
                        
                        for idx, row in df_builtin.iterrows():
                            row_label = f"{row['Substrate']}-{row['Halogen']}"
                            if row['Position'] != '-':
                                row_label += f"-{row['Position']}"
                            if row['Catalyst'] != 'None':
                                row_label += f"-{row['Catalyst']}"
                            
                            if row_label == label_part:
                                export_data.append({
                                    'Series': series_name,
                                    'Substrate': row['Substrate'],
                                    'Halogen': row['Halogen'],
                                    'Position': row['Position'],
                                    'Catalyst': row['Catalyst'],
                                    'R_Energy': row['R_Hartree'],
                                    'TS_Energy': row['TS_Hartree'],
                                    'P_Energy': row['P_Hartree'],
                                    'Note': row['Note']
                                })
                                break
                    except Exception as e:
                        print(f"导出内置数据失败: {e}")
            
            if not export_data:
                return "无数据可导出"
            
            # 导出到CSV文件
            df = pd.DataFrame(export_data)
            export_path = SCRIPT_DIR / "analysis_export.csv"
            df.to_csv(export_path, index=False)
            
            return f"数据已导出到: {export_path} ({len(export_data)} 条记录)"
        
        export_data_btn.click(
            fn=export_analysis_data,
            inputs=[data_series_list, plot_type],
            outputs=[export_status]
        )
        
        # 初始化数据系列列表
        app.load(
            fn=refresh_series_list,
            outputs=[data_series_list]
        )
    
    return app


# =============================================================================
# 主程序
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 过渡态搜索 v3")
    print(f"📂 输出目录: {OUT_DIR}")
    print("=" * 60)
    
    app = create_ui()
    app.launch(
        server_name="127.0.0.1",
        share=False,
        inbrowser=True
    )
