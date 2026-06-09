"""
mission_progress.py
Système de progression en temps réel pour les missions Argos.

Architecture :
  - MissionProgress stocke l'état courant d'une mission en mémoire.
  - Workflow.run() appelle progress.start_step() / progress.finish_step() / progress.log()
  - L'endpoint SSE lit MissionProgress et streame les événements au frontend.
  - Un dict global _store { mission_id: MissionProgress } sert de registre.
"""

import json
import queue
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import Literal


StepStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class StepProgress:
    id:       str
    module:   str
    status:   StepStatus = "pending"
    logs:     list[str]  = field(default_factory=list)
    started:  str | None = None
    finished: str | None = None
    error:    str | None = None

    def to_dict(self) -> dict:
        return {
            "id":       self.id,
            "module":   self.module,
            "status":   self.status,
            "logs":     self.logs,
            "started":  self.started,
            "finished": self.finished,
            "error":    self.error,
        }


class MissionProgress:
    """
    Suivi temps réel d'une mission.
    Thread-safe : les méthodes publiques acquièrent un lock.
    """

    def __init__(self, mission_id: str, step_ids: list[tuple[str, str]]):
        """
        mission_id  : "#MSN-xxxxxxxx"
        step_ids    : [(step_id, module_id), ...]  — dans l'ordre d'exécution
        """
        self.mission_id = mission_id
        self.steps: list[StepProgress] = [
            StepProgress(id=sid, module=mod) for sid, mod in step_ids
        ]
        self.status: StepStatus  = "running"
        self.current_step: int   = 0          # index du step actif
        self._lock  = threading.Lock()
        self._queue: queue.Queue = queue.Queue()  # événements SSE en attente

    # ── Progression ──────────────────────────────────────────────────────────

    def start_step(self, step_id: str) -> None:
        with self._lock:
            step = self._step(step_id)
            if step:
                step.status  = "running"
                step.started = datetime.now().isoformat()
                self.current_step = self.steps.index(step)
            self._push("step_start", {"step_id": step_id})

    def finish_step(self, step_id: str, error: str | None = None) -> None:
        with self._lock:
            step = self._step(step_id)
            if step:
                step.status   = "failed" if error else "completed"
                step.finished = datetime.now().isoformat()
                step.error    = error
            self._push("step_end", {"step_id": step_id, "error": error})

    def log(self, step_id: str, message: str) -> None:
        """Ajoute une ligne de log à un step et la pousse au stream SSE."""
        with self._lock:
            step = self._step(step_id)
            if step:
                step.logs.append(message)
            self._push("log", {"step_id": step_id, "message": message})

    def finish_mission(self, status: StepStatus) -> None:
        with self._lock:
            self.status = status
            self._push("mission_end", {"status": status})

    # ── Lecture ───────────────────────────────────────────────────────────────

    @property
    def percent(self) -> int:
        done = sum(1 for s in self.steps if s.status in ("completed", "failed"))
        return int(done / len(self.steps) * 100) if self.steps else 0

    def snapshot(self) -> dict:
        """Retourne l'état complet pour l'initialisation du frontend."""
        with self._lock:
            return {
                "mission_id":   self.mission_id,
                "status":       self.status,
                "percent":      self.percent,
                "current_step": self.current_step,
                "steps":        [s.to_dict() for s in self.steps],
            }

    # ── SSE stream ────────────────────────────────────────────────────────────

    def events(self):
        """
        Générateur SSE — yield des chaînes "data: {...}\n\n".
        S'arrête quand la mission est terminée et la queue vidée.
        """
        # Snapshot initial pour synchroniser un client qui arrive en cours de route
        yield self._sse("snapshot", self.snapshot())

        while True:
            try:
                event_type, payload = self._queue.get(timeout=30)
            except queue.Empty:
                # Keepalive pour éviter que nginx/browser coupe la connexion
                yield ": keepalive\n\n"
                continue

            yield self._sse(event_type, payload)

            if event_type == "mission_end":
                break

    # ── Privé ─────────────────────────────────────────────────────────────────

    def _step(self, step_id: str) -> StepProgress | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def _push(self, event_type: str, payload: dict) -> None:
        """Enfile un événement SSE (appelé sous lock)."""
        self._queue.put((event_type, {**payload, "percent": self.percent}))

    @staticmethod
    def _sse(event_type: str, payload: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── Registre global ───────────────────────────────────────────────────────────

_store: dict[str, MissionProgress] = {}
_store_lock = threading.Lock()


def register(mission_id: str, step_ids: list[tuple[str, str]]) -> MissionProgress:
    """Crée et enregistre un tracker pour une mission."""
    prog = MissionProgress(mission_id, step_ids)
    with _store_lock:
        _store[mission_id] = prog
    return prog


def get(mission_id: str) -> MissionProgress | None:
    with _store_lock:
        return _store.get(mission_id)


def unregister(mission_id: str) -> None:
    with _store_lock:
        _store.pop(mission_id, None)