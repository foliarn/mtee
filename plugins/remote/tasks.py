"""Run work as a job and hand its result back on the graphical thread (AGENTS.md, Architecture).

Every network call, hash and database write of the plugin runs through here. ``done`` gets the
result, or the error, on the graphical thread; a failing task is raised again, so the Tasks window
shows its readable sentence.

A visible job ends with one sentence in the notifications of the header (MTEE 0.3.0). ``summary``
writes it from the job's result; without a result (a failure, a cancel) the core writes its own
sentence from the label and the error, so ``done`` does not announce the outcome a second time.
"""

from __future__ import annotations

from collections.abc import Callable

from mtee.plugins.api import JobContext, JobId, PluginContext, SummaryFn


def submit[T](
    context: PluginContext,
    label: str,
    work: Callable[[JobContext], T],
    done: Callable[[T | None, BaseException | None], None],
    *,
    visible: bool = True,
    summary: Callable[[T], str] | None = None,
) -> JobId:
    """Submit ``work`` as a job; ``done(result, error)`` runs on the graphical thread.

    ``summary(result)`` gives the sentence the job ends with; it is asked only after ``work``
    returned, on the graphical thread.
    """
    holder: list[T] = []

    def task(job: JobContext) -> None:
        try:
            result = work(job)
        except BaseException as error:
            failure = error
            context.run_on_gui(lambda: done(None, failure))
            raise
        holder.append(result)
        context.run_on_gui(lambda: done(result, None))

    if summary is None:
        return context.jobs.submit(task, label=label, visible=visible)
    return context.jobs.submit(
        task, label=label, visible=visible, summary=result_summary(holder, summary)
    )


def result_summary[T](holder: list[T], summary: Callable[[T], str]) -> SummaryFn:
    """The core's summary function: ``summary`` of the result once there is one, else nothing.

    An empty sentence makes the core write its generic one (``<label>: failed (...)``).
    """

    def sentence(_status: object) -> str:
        return summary(holder[0]) if holder else ""

    return sentence
