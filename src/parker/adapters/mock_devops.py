"""Deterministic Hermes CLI / devops mock (no network)."""

from __future__ import annotations

from typing import Any

from parker.contracts.domains import CLIResult


class MockHermesCLI:
    """Test-run and deploy mock with exit codes and output."""

    def __init__(self) -> None:
        self.projects: dict[str, dict[str, Any]] = {
            "parker-voice-lab": {
                "tests_exit_code": 0,
                "tests_stdout": "112 passed in 9.49s",
                "deploy_targets": {"dashboard": True},
            },
            "dashboard": {
                "tests_exit_code": 0,
                "tests_stdout": "42 passed in 1.2s",
                "deploy_targets": {"dashboard": True},
            },
        }
        self.fail_tests_for: set[str] = set()
        self.calls: list[dict[str, Any]] = []
        self.deployed: list[str] = []

    def reset(self) -> None:
        self.fail_tests_for.clear()
        self.calls.clear()
        self.deployed.clear()
        for project in self.projects.values():
            project["tests_exit_code"] = 0

    def inject_failing_tests(self, project: str) -> None:
        self.fail_tests_for.add(project)
        if project in self.projects:
            self.projects[project]["tests_exit_code"] = 1
            self.projects[project]["tests_stdout"] = "3 failed, 109 passed in 8.1s"

    def run_tests(self, project: str = "parker-voice-lab") -> CLIResult:
        self.calls.append({"command": "test", "project": project})
        info = self.projects.get(project)
        if info is None:
            return CLIResult(
                command="pytest",
                project=project,
                exit_code=2,
                stdout="",
                stderr=f"Unknown project: {project}",
                duration_ms=5.0,
            )
        exit_code = int(info["tests_exit_code"])
        stdout = str(info["tests_stdout"])
        if project in self.fail_tests_for:
            exit_code = 1
            stdout = "3 failed, 109 passed in 8.1s"
        return CLIResult(
            command="pytest -q",
            project=project,
            exit_code=exit_code,
            stdout=stdout,
            stderr="" if exit_code == 0 else "test failures detected",
            duration_ms=120.0,
        )

    def deploy_status(self, target: str = "dashboard") -> CLIResult:
        self.calls.append({"command": "deploy_status", "project": target})
        deployed = target in self.deployed
        return CLIResult(
            command="deploy status",
            project=target,
            exit_code=0,
            stdout="deployed" if deployed else "ready",
            duration_ms=20.0,
        )

    def deploy(self, target: str = "dashboard") -> CLIResult:
        self.calls.append({"command": "deploy", "project": target})
        known = any(target in p.get("deploy_targets", {}) for p in self.projects.values())
        if not known and target not in self.projects:
            return CLIResult(
                command="deploy",
                project=target,
                exit_code=2,
                stdout="",
                stderr=f"Unknown deploy target: {target}",
                duration_ms=10.0,
            )
        self.deployed.append(target)
        return CLIResult(
            command="deploy",
            project=target,
            exit_code=0,
            stdout=f"Deployed {target} successfully.",
            duration_ms=200.0,
        )
