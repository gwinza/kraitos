"""Scientific elimination — weak World Models die, strong models survive."""

from __future__ import annotations

from dataclasses import replace

from reality.reality_models import DivisionInvestigation, WorldModel

ELIMINATION_THRESHOLD = 28.0
WEAKEN_THRESHOLD = 42.0


class EliminationEngine:
    """
    Apply division investigations to update World Model explanatory power.

    The Council never searches for confirmation — it searches for elimination.
    """

    def eliminate(
        self,
        models: tuple[WorldModel, ...],
        investigations: tuple[DivisionInvestigation, ...],
    ) -> tuple[WorldModel, ...]:
        updated: list[WorldModel] = []
        for model in models:
            model_invs = [i for i in investigations if i.world_model_id == model.model_id]
            power = model.explanatory_power
            strengthening: list[str] = list(model.strengthening_evidence)
            weakening: list[str] = list(model.weakening_evidence)
            unexplained: list[str] = list(model.unexplained)

            for inv in model_invs:
                if inv.strengthens:
                    power += inv.confidence * 0.08
                    strengthening.extend(inv.evidence)
                elif inv.weakens:
                    power -= inv.confidence * 0.12
                    weakening.extend(inv.evidence)
                if inv.unexplained:
                    unexplained.append(inv.unexplained)
                    power -= 3.0

            power = max(0.0, min(100.0, power))
            status = model.status
            if power < ELIMINATION_THRESHOLD:
                status = "eliminated"
            elif power < WEAKEN_THRESHOLD:
                status = "weakened"
            else:
                status = "active"

            updated.append(
                replace(
                    model,
                    explanatory_power=round(power, 2),
                    strengthening_evidence=tuple(strengthening[:8]),
                    weakening_evidence=tuple(weakening[:8]),
                    unexplained=tuple(unexplained[:6]),
                    status=status,  # type: ignore[arg-type]
                )
            )
        return tuple(updated)


class ConvergenceEngine:
    """
    Reality Convergence — dominant model emerges from explanatory power.

    No voting. No majority rule. No confirmation meeting.
    """

    def converge(self, models: tuple[WorldModel, ...]) -> tuple[WorldModel, ...]:
        active = [m for m in models if m.status != "eliminated"]
        if not active:
            return models

        active.sort(key=lambda m: m.explanatory_power, reverse=True)
        if len(active) == 1:
            return self._mark_dominant(models, active[0].model_id)

        top = active[0]
        second = active[1]
        margin = top.explanatory_power - second.explanatory_power

        # Dominance requires clear explanatory lead and minimum power
        if margin >= 8.0 and top.explanatory_power >= 48.0:
            return self._mark_dominant(models, top.model_id)

        return models

    @staticmethod
    def _mark_dominant(models: tuple[WorldModel, ...], dominant_id: str) -> tuple[WorldModel, ...]:
        result: list[WorldModel] = []
        for model in models:
            if model.model_id == dominant_id:
                result.append(replace(model, status="dominant"))
            elif model.status == "eliminated":
                result.append(model)
            else:
                result.append(replace(model, status="weakened"))  # type: ignore[arg-type]
        return tuple(result)

    def convergence_summary(
        self,
        models: tuple[WorldModel, ...],
    ) -> tuple[str, float, float, str]:
        """Return dominant_id, convergence_score, uncertainty, summary."""
        active = [m for m in models if m.status in {"active", "dominant", "weakened"}]
        eliminated = [m for m in models if m.status == "eliminated"]
        dominant = next((m for m in models if m.status == "dominant"), None)

        if dominant is None:
            if active:
                top = max(active, key=lambda m: m.explanatory_power)
                score = top.explanatory_power * 0.6
                uncertainty = 100.0 - score
                summary = (
                    f"No dominant reality yet — leading candidate: {top.name} "
                    f"({top.explanatory_power:.0f}% power, {len(eliminated)} eliminated)"
                )
                return top.model_id, score, uncertainty, summary
            return "", 0.0, 100.0, "Insufficient evidence to reconstruct market reality"

        second_power = 0.0
        others = [m for m in active if m.model_id != dominant.model_id]
        if others:
            second_power = max(m.explanatory_power for m in others)

        margin = dominant.explanatory_power - second_power
        convergence_score = min(100.0, dominant.explanatory_power + margin * 0.5)
        uncertainty = max(0.0, 100.0 - convergence_score)

        summary = (
            f"Reality converged: {dominant.name} ({dominant.explanatory_power:.0f}% power, "
            f"+{margin:.0f} vs nearest alternative, {len(eliminated)} models eliminated)"
        )
        return dominant.model_id, convergence_score, uncertainty, summary
