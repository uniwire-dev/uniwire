"""Worker processes for the public MCP server: per-call wall-clock timeout with real termination.

The tool bodies that process a document run in a small pool of child processes (``spawn``: no state shared with
the server). A call that exceeds its time budget gets its worker killed and replaced; a worker that dies (memory
or CPU limit) is replaced as well. On Linux each worker also runs under ``RLIMIT_AS`` (address space) and a
per-call ``RLIMIT_CPU`` budget. The pool size is the concurrency limit: callers beyond it wait for a free worker
(at most the call timeout), then get a "server busy" error.

Only used in public mode (``uniwire-mcp --public``); local use calls :mod:`uniwire.llm.tools` in-process.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import sys
from typing import Any, Optional

from .tools import ToolError

#: Defaults of the public server (docs/llm.md, "Public server").
WORKERS = 2
TIMEOUT_S = 20.0
STARTUP_TIMEOUT_S = 60.0  # importing the library in a fresh worker (slow machines, cold caches); not part of TIMEOUT_S
MEMORY_BYTES = 768 * 1024 * 1024
CPU_S = 25  # CPU seconds per call (Linux), a backstop behind the wall-clock timeout


def _limit_memory(memory_bytes: Optional[int]) -> None:
    if not memory_bytes or not sys.platform.startswith("linux"):  # RLIMIT_AS is not enforced on macOS
        return
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except (ImportError, ValueError, OSError):  # pragma: no cover - platform without the limit
        pass


def _limit_cpu(cpu_s: Optional[int]) -> None:
    """Allow ``cpu_s`` more CPU seconds from now (SIGXCPU then ends the worker, which is replaced)."""
    if not cpu_s or not sys.platform.startswith("linux"):
        return
    try:
        import resource

        used = resource.getrusage(resource.RUSAGE_SELF)
        soft = int(used.ru_utime + used.ru_stime) + 1 + cpu_s
        hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
        if hard != resource.RLIM_INFINITY:
            soft = min(soft, hard)
        resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))
    except (ImportError, ValueError, OSError):  # pragma: no cover
        pass


def _worker(conn: Any, memory_bytes: Optional[int], cpu_s: Optional[int]) -> None:
    """Child process loop: receive (tool name, keyword arguments), send ("ok", result) or ("error", message)."""
    os.environ["UNIWIRE_MCP_PUBLIC"] = "1"
    _limit_memory(memory_bytes)
    from ..resolve import UniwireError
    from . import tools

    tools.PUBLIC = True
    conn.send(("ready", None))  # imports done: the call timeout must not include this start-up time
    while True:
        try:
            name, kwargs = conn.recv()
        except (EOFError, OSError):
            return
        _limit_cpu(cpu_s)
        try:
            reply: tuple[str, Any] = ("ok", getattr(tools, name)(**kwargs))
            # bounded here: the pipe sends a part shared by many nodes once, the server would write it out each time
            if tools.json_longer_than(reply[1], tools.MAX_RESULT_CHARS):
                reply = ("error", f"result too large for this server (at most {tools.MAX_RESULT_CHARS} characters)")
        except (tools.ToolError, UniwireError, KeyError, FileNotFoundError, ValueError) as e:
            reply = ("error", str(e))
        except RecursionError:
            reply = ("error", "document nested too deeply for this server")
        except MemoryError:
            reply = ("error", "out of memory: document too large for this server")
        except Exception as e:  # noqa: BLE001 - never leak a stack trace to the client
            reply = ("error", f"internal error ({type(e).__name__})")
        try:
            conn.send(reply)
        except Exception as e:  # noqa: BLE001 - unpicklable or oversized result
            conn.send(("error", f"internal error ({type(e).__name__})"))


class _Worker:
    def __init__(self, ctx: Any, memory_bytes: Optional[int], cpu_s: Optional[int]):
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_worker, args=(child, memory_bytes, cpu_s), daemon=True,
                                name="uniwire-worker")
        self.proc.start()
        child.close()
        self.ready = False

    def wait_ready(self, timeout: float) -> bool:
        """Wait for the start-up message of the child (library imported); False if it did not come."""
        if not self.ready and self.conn.poll(timeout):
            self.ready = self.conn.recv() == ("ready", None)
        return self.ready

    def kill(self) -> None:
        try:
            self.proc.kill()
            self.proc.join(5)
        finally:
            self.conn.close()


class WorkerPool:
    """``size`` worker processes; :meth:`call` runs ``uniwire.llm.tools.<name>(**kwargs)`` in one of them."""

    def __init__(self, size: int = WORKERS, timeout: float = TIMEOUT_S, memory_bytes: Optional[int] = MEMORY_BYTES,
                 cpu_s: Optional[int] = CPU_S, queue_timeout: Optional[float] = None):
        self.size, self.timeout, self.memory_bytes, self.cpu_s = size, timeout, memory_bytes, cpu_s
        self.queue_timeout = timeout if queue_timeout is None else queue_timeout  # wait for a free worker
        self._ctx = mp.get_context("spawn")
        self._idle: queue.Queue[_Worker] = queue.Queue()
        self._closed = False
        for _ in range(size):
            self._idle.put(self._spawn())

    def _spawn(self) -> _Worker:
        return _Worker(self._ctx, self.memory_bytes, self.cpu_s)

    def call(self, name: str, kwargs: dict[str, Any]) -> Any:
        """Result of the tool, or :class:`ToolError` (tool error, timeout, worker crash, server busy)."""
        if self._closed:
            raise ToolError("server shutting down")
        try:
            w = self._idle.get(timeout=self.queue_timeout)
        except queue.Empty:
            raise ToolError("server busy: too many concurrent requests, retry later") from None
        healthy = False
        try:
            if not w.proc.is_alive():
                w.kill()
                w = self._spawn()
            try:
                if not w.wait_ready(STARTUP_TIMEOUT_S):
                    raise ToolError("server starting, retry in a moment")
                w.conn.send((name, kwargs))
                if not w.conn.poll(self.timeout):
                    raise ToolError(f"timed out after {self.timeout:g} s: document too complex for this server")
                status, value = w.conn.recv()
            except (EOFError, OSError, BrokenPipeError):
                raise ToolError("the computation exceeded the resources of this server") from None
            healthy = True
        finally:
            if not healthy:  # timed out or died: kill it (real termination) and start a fresh one
                w.kill()
                w = self._spawn()
            if self._closed:
                w.kill()
            else:
                self._idle.put(w)
        if status == "error":
            raise ToolError(value)
        return value

    def close(self) -> None:
        """Stop accepting calls and kill the idle worker processes."""
        self._closed = True
        while True:
            try:
                self._idle.get_nowait().kill()
            except queue.Empty:
                return
