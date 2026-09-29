#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EpiLocate Rule B 人工复核 GUI v2
================================

给“不熟悉影像科研/不熟悉 CSV”的组员使用。

你们只需要做三件事：
1. 看左右两套图（必要时点“打开完整 Series 文件夹”滚动看完整 CT）
2. 选择：哪套更适合 / 排除 / 暂缓
3. 点击一个或几个“大白话理由按钮”，脚本自动生成规范理由并保存

用途：
- 读取 outputs/data/formal_series_rule_b_review_v1/manual_review_candidates.csv
- 读取/写入 outputs/data/formal_series_rule_b_review_v1/manual_review_decisions.csv
- 并排显示 montage + metadata
- 一键选择 Series / EXCLUDE_PATIENT / DEFER
- 一键生成符合现有 validator 习惯的复核依据
- 自动填写 reviewer / UTC 时间 / evidence reviewed
- 自动备份原 decisions CSV
- 直接调用 scripts/validate_manual_series_decisions.py 做最终校验

建议保存到：
    EpiLocate/scripts/manual_review_gui.py

启动：
    python scripts/manual_review_gui.py
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk


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

# 与仓库现有 validator 的证据词保持兼容。
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


def find_project_root(explicit: str | None) -> Path:
    markers = (
        Path("configs/formal_series_selection_rule_b_v1.json"),
        Path("scripts/validate_manual_series_decisions.py"),
        Path("outputs/data/formal_series_rule_b_review_v1"),
    )

    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())

    candidates.extend([
        Path.cwd().resolve(),
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent.parent,
    ])

    seen: set[Path] = set()
    for candidate in candidates:
        for root in (candidate, *candidate.parents):
            if root in seen:
                continue
            seen.add(root)
            if all((root / marker).exists() for marker in markers):
                return root

    raise FileNotFoundError(
        "找不到 EpiLocate 项目根目录。\n\n"
        "请把本脚本放到 EpiLocate/scripts/ 下，或运行：\n"
        "python manual_review_gui.py --project-root /path/to/EpiLocate"
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


class ReviewApp:
    def __init__(self, root: tk.Tk, project_root: Path):
        self.tk = root
        self.project_root = project_root
        self.review_dir = (
            project_root
            / "outputs"
            / "data"
            / "formal_series_rule_b_review_v1"
        )
        self.candidates_path = self.review_dir / "manual_review_candidates.csv"
        self.decisions_path = self.review_dir / "manual_review_decisions.csv"
        self.validator_path = project_root / "scripts" / "validate_manual_series_decisions.py"
        self.raw_dir = project_root / "data" / "full_raw"

        if not self.candidates_path.exists() or not self.decisions_path.exists():
            raise FileNotFoundError(
                "没有找到人工复核包。\n\n"
                "请先在项目根目录运行：\n"
                "python scripts/prepare_series_manual_review.py"
            )

        self.candidates = read_csv(self.candidates_path)
        self.decisions = read_csv(self.decisions_path)

        if len(self.decisions) != 13:
            raise ValueError(f"预期 13 个复核病例，实际读取到 {len(self.decisions)} 个。")

        self.candidates_by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.candidates:
            self.candidates_by_case[row["case_id"]].append(row)

        self.case_order = [row["case_id"] for row in self.decisions]
        self.decision_by_case = {row["case_id"]: row for row in self.decisions}

        self.current_index = 0
        self.photo_refs: list[ImageTk.PhotoImage] = []
        self.backup_created = False
        self.series_cache: dict[str, Path | None] = {}

        self.case_title_var = tk.StringVar()
        self.case_meta_var = tk.StringVar()
        self.simple_tip_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.decision_var = tk.StringVar()
        self.reviewer_var = tk.StringVar()
        self.image_reviewed_var = tk.BooleanVar()
        self.metadata_reviewed_var = tk.BooleanVar()

        self._build_ui()
        self._load_case(0)

    def _build_ui(self) -> None:
        self.tk.title("EpiLocate · 13 例人工复核（简易版）")
        self.tk.geometry("1500x980")
        self.tk.minsize(1100, 780)

        style = ttk.Style()
        try:
            style.configure("Title.TLabel", font=("TkDefaultFont", 17, "bold"))
            style.configure("Case.TLabel", font=("TkDefaultFont", 12, "bold"))
            style.configure("Big.TButton", padding=(12, 8))
        except tk.TclError:
            pass

        outer = ttk.Frame(self.tk, padding=12)
        outer.pack(fill="both", expand=True)

        # 顶部
        header = ttk.Frame(outer)
        header.pack(fill="x")

        ttk.Label(
            header,
            text="EpiLocate · 13 例人工复核（简易版）",
            style="Title.TLabel",
        ).pack(side="left")

        self.progress_label = ttk.Label(header, text="")
        self.progress_label.pack(side="right")

        ttk.Label(
            outer,
            text=(
                "你只需要：① 看图　② 选结果　③ 点“大白话理由”按钮　④ 填姓名后保存。"
                "　不要判断患者有没有病，只判断哪套 CT 更适合作为研究输入。"
            ),
            wraplength=1450,
            justify="left",
        ).pack(fill="x", pady=(8, 5))

        ttk.Separator(outer).pack(fill="x", pady=(3, 8))

        info = ttk.Frame(outer)
        info.pack(fill="x")

        ttk.Label(info, textvariable=self.case_title_var, style="Case.TLabel").pack(anchor="w")
        ttk.Label(
            info,
            textvariable=self.simple_tip_var,
            wraplength=1420,
            justify="left",
        ).pack(anchor="w", pady=(4, 2))

        ttk.Label(
            info,
            textvariable=self.case_meta_var,
            wraplength=1420,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        # 图像候选
        self.candidate_frame = ttk.Frame(outer)
        self.candidate_frame.pack(fill="both", expand=True)

        # 决策和理由
        editor = ttk.LabelFrame(outer, text="第 2 步：选结果 + 第 3 步：点理由", padding=10)
        editor.pack(fill="x", pady=(8, 0))

        self.radio_frame = ttk.Frame(editor)
        self.radio_frame.pack(fill="x", pady=(0, 7))

        # 大白话理由按钮
        self.quick_reason_box = ttk.LabelFrame(
            editor,
            text="大白话理由按钮（只点你真的看到了的情况，可以点多个）",
            padding=8,
        )
        self.quick_reason_box.pack(fill="x", pady=(0, 7))

        self.quick_reason_frame = ttk.Frame(self.quick_reason_box)
        self.quick_reason_frame.pack(fill="x")

        reason_header = ttk.Frame(editor)
        reason_header.pack(fill="x")
        ttk.Label(reason_header, text="自动生成的复核依据（你也可以手动改）：").pack(side="left")
        ttk.Button(
            reason_header,
            text="清空理由",
            command=self.clear_reason,
        ).pack(side="right")

        self.reason_text = tk.Text(editor, height=4, wrap="word")
        self.reason_text.pack(fill="x", expand=True, pady=(3, 7))
        self.reason_text.bind("<KeyRelease>", lambda _e: self._set_dirty_status())

        lower = ttk.Frame(editor)
        lower.pack(fill="x")

        ttk.Label(lower, text="复核人：").pack(side="left")
        reviewer_entry = ttk.Entry(lower, textvariable=self.reviewer_var, width=18)
        reviewer_entry.pack(side="left", padx=(4, 14))
        reviewer_entry.bind("<KeyRelease>", lambda _e: self._set_dirty_status())

        ttk.Checkbutton(
            lower,
            text="我已看过图像",
            variable=self.image_reviewed_var,
            command=self._set_dirty_status,
        ).pack(side="left", padx=(0, 12))

        ttk.Checkbutton(
            lower,
            text="我已看过上面的参数",
            variable=self.metadata_reviewed_var,
            command=self._set_dirty_status,
        ).pack(side="left", padx=(0, 12))

        ttk.Label(lower, textvariable=self.status_var).pack(side="right")

        nav = ttk.Frame(outer)
        nav.pack(fill="x", pady=(10, 0))

        ttk.Button(nav, text="← 上一例", command=self.prev_case).pack(side="left")
        ttk.Button(nav, text="保存当前", command=self.save_current).pack(side="left", padx=8)
        ttk.Button(nav, text="保存并下一例 →", command=self.save_and_next).pack(side="left")

        ttk.Button(nav, text="运行最终校验", command=self.run_validator).pack(side="right")
        ttk.Button(
            nav,
            text="打开复核文件夹",
            command=lambda: self.open_path(self.review_dir),
        ).pack(side="right", padx=8)

    def _clear_candidate_frame(self) -> None:
        for widget in self.candidate_frame.winfo_children():
            widget.destroy()
        self.photo_refs.clear()

    def _clear_quick_reason_buttons(self) -> None:
        for widget in self.quick_reason_frame.winfo_children():
            widget.destroy()

    def _load_case(self, index: int) -> None:
        if not (0 <= index < len(self.case_order)):
            return

        self.current_index = index
        case_id = self.case_order[index]
        decision = self.decision_by_case[case_id]
        candidates = self.candidates_by_case[case_id]

        self.progress_label.config(text=f"{index + 1} / {len(self.case_order)}")
        self.case_title_var.set(f"{case_id} · {decision['patient_id']}")

        if case_id == "TIE-012":
            simple = (
                "这例比较特殊：两套都是 B，而且参数非常接近。重点看它们是不是几乎重复，"
                "或有没有覆盖、运动、伪影差异。拿不准就点“看不出差别 / 拿不准 → DEFER”。"
            )
        elif decision["case_type"] == "technical_tie":
            simple = (
                "最简单的看法：左右对比肺里的纹理是否更清楚、哪边噪点更少、哪边伪影更少、"
                "胸部覆盖是否一样。真的看不出区别就 DEFER，不要硬选。"
            )
        else:
            simple = (
                "这例不是二选一。只判断这一套 chest CT 是否像正常可用于研究的胸部诊断 CT："
                "覆盖够不够、图像能不能看、有没有明显运动/特殊后处理。拿不准就 DEFER。"
            )

        self.simple_tip_var.set("大白话： " + simple)
        self.case_meta_var.set(
            f"类型：{decision['case_type']}　|　允许决定：{decision['allowed_decisions']}"
        )

        self._clear_candidate_frame()
        self._clear_quick_reason_buttons()

        for col, row in enumerate(candidates):
            self.candidate_frame.columnconfigure(col, weight=1)
            self._build_candidate_card(self.candidate_frame, col, row)

        self._build_decision_radios(decision)
        self._build_quick_reason_buttons(decision)

        # 恢复已保存内容
        self.reason_text.delete("1.0", "end")
        self.reason_text.insert("1.0", decision.get("reason", ""))
        self.reviewer_var.set(decision.get("reviewer", ""))
        self.image_reviewed_var.set(
            decision.get("image_evidence_reviewed", "").upper() == "YES"
        )
        self.metadata_reviewed_var.set(
            decision.get("metadata_evidence_reviewed", "").upper() == "YES"
        )
        self.decision_var.set(self._row_to_choice(decision))
        self._update_status_label(decision)

    def _build_candidate_card(
        self,
        parent: ttk.Frame,
        column: int,
        row: dict[str, str],
    ) -> None:
        role = row["candidate_role"]
        selectable = role != "excluded_bone_only_context"

        if selectable:
            label_prefix = f"候选 {chr(ord('A') + column)}"
        else:
            label_prefix = "对照项（不可选）"

        kernel = row.get("convolution_kernel") or "<MISSING>"
        card = ttk.LabelFrame(
            parent,
            text=f"{label_prefix} · Kernel {kernel}",
            padding=8,
        )
        card.grid(row=0, column=column, sticky="nsew", padx=5, pady=2)

        if selectable:
            if row["case_type"] == "diagnostic_type_uncertain":
                value = f"INCLUDE::{row['series_uid']}"
                label = "✅ 这套可以作为研究输入"
            else:
                value = f"SELECT::{row['series_uid']}"
                label = f"✅ 选择候选 {chr(ord('A') + column)}"

            ttk.Radiobutton(
                card,
                text=label,
                value=value,
                variable=self.decision_var,
                command=self._set_dirty_status,
            ).pack(anchor="w", pady=(0, 5))
        else:
            ttk.Label(
                card,
                text="这套已被冻结规则排除，只用来帮助你理解，不要选择。",
            ).pack(anchor="w", pady=(0, 5))

        meta = (
            f"重建核 Kernel：{kernel}\n"
            f"层厚：{row.get('slice_thickness_mm', '')} mm　"
            f"像素间距：{row.get('pixel_spacing_row_mm', '')} × "
            f"{row.get('pixel_spacing_column_mm', '')} mm\n"
            f"覆盖范围：{row.get('coverage_mm', '')} mm　"
            f"切片数：{row.get('slice_count', '')}\n"
            f"SeriesDescription：{row.get('series_description', '')}\n"
            f"Series UID：{row['series_uid']}"
        )
        ttk.Label(
            card,
            text=meta,
            justify="left",
            wraplength=670,
        ).pack(anchor="w", pady=(0, 6))

        montage_rel = row.get("montage_path", "").strip()
        montage = self.review_dir / montage_rel if montage_rel else None

        if montage and montage.exists():
            try:
                image = Image.open(montage)
                image.thumbnail((670, 390), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.photo_refs.append(photo)
                ttk.Label(card, image=photo).pack(anchor="center", pady=(0, 6))
            except Exception as exc:
                ttk.Label(card, text=f"Montage 加载失败：{exc}").pack(anchor="w")
        else:
            ttk.Label(card, text="未找到 montage 图").pack(anchor="w")

        buttons = ttk.Frame(card)
        buttons.pack(fill="x", pady=(4, 0))

        if montage and montage.exists():
            ttk.Button(
                buttons,
                text="放大看这张图",
                command=lambda p=montage: self.open_path(p),
            ).pack(side="left")

        ttk.Button(
            buttons,
            text="打开完整 Series 文件夹",
            command=lambda uid=row["series_uid"]: self.open_full_series(uid),
        ).pack(side="left", padx=(8, 0))

    def _build_decision_radios(self, decision: dict[str, str]) -> None:
        for widget in self.radio_frame.winfo_children():
            widget.destroy()

        # 候选 Series 的选择按钮已经在图像卡片里，这里只放排除/暂缓。
        ttk.Radiobutton(
            self.radio_frame,
            text="❌ 两套都不适合作为研究输入 → 排除这个患者",
            value="EXCLUDE_PATIENT",
            variable=self.decision_var,
            command=self._set_dirty_status,
        ).pack(side="left", padx=(0, 18))

        ttk.Radiobutton(
            self.radio_frame,
            text="❓ 我看不出来 / 证据不够 → 暂缓（DEFER）",
            value="DEFER",
            variable=self.decision_var,
            command=self._set_dirty_status,
        ).pack(side="left")

    def _add_reason_button(self, text: str, command, col: int, row: int) -> None:
        ttk.Button(
            self.quick_reason_frame,
            text=text,
            command=command,
            style="Big.TButton",
        ).grid(row=row, column=col, sticky="ew", padx=4, pady=4)
        self.quick_reason_frame.columnconfigure(col, weight=1)

    def _build_quick_reason_buttons(self, decision: dict[str, str]) -> None:
        case_id = decision["case_id"]

        if decision["case_type"] == "diagnostic_type_uncertain":
            self._add_reason_button(
                "✅ 覆盖完整，图像也能正常看 → 可以纳入",
                lambda: self.quick_include_diag(),
                0, 0,
            )
            self._add_reason_button(
                "❌ 胸部覆盖明显不完整 → 排除",
                lambda: self.quick_exclude(
                    "该 Series 胸部解剖覆盖明显不足，不能稳定覆盖需要观察的肺部范围，"
                    "不适合作为本研究的诊断性胸部 CT 输入，因此排除该患者。"
                ),
                1, 0,
            )
            self._add_reason_button(
                "❌ 运动/其他伪影太明显 → 排除",
                lambda: self.quick_exclude(
                    "该 Series 可见明显运动或其他伪影，已经影响肺实质纹理和解剖结构观察，"
                    "不适合作为稳定的研究输入，因此排除该患者。"
                ),
                2, 0,
            )
            self._add_reason_button(
                "❓ 看不懂是不是正常诊断 CT → 暂缓",
                lambda: self.quick_defer(
                    "仅凭当前图像与 metadata 仍无法可靠确认该 Series 是否属于适合作为研究输入的"
                    "诊断性胸部 CT；对其重建用途、覆盖和伪影判断证据不足，因此暂缓决定并交由更有经验的复核者确认。"
                ),
                0, 1,
            )
            return

        # TIE-001 ~ TIE-012
        self._add_reason_button(
            "所选这套：肺纹理更清楚",
            lambda: self.append_selected_reason(
                "所选 Series 与另一候选相比，肺实质纹理和细小结构显示更清楚，"
                "更适合作为本研究的影像输入。"
            ),
            0, 0,
        )
        self._add_reason_button(
            "所选这套：噪点更少",
            lambda: self.append_selected_reason(
                "所选 Series 的图像噪声相对更少，肺实质观察更稳定，"
                "未见因噪声导致的明显质量下降。"
            ),
            1, 0,
        )
        self._add_reason_button(
            "所选这套：伪影更少",
            lambda: self.append_selected_reason(
                "所选 Series 的运动、条纹或其他明显伪影相对更少，"
                "对胸部解剖结构和肺实质观察影响较小。"
            ),
            2, 0,
        )
        self._add_reason_button(
            "所选这套：覆盖更完整",
            lambda: self.append_selected_reason(
                "所选 Series 的胸部解剖覆盖更完整，"
                "可见肺部范围更适合作为本研究的标准输入。"
            ),
            3, 0,
        )

        self._add_reason_button(
            "✅ 整体看，所选这套明显更合适",
            lambda: self.replace_selected_reason(
                "两套候选的基本技术条件可比较；所选 Series 的肺实质纹理显示更清楚，"
                "噪声和伪影对观察的影响更小，胸部覆盖可接受，因此更适合作为本研究输入。"
            ),
            0, 1,
        )
        self._add_reason_button(
            "≈ 两套看起来差不多 → 暂缓",
            lambda: self.quick_defer(
                "两套候选在胸部解剖覆盖、肺实质纹理、图像噪声和伪影方面看不出稳定且可重复的差异，"
                "现有图像与 metadata 证据不足以支持可靠选择，因此暂缓决定。"
            ),
            1, 1,
        )
        self._add_reason_button(
            "❓ 我们看不懂 / 拿不准 → 暂缓",
            lambda: self.quick_defer(
                "当前复核者无法依据现有图像和 metadata 对候选 Series 的诊断适用性、重建表现、"
                "噪声和伪影作出可靠区分，证据不足，因此暂缓决定并交由更有经验的复核者确认。"
            ),
            2, 1,
        )
        self._add_reason_button(
            "❌ 两套都有明显问题 → 排除",
            lambda: self.quick_exclude(
                "两套候选均存在影响肺实质观察的明显质量问题，例如噪声、运动或其他伪影，"
                "无法获得稳定可用的诊断性胸部 CT 研究输入，因此排除该患者。"
            ),
            3, 1,
        )

        if case_id == "TIE-012":
            self._add_reason_button(
                "TIE-012：两套很像重复序列 → 暂缓",
                lambda: self.quick_defer(
                    "两套候选的层厚、像素间距、覆盖和切片数量一致，图像表现也高度相似，"
                    "目前疑似重复 Series；在没有进一步比较几何位置、时间和对应像素前，"
                    "现有证据不足以支持选择，因此暂缓决定。"
                ),
                0, 2,
            )

    def selected_series_uid(self) -> str:
        choice = self.decision_var.get().strip()
        if choice.startswith("SELECT::") or choice.startswith("INCLUDE::"):
            return choice.split("::", 1)[1]
        return ""

    def ensure_selected_series(self) -> bool:
        if not self.selected_series_uid():
            messagebox.showwarning(
                "请先选择候选",
                "请先在上面的候选 A / 候选 B 里选择一套，然后再点这个理由按钮。",
            )
            return False
        return True

    def append_selected_reason(self, sentence: str) -> None:
        if not self.ensure_selected_series():
            return
        existing = self.reason_text.get("1.0", "end").strip()
        if sentence not in existing:
            new_text = (existing + " " + sentence).strip()
            self.reason_text.delete("1.0", "end")
            self.reason_text.insert("1.0", new_text)
        self._set_dirty_status()

    def replace_selected_reason(self, sentence: str) -> None:
        if not self.ensure_selected_series():
            return
        self.reason_text.delete("1.0", "end")
        self.reason_text.insert("1.0", sentence)
        self._set_dirty_status()

    def quick_defer(self, reason: str) -> None:
        self.decision_var.set("DEFER")
        self.reason_text.delete("1.0", "end")
        self.reason_text.insert("1.0", reason)
        self._set_dirty_status()

    def quick_exclude(self, reason: str) -> None:
        self.decision_var.set("EXCLUDE_PATIENT")
        self.reason_text.delete("1.0", "end")
        self.reason_text.insert("1.0", reason)
        self._set_dirty_status()

    def quick_include_diag(self) -> None:
        case_id = self.case_order[self.current_index]
        rows = [
            row for row in self.candidates_by_case[case_id]
            if row["candidate_role"] == "review_candidate"
        ]
        if not rows:
            messagebox.showerror("没有找到待确认 Series", "找不到 DIAG-001 的 review_candidate。")
            return
        self.decision_var.set(f"INCLUDE::{rows[0]['series_uid']}")
        self.reason_text.delete("1.0", "end")
        self.reason_text.insert(
            "1.0",
            "该 Series 可见胸部解剖覆盖较完整，肺实质和主要胸部结构能够连续观察，"
            "未见影响研究使用的明显运动或其他伪影；结合 metadata，现有证据支持其作为"
            "诊断性胸部 CT 研究输入，因此纳入该 Series。"
        )
        self._set_dirty_status()

    def clear_reason(self) -> None:
        self.reason_text.delete("1.0", "end")
        self._set_dirty_status()

    def _row_to_choice(self, row: dict[str, str]) -> str:
        decision = row.get("decision", "").strip()
        uid = row.get("selected_series_uid", "").strip()
        if decision == "SELECT_ONE_CANDIDATE" and uid:
            return f"SELECT::{uid}"
        if decision == "INCLUDE_REVIEW_SERIES" and uid:
            return f"INCLUDE::{uid}"
        if decision in {"EXCLUDE_PATIENT", "DEFER"}:
            return decision
        return ""

    def _choice_to_decision(self) -> tuple[str, str]:
        choice = self.decision_var.get().strip()
        if choice.startswith("SELECT::"):
            return "SELECT_ONE_CANDIDATE", choice.split("::", 1)[1]
        if choice.startswith("INCLUDE::"):
            return "INCLUDE_REVIEW_SERIES", choice.split("::", 1)[1]
        if choice in {"EXCLUDE_PATIENT", "DEFER"}:
            return choice, ""
        return "PENDING", ""

    def _set_dirty_status(self) -> None:
        self.status_var.set("未保存修改")

    def _validate_current_form(
        self,
        decision: str,
        selected_uid: str,
        reason: str,
        reviewer: str,
    ) -> list[str]:
        errors: list[str] = []

        if decision == "PENDING":
            errors.append("请先选择候选 A/B，或者选择“排除 / 暂缓”。")

        if decision in {"SELECT_ONE_CANDIDATE", "INCLUDE_REVIEW_SERIES"} and not selected_uid:
            errors.append("当前决定必须对应一套候选 Series。")

        if len(reason.strip()) < 20:
            errors.append("请点击至少一个“大白话理由”按钮，或手动写满 20 个字符以上。")

        if reason.strip() and not any(term.lower() in reason.lower() for term in EVIDENCE_TERMS):
            errors.append(
                "理由里需要包含可复核证据，例如：覆盖、重建、噪声、锐度、伪影、运动、重复、肺实质纹理。"
            )

        if any(re.search(pattern, reason, flags=re.IGNORECASE) for pattern in FORBIDDEN_REASON_PATTERNS):
            errors.append(
                "理由中出现了禁止依据：不能按 UID 顺序、随机、标签或模型结果来选择。"
            )

        if not reviewer.strip():
            errors.append("请填写复核人姓名。")

        if not self.image_reviewed_var.get():
            errors.append("请勾选“我已看过图像”。")

        if not self.metadata_reviewed_var.get():
            errors.append("请勾选“我已看过上面的参数”。")

        return errors

    def _ensure_backup(self) -> None:
        if self.backup_created:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.decisions_path.with_name(
            f"manual_review_decisions.backup_{stamp}.csv"
        )
        shutil.copy2(self.decisions_path, backup)
        self.backup_created = True

    def _atomic_write_decisions(self) -> None:
        self._ensure_backup()

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

    def save_current(self, show_success: bool = True) -> bool:
        case_id = self.case_order[self.current_index]
        row = self.decision_by_case[case_id]

        decision, selected_uid = self._choice_to_decision()
        reason = self.reason_text.get("1.0", "end").strip()
        reviewer = self.reviewer_var.get().strip()

        errors = self._validate_current_form(decision, selected_uid, reason, reviewer)
        if errors:
            messagebox.showwarning(
                "这一例还没填完整",
                "\n\n".join(f"• {e}" for e in errors),
            )
            return False

        row["decision"] = decision
        row["selected_series_uid"] = selected_uid
        row["reason"] = reason
        row["reviewer"] = reviewer
        row["reviewed_at_utc"] = utc_now()
        row["image_evidence_reviewed"] = "YES"
        row["metadata_evidence_reviewed"] = "YES"
        row["validation_status"] = "READY_FOR_VALIDATION"

        self._atomic_write_decisions()
        self._update_status_label(row)

        if show_success:
            messagebox.showinfo(
                "已保存",
                f"{case_id} 已保存。\n\n结果文件：\n{self.decisions_path}",
            )
        return True

    def _update_status_label(self, row: dict[str, str]) -> None:
        if (
            row.get("decision") not in {"", "PENDING"}
            and row.get("reason", "").strip()
            and row.get("reviewer", "").strip()
        ):
            self.status_var.set(
                f"已保存 · {row.get('decision')} · {row.get('reviewed_at_utc', '')}"
            )
        else:
            self.status_var.set("待完成")

    def save_and_next(self) -> None:
        if not self.save_current(show_success=False):
            return
        if self.current_index < len(self.case_order) - 1:
            self._load_case(self.current_index + 1)
        else:
            messagebox.showinfo(
                "已经看到最后一例",
                "13 个病例已经浏览完。\n\n现在可以点击右下角“运行最终校验”。"
            )

    def prev_case(self) -> None:
        if self.current_index > 0:
            self._load_case(self.current_index - 1)

    def open_full_series(self, series_uid: str) -> None:
        if series_uid in self.series_cache:
            found = self.series_cache[series_uid]
        else:
            found = None
            expected_name = f"CT_{series_uid}"
            if self.raw_dir.exists():
                for path in self.raw_dir.rglob(expected_name):
                    if path.is_dir():
                        found = path
                        break
            self.series_cache[series_uid] = found

        if found is None:
            messagebox.showwarning(
                "没找到完整 Series",
                f"没有在 data/full_raw 下找到：\nCT_{series_uid}",
            )
            return

        self.open_path(found)

    @staticmethod
    def open_path(path: Path) -> None:
        path = path.resolve()
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def run_validator(self) -> None:
        try:
            result = subprocess.run(
                [sys.executable, str(self.validator_path)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as exc:
            messagebox.showerror("校验运行失败", str(exc))
            return

        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        output = output.strip() or "(没有输出)"

        win = tk.Toplevel(self.tk)
        win.title("最终校验结果")
        win.geometry("900x620")

        text_box = tk.Text(win, wrap="word")
        text_box.pack(fill="both", expand=True, padx=10, pady=10)
        text_box.insert("1.0", output)
        text_box.configure(state="disabled")

        if result.returncode == 0:
            messagebox.showinfo(
                "校验通过",
                "13 例人工复核已通过现有 validator。\n"
                "下一步才是显式冻结正式 cohort。",
                parent=win,
            )
        elif result.returncode == 2:
            messagebox.showwarning(
                "还有未决病例",
                "存在 PENDING 或 DEFER。\n"
                "DEFER 本身不是错误，但表示这例还需要更有经验的人继续确认。",
                parent=win,
            )
        else:
            messagebox.showerror(
                "校验未通过",
                "有字段或理由不符合要求，请查看窗口里的详细输出。",
                parent=win,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="EpiLocate Rule B 人工复核 GUI v2")
    parser.add_argument(
        "--project-root",
        help="EpiLocate 项目根目录；脚本放在 scripts/ 下时通常不需要。",
    )
    args = parser.parse_args()

    try:
        project_root = find_project_root(args.project_root)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    root = tk.Tk()
    try:
        ReviewApp(root, project_root)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror("启动失败", str(exc))
        root.destroy()
        return 1

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
