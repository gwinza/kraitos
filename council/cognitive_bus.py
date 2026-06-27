"""Real-time inter-council deliberation bus."""

from __future__ import annotations

from council.cognitive_models import CouncilObservation, DeliberationMessage, CouncilName


class CognitiveBus:
    """Facilitates internal council debate each market update."""

    def deliberate(
        self,
        observations: tuple[CouncilObservation, ...],
        *,
        rounds: int = 2,
    ) -> tuple[DeliberationMessage, ...]:
        if not observations:
            return ()
        by_name = {obs.council: obs for obs in observations}
        messages: list[DeliberationMessage] = []

        for round_index in range(1, rounds + 1):
            for obs in observations:
                messages.append(
                    DeliberationMessage(
                        round_index=round_index,
                        from_council=obs.council,
                        to_council=None,
                        message=f"{obs.council.title()} Council: {obs.headline}",
                    )
                )

            if round_index == 1:
                messages.extend(self._cross_examination(by_name))

            if round_index == 2:
                messages.extend(self._synthesis_responses(by_name))

        return tuple(messages)

    def _cross_examination(
        self,
        by_name: dict[CouncilName, CouncilObservation],
    ) -> list[DeliberationMessage]:
        messages: list[DeliberationMessage] = []
        trend = by_name.get("trend")
        structure = by_name.get("structure")
        liquidity = by_name.get("liquidity")
        volume = by_name.get("volume")
        memory = by_name.get("memory")
        execution = by_name.get("execution")
        story = by_name.get("story")

        if trend and structure and trend.direction != structure.direction:
            if trend.direction != "neutral" and structure.direction != "neutral":
                messages.append(
                    DeliberationMessage(
                        round_index=1,
                        from_council="structure",
                        to_council="trend",
                        message=(
                            f"Structure sees {structure.direction} while trend claims "
                            f"{trend.direction} — which timeframe leads?"
                        ),
                    )
                )

        if liquidity and volume:
            if "weak" in volume.headline.lower() and "stop hunt" in liquidity.headline.lower():
                messages.append(
                    DeliberationMessage(
                        round_index=1,
                        from_council="memory",
                        to_council="volume",
                        message=(
                            "Historically weak volume immediately after stop hunts "
                            "often precedes continuation once acceptance forms."
                        ),
                    )
                )

        if story and execution:
            messages.append(
                DeliberationMessage(
                    round_index=1,
                    from_council="story",
                    to_council="execution",
                    message=(
                        f"Narrative still fits: {story.headline}. "
                        f"Execution advises: {execution.headline}"
                    ),
                )
            )

        if memory and execution:
            messages.append(
                DeliberationMessage(
                    round_index=1,
                    from_council="memory",
                    to_council="execution",
                    message=f"Memory context: {memory.headline}",
                )
            )

        return messages

    def _synthesis_responses(
        self,
        by_name: dict[CouncilName, CouncilObservation],
    ) -> list[DeliberationMessage]:
        messages: list[DeliberationMessage] = []
        bullish = sum(1 for o in by_name.values() if o.direction == "bullish")
        bearish = sum(1 for o in by_name.values() if o.direction == "bearish")
        dominant = "mixed"
        if bullish > bearish + 1:
            dominant = "bullish"
        elif bearish > bullish + 1:
            dominant = "bearish"

        messages.append(
            DeliberationMessage(
                round_index=2,
                from_council="story",
                to_council=None,
                message=f"Internal synthesis: dominant directional evidence is {dominant}.",
            )
        )

        risk = by_name.get("risk")
        if risk and "veto" in risk.headline.lower():
            messages.append(
                DeliberationMessage(
                    round_index=2,
                    from_council="risk",
                    to_council=None,
                    message="Hard risk constraint overrides opportunity — preserve capital.",
                )
            )

        execution = by_name.get("execution")
        if execution:
            messages.append(
                DeliberationMessage(
                    round_index=2,
                    from_council="execution",
                    to_council=None,
                    message=f"Execution posture: {execution.headline}",
                )
            )

        return messages
