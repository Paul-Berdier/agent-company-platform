"""Preuves d'arrêt Toolhelp simulées, sans agir sur des processus de la machine, puis un témoin réel sous Windows
(sur les seuls processus du test) : un processus plus ancien que la racine n'est jamais tenu pour son descendant."""

import ctypes
import os
import subprocess
import sys
import time

import pytest

from acp_poste.local_runner import _windows_force_terminate_tree

RACINE_NEE = 1_000
# Instants de création simulés (FILETIME) ; la racine (PID 1) est sortie.
NAISSANCES = {
    "stale_parent": {2: 500},              # parent déclaré = PID de la racine, mais né avant elle : étranger
    "reused_root": {1: 1_500, 2: 2_000},   # PID racine réattribué à un processus né à 1 500 : 2 est son enfant
    "reused_root_genuine": {1: 1_500, 2: 1_200},  # né entre la racine et la réattribution : vrai descendant
    "stale_parent_protected": {2: 500},    # étranger dont l'arrêt serait refusé : reconnu à sa seule naissance
}


class NativeFunction:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


class ProcessSnapshotApi:
    def __init__(self, scenario):
        self.scenario = scenario
        self.births = {2: 2_000, 3: 3_000, **NAISSANCES.get(scenario, {})}
        self.last_error = 0
        self.snapshots = 0
        self.entries = []
        self.position = 0
        self.opened = []
        self.terminated = []
        self.closed = []
        self.signaled = set() if scenario in {"active", "still_active"} or scenario in NAISSANCES else {2}
        for name in (
            "CreateToolhelp32Snapshot", "Process32FirstW", "Process32NextW",
            "OpenProcess", "TerminateProcess", "WaitForSingleObject", "CloseHandle", "GetProcessTimes",
        ):
            setattr(self, name, NativeFunction(getattr(self, name)))

    def CreateToolhelp32Snapshot(self, flags, pid):
        assert flags == 2 and pid == 0
        self.snapshots += 1
        # La racine a fini ; un descendant reste visible dans les snapshots,
        # même lorsqu'un handle épinglé prouve qu'il est déjà terminé.
        self.entries = [(99, 0), (2, 1)]
        if self.scenario == "missing" and self.snapshots > 1:
            self.entries = [(99, 0)]
        if self.scenario == "late_descendant" and self.snapshots > 1:
            self.entries.append((3, 2))
        return 1000 + self.snapshots

    def _entry(self, pointer):
        if self.position == len(self.entries):
            self.last_error = 18
            return False
        pid, parent = self.entries[self.position]
        pointer._obj.th32ProcessID = pid
        pointer._obj.th32ParentProcessID = parent
        return True

    def Process32FirstW(self, snapshot, pointer):
        self.position = 0
        return self._entry(pointer)

    def Process32NextW(self, snapshot, pointer):
        self.position += 1
        return self._entry(pointer)

    def OpenProcess(self, access, inherit, pid):
        assert pid in {1, 2, 3} and not inherit
        if pid == 1:
            # Propriétaire actuel du PID de la racine sortie : aucun, sauf réattribution.
            if 1 not in self.births:
                self.last_error = 87
                return 0
            assert access == 0x1000
        elif self.scenario in {"missing", "missing_still_listed", "access_denied"}:
            self.last_error = 5 if self.scenario == "access_denied" else 87
            return 0
        elif self.scenario == "stale_parent_protected" and access != 0x1000:
            self.last_error = 5
            return 0
        else:
            # Toute ouverture d'un candidat demande de quoi lire sa naissance.
            assert access & 0x1000
        # Le PID n'est jamais rouvert après épinglage : son identité ne peut
        # pas être remplacée par celle d'un autre processus lors des passes.
        assert pid not in self.opened
        self.opened.append(pid)
        return pid + 100

    def GetProcessTimes(self, handle, creation, exit_time, kernel, user):
        pid = handle - 100
        assert pid in self.opened
        valeur = self.births[pid]
        creation._obj.dwLowDateTime = valeur & 0xFFFFFFFF
        creation._obj.dwHighDateTime = valeur >> 32
        return True

    def WaitForSingleObject(self, handle, timeout):
        assert handle - 100 in self.opened
        if self.scenario == "wait_failed":
            return 0xFFFFFFFF
        return 0 if handle - 100 in self.signaled else 0x102

    def TerminateProcess(self, handle, code):
        assert code == 1
        pid = handle - 100
        self.terminated.append(pid)
        if self.scenario != "still_active":
            self.signaled.add(pid)
        return True

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return True


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("signaled", True), ("active", True), ("late_descendant", True),
        ("still_active", False), ("missing", True),
        ("missing_still_listed", False), ("access_denied", False),
        ("wait_failed", False), ("stale_parent", True), ("reused_root", True),
        ("reused_root_genuine", True), ("stale_parent_protected", True),
    ],
)
async def test_tree_cleanup_uses_pinned_handle_proof(monkeypatch, scenario, expected):
    api = ProcessSnapshotApi(scenario)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda value: setattr(api, "last_error", value), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: api.last_error, raising=False)

    assert await _windows_force_terminate_tree(1, include_root=False, root_birth=RACINE_NEE) is expected

    assert api.snapshots >= 1
    for pid in api.opened:
        assert api.closed.count(pid + 100) == 1
    if scenario == "signaled":
        assert api.opened == [2]
        assert api.terminated == []
    elif scenario == "active":
        assert api.terminated == [2]
    elif scenario == "late_descendant":
        assert api.snapshots >= 3
        assert api.opened == [2, 3]
        assert api.terminated == [3]
    elif scenario in {"stale_parent", "reused_root", "stale_parent_protected"}:
        # Étranger : ouvert en lecture de sa naissance, refermé, jamais terminé.
        assert 2 in api.opened and api.terminated == []
    elif scenario == "reused_root_genuine":
        assert api.terminated == [2]


async def test_racine_de_naissance_inconnue_ne_tue_aucun_descendant(monkeypatch):
    """Racine sortie sans instant de création relevé : aucun descendant n'est prouvable, rien n'est tué et l'arrêt
    n'est pas déclaré prouvé."""
    api = ProcessSnapshotApi("active")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda value: setattr(api, "last_error", value), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: api.last_error, raising=False)

    assert await _windows_force_terminate_tree(1, include_root=False) is False
    assert api.terminated == [] and 2 not in api.opened


@pytest.mark.skipif(os.name != "nt", reason="filiation Windows réelle (exécuté sur windows-2022)")
async def test_processus_plus_ancien_que_la_racine_epargne_puis_vrai_descendant_tue():
    """Témoin réel, sur les seuls processus du test : A lance B puis sort ; B déclare toujours le PID de A pour parent.
    Face à une racine « née après B » portant ce PID (cas d'un PID réattribué), B est épargné ; face à A, sa vraie
    racine, B est tué."""
    from ctypes import wintypes

    from acp_poste.local_runner import _windows_process_birth

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    # Interpréteur réel (pas le lanceur d'un venv, qui intercalerait un processus entre A et B).
    python = getattr(sys, "_base_executable", sys.executable)
    script = ("import subprocess, sys\n"
              "b = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],\n"
              "                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
              "print(b.pid, flush=True)\n"
              "sys.stdin.readline()\n")
    a = subprocess.Popen([python, "-I", "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    poignee_b = None
    try:
        pid_b = int(a.stdout.readline())
        naissance_a = _windows_process_birth(a.pid)  # A vivante, épinglée par le handle de Popen
        assert naissance_a is not None
        # SYNCHRONIZE | PROCESS_TERMINATE : B reste épinglé (son PID ne peut pas être réattribué) pendant le test.
        poignee_b = kernel32.OpenProcess(0x00100000 | 0x0001, False, pid_b)
        assert poignee_b
        a.communicate("\n", timeout=15)
        assert a.returncode == 0

        maintenant = time.time_ns() // 100 + 116_444_736_000_000_000
        assert await _windows_force_terminate_tree(a.pid, include_root=False, root_birth=maintenant) is True
        assert kernel32.WaitForSingleObject(poignee_b, 0) == 0x102, "B, plus ancien que la racine, a été tué"

        assert await _windows_force_terminate_tree(a.pid, include_root=False, root_birth=naissance_a) is True
        assert kernel32.WaitForSingleObject(poignee_b, 5_000) == 0, "B, vrai descendant de A, a survécu"
    finally:
        if poignee_b:
            if kernel32.WaitForSingleObject(poignee_b, 0) != 0:
                kernel32.TerminateProcess(poignee_b, 1)
            kernel32.CloseHandle(poignee_b)
        if a.poll() is None:
            a.kill()
            a.wait(10)
