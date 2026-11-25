"""RAPIDA sign-in for a web app (no terminal prompt).

RAPIDA keeps an encrypted token in ~/.rapida of the OS user running the server and refreshes it on its own
(rapida/az/surgeauth.py). Only when there is no usable token does it need e-mail, password and the
Microsoft Authenticator number. It reads e-mail and password from RAPIDA_USER / RAPIDA_PASSWORD, so the
sign-in runs RAPIDA's own code in a child process with those two variables set for that process only:
nothing is written to disk or printed by this module.
"""
import json
import os
import re
import subprocess
import sys

_STATUS = r"""
import json, datetime
try:
    from rapida.az.surgeauth import SurgeTokenCredential
except Exception as e:
    print(json.dumps({"installed": False, "error": str(e)})); raise SystemExit
c = SurgeTokenCredential()
t = c.token or {}
secs = None
if t.get("expires_at"):
    secs = int((datetime.datetime.fromtimestamp(t["expires_at"]) - datetime.datetime.now()).total_seconds())
print(json.dumps({"installed": True, "token": bool(t), "expires_in": secs,
                  "refreshable": bool(t.get("refresh_token")), "cache": c._cache_file_}))
"""

_SIGN_IN = r"""
import logging, sys
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s", force=True)
from rapida.az.surgeauth import SurgeTokenCredential
c = SurgeTokenCredential()
c.get_token(SurgeTokenCredential.STORAGE_SCOPE)
print("RAPIDA_SIGNED_IN", flush=True)
"""

MFA = re.compile(r"MFA input code is:\s*(\d+)")


def _env(**extra):
    """Child environment that sees the same packages as this kernel."""
    return dict(os.environ, PYTHONUNBUFFERED="1",
                PYTHONPATH=os.pathsep.join(p for p in sys.path if p and os.path.isdir(p)), **extra)


def token_status(timeout=60):
    """{'installed', 'token', 'expires_in', 'refreshable'} – checked in a child process, never prompts."""
    try:
        r = subprocess.run([sys.executable, "-c", _STATUS], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, env=_env())
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"installed": None, "error": f"{type(e).__name__}: {e}"}


def describe(st):
    """(ok, text) for the status panel."""
    if not st.get("installed"):
        return False, "RAPIDA is not installed in this Python environment." if st.get("installed") is False else \
            f"Could not check the RAPIDA sign-in ({st.get('error', 'unknown error')})."
    if not st.get("token"):
        return False, "Not signed in to RAPIDA yet."
    secs = st.get("expires_in") or 0
    if secs > 15 * 60:
        return True, f"Signed in to RAPIDA (token valid for another {secs // 60} min, renewed automatically)."
    if st.get("refreshable"):
        return True, "Signed in to RAPIDA (the token is renewed automatically on the next run)."
    return False, "The RAPIDA sign-in has expired."


def sign_in(email, password, echo=print, on_mfa=None, timeout=300):
    """Run RAPIDA's own login with these credentials. Returns (ok, message).
    on_mfa(number) is called when Microsoft shows the number to type in the Authenticator app."""
    env = _env(RAPIDA_USER=email.strip(), RAPIDA_PASSWORD=password)
    try:
        p = subprocess.Popen([sys.executable, "-u", "-c", _SIGN_IN], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, env=env)
    finally:
        env = None                                         # drop our copy of the password
    ok, last = False, ""
    try:
        for line in p.stdout:
            line = line.rstrip()
            if not line:
                continue
            m = MFA.search(line)
            if m and on_mfa:
                on_mfa(m.group(1))
            if "RAPIDA_SIGNED_IN" in line:
                ok = True
                continue
            if password and password in line:              # never show a line that would contain it
                continue
            last = line
            echo(line)
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        return False, "The sign-in timed out (no approval in the Authenticator app?)."
    if ok and p.returncode == 0:
        return True, "Signed in to RAPIDA."
    return False, f"Sign-in failed: {last or f'exit code {p.returncode}'}"
