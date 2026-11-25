"""Thin wrapper around the RAPIDA CLI (https://github.com/UNDP-Data/rapida).

RAPIDA writes one layer per component into <project>/data/<project>.gpkg:
`polygons` plus `stats.<component>` (all polygon columns + the computed variables).
"""
import contextlib
import glob
import io
import os
import shlex
from pathlib import Path

import pandas as pd

# Used only when RAPIDA cannot be imported (offline preview); mirrors rapida/components/*/variables.py
FALLBACK_CATALOG = {
    "population": {**{v: "sum" for v in ["total", "male_total", "female_total", "child_total", "active_total",
                                        "elderly_total", "male_child", "female_child", "male_active", "female_active",
                                        "male_elderly", "female_elderly"]},
                   "dependency": None, "child_dependency": None, "elderly_dependency": None},
    "buildings": {"nbuildings": "count", "buildings_area": "sum"},
    "roads": {"roads_length": "sum", "roads_density": "density"},
    "elegrid": {"elegrid_length": "sum", "elegrid_density": "density"},
    "deprivation": {"depriv_mean": "mean", "depriv_min": "min", "depriv_max": "max"},
    "rwi": {"rwi_mean": "mean", "rwi_min": "min", "rwi_max": "max"},
    "gdp": {"gdp_sum": "sum", "gdp_mean": "mean", "gdp_min": "min", "gdp_max": "max"},
}
EXCLUDED = {"landuse", "ntl"}          # not auto-runnable / need extra inputs


ISOLATED = True       # run RAPIDA commands in a separate process (see run())


def available():
    # find_spec only: importing rapida.cli would patch the kernel's event loop (nest_asyncio)
    import importlib.util
    return importlib.util.find_spec("rapida") is not None


def initialized():
    try:
        from rapida.session import is_rapida_initialized
        with contextlib.redirect_stdout(io.StringIO()):
            return bool(is_rapida_initialized())
    except Exception:
        return False


def ensure_initialized(echo=print):
    """RAPIDA needs ~/.rapida/config.json (made by `rapida init`); no sign-in is needed for create/assess.
    -> (ok, message)."""
    if initialized():
        return True, "initialised"
    try:
        run("init", "--no-input", echo=echo)
    except Exception as e:
        return False, f"rapida init failed: {e}"
    return (True, "initialised") if initialized() else (False, "rapida init did not write ~/.rapida/config.json")


def kind_of(var, operator):
    if operator in ("sum", "count"):
        return "count"
    if operator in ("min", "max"):
        return operator
    return "mean"


def unit_of(var):
    if var.endswith("_length"):
        return "km"          # RAPIDA reports metres; converted to km
    if var == "buildings_area":
        return "m²"
    if var.startswith("gdp_sum"):
        return "USD"
    return ""


def catalog():
    """DataFrame(component, variable, title, operator, kind, unit) and whether it came from RAPIDA itself."""
    rows, live = [], False
    try:
        if available():
            ensure_initialized(echo=lambda *a: None)
        from rapida.session import Session
        with Session() as s:
            for comp in sorted(s.get_components()):
                if comp in EXCLUDED:
                    continue
                for var in sorted(s.get_variables(component=comp)):
                    cfg = s.get_variable(component=comp, variable=var) or {}
                    rows.append(dict(component=comp, variable=var, title=cfg.get("title", var),
                                     operator=cfg.get("operator")))
        live = bool(rows)
    except Exception:
        rows = []
    if not rows:
        for comp, vs in FALLBACK_CATALOG.items():
            for var, op in vs.items():
                rows.append(dict(component=comp, variable=var, title=var.replace("_", " ").capitalize(), operator=op))
    df = pd.DataFrame(rows)
    df["kind"] = [kind_of(v, o) for v, o in zip(df["variable"], df["operator"])]
    df["unit"] = df["variable"].map(unit_of)
    return df, live


@contextlib.contextmanager
def _keep_cwd():
    cwd = os.getcwd()
    try:
        yield
    finally:
        os.chdir(cwd)


_CHILD = r"""
import sys
from rapida.cli.run import run_cmd
run_cmd(sys.argv[1], sys.argv[2])
"""


def _clean(line):
    import re
    line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", line)        # ANSI colours / cursor moves
    return line.split("\r")[-1].rstrip()                       # progress redraws: keep the last state


def run(command, args, isolated=None, echo=print):
    """Run `rapida <command> <args>`.
    isolated=True (default): in a separate Python process of the same environment. RAPIDA applies nest_asyncio
    and calls asyncio.run() while downloading; inside the Jupyter kernel that nests in the kernel's own event
    loop ("coroutine Kernel.shell_main was never awaited", "Task was destroyed but it is pending!") and can drop
    widget messages or hang the kernel. A child process keeps both apart."""
    isolated = ISOLATED if isolated is None else isolated
    if not isolated:
        from rapida.cli.run import run_cmd
        with _keep_cwd():
            return run_cmd(command, args)
    import subprocess
    import sys
    env = dict(os.environ, PYTHONUNBUFFERED="1", TERM="dumb", COLUMNS="140", NO_COLOR="1",
               PYTHONPATH=os.pathsep.join([p for p in sys.path if p and os.path.isdir(p)]))
    proc = subprocess.Popen([sys.executable, "-u", "-c", _CHILD, command, args], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    last, tail = None, []
    for raw in proc.stdout:
        line = _clean(raw)
        if line and line != last:
            echo(line)
            last = line
            tail = (tail + [line])[-15:]
    rc = proc.wait()
    if rc != 0:
        hint = next((l for l in reversed(tail) if "Error" in l or "error" in l), tail[-1] if tail else "")
        raise RuntimeError(f"rapida {command} stopped with exit code {rc}: {hint}")


def is_project(path):
    """A RAPIDA project folder has a non-empty rapida.json (same rule as rapida.project.Project.is_valid)."""
    cfg = Path(path) / "rapida.json"
    return cfg.exists() and cfg.stat().st_size > 0


def project_state(path):
    """What exists on disk, checked without asking RAPIDA (which prints a warning for missing projects)."""
    path = Path(path)
    st = dict(path=path, folder=path.is_dir(), config=is_project(path), gpkg=None, layers=[])
    g = path / "data" / f"{path.name}.gpkg"
    if not g.exists():
        hits = sorted((path / "data").glob("*.gpkg")) if (path / "data").is_dir() else []
        g = hits[0] if hits else None
    if g is not None and g.exists():
        st["gpkg"] = g
        try:
            st["layers"] = stats_layers(g)
        except Exception:
            pass
    return st


def create_project(name, dest_folder, polygons_path):
    """Create the project unless a valid one already exists. A folder left by a failed attempt
    (no rapida.json) is renamed out of the way, because `rapida create` refuses existing folders."""
    import datetime as _dt
    path = Path(dest_folder) / name
    if is_project(path):
        print(f"Project already exists: {path} – reusing it")
        return path
    if path.exists():
        stale = path.with_name(f"{name}_incomplete_{_dt.datetime.now():%H%M%S}")
        path.rename(stale)
        print(f"⚠ {path.name} was left by an unfinished attempt (no rapida.json); moved to {stale.name}")
    ok, msg = ensure_initialized()
    if not ok:
        raise RuntimeError(msg)
    Path(dest_folder).mkdir(parents=True, exist_ok=True)
    try:
        run("create", f"{shlex.quote(name)} {shlex.quote(str(dest_folder))} -p {shlex.quote(str(polygons_path))}")
    except Exception as e:
        raise RuntimeError(f"rapida create failed: {e}") from e
    if not is_project(path):
        raise RuntimeError(
            f"RAPIDA did not finish creating the project at {path} (no rapida.json). See the RAPIDA messages in "
            "the log. Common causes: no write access to the folder; or the disk cannot lock "
            "GeoPackages (network share) – then set Folder to a local disk or to where earlier RAPIDA projects worked.")
    return path


def assess(project_path, selection, year, force=False):
    """selection: {component: [variables]}; runs one `rapida assess` per component."""
    if not is_project(project_path):
        raise RuntimeError(f"{project_path} is not a RAPIDA project yet – press 'Create project' first")
    for comp, vars_ in selection.items():
        if not vars_:
            continue
        a = f"-c {comp} " + " ".join(f"-v {v}" for v in vars_) + f" -y {int(year)} -p {shlex.quote(str(project_path))}"
        if force:
            a += " -f"
        print(f"\n▶ rapida assess {a}")
        run("assess", a)


def project_gpkg(project_path):
    """GeoPackage of a project folder (or a .gpkg path given directly)."""
    project_path = Path(project_path)
    if project_path.suffix.lower() == ".gpkg":
        if not project_path.exists():
            raise FileNotFoundError(f"{project_path} does not exist")
        return project_path
    if not is_project(project_path):
        raise FileNotFoundError(f"{project_path} is not a RAPIDA project (no rapida.json) – create it first, "
                                f"or point to an existing project")
    st = project_state(project_path)
    if st["gpkg"] is None:
        raise FileNotFoundError(f"No GeoPackage in {project_path / 'data'} – RAPIDA has not written results yet")
    return st["gpkg"]


def copy_back(project_path, dest, mode="gpkg"):
    """Copy a project from the fast temp folder to the output folder (contents only, no timestamps:
    network shares often refuse those). mode 'gpkg': rapida.json + data/*.gpkg ; 'all': the whole folder."""
    from .io_util import copy_file, copy_tree
    project_path, dest = Path(project_path), Path(dest)
    if mode == "all":
        return copy_tree(project_path, dest)
    copy_file(project_path / "rapida.json", dest / "rapida.json")
    for g in (project_path / "data").glob("*.gpkg"):
        copy_file(g, dest / "data" / g.name)
    return dest


def stats_layers(gpkg):
    import pyogrio
    return [str(n) for n, _ in pyogrio.list_layers(str(gpkg)) if str(n).startswith("stats.")]


def show_gui(project_path):
    from rapida_jupyter.util.assess_gui import assessment_gui
    return assessment_gui(project_path=str(project_path))
