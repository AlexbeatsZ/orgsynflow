from __future__ import annotations

import heapq
import json
import math
import shutil
import subprocess
import threading
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.xtb_adapter import run_xtb_job
from adapters.goodvibes_adapter import run_goodvibes
from core.gaussian import GaussianResult, parse_gaussian_log, parse_gaussian_log_progress
from core.gaussian_runner import find_gaussian_executable, run_gaussian_job
from core.kinetics import HARTREE_TO_KJ_MOL, eyring_rate_constant
from core.reaction_mapping import map_reaction


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "data" / "ts-workflows"
ACTIVE_STATES = {"preparing", "queued", "scanning", "refining", "ts_optimizing", "irc", "thermochemistry"}
DEFAULT_CONFIG: dict[str, Any] = {
    "method": "wB97XD",
    "basis": "def2SVP",
    "solvent": None,
    "charge": 0,
    "multiplicity": 1,
    "nproc": 4,
    "memory": "4GB",
    "temperature_k": 298.15,
    "imaginary_threshold_cm1": -50.0,
    "mode_overlap_threshold": 0.15,
    "max_grid_points": 40,
    "max_retries": 2,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TsWorkflowManager:
    def __init__(self, root: Path = WORKFLOW_ROOT) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._pause_events: dict[str, threading.Event] = {}

    def create(
        self,
        reaction_smiles: str,
        workspace_id: str | None = None,
        cell_id: str | None = None,
        reaction_id: str | None = None,
        included_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        workflow_id = f"ts-{uuid.uuid4().hex[:12]}"
        workflow = {
            "workflow_id": workflow_id,
            "workspace_id": workspace_id,
            "cell_id": cell_id,
            "reaction_id": reaction_id,
            "reaction_smiles": reaction_smiles,
            "included_agents": included_agents or [],
            "status": "preparing",
            "stage": "preparing",
            "validation_level": "未验证",
            "created_at": _now(),
            "updated_at": _now(),
            "mapping": None,
            "coordinates": [],
            "candidates": [],
            "grid_points": [],
            "ts_candidates": [],
            "validation": {"level": "未验证", "warnings": []},
            "thermochemistry": None,
            "config": deepcopy(DEFAULT_CONFIG),
            "error": None,
            "warnings": [],
        }
        self._save(workflow)
        self._spawn(workflow_id, self._prepare)
        return workflow

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        path = self._manifest_path(workflow_id)
        if not path.exists():
            return None
        return self._with_log_progress(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[dict[str, Any]]:
        workflows = [json.loads(path.read_text(encoding="utf-8")) for path in self.root.glob("*/manifest.json")]
        return sorted(workflows, key=lambda item: item.get("created_at", ""), reverse=True)

    def confirm(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        workflow = self._require(workflow_id)
        if workflow["status"] not in {"awaiting_confirmation", "paused", "partial", "failed"}:
            raise ValueError(f"当前状态不能启动：{workflow['status']}")
        coordinates = payload.get("coordinates") or workflow.get("coordinates") or []
        if not 1 <= len(coordinates) <= 2:
            raise ValueError("TS 工作流需要确认一到两个反应坐标。")
        selected_candidate_id = (
            payload.get("selected_candidate_id")
            or payload.get("candidate_id")
            or workflow.get("selected_candidate_id")
            or workflow.get("candidates", [{}])[0].get("candidate_id")
        )
        if not any(item.get("candidate_id") == selected_candidate_id for item in workflow.get("candidates", [])):
            raise ValueError("未找到选中的初始构象。")
        if workflow["status"] != "awaiting_confirmation":
            workflow["grid_points"] = []
            workflow["ts_candidates"] = []
            workflow["ts_results"] = []
            workflow["irc"] = None
            workflow["thermochemistry"] = None
            workflow["validation"] = {"level": "未验证", "warnings": ["参数已修改，旧计算阶段未复用。"]}
        workflow["coordinates"] = coordinates
        workflow["selected_candidate_id"] = selected_candidate_id
        workflow["config"] = {**DEFAULT_CONFIG, **workflow.get("config", {}), **(payload.get("config") or {})}
        workflow["status"] = "queued"
        workflow["stage"] = "queued"
        workflow["error"] = None
        workflow["updated_at"] = _now()
        self._save(workflow)
        self._cancel_events[workflow_id] = threading.Event()
        self._spawn(workflow_id, self._execute)
        return self._with_log_progress(workflow)

    def pause(self, workflow_id: str) -> dict[str, Any]:
        workflow = self._require(workflow_id)
        self._pause_events.setdefault(workflow_id, threading.Event()).set()
        workflow["pause_requested"] = True
        workflow["updated_at"] = _now()
        self._save(workflow)
        return self._with_log_progress(workflow)

    def resume(self, workflow_id: str) -> dict[str, Any]:
        workflow = self._require(workflow_id)
        if workflow["status"] not in {"paused", "failed", "partial"}:
            raise ValueError(f"当前状态不能续算：{workflow['status']}")
        workflow["pause_requested"] = False
        workflow["status"] = "queued"
        workflow["error"] = None
        workflow["updated_at"] = _now()
        self._save(workflow)
        self._cancel_events[workflow_id] = threading.Event()
        self._pause_events.setdefault(workflow_id, threading.Event()).clear()
        self._spawn(workflow_id, self._execute)
        return self._with_log_progress(workflow)

    def retry(self, workflow_id: str) -> dict[str, Any]:
        return self.resume(workflow_id)

    def cancel(self, workflow_id: str) -> dict[str, Any]:
        event = self._cancel_events.setdefault(workflow_id, threading.Event())
        event.set()
        workflow = self._require(workflow_id)
        workflow["status"] = "cancelled"
        workflow["stage"] = "cancelled"
        workflow["updated_at"] = _now()
        self._save(workflow)
        _terminate_workflow_gaussian_processes(self._workflow_dir(workflow_id), self.root)
        return self._with_log_progress(workflow)

    def _with_log_progress(self, workflow: dict[str, Any]) -> dict[str, Any]:
        progress = _latest_workflow_log_progress(self._workflow_dir(str(workflow.get("workflow_id") or "")))
        if not progress:
            return workflow
        return {**workflow, "gaussian_progress": progress}

    def export(self, workflow_id: str) -> Path:
        workflow = self._require(workflow_id)
        workflow_dir = self._workflow_dir(workflow_id)
        archive = workflow_dir / f"{workflow_id}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for path in workflow_dir.rglob("*"):
                if path.is_file() and path != archive:
                    handle.write(path, path.relative_to(workflow_dir))
            handle.writestr("summary.json", json.dumps(_public_workflow(workflow), ensure_ascii=False, indent=2))
        return archive

    def recover(self) -> None:
        for workflow in self.list():
            if workflow.get("status") in ACTIVE_STATES:
                workflow.setdefault("warnings", []).append("后端重启中断了活动作业；已保留正常结束的子作业。")
                workflow["updated_at"] = _now()
                if workflow.get("status") == "preparing" and workflow.get("reaction_smiles"):
                    self._save(workflow)
                    self._spawn(workflow["workflow_id"], self._prepare)
                elif workflow.get("selected_candidate_id") and workflow.get("coordinates") and workflow.get("candidates"):
                    workflow["status"] = "queued"
                    workflow["stage"] = "queued"
                    self._save(workflow)
                    self._cancel_events[workflow["workflow_id"]] = threading.Event()
                    self._spawn(workflow["workflow_id"], self._execute)
                else:
                    workflow["status"] = "paused"
                    workflow["stage"] = "interrupted"
                    self._save(workflow)

    def _prepare(self, workflow_id: str) -> None:
        try:
            workflow = self._require(workflow_id)
            reaction_smiles = workflow["reaction_smiles"]
            reactants, agents, products = split_reaction_smiles(reaction_smiles)
            mapping = map_reaction(reaction_smiles).as_dict()
            workflow["mapping"] = mapping
            mapped_reaction = mapping.get("mapped_reaction_smiles")
            mapped_reactants = reactants
            mapped_products = products
            if isinstance(mapped_reaction, str) and mapped_reaction:
                mapped_reactants, _, mapped_products = split_reaction_smiles(mapped_reaction)
            changes = extract_mapped_bond_changes(mapped_reactants, mapped_products)
            workflow["coordinates"] = suggest_scan_coordinates(changes)
            confidence_high = mapping.get("confidence") == "高"
            workflow["requires_manual_coordinates"] = not confidence_high or not 1 <= len(changes) <= 2
            if len(changes) > 2:
                workflow["warnings"].append("检测到超过两个键变化；请选择最多两个关键反应坐标。")
            if not confidence_high:
                workflow["warnings"].append("RXNMapper 映射置信度不足，必须人工确认原子对。")
            candidate_smiles = ".".join([reactants, *workflow.get("included_agents", [])]).strip(".")
            reject_transition_metals(candidate_smiles)
            charge, multiplicity, electronic_warning = infer_charge_and_multiplicity(candidate_smiles)
            workflow["config"]["charge"] = charge
            workflow["config"]["multiplicity"] = multiplicity
            if electronic_warning:
                workflow["warnings"].append(electronic_warning)
            candidates = generate_candidate_geometries(candidate_smiles, count=3)
            for candidate in candidates:
                xtb = run_xtb_job(candidate["xyz"], timeout_seconds=60)
                candidate["preoptimization"] = xtb.status
                candidate["preoptimization_source"] = xtb.source
                candidate["energy_hartree"] = xtb.data.get("total_energy_hartree")
                if isinstance(xtb.data.get("optimized_xyz"), str):
                    candidate["xyz"] = xtb.data["optimized_xyz"]
                if xtb.status != "available":
                    candidate["warning"] = "xTB 不可用或失败；保留 RDKit MMFF/UFF 构象。"
            candidates.sort(key=lambda item: (item.get("energy_hartree") is None, item.get("energy_hartree") or 0.0))
            workflow["candidates"] = candidates
            workflow["status"] = "awaiting_confirmation"
            workflow["stage"] = "awaiting_confirmation"
            workflow["updated_at"] = _now()
            self._save(workflow)
        except Exception as exc:
            self._fail(workflow_id, str(exc))

    def _execute(self, workflow_id: str) -> None:
        try:
            workflow = self._require(workflow_id)
            if find_gaussian_executable() is None:
                raise RuntimeError("未检测到 Gaussian，可准备工作流但不能提交正式计算。")
            candidate = next(item for item in workflow["candidates"] if item["candidate_id"] == workflow["selected_candidate_id"])
            config = workflow["config"]
            if not workflow.get("grid_points"):
                workflow["grid_points"] = build_scan_grid(workflow["coordinates"])
            self._set_stage(workflow, "scanning")
            base_xyz = candidate["xyz"]
            consecutive_failures = 0
            for point in workflow["grid_points"]:
                if point.get("status") == "succeeded":
                    if point.get("final_xyz"):
                        base_xyz = point["final_xyz"]
                    continue
                if self._stop_requested(workflow):
                    return
                result = self._run_scan_point(workflow, point, base_xyz)
                if result and point.get("final_xyz"):
                    base_xyz = point["final_xyz"]
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                self._save(workflow)
                if consecutive_failures >= 3:
                    raise RuntimeError("连续三个扫描点在自动修复后仍失败；工作流已停止，避免继续消耗计算资源。")
            successful = [point for point in workflow["grid_points"] if point.get("status") == "succeeded" and point.get("energy_hartree") is not None]
            if len(successful) < max(3, len(workflow["grid_points"]) // 2):
                raise RuntimeError("收敛扫描点不足，无法可靠识别势垒。")
            candidates = rank_saddle_candidates(successful, workflow["coordinates"])
            if not candidates:
                raise RuntimeError("扫描没有在内部网格找到势垒候选；请扩大或移动扫描范围。")
            self._set_stage(workflow, "refining")
            refinement = build_refinement_grid(workflow["coordinates"], candidates[0], workflow["grid_points"])
            for point in refinement:
                if len(workflow["grid_points"]) >= int(config.get("max_grid_points", 40)):
                    break
                if self._stop_requested(workflow):
                    return
                workflow["grid_points"].append(point)
                self._run_scan_point(workflow, point, candidates[0].get("final_xyz") or base_xyz)
                self._save(workflow)
            successful = [point for point in workflow["grid_points"] if point.get("status") == "succeeded" and point.get("energy_hartree") is not None]
            workflow["ts_candidates"] = rank_saddle_candidates(successful, workflow["coordinates"])[:3]
            validated_result: tuple[dict[str, Any], GaussianResult] | None = None
            for ts_candidate in workflow["ts_candidates"]:
                if self._stop_requested(workflow):
                    return
                validated_result = self._run_ts_candidate(workflow, ts_candidate)
                if validated_result and workflow["validation"].get("irc_match"):
                    break
            if validated_result is None:
                workflow["status"] = "partial"
                workflow["stage"] = "frequency_check"
                workflow["updated_at"] = _now()
                self._save(workflow)
                return
            ts_record, ts_parsed = validated_result
            self._set_stage(workflow, "thermochemistry")
            workflow["thermochemistry"] = self._run_thermochemistry(workflow, candidate["xyz"], ts_parsed)
            workflow["status"] = "completed" if workflow["validation"].get("irc_match") else "partial"
            workflow["stage"] = "completed"
            workflow["validation_level"] = workflow["validation"]["level"]
            workflow["updated_at"] = _now()
            self._save(workflow)
        except Exception as exc:
            self._fail(workflow_id, str(exc))

    def _run_scan_point(self, workflow: dict[str, Any], point: dict[str, Any], xyz: str) -> bool:
        config = workflow["config"]
        point["status"] = "running"
        point["started_at"] = _now()
        self._save(workflow)
        constraints = [f"B {coordinate['atom1']} {coordinate['atom2']} {value:.5f} F" for coordinate, value in zip(workflow["coordinates"], point["values"])]
        adjusted_xyz = set_xyz_distances(xyz, workflow["coordinates"], point["values"])
        result = None
        point["attempts"] = []
        work_dir = self._workflow_dir(workflow["workflow_id"]) / "scan" / point["point_id"]
        for attempt in range(int(config.get("max_retries", 2)) + 1):
            route = "opt=(modredundant,calcfc,maxcycles=120)"
            if attempt:
                route += " scf=(xqc,maxcycle=512)"
            attempt_dir = work_dir / f"attempt-{attempt + 1}"
            gjf = build_gaussian_input_from_xyz(adjusted_xyz, route, config, f"OrgSynFlow scan {point['point_id']}", constraints)
            result = run_gaussian_job(gjf, work_dir=attempt_dir, timeout_seconds=7200, cancel_event=self._cancel_events.setdefault(workflow["workflow_id"], threading.Event()))
            point["attempts"].append({"work_dir": str(attempt_dir), "success": result.success, "message": result.message})
            if result.success:
                break
        assert result is not None
        point["finished_at"] = _now()
        point["work_dir"] = str(work_dir)
        point["status"] = "succeeded" if result.success else "failed"
        point["error"] = None if result.success else result.message
        if result.parsed_result:
            point["energy_hartree"] = result.parsed_result.final_energy_hartree
            point["final_xyz"] = result.parsed_result.final_coordinates_xyz
        return result.success

    def _run_ts_candidate(self, workflow: dict[str, Any], candidate: dict[str, Any]) -> tuple[dict[str, Any], GaussianResult] | None:
        self._set_stage(workflow, "ts_optimizing")
        config = workflow["config"]
        xyz = candidate.get("final_xyz")
        if not xyz:
            return None
        record = {"candidate_id": candidate["point_id"], "status": "running", "attempts": []}
        for attempt in range(int(config.get("max_retries", 2)) + 1):
            route = "opt=(ts,calcfc,noeigentest,maxcycles=150) freq"
            if attempt:
                route += " scf=(xqc,maxcycle=512)"
            work_dir = self._workflow_dir(workflow["workflow_id"]) / "ts" / f"{candidate['point_id']}-attempt-{attempt + 1}"
            gjf = build_gaussian_input_from_xyz(xyz, route, config, f"OrgSynFlow TS candidate {candidate['point_id']}")
            result = run_gaussian_job(gjf, work_dir=work_dir, timeout_seconds=14400, cancel_event=self._cancel_events[workflow["workflow_id"]])
            record["attempts"].append({"work_dir": str(work_dir), "log_path": result.log_path, "success": result.success, "message": result.message})
            if not result.success or not result.parsed_result:
                continue
            parsed = result.parsed_result
            significant = [value for value in parsed.frequencies_cm1 if value <= float(config["imaginary_threshold_cm1"])]
            overlap = reaction_mode_overlap(parsed, workflow["coordinates"])
            frequency_ok = len(significant) == 1 and overlap >= float(config["mode_overlap_threshold"])
            workflow["validation"] = {
                "level": "频率合格" if frequency_ok else "TS 收敛",
                "normal_termination": parsed.normal_termination,
                "significant_imaginary_frequencies_cm1": significant,
                "mode_overlap": overlap,
                "frequency_ok": frequency_ok,
                "warnings": [] if frequency_ok else ["虚频数量或振动模式与目标反应坐标不匹配。"],
            }
            record["status"] = "frequency_qualified" if frequency_ok else "rejected"
            record["frequency_result"] = parsed.as_dict()
            workflow.setdefault("ts_results", []).append(record)
            self._save(workflow)
            if not frequency_ok:
                return None
            irc_ok = self._run_irc(workflow, parsed)
            workflow["validation"]["irc_match"] = irc_ok
            workflow["validation"]["level"] = "IRC 验证" if irc_ok else "频率合格"
            return record, parsed
        record["status"] = "failed"
        workflow.setdefault("ts_results", []).append(record)
        self._save(workflow)
        return None

    def _run_irc(self, workflow: dict[str, Any], ts_result: GaussianResult) -> bool:
        self._set_stage(workflow, "irc")
        if not ts_result.final_coordinates_xyz:
            return False
        endpoints: dict[str, Any] = {}
        for direction in ("forward", "reverse"):
            route = f"irc=(calcfc,{direction},maxpoints=30,stepsize=10)"
            work_dir = self._workflow_dir(workflow["workflow_id"]) / "irc" / direction
            gjf = build_gaussian_input_from_xyz(ts_result.final_coordinates_xyz, route, workflow["config"], f"OrgSynFlow IRC {direction}")
            result = run_gaussian_job(gjf, work_dir=work_dir, timeout_seconds=14400, cancel_event=self._cancel_events[workflow["workflow_id"]])
            endpoints[direction] = result.as_dict()
        workflow["irc"] = endpoints
        parsed = [item.get("parsed_result") for item in endpoints.values() if isinstance(item, dict)]
        xyz_values = [item.get("final_coordinates_xyz") for item in parsed if isinstance(item, dict) and item.get("final_coordinates_xyz")]
        return len(xyz_values) == 2 and irc_endpoints_match(xyz_values[0], xyz_values[1], workflow["coordinates"])

    def _run_thermochemistry(self, workflow: dict[str, Any], reactant_xyz: str, ts_result: GaussianResult) -> dict[str, Any]:
        _, _, product_smiles = split_reaction_smiles(workflow["reaction_smiles"])
        product_xyz = generate_candidate_geometries(product_smiles, count=1)[0]["xyz"]
        results: dict[str, GaussianResult] = {"ts": ts_result}
        log_paths: list[str] = []
        ts_records = workflow.get("ts_results") or []
        if ts_records:
            attempts = ts_records[-1].get("attempts") or []
            if attempts and attempts[-1].get("log_path"):
                log_paths.append(attempts[-1]["log_path"])
        for name, xyz in (("reactant", reactant_xyz), ("product", product_xyz)):
            route = "opt=(calcfc,maxcycles=150) freq"
            work_dir = self._workflow_dir(workflow["workflow_id"]) / "thermochemistry" / name
            gjf = build_gaussian_input_from_xyz(xyz, route, workflow["config"], f"OrgSynFlow {name} thermochemistry")
            run = run_gaussian_job(gjf, work_dir=work_dir, timeout_seconds=14400, cancel_event=self._cancel_events[workflow["workflow_id"]])
            if not run.success or not run.parsed_result:
                return {"status": "partial", "error": f"{name} 热化学计算失败。", "standard_state": standard_state(workflow["config"])}
            results[name] = run.parsed_result
            if run.log_path:
                log_paths.append(run.log_path)
        energies = {key: value.final_energy_hartree for key, value in results.items()}
        gibbs = {key: value.gibbs_free_energy_hartree for key, value in results.items()}
        if any(value is None for value in gibbs.values()):
            return {"status": "partial", "energies_hartree": energies, "gibbs_hartree": gibbs, "error": "缺少 Gibbs 自由能。"}
        delta_g_rxn = (float(gibbs["product"]) - float(gibbs["reactant"])) * HARTREE_TO_KJ_MOL
        forward = (float(gibbs["ts"]) - float(gibbs["reactant"])) * HARTREE_TO_KJ_MOL
        reverse = (float(gibbs["ts"]) - float(gibbs["product"])) * HARTREE_TO_KJ_MOL
        temperature = float(workflow["config"].get("temperature_k", 298.15))
        goodvibes = run_goodvibes(log_paths) if len(log_paths) == 3 else None
        method = "GoodVibes + Gaussian thermochemistry" if goodvibes and goodvibes.status == "available" else "Gaussian thermochemistry fallback"
        return {
            "status": "succeeded",
            "energies_hartree": energies,
            "gibbs_hartree": gibbs,
            "delta_g_rxn_kj_mol": round(delta_g_rxn, 3),
            "delta_g_activation_forward_kj_mol": round(forward, 3),
            "delta_g_activation_reverse_kj_mol": round(reverse, 3),
            "eyring_rate_forward_s_inv": eyring_rate_constant(forward, temperature) if forward >= 0 else None,
            "temperature_k": temperature,
            "standard_state": standard_state(workflow["config"]),
            "method": method,
            "goodvibes": goodvibes.as_dict() if goodvibes else None,
        }

    def _set_stage(self, workflow: dict[str, Any], stage: str) -> None:
        workflow["status"] = stage
        workflow["stage"] = stage
        workflow["updated_at"] = _now()
        self._save(workflow)

    def _stop_requested(self, workflow: dict[str, Any]) -> bool:
        latest = self._require(workflow["workflow_id"])
        if latest.get("status") == "cancelled" or self._cancel_events.setdefault(workflow["workflow_id"], threading.Event()).is_set():
            workflow["status"] = "cancelled"
            workflow["stage"] = "cancelled"
            workflow["updated_at"] = _now()
            self._save(workflow)
            return True
        if latest.get("pause_requested") or self._pause_events.setdefault(workflow["workflow_id"], threading.Event()).is_set():
            workflow["status"] = "paused"
            workflow["stage"] = "paused"
            workflow["pause_requested"] = False
            self._pause_events[workflow["workflow_id"]].clear()
            workflow["updated_at"] = _now()
            self._save(workflow)
            return True
        return False

    def _fail(self, workflow_id: str, message: str) -> None:
        workflow = self.get(workflow_id)
        if workflow is None or workflow.get("status") == "cancelled":
            return
        workflow["status"] = "failed"
        workflow["stage"] = "failed"
        workflow["error"] = message
        workflow["updated_at"] = _now()
        self._save(workflow)

    def _spawn(self, workflow_id: str, target: Any) -> None:
        with self._lock:
            current = self._threads.get(workflow_id)
            if current and current.is_alive():
                raise ValueError("工作流已经在运行。")
            thread = threading.Thread(target=target, args=(workflow_id,), daemon=True, name=f"orgsynflow-{workflow_id}")
            self._threads[workflow_id] = thread
            thread.start()

    def _save(self, workflow: dict[str, Any]) -> None:
        with self._lock:
            workflow["updated_at"] = _now()
            directory = self._workflow_dir(workflow["workflow_id"])
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "manifest.json"
            temp = directory / "manifest.json.tmp"
            temp.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(path)

    def _require(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.get(workflow_id)
        if workflow is None:
            raise FileNotFoundError(f"TS workflow not found: {workflow_id}")
        return workflow

    def _workflow_dir(self, workflow_id: str) -> Path:
        if not workflow_id.startswith("ts-") or not workflow_id.replace("-", "").isalnum():
            raise ValueError("Invalid workflow id")
        return self.root / workflow_id

    def _manifest_path(self, workflow_id: str) -> Path:
        return self._workflow_dir(workflow_id) / "manifest.json"


def split_reaction_smiles(reaction_smiles: str) -> tuple[str, str, str]:
    if ">>" in reaction_smiles:
        left, right = reaction_smiles.split(">>", 1)
        return left.strip(), "", right.strip()
    parts = reaction_smiles.split(">")
    if len(parts) != 3:
        raise ValueError("需要单步 reaction SMILES：reactants>agents>products 或 reactants>>products。")
    return tuple(part.strip() for part in parts)  # type: ignore[return-value]


def extract_mapped_bond_changes(mapped_reactants: str, mapped_products: str) -> list[dict[str, Any]]:
    from rdkit import Chem

    reactant = Chem.MolFromSmiles(mapped_reactants)
    product = Chem.MolFromSmiles(mapped_products)
    if reactant is None or product is None:
        return []
    reactant_indices = {atom.GetAtomMapNum(): atom.GetIdx() + 1 for atom in reactant.GetAtoms() if atom.GetAtomMapNum()}
    symbols = {atom.GetAtomMapNum(): atom.GetSymbol() for atom in reactant.GetAtoms() if atom.GetAtomMapNum()}

    def bonds(mol: Any) -> dict[tuple[int, int], float]:
        result: dict[tuple[int, int], float] = {}
        for bond in mol.GetBonds():
            a = bond.GetBeginAtom().GetAtomMapNum()
            b = bond.GetEndAtom().GetAtomMapNum()
            if a and b:
                result[tuple(sorted((a, b)))] = float(bond.GetBondTypeAsDouble())
        return result

    before, after = bonds(reactant), bonds(product)
    changes: list[dict[str, Any]] = []
    for pair in sorted(set(before) | set(after)):
        old, new = before.get(pair, 0.0), after.get(pair, 0.0)
        if math.isclose(old, new):
            continue
        if pair[0] not in reactant_indices or pair[1] not in reactant_indices:
            continue
        kind = "formed" if old == 0 else "broken" if new == 0 else "order_changed"
        changes.append({
            "map1": pair[0], "map2": pair[1],
            "atom1": reactant_indices[pair[0]], "atom2": reactant_indices[pair[1]],
            "label": f"{symbols.get(pair[0], '?')}{pair[0]}–{symbols.get(pair[1], '?')}{pair[1]}",
            "element1": symbols.get(pair[0], "C"), "element2": symbols.get(pair[1], "C"),
            "kind": kind, "reactant_order": old, "product_order": new,
        })
    return changes


def suggest_scan_coordinates(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coordinates: list[dict[str, Any]] = []
    for change in changes[:2]:
        equilibrium = estimated_bond_length(str(change.get("element1", "C")), str(change.get("element2", "C")))
        if change["kind"] == "formed":
            start, end = max(3.0, equilibrium + 1.2), equilibrium
        elif change["kind"] == "broken":
            start, end = equilibrium, max(3.0, equilibrium + 1.2)
        else:
            start, end = 1.55, 1.30 if change["product_order"] > change["reactant_order"] else 1.75
        coordinates.append({**change, "start": start, "end": end})
    return coordinates


def estimated_bond_length(element1: str, element2: str) -> float:
    radii = {
        "H": 0.31, "B": 0.85, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
        "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39,
    }
    return round(radii.get(element1, 0.8) + radii.get(element2, 0.8), 3)


def reject_transition_metals(smiles: str) -> None:
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("无法解析反应物 SMILES。")
    transition_metals = set(range(21, 31)) | set(range(39, 49)) | set(range(72, 81))
    if any(atom.GetAtomicNum() in transition_metals for atom in mol.GetAtoms()):
        raise ValueError("首版 TS 工作流不支持过渡金属体系。")


def infer_charge_and_multiplicity(smiles: str) -> tuple[int, int, str | None]:
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("无法从反应物推导电荷与多重度。")
    charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
    unpaired = sum(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms())
    if unpaired == 0:
        return charge, 1, None
    if unpaired == 1:
        return charge, 2, "检测到一个未配对电子；默认使用二重态，请人工确认。"
    return charge, unpaired + 1, f"检测到 {unpaired} 个未配对电子；多重度存在耦合歧义，必须人工确认。"


def generate_candidate_geometries(smiles: str, count: int = 3) -> list[dict[str, Any]]:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    base = Chem.MolFromSmiles(smiles)
    if base is None:
        raise ValueError(f"无法解析 SMILES：{smiles}")
    candidates: list[dict[str, Any]] = []
    for index in range(count):
        mol = Chem.AddHs(Chem.Mol(base))
        params = AllChem.ETKDGv3()
        params.randomSeed = 20260620 + index
        if AllChem.EmbedMolecule(mol, params) != 0:
            raise RuntimeError("RDKit 无法生成初始 3D 构象。")
        if AllChem.MMFFHasAllMoleculeParams(mol):
            AllChem.MMFFOptimizeMolecule(mol, maxIters=300)
            fallback = "MMFF"
        else:
            AllChem.UFFOptimizeMolecule(mol, maxIters=300)
            fallback = "UFF"
        conf = mol.GetConformer()
        fragments = Chem.GetMolFrags(mol)
        for frag_index, atom_indices in enumerate(fragments[1:], start=1):
            angle = index * (2 * math.pi / max(count, 1))
            dx = (2.8 + index * 0.25) * frag_index * math.cos(angle)
            dy = (2.8 + index * 0.25) * frag_index * math.sin(angle)
            for atom_index in atom_indices:
                point = conf.GetAtomPosition(atom_index)
                conf.SetAtomPosition(atom_index, (point.x + dx, point.y + dy, point.z + 0.2 * index))
        min_distance = separate_overlapping_fragments(mol, fragments)
        lines = []
        for atom in mol.GetAtoms():
            point = conf.GetAtomPosition(atom.GetIdx())
            lines.append(f"{atom.GetSymbol():<2} {point.x: .8f} {point.y: .8f} {point.z: .8f}")
        candidates.append({
            "candidate_id": f"candidate-{index + 1}",
            "label": f"候选构象 {index + 1}",
            "xyz": f"{mol.GetNumAtoms()}\nOrgSynFlow candidate {index + 1}\n" + "\n".join(lines) + "\n",
            "fallback_method": fallback,
            "minimum_interfragment_distance": min_distance,
        })
    return candidates


def separate_overlapping_fragments(mol: Any, fragments: tuple[tuple[int, ...], ...], minimum_distance: float = 1.25) -> float:
    """Move disconnected fragments apart if RDKit embeds them with obvious overlap."""
    if len(fragments) < 2:
        return float("inf")
    conf = mol.GetConformer()
    fragments = tuple(tuple(fragment) for fragment in fragments)
    for _ in range(12):
        closest = _closest_fragment_pair(mol, fragments)
        if closest["distance"] >= minimum_distance:
            return round(float(closest["distance"]), 4)
        first_fragment = fragments[int(closest["first_fragment"])]
        second_fragment = fragments[int(closest["second_fragment"])]
        first_center = _fragment_centroid(conf, first_fragment)
        second_center = _fragment_centroid(conf, second_fragment)
        vector = [second_center[i] - first_center[i] for i in range(3)]
        norm = math.sqrt(sum(value * value for value in vector))
        if norm < 1e-6:
            vector = [1.0, 0.0, 0.0]
            norm = 1.0
        unit = [value / norm for value in vector]
        shift = (minimum_distance - float(closest["distance"]) + 0.25) / 2
        _translate_fragment(conf, first_fragment, [-shift * value for value in unit])
        _translate_fragment(conf, second_fragment, [shift * value for value in unit])
    return round(float(_closest_fragment_pair(mol, fragments)["distance"]), 4)


def _closest_fragment_pair(mol: Any, fragments: tuple[tuple[int, ...], ...]) -> dict[str, float | int]:
    conf = mol.GetConformer()
    best: dict[str, float | int] = {"distance": float("inf"), "first_fragment": 0, "second_fragment": 1}
    for first_index, first_fragment in enumerate(fragments[:-1]):
        for second_index, second_fragment in enumerate(fragments[first_index + 1:], start=first_index + 1):
            for first_atom_index in first_fragment:
                first_atom = mol.GetAtomWithIdx(first_atom_index)
                if first_atom.GetAtomicNum() == 1:
                    continue
                first_point = conf.GetAtomPosition(first_atom_index)
                for second_atom_index in second_fragment:
                    second_atom = mol.GetAtomWithIdx(second_atom_index)
                    if second_atom.GetAtomicNum() == 1:
                        continue
                    second_point = conf.GetAtomPosition(second_atom_index)
                    distance = math.dist(
                        (first_point.x, first_point.y, first_point.z),
                        (second_point.x, second_point.y, second_point.z),
                    )
                    if distance < float(best["distance"]):
                        best = {"distance": distance, "first_fragment": first_index, "second_fragment": second_index}
    if math.isinf(float(best["distance"])):
        return {"distance": float("inf"), "first_fragment": 0, "second_fragment": 1}
    return best


def _fragment_centroid(conf: Any, atom_indices: tuple[int, ...]) -> list[float]:
    points = [conf.GetAtomPosition(atom_index) for atom_index in atom_indices]
    return [
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
        sum(point.z for point in points) / len(points),
    ]


def _translate_fragment(conf: Any, atom_indices: tuple[int, ...], vector: list[float]) -> None:
    for atom_index in atom_indices:
        point = conf.GetAtomPosition(atom_index)
        conf.SetAtomPosition(atom_index, (point.x + vector[0], point.y + vector[1], point.z + vector[2]))


def build_scan_grid(coordinates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = [9] if len(coordinates) == 1 else [5, 5]
    axes = [[coordinate["start"] + (coordinate["end"] - coordinate["start"]) * i / (count - 1) for i in range(count)] for coordinate, count in zip(coordinates, counts)]
    points: list[dict[str, Any]] = []
    if len(axes) == 1:
        for i, value in enumerate(axes[0]):
            points.append({"point_id": f"scan-{i:02d}", "indices": [i], "values": [value], "status": "pending", "refined": False})
    else:
        for i, first in enumerate(axes[0]):
            second_axis = axes[1] if i % 2 == 0 else list(reversed(axes[1]))
            for second in second_axis:
                j = min(range(len(axes[1])), key=lambda item: abs(axes[1][item] - second))
                points.append({"point_id": f"scan-{i:02d}-{j:02d}", "indices": [i, j], "values": [first, second], "status": "pending", "refined": False})
    return points


def rank_saddle_candidates(points: list[dict[str, Any]], coordinates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(coordinates) == 1:
        ordered = sorted(points, key=lambda item: item["indices"][0])
        interior = ordered[1:-1]
        return sorted(interior, key=lambda item: float(item["energy_hartree"]), reverse=True)
    by_index = {tuple(point["indices"]): point for point in points if len(point.get("indices", [])) == 2 and not point.get("refined")}
    if (0, 0) not in by_index or (4, 4) not in by_index:
        return []
    path = _minimum_barrier_path(by_index, (0, 0), (4, 4))
    path_points = [by_index[index] for index in path[1:-1]]
    ranked = sorted(path_points, key=lambda item: float(item["energy_hartree"]), reverse=True)
    remaining = sorted(
        [point for index, point in by_index.items() if index not in path and 0 not in index and 4 not in index],
        key=lambda item: float(item["energy_hartree"]), reverse=True,
    )
    return ranked + remaining


def _minimum_barrier_path(points: dict[tuple[int, int], dict[str, Any]], start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    queue: list[tuple[float, tuple[int, int]]] = [(float(points[start]["energy_hartree"]), start)]
    costs = {start: queue[0][0]}
    parents: dict[tuple[int, int], tuple[int, int]] = {}
    while queue:
        cost, current = heapq.heappop(queue)
        if current == end:
            break
        if cost > costs[current]:
            continue
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (current[0] + di, current[1] + dj)
            if neighbor not in points:
                continue
            next_cost = max(cost, float(points[neighbor]["energy_hartree"]))
            if next_cost < costs.get(neighbor, float("inf")):
                costs[neighbor] = next_cost
                parents[neighbor] = current
                heapq.heappush(queue, (next_cost, neighbor))
    if end not in costs:
        return []
    path = [end]
    while path[-1] != start:
        path.append(parents[path[-1]])
    return list(reversed(path))


def build_refinement_grid(coordinates: list[dict[str, Any]], candidate: dict[str, Any], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_values = {tuple(round(value, 6) for value in point["values"]) for point in existing}
    steps = [abs(float(coordinate["end"]) - float(coordinate["start"])) / (8 if len(coordinates) == 1 else 4) for coordinate in coordinates]
    offsets = [-0.5, 0.0, 0.5]
    combinations = [(offset,) for offset in offsets] if len(coordinates) == 1 else [(a, b) for a in offsets for b in offsets]
    points: list[dict[str, Any]] = []
    for index, combo in enumerate(combinations):
        values = [float(value) + steps[i] * combo[i] for i, value in enumerate(candidate["values"])]
        key = tuple(round(value, 6) for value in values)
        if key in existing_values:
            continue
        points.append({"point_id": f"refine-{index:02d}", "indices": list(candidate["indices"]), "values": values, "status": "pending", "refined": True})
    return points


def build_gaussian_input_from_xyz(xyz: str, route: str, config: dict[str, Any], title: str, constraints: list[str] | None = None) -> str:
    lines = xyz.strip().splitlines()
    coordinates = lines[2:] if lines and lines[0].strip().isdigit() else lines
    solvent = config.get("solvent")
    solvent_route = f" scrf=(smd,solvent={solvent})" if solvent else ""
    return "\n".join([
        f"%nprocshared={int(config.get('nproc', 4))}",
        f"%mem={config.get('memory', '4GB')}",
        f"# {route} {config.get('method', 'wB97XD')}/{config.get('basis', 'def2SVP')}{solvent_route}",
        "", title, "", f"{int(config.get('charge', 0))} {int(config.get('multiplicity', 1))}",
        *coordinates, "", *(constraints or []), "",
    ])


def reaction_mode_overlap(result: GaussianResult, coordinates: list[dict[str, Any]]) -> float:
    significant_modes = [mode for mode in result.vibration_modes if float(mode.get("frequency_cm1", 0.0)) < 0]
    if not significant_modes:
        return 0.0
    mode = min(significant_modes, key=lambda item: float(item.get("frequency_cm1", 0.0)))
    displacements = mode.get("displacements") or []
    total_norm = math.sqrt(sum(float(value) ** 2 for vector in displacements for value in vector)) or 1.0
    selected = 0.0
    for coordinate in coordinates:
        for atom_number in (coordinate["atom1"], coordinate["atom2"]):
            index = int(atom_number) - 1
            if 0 <= index < len(displacements):
                selected += math.sqrt(sum(float(value) ** 2 for value in displacements[index]))
    return round(min(selected / total_norm, 1.0), 4)


def irc_endpoints_match(first_xyz: str, second_xyz: str, coordinates: list[dict[str, Any]]) -> bool:
    def endpoint_state(xyz: str) -> tuple[bool, bool]:
        atoms = _xyz_atoms(xyz)
        reactant_ok = True
        product_ok = True
        for coordinate in coordinates:
            first = atoms[int(coordinate["atom1"]) - 1]
            second = atoms[int(coordinate["atom2"]) - 1]
            distance = math.dist(first[1:], second[1:])
            if coordinate["kind"] == "formed":
                reactant_ok &= distance > 2.0
                product_ok &= distance < 2.0
            elif coordinate["kind"] == "broken":
                reactant_ok &= distance < 2.0
                product_ok &= distance > 2.0
        return reactant_ok, product_ok

    first_state, second_state = endpoint_state(first_xyz), endpoint_state(second_xyz)
    return (first_state[0] and second_state[1]) or (first_state[1] and second_state[0])


def _xyz_atoms(xyz: str) -> list[tuple[str, float, float, float]]:
    lines = xyz.strip().splitlines()
    body = lines[2:] if lines and lines[0].strip().isdigit() else lines
    atoms = []
    for line in body:
        parts = line.split()
        if len(parts) >= 4:
            atoms.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
    return atoms


def set_xyz_distances(xyz: str, coordinates: list[dict[str, Any]], values: list[float]) -> str:
    atoms = [list(atom) for atom in _xyz_atoms(xyz)]
    for coordinate, target in zip(coordinates, values):
        first_index = int(coordinate["atom1"]) - 1
        second_index = int(coordinate["atom2"]) - 1
        if not (0 <= first_index < len(atoms) and 0 <= second_index < len(atoms)):
            raise ValueError("扫描原子编号超出初始构象范围。")
        first = atoms[first_index]
        second = atoms[second_index]
        vector = [float(second[i]) - float(first[i]) for i in range(1, 4)]
        length = math.sqrt(sum(value * value for value in vector))
        if length < 1e-8:
            vector, length = [1.0, 0.0, 0.0], 1.0
        unit = [value / length for value in vector]
        for axis in range(3):
            second[axis + 1] = float(first[axis + 1]) + unit[axis] * float(target)
    body = "\n".join(f"{atom[0]:<2} {float(atom[1]): .8f} {float(atom[2]): .8f} {float(atom[3]): .8f}" for atom in atoms)
    return f"{len(atoms)}\nOrgSynFlow distance-adjusted geometry\n{body}\n"


def standard_state(config: dict[str, Any]) -> str:
    return "1 M" if config.get("solvent") else "1 atm"


def _public_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in workflow.items() if key not in {"raw_logs"}}
    workflow_id = str(workflow.get("workflow_id") or "")
    if workflow_id:
        progress = _latest_workflow_log_progress(WORKFLOW_ROOT / workflow_id)
        if progress:
            public["gaussian_progress"] = progress
    return public


def _latest_workflow_log_progress(workflow_dir: Path) -> dict[str, Any] | None:
    if not workflow_dir.exists():
        return None
    candidates = sorted(
        [*workflow_dir.rglob("*.log"), *workflow_dir.rglob("*.out")],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    log_path = candidates[0]
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "log_path": str(log_path),
        "log_tail": text[-12000:],
        "progress": parse_gaussian_log_progress(text),
    }


def _terminate_workflow_gaussian_processes(workflow_dir: Path, workflow_root: Path = WORKFLOW_ROOT) -> None:
    """Stop only Gaussian Link processes whose command line names this workflow directory."""
    if not workflow_dir.resolve().is_relative_to(workflow_root.resolve()):
        raise ValueError("Refusing to terminate processes outside the TS workflow root.")
    if __import__("os").name != "nt":
        return
    escaped = str(workflow_dir.resolve()).replace("'", "''")
    script = (
        f"$needle='{escaped}'; "
        "$targets=Get-CimInstance Win32_Process | Where-Object { "
        "$_.CommandLine -and $_.CommandLine.Contains($needle) -and $_.Name -match '^l\\d+\\.exe$' }; "
        "$targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


ts_workflow_manager = TsWorkflowManager()
ts_workflow_manager.recover()
