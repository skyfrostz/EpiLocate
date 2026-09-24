#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# EpiLocate Rule B 人工复核 Web 工具
# 不使用 Tk，只用 Python 标准库启动本地网页。
#
# 建议放到：
#   EpiLocate/scripts/manual_review_web.py
#
# 启动：
#   python3 scripts/manual_review_web.py
#
# 浏览器访问：
#   http://127.0.0.1:8765

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DECISION_FIELDS = [
    "protocol_id",
    "case_id",
    "patient_id",
    "case_type",
    "candidate_series_uids",
    "allowed_decisions",
    "decision",
    "selected_series_uid",
    "reason",
    "reviewer",
    "reviewed_at_utc",
    "image_evidence_reviewed",
    "metadata_evidence_reviewed",
    "validation_status",
]

EVIDENCE_TERMS = (
    "diagnostic", "anatom", "coverage", "reconstruction", "kernel", "noise",
    "sharp", "artifact", "motion", "duplicate", "phase",
    "诊断", "解剖", "覆盖", "重建", "核", "噪声", "锐度",
    "伪影", "运动", "重复", "期相", "肺实质", "纹理",
)

FORBIDDEN_REASON_PATTERNS = (
    r"\brandom\b",
    r"随机",
    r"\bcollection\b",
    r"\blabel\b",
    r"标签",
    r"(?:UID|uid).*(?:small|large|first|last|最小|最大|第一|最后)",
    r"(?:first|last|第一|最后).*(?:UID|uid)",
    r"列表.*(?:第一|最后)",
    r"模型|accuracy|AUC|loss|prediction|预测",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def find_project_root(explicit: str | None) -> Path:
    markers = (
        Path("configs/formal_series_selection_rule_b_v1.json"),
        Path("scripts/validate_manual_series_decisions.py"),
        Path("outputs/data/formal_series_rule_b_review_v1"),
    )

    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())

    candidates.extend(
        [
            Path.cwd().resolve(),
            Path(__file__).resolve().parent,
            Path(__file__).resolve().parent.parent,
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        for root in (candidate, *candidate.parents):
            if root in seen:
                continue
            seen.add(root)
            if all((root / marker).exists() for marker in markers):
                return root

    raise FileNotFoundError(
        "找不到 EpiLocate 项目根目录。请把脚本放到 EpiLocate/scripts/ 下，"
        "或使用 --project-root 指定项目目录。"
    )


class ReviewStore:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.review_dir = project_root / "outputs/data/formal_series_rule_b_review_v1"
        self.candidates_path = self.review_dir / "manual_review_candidates.csv"
        self.decisions_path = self.review_dir / "manual_review_decisions.csv"
        self.validator_path = project_root / "scripts/validate_manual_series_decisions.py"
        self.raw_dir = project_root / "data/full_raw"

        if not self.candidates_path.exists() or not self.decisions_path.exists():
            raise FileNotFoundError(
                "没有找到人工复核包。请先运行："
                "python3 scripts/prepare_series_manual_review.py"
            )

        self.lock = threading.Lock()
        self.backup_created = False
        self.series_cache: dict[str, Path | None] = {}
        self.reload()

    def reload(self) -> None:
        self.candidates = read_csv(self.candidates_path)
        self.decisions = read_csv(self.decisions_path)

        self.candidates_by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.candidates:
            self.candidates_by_case[row["case_id"]].append(row)

        self.case_order = [row["case_id"] for row in self.decisions]
        self.decision_by_case = {row["case_id"]: row for row in self.decisions}

        if len(self.case_order) != 13:
            raise ValueError(f"预期 13 个病例，实际读取到 {len(self.case_order)} 个。")

    def ensure_backup(self) -> None:
        if self.backup_created:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.decisions_path.with_name(
            f"manual_review_decisions.backup_{stamp}.csv"
        )
        shutil.copy2(self.decisions_path, backup)
        self.backup_created = True

    def atomic_write(self) -> None:
        self.ensure_backup()
        tmp = self.decisions_path.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=DECISION_FIELDS,
                extrasaction="ignore",
            )
            writer.writeheader()
            for case_id in self.case_order:
                row = self.decision_by_case[case_id]
                writer.writerow({field: row.get(field, "") for field in DECISION_FIELDS})
        tmp.replace(self.decisions_path)

    def validate_form(
        self,
        decision: str,
        selected_uid: str,
        reason: str,
        reviewer: str,
    ) -> list[str]:
        errors: list[str] = []

        if decision == "PENDING":
            errors.append("请选择候选 Series、排除患者，或暂缓（DEFER）。")

        if decision in {"SELECT_ONE_CANDIDATE", "INCLUDE_REVIEW_SERIES"} and not selected_uid:
            errors.append("当前决定需要选择一个 Series。")

        if len(reason.strip()) < 20:
            errors.append("理由至少 20 个字符。最简单的方法是点一个“大白话理由”按钮。")

        if reason.strip() and not any(term.lower() in reason.lower() for term in EVIDENCE_TERMS):
            errors.append(
                "理由需要包含覆盖、重建、噪声、锐度、伪影、运动、重复、肺实质纹理等可复核证据。"
            )

        if any(re.search(pattern, reason, re.I) for pattern in FORBIDDEN_REASON_PATTERNS):
            errors.append("不能用 UID 顺序、随机、标签或模型结果作为选择依据。")

        if not reviewer.strip():
            errors.append("请填写复核人姓名。")

        return errors

    def save_case(self, payload: dict) -> dict:
        case_id = str(payload.get("case_id", ""))
        if case_id not in self.decision_by_case:
            raise ValueError("未知 case_id。")

        decision = str(payload.get("decision", "PENDING"))
        selected_uid = str(payload.get("selected_series_uid", ""))
        reason = str(payload.get("reason", "")).strip()
        reviewer = str(payload.get("reviewer", "")).strip()

        errors = self.validate_form(decision, selected_uid, reason, reviewer)
        if errors:
            return {"ok": False, "errors": errors}

        allowed_uids = {
            row["series_uid"]
            for row in self.candidates_by_case[case_id]
            if row["candidate_role"] != "excluded_bone_only_context"
        }

        if selected_uid and selected_uid not in allowed_uids:
            return {"ok": False, "errors": ["选择的 Series UID 不在候选清单中。"]}

        with self.lock:
            row = self.decision_by_case[case_id]
            row["decision"] = decision
            row["selected_series_uid"] = selected_uid
            row["reason"] = reason
            row["reviewer"] = reviewer
            row["reviewed_at_utc"] = utc_now()
            row["image_evidence_reviewed"] = "YES"
            row["metadata_evidence_reviewed"] = "YES"
            row["validation_status"] = "READY_FOR_VALIDATION"
            self.atomic_write()

        return {
            "ok": True,
            "reviewed_at_utc": row["reviewed_at_utc"],
        }

    def find_series_dir(self, series_uid: str) -> Path | None:
        if series_uid in self.series_cache:
            return self.series_cache[series_uid]

        target = f"CT_{series_uid}"
        found: Path | None = None

        if self.raw_dir.exists():
            for path in self.raw_dir.rglob(target):
                if path.is_dir():
                    found = path
                    break

        self.series_cache[series_uid] = found
        return found

    def run_validator(self) -> dict:
        result = subprocess.run(
            [sys.executable, str(self.validator_path)],
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def page_template(store: ReviewStore, current_index: int) -> str:
    case_id = store.case_order[current_index]
    decision_row = store.decision_by_case[case_id]
    candidates = store.candidates_by_case[case_id]

    saved_decision = decision_row.get("decision", "")
    saved_uid = decision_row.get("selected_series_uid", "")

    if saved_decision == "SELECT_ONE_CANDIDATE":
        saved_choice = f"SELECT::{saved_uid}"
    elif saved_decision == "INCLUDE_REVIEW_SERIES":
        saved_choice = f"INCLUDE::{saved_uid}"
    elif saved_decision in {"EXCLUDE_PATIENT", "DEFER"}:
        saved_choice = saved_decision
    else:
        saved_choice = ""

    if case_id == "TIE-012":
        simple_tip = (
            "这例两套都是 B，而且参数几乎一样。重点看它们是不是重复，"
            "或有没有覆盖、运动、伪影差异。拿不准就点“疑似重复 / 暂缓”。"
        )
    elif decision_row["case_type"] == "technical_tie":
        simple_tip = (
            "只比较哪套更适合作为研究输入：肺纹理是否更清楚、噪点是否更少、"
            "伪影是否更少、覆盖是否更完整。真的看不出来就 DEFER。"
        )
    else:
        simple_tip = (
            "这例不是二选一。只判断 review_candidate 是否像正常可用于研究的诊断性胸部 CT："
            "覆盖够不够、图像能不能看、有没有明显运动或特殊后处理。"
        )

    cards: list[str] = []
    selectable_index = 0

    for row in candidates:
        role = row["candidate_role"]
        selectable = role != "excluded_bone_only_context"

        if selectable:
            label = f"候选 {chr(ord('A') + selectable_index)}"
            selectable_index += 1
        else:
            label = "对照项（不可选）"

        if selectable:
            if decision_row["case_type"] == "diagnostic_type_uncertain":
                value = f"INCLUDE::{row['series_uid']}"
                choose_label = "这套可以作为研究输入"
            else:
                value = f"SELECT::{row['series_uid']}"
                choose_label = f"选择 {label}"

            checked = "checked" if saved_choice == value else ""
            radio = (
                f'<label class="choice">'
                f'<input type="radio" name="decision_choice" value="{esc(value)}" {checked}>'
                f'<span>✅ {esc(choose_label)}</span>'
                f'</label>'
            )
        else:
            radio = '<div class="muted">该项只作对照，不能选择。</div>'

        montage_rel = row.get("montage_path", "").strip()
        if montage_rel:
            image_url = "/file?" + urllib.parse.urlencode({"path": montage_rel})
            image_html = f'<img class="montage" src="{esc(image_url)}" alt="montage">'
        else:
            image_html = '<div class="muted">没有 montage</div>'

        open_series = ""
        if selectable:
            open_series = (
                f'<button class="secondary" '
                f'onclick="openSeries({json.dumps(row["series_uid"])})">'
                f'打开完整 Series 文件夹</button>'
            )

        card = f'''
<section class="card">
  <h3>{esc(label)} · Kernel {esc(row.get("convolution_kernel", ""))}</h3>
  {radio}
  <div class="meta">
    <div><b>层厚：</b>{esc(row.get("slice_thickness_mm"))} mm</div>
    <div><b>像素间距：</b>{esc(row.get("pixel_spacing_row_mm"))} × {esc(row.get("pixel_spacing_column_mm"))} mm</div>
    <div><b>覆盖：</b>{esc(row.get("coverage_mm"))} mm</div>
    <div><b>切片：</b>{esc(row.get("slice_count"))}</div>
    <div><b>Description：</b>{esc(row.get("series_description"))}</div>
    <div class="uid"><b>Series UID：</b>{esc(row.get("series_uid"))}</div>
  </div>
  {image_html}
  <div class="card-actions">{open_series}</div>
</section>
'''
        cards.append(card)

    if decision_row["case_type"] == "diagnostic_type_uncertain":
        reason_buttons = [
            ("覆盖完整、图像正常 → 纳入", "diag_include"),
            ("覆盖明显不完整 → 排除", "diag_coverage_bad"),
            ("运动/伪影明显 → 排除", "diag_artifact_bad"),
            ("看不懂是不是诊断 CT → 暂缓", "diag_defer"),
        ]
    else:
        reason_buttons = [
            ("所选这套：肺纹理更清楚", "sel_texture"),
            ("所选这套：噪点更少", "sel_noise"),
            ("所选这套：伪影更少", "sel_artifact"),
            ("所选这套：覆盖更完整", "sel_coverage"),
            ("整体看，所选这套更合适", "sel_overall"),
            ("两套看起来差不多 → 暂缓", "tie_same"),
            ("我们看不懂 / 拿不准 → 暂缓", "tie_unsure"),
            ("两套都有明显问题 → 排除", "tie_exclude"),
        ]

        if case_id == "TIE-012":
            reason_buttons.append(("TIE-012：疑似重复序列 → 暂缓", "tie12_duplicate"))

    reason_buttons_html = "".join(
        f'<button class="reason-btn" onclick="applyReason({json.dumps(key)})">{esc(text)}</button>'
        for text, key in reason_buttons
    )

    exclude_checked = "checked" if saved_choice == "EXCLUDE_PATIENT" else ""
    defer_checked = "checked" if saved_choice == "DEFER" else ""

    prev_disabled = "disabled" if current_index == 0 else ""
    next_disabled = "disabled" if current_index == len(store.case_order) - 1 else ""

    html_page = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EpiLocate 人工复核</title>
<style>
:root {{
  --bg:#f5f7fb;
  --panel:#ffffff;
  --line:#dde3ea;
  --text:#17202a;
  --muted:#687583;
  --accent:#2563eb;
  --soft:#eef4ff;
  --danger:#b42318;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);
  color:var(--text);
}}
.container {{
  max-width:1500px;
  margin:0 auto;
  padding:22px;
}}
.top {{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:12px;
}}
h1 {{
  font-size:24px;
  margin:0;
}}
.progress {{
  color:var(--muted);
}}
.notice {{
  margin:14px 0;
  padding:12px 14px;
  background:#fff8e8;
  border:1px solid #f2d48d;
  border-radius:12px;
  line-height:1.7;
}}
.case-head {{
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:14px;
  padding:16px;
  margin-bottom:14px;
}}
.case-head h2 {{
  margin:0 0 8px;
  font-size:20px;
}}
.tip {{
  color:#183153;
  line-height:1.7;
}}
.grid {{
  display:grid;
  grid-template-columns:repeat({max(1, len(candidates))}, minmax(0,1fr));
  gap:14px;
}}
.card {{
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:14px;
  padding:14px;
  min-width:0;
}}
.card h3 {{
  margin:0 0 10px;
}}
.choice {{
  display:block;
  padding:10px;
  background:var(--soft);
  border-radius:10px;
  font-weight:700;
  cursor:pointer;
}}
.meta {{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:5px 14px;
  font-size:14px;
  margin:12px 0;
  line-height:1.5;
}}
.uid {{
  grid-column:1/-1;
  word-break:break-all;
  color:var(--muted);
}}
.montage {{
  width:100%;
  max-height:430px;
  object-fit:contain;
  border-radius:10px;
  background:#111;
}}
.card-actions {{
  margin-top:10px;
}}
.editor {{
  margin-top:14px;
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:14px;
  padding:16px;
}}
.decision-row {{
  display:flex;
  flex-wrap:wrap;
  gap:12px;
  margin-bottom:12px;
}}
.decision-pill {{
  padding:10px 12px;
  border:1px solid var(--line);
  border-radius:10px;
}}
.reason-buttons {{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:8px;
  margin:10px 0;
}}
button {{
  border:0;
  border-radius:10px;
  padding:10px 14px;
  cursor:pointer;
  font-weight:650;
}}
button:disabled {{
  opacity:.4;
  cursor:not-allowed;
}}
.reason-btn {{
  background:#edf2f7;
  color:#243244;
  min-height:48px;
}}
.primary {{
  background:var(--accent);
  color:#fff;
}}
.secondary {{
  background:#edf2f7;
  color:#243244;
}}
textarea {{
  width:100%;
  min-height:100px;
  padding:12px;
  border:1px solid var(--line);
  border-radius:10px;
  font:inherit;
  resize:vertical;
}}
.form-row {{
  display:flex;
  gap:12px;
  align-items:center;
  margin-top:10px;
  flex-wrap:wrap;
}}
input[type=text] {{
  padding:10px 12px;
  border:1px solid var(--line);
  border-radius:10px;
  min-width:180px;
}}
.actions {{
  display:flex;
  justify-content:space-between;
  gap:12px;
  margin-top:14px;
}}
.left-actions,.right-actions {{
  display:flex;
  gap:8px;
}}
.status {{
  margin-top:10px;
  padding:10px;
  border-radius:10px;
  display:none;
  white-space:pre-wrap;
}}
.status.ok {{
  display:block;
  background:#ecfdf3;
  color:#166534;
}}
.status.err {{
  display:block;
  background:#fff1f2;
  color:#9f1239;
}}
.muted {{
  color:var(--muted);
}}
@media (max-width:1000px) {{
  .grid {{
    grid-template-columns:1fr;
  }}
  .reason-buttons {{
    grid-template-columns:1fr 1fr;
  }}
}}
</style>
</head>
<body>
<div class="container">
  <div class="top">
    <h1>EpiLocate · 13 例人工复核（浏览器版）</h1>
    <div class="progress">{current_index + 1} / {len(store.case_order)}</div>
  </div>

  <div class="notice">
    <b>只做一件事：</b>判断哪套 CT 更适合作为研究输入。不要判断患者有没有病。<br>
    看不出来时，选择 <b>DEFER</b> 才是正确做法，不要硬选。
  </div>

  <section class="case-head">
    <h2>{esc(case_id)} · {esc(decision_row["patient_id"])}</h2>
    <div class="tip">{esc(simple_tip)}</div>
    <div class="muted" style="margin-top:7px">
      类型：{esc(decision_row["case_type"])}　|　允许决定：{esc(decision_row["allowed_decisions"])}
    </div>
  </section>

  <div class="grid">
    {''.join(cards)}
  </div>

  <section class="editor">
    <h3 style="margin-top:0">选择结果</h3>

    <div class="decision-row">
      <label class="decision-pill">
        <input type="radio" name="decision_choice" value="EXCLUDE_PATIENT" {exclude_checked}>
        ❌ 两套都不适合 → 排除患者
      </label>

      <label class="decision-pill">
        <input type="radio" name="decision_choice" value="DEFER" {defer_checked}>
        ❓ 看不出来 / 证据不够 → DEFER
      </label>
    </div>

    <h3>大白话理由按钮</h3>
    <div class="muted">只点你真正看到了的情况。程序会自动把它写成规范理由。</div>

    <div class="reason-buttons">
      {reason_buttons_html}
    </div>

    <label><b>自动生成的理由（可以手动修改）</b></label>
    <textarea id="reason">{esc(decision_row.get("reason", ""))}</textarea>

    <div class="form-row">
      <label>
        <b>复核人：</b>
        <input id="reviewer" type="text" value="{esc(decision_row.get("reviewer", ""))}" placeholder="例如：王淼">
      </label>
      <span class="muted">
        保存时会自动写 UTC 时间，并标记图像和 metadata 已复核。
      </span>
    </div>

    <div id="status" class="status"></div>

    <div class="actions">
      <div class="left-actions">
        <button class="secondary" onclick="goCase({current_index - 1})" {prev_disabled}>← 上一例</button>
        <button class="primary" onclick="saveCase(false)">保存当前</button>
        <button class="primary" onclick="saveCase(true)" {next_disabled}>保存并下一例 →</button>
      </div>

      <div class="right-actions">
        <button class="secondary" onclick="runValidator()">运行最终校验</button>
      </div>
    </div>
  </section>
</div>

<script>
const CASE_ID = {json.dumps(case_id, ensure_ascii=False)};
const NEXT_INDEX = {current_index + 1};

const reasonMap = {{
  sel_texture: "所选 Series 与另一候选相比，肺实质纹理和细小结构显示更清楚，更适合作为本研究的影像输入。",
  sel_noise: "所选 Series 的图像噪声相对更少，肺实质观察更稳定，未见因噪声导致的明显质量下降。",
  sel_artifact: "所选 Series 的运动、条纹或其他明显伪影相对更少，对胸部解剖结构和肺实质观察影响较小。",
  sel_coverage: "所选 Series 的胸部解剖覆盖更完整，可见肺部范围更适合作为本研究的标准输入。",
  sel_overall: "两套候选的基本技术条件可比较；所选 Series 的肺实质纹理显示更清楚，噪声和伪影对观察的影响更小，胸部覆盖可接受，因此更适合作为本研究输入。",
  tie_same: "两套候选在胸部解剖覆盖、肺实质纹理、图像噪声和伪影方面看不出稳定且可重复的差异，现有图像与 metadata 证据不足以支持可靠选择，因此暂缓决定。",
  tie_unsure: "当前复核者无法依据现有图像和 metadata 对候选 Series 的诊断适用性、重建表现、噪声和伪影作出可靠区分，证据不足，因此暂缓决定并交由更有经验的复核者确认。",
  tie_exclude: "两套候选均存在影响肺实质观察的明显质量问题，例如噪声、运动或其他伪影，无法获得稳定可用的诊断性胸部 CT 研究输入，因此排除该患者。",
  tie12_duplicate: "两套候选的层厚、像素间距、覆盖和切片数量一致，图像表现也高度相似，目前疑似重复 Series；在没有进一步比较几何位置、时间和对应像素前，现有证据不足以支持选择，因此暂缓决定。",
  diag_include: "该 Series 可见胸部解剖覆盖较完整，肺实质和主要胸部结构能够连续观察，未见影响研究使用的明显运动或其他伪影；结合 metadata，现有证据支持其作为诊断性胸部 CT 研究输入，因此纳入该 Series。",
  diag_coverage_bad: "该 Series 胸部解剖覆盖明显不足，不能稳定覆盖需要观察的肺部范围，不适合作为本研究的诊断性胸部 CT 输入，因此排除该患者。",
  diag_artifact_bad: "该 Series 可见明显运动或其他伪影，已经影响肺实质纹理和解剖结构观察，不适合作为稳定的研究输入，因此排除该患者。",
  diag_defer: "仅凭当前图像与 metadata 仍无法可靠确认该 Series 是否属于适合作为研究输入的诊断性胸部 CT；对其重建用途、覆盖和伪影判断证据不足，因此暂缓决定并交由更有经验的复核者确认。"
}};

function selectedChoice() {{
  const el = document.querySelector('input[name="decision_choice"]:checked');
  return el ? el.value : "";
}}

function setChoice(value) {{
  const all = document.querySelectorAll('input[name="decision_choice"]');
  for (const el of all) {{
    if (el.value === value) {{
      el.checked = true;
      return true;
    }}
  }}
  return false;
}}

function applyReason(key) {{
  const reason = reasonMap[key] || "";

  if (["tie_same","tie_unsure","tie12_duplicate","diag_defer"].includes(key)) {{
    setChoice("DEFER");
    document.getElementById("reason").value = reason;
    return;
  }}

  if (["tie_exclude","diag_coverage_bad","diag_artifact_bad"].includes(key)) {{
    setChoice("EXCLUDE_PATIENT");
    document.getElementById("reason").value = reason;
    return;
  }}

  if (key === "diag_include") {{
    const candidate = document.querySelector('input[name="decision_choice"][value^="INCLUDE::"]');
    if (candidate) candidate.checked = true;
    document.getElementById("reason").value = reason;
    return;
  }}

  const choice = selectedChoice();
  if (!(choice.startsWith("SELECT::") || choice.startsWith("INCLUDE::"))) {{
    showStatus(false, "请先在上面的候选 A / B 中选择一套，再点这个理由按钮。");
    return;
  }}

  const box = document.getElementById("reason");

  if (key === "sel_overall") {{
    box.value = reason;
  }} else if (!box.value.includes(reason)) {{
    box.value = (box.value.trim() + " " + reason).trim();
  }}
}}

function parseChoice(choice) {{
  if (choice.startsWith("SELECT::")) {{
    return ["SELECT_ONE_CANDIDATE", choice.slice(8)];
  }}
  if (choice.startsWith("INCLUDE::")) {{
    return ["INCLUDE_REVIEW_SERIES", choice.slice(9)];
  }}
  if (choice === "EXCLUDE_PATIENT" || choice === "DEFER") {{
    return [choice, ""];
  }}
  return ["PENDING", ""];
}}

function showStatus(ok, message) {{
  const el = document.getElementById("status");
  el.className = "status " + (ok ? "ok" : "err");
  el.textContent = message;
}}

async function saveCase(goNext) {{
  const [decision, selected_series_uid] = parseChoice(selectedChoice());

  const payload = {{
    case_id: CASE_ID,
    decision: decision,
    selected_series_uid: selected_series_uid,
    reason: document.getElementById("reason").value,
    reviewer: document.getElementById("reviewer").value
  }};

  const res = await fetch("/api/save", {{
    method: "POST",
    headers: {{"Content-Type":"application/json"}},
    body: JSON.stringify(payload)
  }});

  const data = await res.json();

  if (!data.ok) {{
    showStatus(false, (data.errors || ["保存失败"]).join("\\n"));
    return;
  }}

  showStatus(true, "已保存 · " + data.reviewed_at_utc);

  if (goNext) {{
    setTimeout(() => goCase(NEXT_INDEX), 250);
  }}
}}

function goCase(index) {{
  if (index < 0) return;
  window.location.href = "/?case=" + index;
}}

async function openSeries(uid) {{
  const res = await fetch("/api/open-series", {{
    method: "POST",
    headers: {{"Content-Type":"application/json"}},
    body: JSON.stringify({{series_uid:uid}})
  }});

  const data = await res.json();

  if (!data.ok) {{
    showStatus(false, data.error || "无法打开 Series 文件夹");
  }}
}}

async function runValidator() {{
  showStatus(true, "正在运行校验...");

  const res = await fetch("/api/validate", {{method:"POST"}});
  const data = await res.json();

  const output =
    (data.stdout || "") +
    (data.stderr ? "\\n" + data.stderr : "");

  showStatus(
    data.returncode === 0,
    "校验返回码：" + data.returncode + "\\n\\n" + output
  );
}}
</script>
</body>
</html>
'''
    return html_page


class Handler(BaseHTTPRequestHandler):
    store: ReviewStore | None = None

    def log_message(self, format, *args):
        return

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        self.send_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        assert self.store is not None
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            qs = urllib.parse.parse_qs(parsed.query)

            try:
                idx = int(qs.get("case", ["0"])[0])
            except ValueError:
                idx = 0

            idx = max(0, min(idx, len(self.store.case_order) - 1))
            body = page_template(self.store, idx).encode("utf-8")
            self.send_bytes(body, "text/html; charset=utf-8")
            return

        if parsed.path == "/file":
            qs = urllib.parse.parse_qs(parsed.query)
            rel = qs.get("path", [""])[0]
            target = (self.store.review_dir / rel).resolve()

            try:
                target.relative_to(self.store.review_dir.resolve())
            except ValueError:
                self.send_error(403)
                return

            if not target.is_file():
                self.send_error(404)
                return

            ctype = "image/png" if target.suffix.lower() == ".png" else "application/octet-stream"
            self.send_bytes(target.read_bytes(), ctype)
            return

        self.send_error(404)

    def do_POST(self):
        assert self.store is not None
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/save":
            try:
                payload = self.read_json()
                result = self.store.save_case(payload)
                self.send_json(result, 200 if result.get("ok") else 400)
            except Exception as exc:
                self.send_json({"ok": False, "errors": [str(exc)]}, 500)
            return

        if parsed.path == "/api/open-series":
            try:
                payload = self.read_json()
                uid = str(payload.get("series_uid", ""))
                folder = self.store.find_series_dir(uid)

                if not folder:
                    self.send_json(
                        {
                            "ok": False,
                            "error": "在 data/full_raw 中没有找到该完整 Series 文件夹。",
                        },
                        404,
                    )
                    return

                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(folder)])
                elif os.name == "nt":
                    os.startfile(str(folder))  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", str(folder)])

                self.send_json({"ok": True, "path": str(folder)})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, 500)
            return

        if parsed.path == "/api/validate":
            try:
                result = self.store.run_validator()
                self.send_json(result)
            except Exception as exc:
                self.send_json(
                    {
                        "returncode": -1,
                        "stdout": "",
                        "stderr": str(exc),
                    },
                    500,
                )
            return

        self.send_error(404)


def main() -> int:
    parser = argparse.ArgumentParser(description="EpiLocate Rule B 人工复核 Web 工具")
    parser.add_argument("--project-root", help="EpiLocate 项目根目录")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    try:
        project_root = find_project_root(args.project_root)
        store = ReviewStore(project_root)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    Handler.store = store
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"

    print("=" * 64)
    print("EpiLocate 人工复核 Web 工具已启动")
    print(f"项目目录：{project_root}")
    print(f"打开地址：{url}")
    print("按 Ctrl+C 停止")
    print("=" * 64)

    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
