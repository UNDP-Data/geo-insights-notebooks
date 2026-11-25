"""Safe GeoPackage writing.

A GeoPackage is an SQLite database. On network-mounted folders (SMB/CIFS, some NFS or Azure file
shares) SQLite often cannot lock the file and GDAL fails with "Failed to start transaction".
So every GeoPackage is built in a local temporary folder and then copied into place: the copy is
a plain file copy and needs no database locking.
"""
import datetime as dt
import shutil
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

SIDECARS = ("-journal", "-wal", "-shm")


def copy_file(src, dst):
    """Copy contents only. shutil.copy2/copytree also copy timestamps and permissions, which network shares
    (SMB/CIFS, Azure Files, blobfuse…) often refuse with 'Operation not permitted'."""
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return Path(dst)


def copy_tree(src, dst):
    """Recursive copy of contents only (see copy_file); merges into an existing folder."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        t = dst / p.relative_to(src)
        if p.is_dir():
            t.mkdir(parents=True, exist_ok=True)
        elif p.is_file():
            copy_file(p, t)
    return dst


def _write_layer(obj, path, layer):
    if isinstance(obj, gpd.GeoDataFrame):
        try:
            obj.to_file(path, layer=layer, driver="GPKG", engine="pyogrio")
        except Exception:
            obj.to_file(path, layer=layer, driver="GPKG", engine="fiona")
    else:
        import pyogrio
        pyogrio.write_dataframe(pd.DataFrame(obj), str(path), layer=layer, driver="GPKG")


def _remove(path):
    for p in [Path(str(path) + s) for s in SIDECARS] + [Path(path)]:
        if p.exists():
            p.unlink()


def place(tmp_file, dest):
    """Copy a finished file into dest. If dest is locked by another program, use a new name."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        _remove(dest)
        copy_file(tmp_file, dest)
        return dest
    except OSError as e:
        alt = dest.with_name(f"{dest.stem}_{dt.datetime.now():%H%M%S}{dest.suffix}")
        copy_file(tmp_file, alt)
        print(f"⚠ {dest.name} could not be replaced ({e}); written as {alt.name} instead. "
              f"Close any program that has the old file open (QGIS, ArcGIS, another notebook).")
        return alt


def write_gpkg(layers, dest):
    """layers: list of (GeoDataFrame | DataFrame, layer_name). Returns the path actually written."""
    tmpdir = Path(tempfile.mkdtemp(prefix="rapida_onepager_"))
    try:
        tmp = tmpdir / Path(dest).name
        for obj, name in layers:
            _write_layer(obj, tmp, name)
        return place(tmp, dest)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def gpkg_to_gdb(gpkg, gdb_dest):
    """Copy every layer of a GeoPackage into an Esri File Geodatabase (GDAL 3.6+), built locally first."""
    import pyogrio
    tmpdir = Path(tempfile.mkdtemp(prefix="rapida_onepager_"))
    try:
        tmp = tmpdir / Path(gdb_dest).name
        for name, _ in pyogrio.list_layers(str(gpkg)):
            df = pyogrio.read_dataframe(str(gpkg), layer=name)
            # File GDB stores Integer64 as Float64 unless it targets ArcGIS Pro 3.2+: use 32-bit where values fit
            for c in df.columns:
                if str(df[c].dtype) == "int64" and (df[c].empty or df[c].abs().max() < 2 ** 31):
                    df[c] = df[c].astype("int32")
            pyogrio.write_dataframe(df, str(tmp), layer=name, driver="OpenFileGDB")
        gdb_dest = Path(gdb_dest)
        if gdb_dest.exists():
            shutil.rmtree(gdb_dest, ignore_errors=True)
        copy_tree(tmp, gdb_dest)
        return gdb_dest
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
