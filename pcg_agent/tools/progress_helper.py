"""Helper functions for creating progress tracker payloads.

Simple utilities to generate progress tracker data that renders
in the frontend via the show_progress tool.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

ProgressStatus = Literal["pending", "in-progress", "completed", "failed"]
ProgressOutcome = Literal["success", "failure", "cancelled"]


def create_progress_step(
    step_id: str,
    label: str,
    status: ProgressStatus,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a single progress step.
    
    Args:
        step_id: Unique identifier for the step.
        label: Display name for the step.
        status: Current status of the step.
        description: Optional description of what this step does.
    
    Returns:
        Dict representing a progress step.
    """
    step: dict[str, Any] = {
        "id": step_id,
        "label": label,
        "status": status,
    }
    if description:
        step["description"] = description
    return step


def create_progress_tracker(
    tracker_id: str,
    steps: list[dict[str, Any]],
    elapsed_time: float | None = None,
) -> dict[str, Any]:
    """Create a progress tracker payload without completion receipt.
    
    Args:
        tracker_id: Unique identifier for this progress tracker.
        steps: List of progress steps (use create_progress_step).
        elapsed_time: Optional elapsed time in milliseconds.
    
    Returns:
        Dict that can be returned as a tool result for show_progress.
    
    Example:
        >>> steps = [
        ...     create_progress_step("load", "Chargement FEC", "completed"),
        ...     create_progress_step("validate", "Validation", "in-progress"),
        ...     create_progress_step("analyze", "Analyse", "pending"),
        ... ]
        >>> create_progress_tracker("fec-upload-1", steps)
    """
    result: dict[str, Any] = {
        "id": tracker_id,
        "steps": steps,
    }
    if elapsed_time is not None:
        result["elapsedTime"] = elapsed_time
    return result


def create_progress_receipt(
    tracker_id: str,
    steps: list[dict[str, Any]],
    outcome: ProgressOutcome,
    summary: str,
    elapsed_time: float | None = None,
    identifiers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a completed progress tracker with receipt.
    
    Args:
        tracker_id: Unique identifier for this progress tracker.
        steps: List of progress steps (all should be completed/failed).
        outcome: Final outcome of the workflow.
        summary: Human-readable summary of the result.
        elapsed_time: Optional elapsed time in milliseconds.
        identifiers: Optional metadata identifiers.
    
    Returns:
        Dict that can be returned as a tool result for show_progress.
    
    Example:
        >>> steps = [
        ...     create_progress_step("step1", "Étape 1", "completed"),
        ...     create_progress_step("step2", "Étape 2", "completed"),
        ... ]
        >>> create_progress_receipt(
        ...     "analysis-1",
        ...     steps,
        ...     "success",
        ...     "Analyse terminée avec succès",
        ...     elapsed_time=2500
        ... )
    """
    choice: dict[str, Any] = {
        "outcome": outcome,
        "summary": summary,
        "at": datetime.utcnow().isoformat() + "Z",
    }
    if identifiers:
        choice["identifiers"] = identifiers
    
    result: dict[str, Any] = {
        "id": tracker_id,
        "steps": steps,
        "choice": choice,
    }
    if elapsed_time is not None:
        result["elapsedTime"] = elapsed_time
    
    return result


# Example usage for common PCG operations
def fec_upload_progress(status: ProgressStatus = "in-progress") -> dict[str, Any]:
    """Create progress tracker for FEC file upload.
    
    Args:
        status: Status of the validation step.
    
    Returns:
        Progress tracker payload for FEC upload.
    """
    steps = [
        create_progress_step("upload", "Téléchargement du fichier", "completed"),
        create_progress_step("parse", "Lecture du fichier Excel", "completed"),
        create_progress_step("validate", "Validation des écritures", status),
        create_progress_step("load", "Chargement en mémoire", "pending" if status != "completed" else "completed"),
    ]
    return create_progress_tracker("fec-upload", steps)


def waterfall_calculation_progress(current_step: int = 0) -> dict[str, Any]:
    """Create progress tracker for waterfall calculation.
    
    Args:
        current_step: Current step index (0-3).
    
    Returns:
        Progress tracker payload for waterfall calculation.
    """
    step_configs = [
        ("result", "Calcul du résultat net"),
        ("charges", "Agrégation des charges"),
        ("products", "Agrégation des produits"),
        ("waterfall", "Construction de la cascade"),
    ]
    
    steps = []
    for i, (step_id, label) in enumerate(step_configs):
        if i < current_step:
            status: ProgressStatus = "completed"
        elif i == current_step:
            status = "in-progress"
        else:
            status = "pending"
        steps.append(create_progress_step(step_id, label, status))
    
    return create_progress_tracker("waterfall-calc", steps)


def analysis_complete_receipt(
    operation: str,
    elapsed_ms: float,
    success: bool = True,
) -> dict[str, Any]:
    """Create a completion receipt for any analysis operation.
    
    Args:
        operation: Name of the operation (e.g., "Analyse de rentabilité").
        elapsed_ms: Elapsed time in milliseconds.
        success: Whether the operation succeeded.
    
    Returns:
        Progress tracker with receipt showing completion.
    """
    outcome: ProgressOutcome = "success" if success else "failure"
    summary = f"{operation} terminée avec succès" if success else f"{operation} échouée"
    
    steps = [
        create_progress_step("analyze", operation, "completed" if success else "failed"),
    ]
    
    return create_progress_receipt(
        "analysis-receipt",
        steps,
        outcome,
        summary,
        elapsed_time=elapsed_ms,
    )
