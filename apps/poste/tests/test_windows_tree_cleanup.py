"""Preuves d'arrêt Toolhelp simulées, sans agir sur des processus de la machine."""

import ctypes

import pytest

from acp_poste.local_runner import _windows_force_terminate_tree


class NativeFunction:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


class ProcessSnapshotApi:
    def __init__(self, scenario):
        self.scenario = scenario
        self.last_error = 0
        self.snapshots = 0
        self.entries = []
        self.position = 0
        self.opened = []
        self.terminated = []
        self.closed = []
        self.signaled = set() if scenario in {"active", "still_active"} else {2}
        for name in (
            "CreateToolhelp32Snapshot", "Process32FirstW", "Process32NextW",
            "OpenProcess", "TerminateProcess", "WaitForSingleObject", "CloseHandle",
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
        assert pid in {2, 3} and not inherit
        if self.scenario in {"missing", "missing_still_listed", "access_denied"}:
            self.last_error = 5 if self.scenario == "access_denied" else 87
            return 0
        # Le PID n'est jamais rouvert après épinglage : son identité ne peut
        # pas être remplacée par celle d'un autre processus lors des passes.
        assert pid not in self.opened
        self.opened.append(pid)
        return pid + 100

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
        ("wait_failed", False),
    ],
)
async def test_tree_cleanup_uses_pinned_handle_proof(monkeypatch, scenario, expected):
    api = ProcessSnapshotApi(scenario)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda value: setattr(api, "last_error", value), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: api.last_error, raising=False)

    assert await _windows_force_terminate_tree(1, include_root=False) is expected

    assert api.snapshots >= 2
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
