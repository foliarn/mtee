"""Run work as a job and hand its result back on the graphical thread (AGENTS.md, Architecture).

Every network call, hash and database write of the plugin runs through here. ``done`` gets the
result, or the error, on the graphical thread; a failing task is raised again, so Tasks shows
its readable sentence.
"""

from __future__ import annotations

from collections.abc import Callable

from mtee.plugins.api import JobContext, JobId, PluginContext


def submit[T](
    context: PluginContext,
    label: str,
    work: Callable[[JobContext], T],
    done: Callable[[T | None, BaseException | None], None],
    *,
    visible: bool = True,
) -> JobId:
    """Submit ``work`` as a job; ``done(result, error)`` runs on the graphical thread."""

    def task(job: JobContext) -> None:
        try:
            result = work(job)
        except BaseException as error:
            failure = error
            context.run_on_gui(lambda: done(None, failure))
            raise
        context.run_on_gui(lambda: done(result, None))

    return context.jobs.submit(task, label=label, visible=visible)
