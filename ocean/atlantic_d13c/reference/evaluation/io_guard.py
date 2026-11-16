"""Bounded readers for untrusted Atlantic d13C-DIC v0.5 outputs."""

from __future__ import annotations

import ast
import gzip
import io
import os
import re
import stat
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from netCDF4 import Dataset
from PIL import Image


DELIVERABLES = (
    "qc_observations.csv.gz",
    "reconstructed_points.csv.gz",
    "climatology.nc",
    "representative.png",
    "methodology.md",
    "build_product.py",
)
MAX_FILE_BYTES = {
    "qc_observations.csv.gz": 16 << 20,
    "reconstructed_points.csv.gz": 32 << 20,
    "climatology.nc": 96 << 20,
    "representative.png": 32 << 20,
    "methodology.md": 2 << 20,
    "build_product.py": 4 << 20,
}
MAX_UNCOMPRESSED_BYTES = {
    "qc_observations.csv.gz": 32 << 20,
    "reconstructed_points.csv.gz": 64 << 20,
}
QC_COLUMNS = (
    "observation_id",
    "expocode",
    "adjusted_d13c_dic_per_mille",
    "quality_flag",
)
POINT_COLUMNS = (
    "sample_id",
    "d13c_dic_per_mille",
    "uncertainty_per_mille",
    "quality_flag",
)


class AgentOutputError(ValueError):
    """A candidate-controlled delivery error that deterministically scores zero."""


def _ordinary(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()
    except OSError:
        return False


def validate_directory(output_dir: Path) -> None:
    try:
        entries = []
        with os.scandir(output_dir) as iterator:
            for entry in iterator:
                entries.append(Path(entry.path))
                if len(entries) > len(DELIVERABLES):
                    raise AgentOutputError("DELIVERABLE_COUNT")
    except AgentOutputError:
        raise
    except OSError as exc:
        raise AgentOutputError(f"OUTPUT_DIRECTORY_UNREADABLE:{type(exc).__name__}") from exc
    names = sorted(path.name for path in entries)
    if names != sorted(DELIVERABLES):
        raise AgentOutputError(f"DELIVERABLE_SET:{','.join(names)}")
    for path in entries:
        if not _ordinary(path):
            raise AgentOutputError(f"NON_ORDINARY:{path.name}")
        size = path.stat().st_size
        if size <= 0 or size > MAX_FILE_BYTES[path.name]:
            raise AgentOutputError(f"SIZE_BOUND:{path.name}:{size}")


def _magic(path: Path, length: int = 8) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            return os.read(descriptor, length)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise AgentOutputError(f"UNREADABLE:{path.name}:{type(exc).__name__}") from exc


def _bounded_gzip_csv(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    if _magic(path, 2) != b"\x1f\x8b":
        raise AgentOutputError(f"GZIP_MAGIC:{path.name}")
    try:
        with gzip.open(path, "rb") as stream:
            content = stream.read(MAX_UNCOMPRESSED_BYTES[path.name] + 1)
    except Exception as exc:
        raise AgentOutputError(f"GZIP_UNREADABLE:{path.name}:{type(exc).__name__}") from exc
    if len(content) > MAX_UNCOMPRESSED_BYTES[path.name]:
        raise AgentOutputError(f"GZIP_EXPANSION_BOUND:{path.name}")
    try:
        frame = pd.read_csv(
            io.BytesIO(content),
            dtype={columns[0]: "string", columns[-1]: "string"},
            keep_default_na=False,
        )
    except Exception as exc:
        raise AgentOutputError(f"CSV_UNREADABLE:{path.name}:{type(exc).__name__}") from exc
    if tuple(frame.columns) != columns:
        raise AgentOutputError(f"CSV_COLUMNS:{path.name}")
    return frame


def _strict_integer(series: pd.Series, name: str, path: Path) -> np.ndarray:
    text = series.astype(str)
    if not text.map(lambda value: re.fullmatch(r"-?[0-9]+", value) is not None).all():
        raise AgentOutputError(f"INTEGER_FORMAT:{path.name}:{name}")
    try:
        return text.astype(np.int64).to_numpy()
    except Exception as exc:
        raise AgentOutputError(f"INTEGER_RANGE:{path.name}:{name}") from exc


def load_qc(
    path: Path,
    expected_ids: np.ndarray,
    expected_expocodes: np.ndarray,
) -> dict[str, np.ndarray]:
    frame = _bounded_gzip_csv(path, QC_COLUMNS)
    if len(frame) != len(expected_ids):
        raise AgentOutputError("QC_ROW_COUNT")
    ids = _strict_integer(frame[QC_COLUMNS[0]], QC_COLUMNS[0], path)
    if not np.array_equal(ids, expected_ids):
        raise AgentOutputError("QC_SUPPORT_OR_ORDER")
    expocodes = frame["expocode"].astype(str).to_numpy()
    if not np.array_equal(expocodes, expected_expocodes):
        raise AgentOutputError("QC_EXPOCODE_SUPPORT")
    flags = _strict_integer(frame["quality_flag"], "quality_flag", path)
    if not np.isin(flags, (2, 3, 9)).all():
        raise AgentOutputError("QC_FLAG_DOMAIN")
    values = pd.to_numeric(frame["adjusted_d13c_dic_per_mille"], errors="coerce").to_numpy(float)
    valid = values != -9999.0
    if (
        not np.isfinite(values).all()
        or np.any(values[valid] < -2.0)
        or np.any(values[valid] > 3.0)
        or not np.isin(flags[valid], (2, 3)).all()
        or not np.isin(flags[~valid], (3, 9)).all()
    ):
        raise AgentOutputError("QC_VALUE_FLAG_CLOSURE")
    if int(valid.sum()) < 8_000 or np.unique(values[valid]).size < 500 or float(np.std(values[valid])) < 0.05:
        raise AgentOutputError("QC_DEGENERATE")
    return {"ids": ids, "expocodes": expocodes, "values": values, "flags": flags}


def load_points(path: Path, expected_ids: np.ndarray) -> dict[str, np.ndarray]:
    frame = _bounded_gzip_csv(path, POINT_COLUMNS)
    if len(frame) != len(expected_ids):
        raise AgentOutputError("POINT_ROW_COUNT")
    ids = _strict_integer(frame[POINT_COLUMNS[0]], POINT_COLUMNS[0], path)
    if not np.array_equal(ids, expected_ids):
        raise AgentOutputError("POINT_SUPPORT_OR_ORDER")
    flags = _strict_integer(frame["quality_flag"], "quality_flag", path)
    values = pd.to_numeric(frame["d13c_dic_per_mille"], errors="coerce").to_numpy(float)
    uncertainty = pd.to_numeric(frame["uncertainty_per_mille"], errors="coerce").to_numpy(float)
    if (
        not np.isin(flags, (2, 3)).all()
        or not np.isfinite(values).all()
        or not np.isfinite(uncertainty).all()
        or np.any(values < -2.0)
        or np.any(values > 3.0)
        or np.any(uncertainty < 0.07)
        or np.any(uncertainty > 1.0)
    ):
        raise AgentOutputError("POINT_VALUE_FLAG_DOMAIN")
    if np.unique(values).size < 1_000 or float(np.std(values)) < 0.05:
        raise AgentOutputError("POINT_DEGENERATE")
    if np.unique(uncertainty).size < 1 or float(np.median(uncertainty)) < 0.07:
        raise AgentOutputError("POINT_UNCERTAINTY_DEGENERATE")
    return {"ids": ids, "values": values, "uncertainty": uncertainty, "flags": flags}


def _reject_external_hdf5_links(path: Path) -> None:
    try:
        with h5py.File(path, "r") as handle:
            pending = [handle]
            visited: set[int] = set()
            while pending:
                group = pending.pop()
                address = int(h5py.h5o.get_info(group.id).addr)
                if address in visited:
                    continue
                visited.add(address)
                if len(visited) > 10_000:
                    raise AgentOutputError(f"HDF5_OBJECT_BOUND:{path.name}")
                for name in group:
                    link = group.get(name, getlink=True)
                    if isinstance(link, h5py.ExternalLink):
                        raise AgentOutputError(f"EXTERNAL_LINK:{path.name}:{name}")
                    value = group.get(name)
                    if isinstance(value, h5py.Group):
                        pending.append(value)
    except AgentOutputError:
        raise
    except Exception as exc:
        raise AgentOutputError(f"HDF5_LINK_SCAN:{type(exc).__name__}") from exc


def load_climatology(
    path: Path,
    expected_depth: np.ndarray,
    expected_lat: np.ndarray,
    expected_lon: np.ndarray,
    valid_mask: np.ndarray,
) -> dict[str, np.ndarray]:
    if _magic(path) != b"\x89HDF\r\n\x1a\n":
        raise AgentOutputError("NETCDF4_MAGIC")
    _reject_external_hdf5_links(path)
    try:
        with Dataset(path, "r") as dataset:
            dataset.set_auto_mask(False)
            if dataset.data_model != "NETCDF4" or dataset.groups:
                raise AgentOutputError("NETCDF_MODEL_OR_GROUPS")
            if tuple(dataset.dimensions) != ("depth", "lat", "lon"):
                raise AgentOutputError("NETCDF_DIMENSION_ORDER")
            if tuple(len(dataset.dimensions[name]) for name in dataset.dimensions) != (33, 180, 360):
                raise AgentOutputError("NETCDF_DIMENSION_SIZES")
            if set(dataset.variables) != {"depth", "lat", "lon", "d13c_dic", "uncertainty"}:
                raise AgentOutputError("NETCDF_VARIABLE_SET")
            expected_coordinates = {
                "depth": (expected_depth, "m"),
                "lat": (expected_lat, "degrees_north"),
                "lon": (expected_lon, "degrees_east"),
            }
            for name, (expected, units) in expected_coordinates.items():
                variable = dataset.variables[name]
                if variable.dtype != np.dtype("float64") or variable.dimensions != (name,):
                    raise AgentOutputError(f"COORDINATE_SCHEMA:{name}")
                if getattr(variable, "units", None) != units or not np.array_equal(variable[:], expected):
                    raise AgentOutputError(f"COORDINATE_VALUES:{name}")
            if getattr(dataset.variables["depth"], "positive", None) != "down":
                raise AgentOutputError("DEPTH_POSITIVE")
            result: dict[str, np.ndarray] = {}
            for name, units, low, high in (
                ("d13c_dic", "per_mille_VPDB", -2.0, 3.0),
                ("uncertainty", "per_mille", 0.07, 1.0),
            ):
                variable = dataset.variables[name]
                if variable.dtype != np.dtype("float32") or variable.dimensions != ("depth", "lat", "lon"):
                    raise AgentOutputError(f"GRID_VARIABLE_SCHEMA:{name}")
                fill = getattr(variable, "_FillValue", None)
                if fill is None or np.float32(fill) != np.float32(-9999.0) or getattr(variable, "units", None) != units:
                    raise AgentOutputError(f"GRID_VARIABLE_ATTRIBUTES:{name}")
                values = np.asarray(variable[:], dtype=np.float32)
                if (
                    not np.isfinite(values).all()
                    or np.any(values[~valid_mask] != np.float32(-9999.0))
                    or np.any(values[valid_mask] < low)
                    or np.any(values[valid_mask] > high)
                ):
                    raise AgentOutputError(f"GRID_MASK_OR_RANGE:{name}")
                result[name] = values
            grid_values = result["d13c_dic"][valid_mask].astype(float)
            if np.unique(grid_values).size < 1_000 or float(np.std(grid_values)) < 0.05:
                raise AgentOutputError("GRID_DEGENERATE")
            return result
    except AgentOutputError:
        raise
    except Exception as exc:
        raise AgentOutputError(f"NETCDF_UNREADABLE:{type(exc).__name__}") from exc


def validate_png(path: Path) -> dict[str, int]:
    if _magic(path) != b"\x89PNG\r\n\x1a\n":
        raise AgentOutputError("PNG_MAGIC")
    try:
        with Image.open(path) as image:
            width, height, image_format = image.width, image.height, image.format
            image.verify()
    except Exception as exc:
        raise AgentOutputError(f"PNG_UNREADABLE:{type(exc).__name__}") from exc
    if image_format != "PNG":
        raise AgentOutputError("PNG_FORMAT")
    return {"width": width, "height": height}


def validate_methodology(path: Path) -> dict[str, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AgentOutputError(f"METHODOLOGY_UNREADABLE:{type(exc).__name__}") from exc
    nonspace = [character for character in text if not character.isspace()]
    if not nonspace:
        raise AgentOutputError("METHODOLOGY_EMPTY")
    return {"characters": len(text), "unique_nonspace_characters": len(set(nonspace))}


def validate_source(path: Path) -> dict[str, int]:
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=path.name)
        nodes = list(ast.walk(tree))
    except (OSError, UnicodeError, SyntaxError, RecursionError, MemoryError) as exc:
        raise AgentOutputError(f"SOURCE_INVALID:{type(exc).__name__}") from exc
    functions = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in nodes)
    return {"characters": len(text), "ast_nodes": len(nodes), "functions": functions}
