from __future__ import annotations

import csv
import html
import io
import json
import math
import os
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.errors import AppError
from app.persistence.export_repository import ExportRepository
from app.tasks.models import TaskState


class ExportCancelled(RuntimeError):
    pass


def _csv_text(headers: list[str], rows: list[list[Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()


def _zip_entry(archive: zipfile.ZipFile, name: str, content: str) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, content.encode("utf-8"))


def _community_positions(snapshot: dict[str, Any], width: int, height: int) -> dict[int, tuple[float, float]]:
    communities = snapshot["communityMetrics"]
    radius = min(width, height) * 0.34
    center = (width / 2, height / 2)
    return {
        item["communityId"]: (
            center[0] + radius * math.cos(2 * math.pi * index / max(1, len(communities)) - math.pi / 2),
            center[1] + radius * math.sin(2 * math.pi * index / max(1, len(communities)) - math.pi / 2),
        )
        for index, item in enumerate(communities)
    }


def _community_label(snapshot: dict[str, Any], community: dict[str, Any]) -> str:
    annotation = next(
        (item for item in snapshot["annotations"] if item["communityId"] == community["communityId"]),
        None,
    )
    return (annotation or {}).get("name") or community.get("suggestedName") or f"Community {community['communityId']}"


def _svg(snapshot: dict[str, Any], width: int = 1400, height: int = 900) -> str:
    positions = _community_positions(snapshot, width, height)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f3f6fa"/>',
        f'<text x="48" y="56" font-family="sans-serif" font-size="26" fill="#14213d">{html.escape(snapshot["analysis"]["name"])}</text>',
    ]
    for edge in snapshot["communityEdges"]:
        source = positions.get(edge["sourceCommunity"])
        target = positions.get(edge["targetCommunity"])
        if not source or not target:
            continue
        width_value = max(1.0, min(9.0, math.sqrt(edge["totalWeight"])))
        lines.append(
            f'<line x1="{source[0]:.2f}" y1="{source[1]:.2f}" x2="{target[0]:.2f}" y2="{target[1]:.2f}" '
            f'stroke="#7b879e" stroke-width="{width_value:.2f}" opacity="0.65"/>'
        )
    for community in snapshot["communityMetrics"]:
        x, y = positions[community["communityId"]]
        radius = max(24.0, min(68.0, 18 + math.sqrt(community["nodeCount"]) * 6))
        label = html.escape(_community_label(snapshot, community))
        lines.extend([
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="#1d3557" stroke="#e76f51" stroke-width="3"/>',
            f'<text x="{x:.2f}" y="{y - 2:.2f}" text-anchor="middle" font-family="sans-serif" font-size="14" fill="white">{label}</text>',
            f'<text x="{x:.2f}" y="{y + 18:.2f}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#dce6f2">{community["nodeCount"]} objektum</text>',
        ])
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


class ExportService:
    def __init__(self, repository: ExportRepository, export_dir: Path) -> None:
        self.repository = repository
        self.export_dir = export_dir

    @staticmethod
    def _check_cancelled(cancelled: threading.Event) -> None:
        if cancelled.is_set():
            raise ExportCancelled("Export was cancelled.")

    def _write_json(self, path: Path, snapshot: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(snapshot, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            output.write("\n")

    def _write_csv(self, path: Path, snapshot: dict[str, Any]) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            _zip_entry(archive, "objects.csv", _csv_text(
                ["id", "owner", "name", "object_type", "status", "is_external"],
                [[item["id"], item["owner"], item["name"], item["objectType"], item["status"], item["isExternal"]] for item in snapshot["nodes"]],
            ))
            _zip_entry(archive, "relationships.csv", _csv_text(
                ["id", "source", "target", "relationship_type", "confidence", "origin"],
                [[item["id"], item["source"], item["target"], item["relationshipType"], item["confidence"], item["origin"]] for item in snapshot["relationships"]],
            ))
            _zip_entry(archive, "memberships.csv", _csv_text(
                ["object_id", "community_id", "stability"],
                [[item["objectId"], item["communityId"], item["stability"]] for item in snapshot["memberships"]],
            ))
            _zip_entry(archive, "community_metrics.csv", _csv_text(
                ["community_id", "suggested_name", "node_count", "internal_weight", "external_weight", "density", "conductance", "stability"],
                [[item["communityId"], item.get("suggestedName"), item["nodeCount"], item["internalWeight"], item["externalWeight"], item["internalDensity"], item["conductance"], item.get("stability")] for item in snapshot["communityMetrics"]],
            ))
            _zip_entry(archive, "centrality.csv", _csv_text(
                ["object_id", "metric", "value", "metadata_json"],
                [[item["objectId"], item["metric"], item["value"], json.dumps(item["metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))] for item in snapshot["centrality"]],
            ))
            _zip_entry(archive, "analysis.json", json.dumps(snapshot["analysis"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    def _write_png(self, path: Path, snapshot: dict[str, Any]) -> None:
        width, height = 1400, 900
        image = Image.new("RGB", (width, height), "#f3f6fa")
        draw = ImageDraw.Draw(image)
        positions = _community_positions(snapshot, width, height)
        draw.text((48, 32), snapshot["analysis"]["name"], fill="#14213d")
        for edge in snapshot["communityEdges"]:
            source = positions.get(edge["sourceCommunity"])
            target = positions.get(edge["targetCommunity"])
            if source and target:
                draw.line((*source, *target), fill="#7b879e", width=max(1, min(9, round(math.sqrt(edge["totalWeight"])))))
        for community in snapshot["communityMetrics"]:
            x, y = positions[community["communityId"]]
            radius = max(24, min(68, round(18 + math.sqrt(community["nodeCount"]) * 6)))
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#1d3557", outline="#e76f51", width=3)
            label = _community_label(snapshot, community)
            box = draw.textbbox((0, 0), label)
            draw.text((x - (box[2] - box[0]) / 2, y - 7), label, fill="white")
        image.save(path, format="PNG", optimize=False, compress_level=9)

    def run(
        self,
        export_id: str,
        analysis_id: str,
        export_format: str,
        report: Callable[..., None],
        cancelled: threading.Event,
    ) -> None:
        if not self.repository.mark_running(export_id):
            raise ExportCancelled("Export was cancelled before it started.")
        report(TaskState.EXPORTING, message=f"Generating deterministic {export_format} export.")
        snapshot = self.repository.snapshot(analysis_id)
        if snapshot is None:
            raise AppError("ANALYSIS_NOT_COMPLETE", "Only completed analyses can be exported.", status_code=409)
        self._check_cancelled(cancelled)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        extension = {"JSON": "json", "CSV": "zip", "SVG": "svg", "PNG": "png"}[export_format]
        content_type = {
            "JSON": "application/json", "CSV": "application/zip",
            "SVG": "image/svg+xml", "PNG": "image/png",
        }[export_format]
        filename = f"analysis-{analysis_id}.{extension}"
        target = self.export_dir / f"{export_id}.{extension}"
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            if export_format == "JSON":
                self._write_json(temporary, snapshot)
            elif export_format == "CSV":
                self._write_csv(temporary, snapshot)
            elif export_format == "SVG":
                temporary.write_text(_svg(snapshot), encoding="utf-8", newline="\n")
            else:
                self._write_png(temporary, snapshot)
            self._check_cancelled(cancelled)
            os.replace(temporary, target)
            if not self.repository.mark_success(
                export_id, filename=filename, content_type=content_type, file_path=target,
            ):
                target.unlink(missing_ok=True)
                raise ExportCancelled("Export was cancelled before publication.")
        finally:
            temporary.unlink(missing_ok=True)
