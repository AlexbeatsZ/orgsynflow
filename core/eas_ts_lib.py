# -*- coding: utf-8 -*-
"""
过渡态搜索库 - Transition State Search Library
将所有工具函数集中在这里，保持notebook简洁
"""

import os
import sys
import subprocess
import shutil
import re
import glob
import copy
import math
import json
import datetime
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

# RDKit
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry.rdGeometry import Point3D

# Visualization
import matplotlib.pyplot as plt
try:
    from IPython.display import display, clear_output
    HAS_IPYTHON = True
except ImportError:
    HAS_IPYTHON = False
    def display(*args, **kwargs): pass
    def clear_output(*args, **kwargs): pass

try:
    import py3Dmol
    HAS_PY3DMOL = True
except ImportError:
    HAS_PY3DMOL = False

from core.gaussian_runner import find_gaussian_executable

# =============================================================================
# 配置类定义
# =============================================================================

@dataclass
class HalogenPreset:
    """卤素预设参数"""
    name: str
    smiles: str
    symbol: str
    typical_bond_length: float  # C-X 典型键长
    scan_end: float             # 扫描终点
    scan_start: float           # 扫描起点
    initial_distance: float     # 初始距离
    xx_bond_length: float       # X-X 键长

HALOGEN_PRESETS = {
    "F2": HalogenPreset("Fluorine", "FF", "F", 1.35, 1.5, 2.8, 2.8, 1.42),
    "Cl2": HalogenPreset("Chlorine", "ClCl", "Cl", 1.73, 1.8, 3.0, 3.0, 1.99),
    "Br2": HalogenPreset("Bromine", "BrBr", "Br", 1.89, 1.9, 3.0, 3.0, 2.28),
    "I2": HalogenPreset("Iodine", "II", "I", 2.10, 2.1, 3.2, 3.2, 2.67),
}

CALCULATION_SCHEMES = {
    "superfast": {"desc": "PM7 半经验 (秒级)", "method": "PM7", "basis": None, "disp": None},
    "fast": {"desc": "B3LYP/3-21G+GD3BJ", "method": "B3LYP", "basis": "3-21G", "disp": "EmpiricalDispersion=GD3BJ"},
    "fast_wB97XD": {"desc": "wB97XD/3-21G (推荐快速)", "method": "wB97XD", "basis": "3-21G", "disp": None},
    "standard": {"desc": "wB97XD/6-31G(d)", "method": "wB97XD", "basis": "6-31G(d)", "disp": None},
    "standard_M062X": {"desc": "M06-2X/6-31G(d)", "method": "M062X", "basis": "6-31G(d)", "disp": None},
    "high": {"desc": "wB97XD/def2-TZVP (高精度)", "method": "wB97XD", "basis": "def2-TZVP", "disp": None},
    "high_M062X": {"desc": "M06-2X/def2-TZVP", "method": "M062X", "basis": "def2-TZVP", "disp": None},
}

@dataclass
class TSConfig:
    """过渡态搜索配置 - 所有参数集中在这里"""
    # ===== 反应物 =====
    aromatic_smiles: str = "c1ccccc1"
    aromatic_name: str = "Benzene"
    halogen_preset: str = "Br2"
    
    # ===== 初始几何 (端基进攻 T型) =====
    c_x_initial_distance: float = 3.0
    c_x_x_angle: float = 175.0
    ipso_carbon_index: int = 1  # 1-based
    
    # ===== 计算方法 =====
    scheme_name: str = "fast_wB97XD"
    solvent: str = "Dichloromethane"
    solvent_model: str = "SMD"
    
    # ===== 扫描设置 =====
    scan_start: float = 3.0
    scan_end: float = 1.9
    default_step_size: float = 0.1
    variable_steps: List[Tuple[float, float, float]] = field(default_factory=list)
    single_point_distances: List[float] = field(default_factory=list)
    
    # ===== 终止条件 =====
    auto_stop_at_ts: bool = True
    energy_drop_threshold: float = 0.5  # kcal/mol
    
    # ===== 功能开关 =====
    enable_symmetry_breaking: bool = True   # 打破对称性
    enable_freq_analysis: bool = True       # 频率分析
    handle_imaginary_freq: bool = True      # 处理虚频
    imaginary_freq_threshold: float = 50.0  # 小虚频阈值 (cm^-1)
    
    # ===== 硬件 =====
    nproc: int = 18
    memory: str = "20GB"
    scan_opt_mode: str = "CalcFC"
    
    # ===== 工作目录 =====
    base_dir: str = "out"
    run_name: str = ""
    
    # ===== 可视化 =====
    realtime_plot: bool = True


# =============================================================================
# 扫描距离生成
# =============================================================================

def generate_scan_distances(cfg: TSConfig) -> List[float]:
    """生成扫描距离列表(支持变步长和单点)"""
    distances = []
    
    if cfg.variable_steps:
        for start, end, step in cfg.variable_steps:
            current = start
            while current > end + 1e-6:
                current -= step
                if current >= end - 1e-6:
                    distances.append(round(current, 4))
    else:
        current = cfg.scan_start
        while current > cfg.scan_end + 1e-6:
            current -= cfg.default_step_size
            if current >= cfg.scan_end - 1e-6:
                distances.append(round(current, 4))
    
    # 添加额外单点
    if cfg.single_point_distances:
        for d in cfg.single_point_distances:
            if d not in distances:
                distances.append(d)
        distances.sort(reverse=True)
    
    return distances


# =============================================================================
# 结构生成
# =============================================================================

def generate_endon_complex(ar_smiles: str, hal_smiles: str, ipso_idx: int, 
                           c_x_dist: float, c_x_x_angle: float, x_x_bond: float,
                           symmetry_breaking: bool = True):
    """
    生成端基进攻(T型)复合物
    
    Args:
        ar_smiles: 芳香族SMILES
        hal_smiles: 卤素SMILES  
        ipso_idx: 被进攻碳的索引 (0-based)
        c_x_dist: C-X初始距离
        c_x_x_angle: C-X-X角度
        x_x_bond: X-X键长
        symmetry_breaking: 是否打破对称性
    """
    print(f"生成T型构型: C{ipso_idx+1}-X={c_x_dist}Å, ∠C-X-X={c_x_x_angle}°")
    
    # 生成芳香族分子
    aromatic = Chem.AddHs(Chem.MolFromSmiles(ar_smiles))
    AllChem.EmbedMolecule(aromatic, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(aromatic)
    
    # 生成卤素分子
    halogen = Chem.AddHs(Chem.MolFromSmiles(hal_smiles))
    AllChem.EmbedMolecule(halogen, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(halogen)
    
    ar_conf = aromatic.GetConformer()
    c_ipso_pos = ar_conf.GetAtomPosition(ipso_idx)
    
    # 计算苯环平面法向量
    c_atoms = [a.GetIdx() for a in aromatic.GetAtoms() if a.GetSymbol() == 'C'][:3]
    p1 = np.array([ar_conf.GetAtomPosition(c_atoms[0]).x, 
                   ar_conf.GetAtomPosition(c_atoms[0]).y, 
                   ar_conf.GetAtomPosition(c_atoms[0]).z])
    p2 = np.array([ar_conf.GetAtomPosition(c_atoms[1]).x, 
                   ar_conf.GetAtomPosition(c_atoms[1]).y, 
                   ar_conf.GetAtomPosition(c_atoms[1]).z])
    p3 = np.array([ar_conf.GetAtomPosition(c_atoms[2]).x, 
                   ar_conf.GetAtomPosition(c_atoms[2]).y, 
                   ar_conf.GetAtomPosition(c_atoms[2]).z])
    normal = np.cross(p2-p1, p3-p1)
    normal = normal / np.linalg.norm(normal)
    
    # 进攻原子位置
    c_ipso = np.array([c_ipso_pos.x, c_ipso_pos.y, c_ipso_pos.z])
    x_attack_pos = c_ipso + normal * c_x_dist
    
    # 离去原子位置 (略微倾斜打破对称性)
    tilt = math.radians(180 - c_x_x_angle)
    perp = np.cross(normal, [1,0,0]) if abs(normal[0]) < 0.9 else np.cross(normal, [0,1,0])
    perp = perp / np.linalg.norm(perp)
    
    if symmetry_breaking:
        # 添加微小侧向偏移打破对称性
        x_dep_dir = normal * math.cos(tilt) + perp * math.sin(tilt)
    else:
        x_dep_dir = normal
    x_dep_dir = x_dep_dir / np.linalg.norm(x_dep_dir)
    x_departing_pos = x_attack_pos + x_dep_dir * x_x_bond
    
    # 合并分子
    combined = Chem.CombineMols(aromatic, halogen)
    combined_conf = combined.GetConformer()
    n_ar = aromatic.GetNumAtoms()
    
    hal_atoms = [a.GetIdx() for a in halogen.GetAtoms() if a.GetSymbol() not in ['H']]
    combined_conf.SetAtomPosition(n_ar + hal_atoms[0], Point3D(*x_attack_pos))
    if len(hal_atoms) > 1:
        combined_conf.SetAtomPosition(n_ar + hal_atoms[1], Point3D(*x_departing_pos))
    
    print(f"✅ T型构型生成成功")
    return combined


def set_fragment_distance(mol, a1_idx: int, a2_idx: int, target: float):
    """
    设置两原子间距离(移动卤素片段)
    
    Args:
        mol: RDKit分子
        a1_idx: 原子1索引 (1-based)
        a2_idx: 原子2索引 (1-based)
        target: 目标距离
    """
    mol_c = copy.deepcopy(mol)
    conf = mol_c.GetConformer()
    i1, i2 = a1_idx - 1, a2_idx - 1
    
    p1 = np.array([conf.GetAtomPosition(i1).x, conf.GetAtomPosition(i1).y, conf.GetAtomPosition(i1).z])
    p2 = np.array([conf.GetAtomPosition(i2).x, conf.GetAtomPosition(i2).y, conf.GetAtomPosition(i2).z])
    
    cur = np.linalg.norm(p2 - p1)
    d = (p2 - p1) / cur
    delta = target - cur
    
    hals = {'F', 'Cl', 'Br', 'I'}
    if mol_c.GetAtomWithIdx(i2).GetSymbol() in hals:
        for i in range(mol_c.GetNumAtoms()):
            if mol_c.GetAtomWithIdx(i).GetSymbol() in hals:
                op = conf.GetAtomPosition(i)
                conf.SetAtomPosition(i, Point3D(op.x + d[0]*delta, op.y + d[1]*delta, op.z + d[2]*delta))
    
    return mol_c


def update_mol_coordinates(original_mol, results: dict):
    """更新分子坐标为优化后的坐标"""
    geometry = results.get('geometry')
    if not geometry:
        return original_mol
    
    optimized_mol = Chem.Mol(original_mol)
    if optimized_mol.GetNumConformers() == 0:
        conf = Chem.Conformer(optimized_mol.GetNumAtoms())
        optimized_mol.AddConformer(conf)
    
    conf = optimized_mol.GetConformer(0)
    for i, atom in enumerate(geometry):
        if i < optimized_mol.GetNumAtoms():
            conf.SetAtomPosition(i, (atom['x'], atom['y'], atom['z']))
    
    return optimized_mol


def get_atom_distance(mol, atom_idx1: int, atom_idx2: int) -> float:
    """计算两个原子之间的距离 (1-based索引)"""
    conf = mol.GetConformer()
    pos1 = conf.GetAtomPosition(atom_idx1 - 1)  # 转换为0-based
    pos2 = conf.GetAtomPosition(atom_idx2 - 1)
    return pos1.Distance(pos2)


# =============================================================================
# Gaussian 输入文件生成
# =============================================================================

def create_gaussian_input(mol, filename: str, method: str, title: str,
                          nproc: int, mem: str, chk: str,
                          charge: int = 0, mult: int = 1,
                          extra_section: str = ""):
    """
    创建Gaussian输入文件 (正确的换行格式)
    """
    conf = mol.GetConformer()
    
    with open(filename, 'w', newline='\n') as f:
        f.write(f"%nproc={nproc}\n")
        f.write(f"%mem={mem}\n")
        f.write(f"%chk={os.path.basename(chk)}\n")
        f.write(f"{method}\n")
        f.write("\n")
        f.write(f"{title}\n")
        f.write("\n")
        f.write(f"{charge} {mult}\n")
        
        for i in range(mol.GetNumAtoms()):
            a = mol.GetAtomWithIdx(i)
            p = conf.GetAtomPosition(i)
            f.write(f"{a.GetSymbol():2s} {p.x:14.8f} {p.y:14.8f} {p.z:14.8f}\n")
        
        f.write("\n")
        if extra_section:
            f.write(extra_section)
            if not extra_section.endswith("\n"):
                f.write("\n")
        f.write("\n")
    
    return filename


def create_scan_input(mol, filename: str, scan_constraint: str, method: str,
                      nproc: int, mem: str, chk: str,
                      charge: int = 0, mult: int = 1):
    """
    创建扫描输入文件
    """
    extra = f"{scan_constraint}\n"
    return create_gaussian_input(mol, filename, method, "Scan", nproc, mem, chk, charge, mult, extra)


# =============================================================================
# Checkpoint 文件管理
# =============================================================================

def find_best_checkpoint(work_dir: str, target_dist: float, symbol: str) -> Optional[str]:
    """智能寻找最佳checkpoint文件"""
    best_chk, best_diff = None, float('inf')
    
    # 优先找扫描步骤的chk
    for chk in glob.glob(os.path.join(work_dir, "*_scan_*.chk")):
        log = chk.replace('.chk', '.log')
        if os.path.exists(log):
            try:
                with open(log, 'r') as f:
                    if 'Normal termination' in f.read():
                        m = re.search(r'_d([\d.]+)\.chk', chk)
                        if m:
                            d = float(m.group(1))
                            if d >= target_dist - 0.05 and abs(d - target_dist) < best_diff:
                                best_diff = abs(d - target_dist)
                                best_chk = chk
            except:
                pass
    
    # 没找到则尝试优化的chk
    if not best_chk:
        for chk in glob.glob(os.path.join(work_dir, "*_opt.chk")):
            log = chk.replace('.chk', '.log')
            if os.path.exists(log):
                try:
                    with open(log, 'r') as f:
                        if 'Normal termination' in f.read():
                            best_chk = chk
                            break
                except:
                    pass
    
    if best_chk:
        print(f"   🔍 找到checkpoint: {os.path.basename(best_chk)}")
    
    return best_chk


# =============================================================================
# Gaussian 作业执行
# =============================================================================

def run_gaussian_job(gjf_file: str, run_dir: str = None) -> Optional[subprocess.Popen]:
    """运行Gaussian作业，返回进程对象"""
    gjf_path = Path(gjf_file)
    if not gjf_path.exists():
        print(f"错误: 输入文件不存在: {gjf_file}")
        return None
    
    if run_dir is None:
        run_dir = gjf_path.parent
    
    run_dir_path = Path(run_dir)
    run_dir_path.mkdir(parents=True, exist_ok=True)
    
    local_gjf = run_dir_path / gjf_path.name
    if gjf_path.resolve() != local_gjf.resolve():
        shutil.copy2(gjf_path, local_gjf)
    
    local_log = local_gjf.with_suffix('.log')
    
    try:
        exe = find_gaussian_executable()
        if not exe:
            print("❌ 未找到 Gaussian 可执行文件")
            return None
        cmd = [exe, local_gjf.name, local_log.name]
        print(f"执行: {' '.join(cmd)} (PID 将被记录)")
        
        env = os.environ.copy()
        env['GAUSS_SCRDIR'] = str(run_dir_path)
        
        # 使用Popen启动进程，不等待完成
        process = subprocess.Popen(
            cmd,
            cwd=str(run_dir_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print(f"✅ 进程启动，PID: {process.pid}")
        return process
        
    except FileNotFoundError:
        print("❌ 未找到 Gaussian 可执行文件")
        return None
    except Exception as e:
        print(f"❌ 启动进程失败: {e}")
        return None


# =============================================================================
# Gaussian 输出解析
# =============================================================================

def read_gaussian16_output_opt(filename: str) -> Optional[dict]:
    """读取Gaussian优化输出"""
    if not os.path.exists(filename):
        return None
    
    results = {
        'energy': None,
        'geometry': None,
        'frequencies': [],
        'converged': False
    }
    
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # 检查收敛
    for line in lines:
        if 'Normal termination' in line:
            results['converged'] = True
            break
    
    # 提取能量 (最后一个SCF能量)
    for line in reversed(lines):
        if 'SCF Done' in line:
            m = re.search(r'E\([^)]+\)\s*=\s*([+-]?\d+\.\d+)', line)
            if m:
                results['energy'] = float(m.group(1))
                break
    
    # 提取几何结构
    geom_idx = None
    for i, line in enumerate(lines):
        if 'Standard orientation' in line or 'Input orientation' in line:
            geom_idx = i
    
    if geom_idx:
        results['geometry'] = extract_geometry_from_position(lines, geom_idx)
    
    # 提取频率
    for line in lines:
        if "Frequencies --" in line:
            parts = line.split()[2:]
            for p in parts:
                try:
                    results['frequencies'].append(float(p))
                except:
                    pass
    
    return results


def extract_geometry_from_position(lines: list, start_idx: int) -> list:
    """从指定位置提取几何结构"""
    geometry = []
    
    # 跳过表头
    i = start_idx + 5
    
    atomic_symbols = {
        1: 'H', 6: 'C', 7: 'N', 8: 'O', 9: 'F',
        15: 'P', 16: 'S', 17: 'Cl', 35: 'Br', 53: 'I'
    }
    
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('-') or not line:
            break
        
        parts = line.split()
        if len(parts) >= 6:
            try:
                atom_num = int(parts[0])
                atomic_num = int(parts[1])
                x = float(parts[3])
                y = float(parts[4])
                z = float(parts[5])
                
                element = atomic_symbols.get(atomic_num, 'X')
                geometry.append({
                    'atom_num': atom_num,
                    'element': element,
                    'x': x, 'y': y, 'z': z
                })
            except:
                break
        i += 1
    
    return geometry


def read_scan_output_robust(filename: str) -> Optional[list]:
    """读取扫描输出，返回所有步骤的结果"""
    if not os.path.exists(filename):
        return None
    
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # 检查是否正常终止或有部分结果
    if 'SCF Done' not in content:
        return None
    
    lines = content.split('\n')
    steps = []
    
    # 提取最后一个结构和能量
    last_energy = None
    for line in reversed(lines):
        if 'SCF Done' in line:
            m = re.search(r'E\([^)]+\)\s*=\s*([+-]?\d+\.\d+)', line)
            if m:
                last_energy = float(m.group(1))
                break
    
    geom_idx = None
    for i, line in enumerate(lines):
        if 'Standard orientation' in line or 'Input orientation' in line:
            geom_idx = i
    
    if last_energy and geom_idx:
        geometry = extract_geometry_from_position(lines, geom_idx)
        steps.append({
            'energy': last_energy,
            'geometry': geometry
        })
    
    return steps if steps else None


# =============================================================================
# 频率分析
# =============================================================================

def analyze_frequencies(freqs: list, small_threshold: float = 50.0) -> Tuple[int, str, dict]:
    """
    分析虚频特征
    
    分类代码:
    0: 无虚频 (极小值点)
    1: 多个大虚频
    2: 一个大虚频 + 若干小虚频
    3: 多个小虚频
    4: 只有一个小虚频
    5: 只有一个大虚频 (理想TS)
    
    Returns:
        (category_code, description, details_dict)
    """
    imag_freqs = [f for f in freqs if f < 0]
    count = len(imag_freqs)
    
    if count == 0:
        return 0, "无虚频 (极小值点)", {'imag_freqs': []}
    
    large_imag = [f for f in imag_freqs if abs(f) >= small_threshold]
    small_imag = [f for f in imag_freqs if abs(f) < small_threshold]
    
    large_count = len(large_imag)
    
    details = {
        'imag_freqs': imag_freqs,
        'large_imag': large_imag,
        'small_imag': small_imag
    }
    
    if large_count == 0:
        if count == 1:
            return 4, f"只有一个小虚频 ({imag_freqs[0]:.1f} cm⁻¹) - 势能面平坦", details
        else:
            return 3, f"多个小虚频 ({count}个) - 势能面平坦", details
    elif large_count == 1:
        if len(small_imag) == 0:
            return 5, f"✅ 理想TS: 一个大虚频 ({large_imag[0]:.1f} cm⁻¹)", details
        else:
            return 2, f"一个大虚频 + {len(small_imag)}个小虚频 - 可能是TS", details
    else:
        return 1, f"多个大虚频 ({large_count}个) - 高阶鞍点", details


def get_last_frequencies_robust(filename: str) -> list:
    """从Gaussian log文件读取最后一次频率分析结果"""
    if not os.path.exists(filename):
        return []
    
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # 找最后一个频率块
    block_indices = [i for i, line in enumerate(lines) if "Harmonic frequencies" in line]
    
    start_idx = 0
    if block_indices:
        start_idx = block_indices[-1]
    
    final_freqs = []
    for line in lines[start_idx:]:
        if "Frequencies --" in line:
            parts = line.split("--")[1].split()
            final_freqs.extend([float(x) for x in parts])
    
    return final_freqs


def print_gaussian_results(results: dict):
    """打印Gaussian结果"""
    if results.get('energy'):
        print(f"能量: {results['energy']:.6f} Hartree")
    
    freqs = results.get('frequencies', [])
    if freqs:
        print(f"频率数量: {len(freqs)}")
        imag_freqs = [f for f in freqs if f < 0]
        if imag_freqs:
            print(f"虚频 ({len(imag_freqs)}): {imag_freqs}")
        else:
            print("无虚频 (极小值点)")
    
    if results.get('geometry'):
        print(f"几何结构: 包含 {len(results['geometry'])} 个原子")


# =============================================================================
# 3D可视化
# =============================================================================

def view_3d_structure(mol, name: str = "Structure"):
    """显示分子3D结构，返回HTML字符串"""
    if not HAS_PY3DMOL:
        print("py3Dmol未安装，跳过3D显示")
        return "<p>py3Dmol未安装，无法显示3D结构</p>"
    
    try:
        # 确保分子有构象
        if mol.GetNumConformers() == 0:
            # 添加氢并生成3D构象
            mol = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol)
        
        mb = Chem.MolToMolBlock(mol)
        view = py3Dmol.view(width=600, height=400)
        view.addModel(mb, 'mol')
        view.setStyle({'stick': {'radius': 0.12}, 'sphere': {'radius': 0.35}})
        view.setBackgroundColor('0xeeeeee')
        
        # 添加原子标签
        conf = mol.GetConformer()
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            view.addLabel(f"{i+1}", {
                'position': {'x': pos.x + 0.2, 'y': pos.y + 0.2, 'z': pos.z + 0.2},
                'fontColor': 'black',
                'backgroundColor': 'transparent',
                'fontSize': 12
            })
        
        view.zoomTo()
        # 返回HTML字符串
        return view._repr_html_()
    except Exception as e:
        print(f"3D显示失败: {e}")
        return f"<p>3D显示失败: {e}</p>"


def view_optimized_structure_elegant(results: dict, name: str = "Structure"):
    """显示优化后的结构"""
    if not HAS_PY3DMOL:
        return None
    
    geometry = results.get('geometry')
    if not geometry:
        return None
    
    try:
        xyz_content = f"{len(geometry)}\n\n"
        for atom in geometry:
            xyz_content += f"{atom['element']} {atom['x']:.6f} {atom['y']:.6f} {atom['z']:.6f}\n"
        
        view = py3Dmol.view(width=600, height=400)
        view.addModel(xyz_content, "xyz")
        view.setStyle({'stick': {'radius': 0.12}, 'sphere': {'radius': 0.35}})
        view.setBackgroundColor('0xeeeeee')
        
        for i, atom in enumerate(geometry):
            view.addLabel(f"{atom['atom_num']}", {
                'position': {'x': atom['x'] + 0.2, 'y': atom['y'] + 0.2, 'z': atom['z'] + 0.2},
                'fontColor': 'black',
                'backgroundColor': 'transparent',
                'fontSize': 12
            })
        
        view.zoomTo()
        print(f"📊 {name}")
        return view
    except:
        return None


# =============================================================================
# 实时绘图
# =============================================================================

class RealtimePlotter:
    """实时能量曲线绘图"""
    
    def __init__(self, title: str = "PES Scan"):
        self.distances = []
        self.energies = []
        self.title = title
        self.fig = None
        self.ax = None
        self.line = None
        self.highlight = None
    
    def initialize(self):
        self.fig, self.ax = plt.subplots(figsize=(10, 5))
        self.line, = self.ax.plot([], [], 'bo-', lw=2, ms=8)
        self.highlight, = self.ax.plot([], [], 'r*', ms=20)
        self.ax.set_xlabel('C-X Distance (Å)')
        self.ax.set_ylabel('Relative Energy (kcal/mol)')
        self.ax.set_title(self.title)
        self.ax.grid(True, alpha=0.3)
        self.ax.invert_xaxis()
        plt.tight_layout()
        display(self.fig)
    
    def update(self, dist: float, energy: float, highlight_idx: int = None):
        self.distances.append(dist)
        self.energies.append(energy)
        
        min_e = min(self.energies)
        rel = [(e - min_e) * 627.5 for e in self.energies]
        
        self.line.set_data(self.distances, rel)
        
        hi = highlight_idx if highlight_idx is not None else rel.index(max(rel))
        self.highlight.set_data([self.distances[hi]], [rel[hi]])
        
        self.ax.relim()
        self.ax.autoscale_view()
        clear_output(wait=True)
        display(self.fig)
    
    def finalize(self, ts_idx: int = None):
        if ts_idx is not None and 0 <= ts_idx < len(self.distances):
            min_e = min(self.energies)
            rel = [(e - min_e) * 627.5 for e in self.energies]
            self.ax.annotate(
                f'TS Guess\n({self.distances[ts_idx]:.2f}Å)',
                xy=(self.distances[ts_idx], rel[ts_idx]),
                xytext=(self.distances[ts_idx] + 0.15, rel[ts_idx] + 1.5),
                fontsize=10,
                arrowprops=dict(arrowstyle='->', color='red')
            )
        clear_output(wait=True)
        display(self.fig)


# =============================================================================
# 扫描结果管理
# =============================================================================

class ScanManager:
    """扫描结果管理器"""
    
    def __init__(self, work_dir: str, config: TSConfig):
        self.work_dir = work_dir
        self.config = config
        self.scan_history = []
        self.ts_guess_idx = None
        self.complex_mol = None
        self.scan_pair = None
    
    def add_result(self, step: int, distance: float, energy: float, 
                   geometry: list, mol):
        """添加扫描结果"""
        self.scan_history.append({
            'step': step,
            'distance': distance,
            'energy': energy,
            'geometry': geometry,
            'mol': copy.deepcopy(mol)
        })
    
    def get_ts_guess(self) -> int:
        """获取TS猜测索引"""
        if not self.scan_history:
            return -1
        
        energies = [h['energy'] for h in self.scan_history]
        return energies.index(max(energies))
    
    def print_summary(self):
        """打印扫描结果汇总"""
        if not self.scan_history:
            print("无扫描数据")
            return
        
        energies = [h['energy'] for h in self.scan_history]
        min_e = min(energies)
        
        print("=" * 60)
        print(f"{'步骤':^6} {'距离(Å)':^10} {'能量(Ha)':^16} {'相对能量(kcal/mol)':^20}")
        print("-" * 60)
        
        for h in self.scan_history:
            rel_e = (h['energy'] - min_e) * 627.5
            marker = " ⭐" if h['step'] - 1 == self.ts_guess_idx else ""
            print(f"{h['step']:^6} {h['distance']:^10.3f} {h['energy']:^16.6f} {rel_e:^20.2f}{marker}")
        
        print("-" * 60)
    
    def plot_energy_curve(self, save_path: str = None):
        """绘制能量曲线"""
        if not self.scan_history:
            return
        
        dists = [h['distance'] for h in self.scan_history]
        min_e = min(h['energy'] for h in self.scan_history)
        rel_e = [(h['energy'] - min_e) * 627.5 for h in self.scan_history]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(dists, rel_e, 'bo-', lw=2, ms=8)
        
        if self.ts_guess_idx is not None:
            ax.plot(dists[self.ts_guess_idx], rel_e[self.ts_guess_idx], 
                   'r*', ms=20, label=f'TS (Step {self.ts_guess_idx + 1})')
        
        ax.set_xlabel('C-X Distance (Å)', fontsize=12)
        ax.set_ylabel('Relative Energy (kcal/mol)', fontsize=12)
        ax.set_title(f'PES Scan: {self.config.aromatic_name} + {self.config.halogen_preset}')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.invert_xaxis()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
        plt.show()
    
    def save_results(self, filename: str = "scan_results.json"):
        """保存结果到JSON"""
        data = {
            'config': {
                'aromatic': self.config.aromatic_name,
                'halogen': self.config.halogen_preset,
                'scheme': self.config.scheme_name,
                'solvent': self.config.solvent,
            },
            'scan_results': [
                {'step': h['step'], 'distance': h['distance'], 'energy': h['energy']}
                for h in self.scan_history
            ],
            'ts_guess_step': self.ts_guess_idx + 1 if self.ts_guess_idx is not None else None
        }
        
        path = os.path.join(self.work_dir, filename)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ 结果已保存: {path}")
        return path
    
    def load_results(self, filename: str = "scan_results.json") -> bool:
        """从JSON加载结果"""
        path = os.path.join(self.work_dir, filename)
        if not os.path.exists(path):
            return False
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        # 重建历史记录 (不含mol对象)
        self.scan_history = []
        for r in data.get('scan_results', []):
            self.scan_history.append({
                'step': r['step'],
                'distance': r['distance'],
                'energy': r['energy'],
                'geometry': None,
                'mol': None
            })
        
        if data.get('ts_guess_step'):
            self.ts_guess_idx = data['ts_guess_step'] - 1
        
        print(f"✅ 已加载 {len(self.scan_history)} 步扫描结果")
        return True


# =============================================================================
# 主扫描函数
# =============================================================================

def run_smart_scan(config: TSConfig, manager: ScanManager) -> bool:
    """
    执行智能势能面扫描
    
    Args:
        config: 配置对象
        manager: 扫描管理器
    
    Returns:
        是否成功完成
    """
    halogen = HALOGEN_PRESETS[config.halogen_preset]
    scheme = CALCULATION_SCHEMES[config.scheme_name]
    
    print("=" * 60)
    print("🔬 开始智能势能面扫描")
    print("=" * 60)
    
    # 生成初始结构
    if manager.complex_mol is None:
        manager.complex_mol = generate_endon_complex(
            config.aromatic_smiles, halogen.smiles,
            config.ipso_carbon_index - 1,
            config.c_x_initial_distance,
            config.c_x_x_angle,
            halogen.xx_bond_length,
            config.enable_symmetry_breaking
        )
    
    if manager.complex_mol is None:
        print("❌ 结构生成失败")
        return False
    
    # 自动检测扫描坐标
    if manager.scan_pair is None:
        conf = manager.complex_mol.GetConformer()
        c_idx = [a.GetIdx() for a in manager.complex_mol.GetAtoms() if a.GetSymbol() == 'C']
        x_idx = [a.GetIdx() for a in manager.complex_mol.GetAtoms() if a.GetSymbol() == halogen.symbol]
        
        min_d = float('inf')
        for ci in c_idx:
            for xi in x_idx:
                d = conf.GetAtomPosition(ci).Distance(conf.GetAtomPosition(xi))
                if d < min_d:
                    min_d = d
                    manager.scan_pair = (ci + 1, xi + 1)
        
        print(f"📍 扫描坐标: C{manager.scan_pair[0]} - {halogen.symbol}{manager.scan_pair[1]}")
    
    # 生成扫描距离
    scan_distances = generate_scan_distances(config)
    print(f"📊 扫描范围: {config.scan_start}Å → {config.scan_end}Å ({len(scan_distances)}步)")
    
    # 构建方法字符串
    method_basis = f"{scheme['method']}/{scheme['basis']}" if scheme['basis'] else scheme['method']
    
    current_mol = copy.deepcopy(manager.complex_mol)
    prev_chk = None
    highest_e, highest_idx = -float('inf'), -1
    e_threshold = config.energy_drop_threshold / 627.5
    
    # 实时绘图
    plotter = None
    if config.realtime_plot:
        plotter = RealtimePlotter(f"PES Scan: {config.aromatic_name} + {halogen.name}")
        plotter.initialize()
    
    for step, target_dist in enumerate(scan_distances):
        print(f"\n--- 步骤 {step+1}/{len(scan_distances)} (d={target_dist:.2f}Å) ---")
        sys.stdout.flush()
        
        # 调整几何结构
        current_mol = set_fragment_distance(current_mol, manager.scan_pair[0], manager.scan_pair[1], target_dist)
        
        # 文件路径
        step_name = f"{config.aromatic_name}_{halogen.name}_scan_d{target_dist:.2f}"
        step_gjf = os.path.join(manager.work_dir, f"{step_name}.gjf")
        step_log = os.path.join(manager.work_dir, f"{step_name}.log")
        step_chk = os.path.join(manager.work_dir, f"{step_name}.chk")
        
        # 断点续算检查
        step_done = False
        res = None
        if os.path.exists(step_log):
            res = read_scan_output_robust(step_log)
            if res:
                print(f"✅ 已完成，读取结果")
                step_done = True
        
        if not step_done:
            # 寻找checkpoint
            use_guess = False
            if prev_chk and os.path.exists(prev_chk):
                try:
                    shutil.copy2(prev_chk, step_chk)
                    use_guess = True
                    print("   (继承上一步checkpoint)")
                except:
                    pass
            elif step > 0:
                found_chk = find_best_checkpoint(manager.work_dir, target_dist, halogen.symbol)
                if found_chk:
                    try:
                        shutil.copy2(found_chk, step_chk)
                        use_guess = True
                    except:
                        pass
            
            # 构建方法
            opt_cmd = "ModRedundant"
            if config.scan_opt_mode == "CalcFC":
                opt_cmd += ",CalcFC" if step == 0 else (",ReadFC" if use_guess else "")
            elif config.scan_opt_mode == "CalcAll":
                opt_cmd += ",CalcAll"
            
            scan_method = f"# {method_basis} opt({opt_cmd}) nosymm"
            if scheme['disp']:
                scan_method += f" {scheme['disp']}"
            if config.solvent:
                scan_method += f" SCRF=({config.solvent_model},Solvent={config.solvent})"
            if use_guess:
                scan_method += " Guess=Read"
            
            # 生成输入文件
            scan_constraint = f"{manager.scan_pair[0]} {manager.scan_pair[1]} F"
            create_scan_input(current_mol, step_gjf, scan_constraint, scan_method,
                            config.nproc, config.memory, step_chk)
            
            # 运行
            success = run_gaussian_job(step_gjf, run_dir=manager.work_dir)
            if not success:
                print(f"❌ 步骤 {step+1} 失败")
                break
            
            res = read_scan_output_robust(step_log)
        
        if not res:
            print(f"⚠️ 无法读取步骤 {step+1} 结果")
            break
        
        # 处理结果
        last = res[-1]
        energy = last['energy']
        current_mol = update_mol_coordinates(current_mol, {'geometry': last['geometry']})
        
        manager.add_result(step + 1, target_dist, energy, last['geometry'], current_mol)
        
        if manager.scan_history:
            rel_e = (energy - manager.scan_history[0]['energy']) * 627.5
            print(f"能量: {energy:.6f} Ha ({rel_e:+.2f} kcal/mol)")
        
        prev_chk = step_chk
        
        # 实时更新图
        if plotter:
            plotter.update(target_dist, energy, highest_idx if highest_idx >= 0 else None)
        
        # TS检测
        if energy > highest_e:
            highest_e, highest_idx = energy, step
        
        if config.auto_stop_at_ts and highest_idx >= 0 and highest_idx < step:
            drop = highest_e - energy
            if drop > e_threshold:
                print(f"\n🎯 检测到能量下降 {drop*627.5:.2f} kcal/mol > 阈值")
                print(f"   最高点: 步骤 {highest_idx+1} ({scan_distances[highest_idx]:.2f}Å)")
                manager.ts_guess_idx = highest_idx
                break
    
    # 结果处理
    if manager.scan_history:
        if manager.ts_guess_idx is None:
            manager.ts_guess_idx = manager.get_ts_guess()
        
        if plotter:
            plotter.finalize(manager.ts_guess_idx)
        
        print(f"\n✅ 扫描完成! TS猜测: 步骤 {manager.ts_guess_idx+1}")
        return True
    
    return False


def run_ts_optimization(config: TSConfig, manager: ScanManager, 
                        selected_step: int = None) -> Optional[dict]:
    """
    执行TS优化
    
    Args:
        config: 配置
        manager: 扫描管理器
        selected_step: 选择的步骤 (1-based), None表示使用自动检测
    
    Returns:
        优化结果字典
    """
    if not manager.scan_history:
        print("❌ 无扫描历史")
        return None
    
    # 确定选择的步骤
    if selected_step is not None:
        if 1 <= selected_step <= len(manager.scan_history):
            idx = selected_step - 1
        else:
            print(f"⚠️ 步骤 {selected_step} 超出范围，使用自动选择")
            idx = manager.ts_guess_idx
    else:
        idx = manager.ts_guess_idx
    
    print(f"使用步骤 {idx+1} (d={manager.scan_history[idx]['distance']:.2f}Å) 进行TS优化")
    
    halogen = HALOGEN_PRESETS[config.halogen_preset]
    scheme = CALCULATION_SCHEMES[config.scheme_name]
    selected_mol = manager.scan_history[idx]['mol']
    
    ts_filename = f"{config.aromatic_name}_{halogen.name}_TS"
    ts_gjf = os.path.join(manager.work_dir, f"{ts_filename}.gjf")
    ts_log = os.path.join(manager.work_dir, f"{ts_filename}.log")
    ts_chk = os.path.join(manager.work_dir, f"{ts_filename}.chk")
    
    # 检查是否已完成
    if os.path.exists(ts_log):
        ts_results = read_gaussian16_output_opt(ts_log)
        if ts_results and ts_results.get('converged'):
            print("✅ TS优化已完成，加载结果")
            return ts_results
    
    # 尝试复制checkpoint
    src_chk = os.path.join(manager.work_dir, 
                          f"{config.aromatic_name}_{halogen.name}_scan_d{manager.scan_history[idx]['distance']:.2f}.chk")
    use_guess = False
    if os.path.exists(src_chk):
        try:
            shutil.copy2(src_chk, ts_chk)
            use_guess = True
            print("   (继承扫描checkpoint)")
        except:
            pass
    
    # 构建TS优化方法
    method_basis = f"{scheme['method']}/{scheme['basis']}" if scheme['basis'] else scheme['method']
    ts_method = f"# {method_basis} opt=(TS,CalcFC,NoEigen) nosymm"
    
    if config.enable_freq_analysis:
        ts_method += " Freq"
    
    if scheme['disp']:
        ts_method += f" {scheme['disp']}"
    if config.solvent:
        ts_method += f" SCRF=({config.solvent_model},Solvent={config.solvent})"
    if use_guess:
        ts_method += " Guess=Read"
    
    print(f"方法: {ts_method}")
    
    # 生成输入文件
    create_gaussian_input(selected_mol, ts_gjf, ts_method, "TS Optimization",
                         config.nproc, config.memory, ts_chk)
    
    print("正在运行TS优化...")
    success = run_gaussian_job(ts_gjf, run_dir=manager.work_dir)
    
    if success:
        ts_results = read_gaussian16_output_opt(ts_log)
        
        if ts_results:
            print("\n" + "-" * 40)
            print_gaussian_results(ts_results)
            
            # 检查虚频
            if config.enable_freq_analysis and ts_results.get('frequencies'):
                cat, desc, details = analyze_frequencies(
                    ts_results['frequencies'], 
                    config.imaginary_freq_threshold
                )
                print(f"\n频率分析: {desc}")
        
        return ts_results
    else:
        print("❌ TS优化失败")
        return None


# =============================================================================
# 便捷函数
# =============================================================================

def quick_view_history(work_dir: str) -> Optional[ScanManager]:
    """快速查看已有的扫描历史"""
    config = TSConfig()
    manager = ScanManager(work_dir, config)
    
    if manager.load_results():
        manager.print_summary()
        manager.plot_energy_curve()
        return manager
    else:
        print(f"未找到扫描结果: {work_dir}")
        return None


def list_available_runs(base_dir: str = "out") -> list:
    """列出所有可用的运行目录"""
    runs = []
    if os.path.exists(base_dir):
        for d in os.listdir(base_dir):
            path = os.path.join(base_dir, d)
            if os.path.isdir(path):
                json_file = os.path.join(path, "scan_results.json")
                if os.path.exists(json_file):
                    runs.append(d)
    return runs


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
    displacements = parse_vibration_displacement(log_file)
    if displacements is None:
        return None, "无法解析虚频位移向量"
    
    # 应用位移
    # 这里需要实现位移应用的逻辑
    return None, "功能开发中"


def create_mol_from_geometry(geometry):
    """
    从几何结构数据创建RDKit分子对象
    
    参数:
    geometry: 记录结构数据
    
    返回:
    RDKit分子对象
    """
    try:
        # 创建空的分子对象
        mol = Chem.RWMol()
        
        # 添加原子
        for atom_data in geometry:
            element = atom_data['element']
            # 将元素符号转换为原子类型
            element_to_atomic_num = {
                'H': 1, 'C': 6, 'N': 7, 'O': 8, 'F': 9,
                'P': 15, 'S': 16, 'Cl': 17, 'Br': 35, 'I': 53
            }
            atomic_num = element_to_atomic_num.get(element, 6)  # 默认使用碳
            
            new_atom = Chem.Atom(atomic_num)
            mol.AddAtom(new_atom)
        
        # 转换为完整的分子对象
        mol = mol.GetMol()
        
        # 创建构象并设置坐标
        conf = Chem.Conformer(len(geometry))
        for i, atom_data in enumerate(geometry):
            conf.SetAtomPosition(i, (atom_data['x'], atom_data['y'], atom_data['z']))
        
        mol.AddConformer(conf)
        
        return mol
        
    except Exception as e:
        print(f"从几何结构创建分子时出错: {e}")
        return None


def view_3d_structure(mol, name: str = "Structure"):
    """显示分子3D结构，返回HTML字符串"""
    if not HAS_PY3DMOL:
        print("py3Dmol未安装，跳过3D显示")
        return "<p>py3Dmol未安装，无法显示3D结构</p>"
    
    try:
        # 确保分子有构象
        if mol.GetNumConformers() == 0:
            # 添加氢并生成3D构象
            mol = Chem.AddHs(mol)
            success = AllChem.EmbedMolecule(mol, randomSeed=42)
            if success == -1:
                # 如果嵌入失败，使用距离几何
                AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol)
        
        mb = Chem.MolToMolBlock(mol)
        if not mb:
            return "<p>无法生成分子结构数据</p>"
            
        # 创建完整的HTML页面用于iframe
        safe_name = name.replace(' ', '_').replace('-', '_')
        html_page = f"""<!DOCTYPE html>
<html>
<head>
    <title>3D分子结构 - {name}</title>
    <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        #viewer {{ width: 100%; height: 500px; border: 1px solid #ccc; }}
        .controls {{ margin: 10px 0; }}
    </style>
</head>
<body>
    <h2>3D分子结构预览 - {name}</h2>
    <div class="controls">
        <p><strong>操作说明：</strong></p>
        <ul>
            <li>鼠标左键拖拽：旋转分子</li>
            <li>鼠标滚轮：缩放</li>
            <li>鼠标右键拖拽：平移</li>
        </ul>
    </div>
    <div id="viewer"></div>
    
    <script>
        $(document).ready(function() {{
            try {{
                var viewer = $3Dmol.createViewer($("#viewer"));
                viewer.addModel(`{mb}`, "mol");
                viewer.setStyle({{'stick': {{'radius': 0.12}}, 'sphere': {{'radius': 0.35}}}});
                viewer.setBackgroundColor('0xeeeeee');
                
                // 添加原子标签
                var model = viewer.getModel();
                var atoms = model.atoms;  // 获取所有原子
                for (var i = 0; i < Math.min(atoms.length, 20); i++) {{
                    var atom = atoms[i];
                    viewer.addLabel((i+1).toString(), {{
                        position: {{x: atom.x + 0.3, y: atom.y + 0.3, z: atom.z + 0.3}},  // 稍微偏移避免重叠
                        fontColor: 'white',
                        backgroundColor: 'rgba(0, 0, 0, 0.7)',
                        fontSize: 12,
                        font: 'Arial, sans-serif',
                        showBackground: true
                    }});
                }}
                
                viewer.zoomTo();
                viewer.render();
                
                console.log('3D viewer initialized successfully');
            }} catch (e) {{
                console.error('Error initializing 3D viewer:', e);
                document.getElementById('viewer').innerHTML = '<p style="color: red;">3D显示初始化失败: ' + e.message + '</p>';
            }}
        }});
    </script>
</body>
</html>"""
        
        # 将HTML页面保存为临时文件
        import tempfile
        import base64
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_page)
            temp_file_path = f.name
        
        # 返回iframe和下载链接
        iframe_html = f"""
<div style="border: 1px solid #ccc; padding: 10px; margin: 10px 0; background: #f9f9f9;">
    <p><strong>3D分子结构预览 - {name}</strong></p>
    <p>如果下方没有显示3D结构，请点击下方链接在新窗口中查看：</p>
    <iframe src="data:text/html;base64,{base64.b64encode(html_page.encode()).decode()}" 
            width="100%" height="500" style="border: 1px solid #ddd;">
        <p>您的浏览器不支持iframe，请<a href="data:text/html;base64,{base64.b64encode(html_page.encode()).decode()}" target="_blank">点击这里</a>在新窗口中查看3D结构。</p>
    </iframe>
    <br>
    <a href="data:text/html;base64,{base64.b64encode(html_page.encode()).decode()}" target="_blank" style="color: blue; text-decoration: underline;">
        🔗 在新窗口中打开3D结构
    </a>
</div>
"""
        
        return iframe_html
        
    except Exception as e:
        print(f"3D显示失败: {e}")
        return f"<p>3D显示失败: {e}</p>"


def refine_scan_peak(scan_history, peak_idx, scan_pair, work_dir, base_name, 
                     method_template, nproc, mem, max_refine_steps=3):
    """
    对扫描峰值进行精细化扫描 (简化版：取能量最高的3个点，进行二分法扫描)。
    
    逻辑：
    1. 找到当前能量最高的3个点
    2. 在相邻的最高能量点之间各扫描一个中间点
    3. 如果发现新的更高能量点，停止
    4. 否则重复这个过程
    
    参数:
    - scan_history: 历史扫描记录列表 [{'energy':..., 'mol':..., 'geometry':...}]
    - peak_idx: 当前峰值在 history 中的索引 (已弃用，函数会自动找到最高能量点)
    - scan_pair: (atom1_idx, atom2_idx) 1-based
    - method_template: Gaussian 方法字符串模板 (不含 opt 部分)
    - max_refine_steps: 最大细分次数
    
    返回: (new_peak_mol, new_peak_energy, updated_history)
    """
    import copy
    
    # 输入验证
    if not scan_history or not isinstance(scan_history, list) or len(scan_history) < 2:
        print("   错误: scan_history 无效或点数不足")
        return None, None, None
    
    current_history = copy.deepcopy(scan_history)
    
    print(f"\n🔎 开始精细化扫描 (简化版)...")
    print(f"   初始历史点数: {len(current_history)}")
    
    for step in range(max_refine_steps):
        print(f"   --- 细分轮次 {step+1}/{max_refine_steps} ---")
        
        # 1. 按能量排序，找到最高的3个点
        sorted_by_energy = sorted(current_history, key=lambda x: x['energy'], reverse=True)
        top_3_points = sorted_by_energy[:3]  # 能量最高的3个点
        
        energies_str = [f"{p['energy']:.6f}" for p in top_3_points]
        print(f"   当前最高3个点的能量: {energies_str}")
        
        # 2. 在这3个点之间进行二分法扫描
        new_points_to_scan = []
        
        # 对相邻的点进行二分
        for i in range(len(top_3_points) - 1):
            point1 = top_3_points[i]
            point2 = top_3_points[i + 1]
            
            dist1 = get_atom_distance(point1['mol'], scan_pair[0], scan_pair[1])
            dist2 = get_atom_distance(point2['mol'], scan_pair[0], scan_pair[1])
            
            # 计算中间距离
            mid_dist = (dist1 + dist2) / 2.0
            
            # 检查是否已经扫描过这个距离
            is_scanned = False
            for h in current_history:
                d = get_atom_distance(h['mol'], scan_pair[0], scan_pair[1])
                if abs(d - mid_dist) < 0.001:
                    is_scanned = True
                    break
            
            if not is_scanned:
                new_points_to_scan.append({
                    'distance': mid_dist,
                    'base_mol': point1['mol'],  # 使用能量更高的点作为基准
                    'desc': f"二分点 {i+1}-{i+2}"
                })
                print(f"   计划扫描: {mid_dist:.4f} Å ({point1['energy']:.6f} 和 {point2['energy']:.6f} 之间)")
        
        if not new_points_to_scan:
            print("   没有新的点需要扫描，已收敛。")
            break
        
        # 3. 执行扫描
        any_new_max = False
        max_energy_before = max(h['energy'] for h in current_history)
        
        for point_info in new_points_to_scan:
            target_dist = point_info['distance']
            base_mol = point_info['base_mol']
            desc = point_info['desc']
            
            # 准备分子
            mol_to_run = copy.deepcopy(base_mol)
            mol_to_run = set_fragment_distance(mol_to_run, scan_pair[0], scan_pair[1], target_dist)
            
            # 准备文件名
            refine_name = f"{base_name}_refine_{step}_{int(target_dist*100)}"
            gjf_file = os.path.join(work_dir, f"{refine_name}.gjf")
            log_file = os.path.join(work_dir, f"{refine_name}.log")
            
            # 构建输入
            scan_lines = [f"{scan_pair[0]} {scan_pair[1]} F"]
            if "opt" not in method_template.lower():
                run_method = f"{method_template} opt(ModRedundant) nosymm"
            else:
                run_method = method_template
            
            # 生成文件
            with open(gjf_file, 'w') as f:
                f.write(f"%nproc={nproc}\n")
                f.write(f"%mem={mem}\n")
                f.write(f"{run_method}\n\n")
                f.write(f"Refine Scan {target_dist}\n\n")
                f.write("0 1\n")
                
                conf = mol_to_run.GetConformer()
                for i in range(mol_to_run.GetNumAtoms()):
                    pos = conf.GetAtomPosition(i)
                    sym = mol_to_run.GetAtomWithIdx(i).GetSymbol()
                    f.write(f"{sym:2s} {pos.x:14.8f} {pos.y:14.8f} {pos.z:14.8f}\n")
                f.write("\n")
                for line in scan_lines:
                    f.write(f"{line}\n")
                f.write("\n")
            
            # 运行
            print(f"   正在计算 {desc}: 距离 {target_dist:.4f} Å ...")
            success = run_gaussian_job(gjf_file, run_dir=work_dir)
            
            if success:
                # 读取结果
                res = read_gaussian16_output_opt(log_file)
                if res and 'energy' in res:
                    e = res['energy']
                    print(f"     -> 能量: {e:.6f}")
                    
                    # 更新分子几何
                    mol_res = update_mol_coordinates(mol_to_run, res)
                    
                    # 添加到历史
                    new_entry = {
                        'energy': e,
                        'geometry': res['geometry'],
                        'mol': mol_res,
                        'step': -1  # 标记为精细化步骤
                    }
                    current_history.append(new_entry)
                    
                    if e > max_energy_before:
                        print("     ✨ 发现新的更高能量点！")
                        any_new_max = True
                else:
                    print("     读取结果失败。")
            else:
                print("     计算失败。")
        
        if not any_new_max:
            print("   本轮未发现更高能量点，精细化结束。")
            break
    
    # 返回最终的最高能量点
    if current_history:
        best_entry = max(current_history, key=lambda x: x['energy'])
        return best_entry['mol'], best_entry['energy'], current_history
    else:
        return None, None, None


if __name__ == "__main__":
    print("✅ ts_search_lib 加载完成")
    print(f"   卤素预设: {list(HALOGEN_PRESETS.keys())}")
    print(f"   计算方案: {list(CALCULATION_SCHEMES.keys())}")
