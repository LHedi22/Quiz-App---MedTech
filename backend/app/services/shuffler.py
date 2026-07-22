"""Generates exam versions: independently shuffled question order and, within each
question, independently shuffled option order, with an anti-clustering pass so the
correct-answer letter isn't obviously predictable across a version's questions.
"""

import random
from collections import Counter

from app.models.version import QuestionForShuffle, ShuffledVersion

# Acceptable seed types for random.Random: None, int, float, str, bytes, bytearray.
Seed = None | int | float | str | bytes | bytearray

# Anti-clustering threshold (Subtask 3.2): reroll a version's shuffle if more than this
# fraction of its questions land their correct answer on the same letter.
CORRECT_LETTER_MAX_FRACTION = 0.5

# Safety valve so the anti-clustering reroll pass can never spin forever: after this many
# attempts, the best-effort (last) shuffle is accepted even if it's still over threshold.
MAX_RESHUFFLE_ATTEMPTS = 200


def _letter_to_index(letter: str) -> int:
    return ord(letter.upper()) - ord("A")


def _new_correct_letter(shuffled_option_order: list[int], correct_canonical_index: int) -> str:
    new_index = shuffled_option_order.index(correct_canonical_index)
    return chr(ord("A") + new_index)


def _shuffle_once(
    questions: list[QuestionForShuffle], rng: random.Random
) -> tuple[list, dict[str, list[int]], dict[str, str]]:
    order = [q.id for q in questions]
    rng.shuffle(order)

    option_order: dict[str, list[int]] = {}
    correct_letters: dict[str, str] = {}
    for question in questions:
        indices = list(range(len(question.options)))
        rng.shuffle(indices)
        option_order[str(question.id)] = indices
        correct_letters[str(question.id)] = _new_correct_letter(
            indices, _letter_to_index(question.correct_option)
        )

    return order, option_order, correct_letters


def _distribution_signature(correct_letters: dict[str, str]) -> tuple:
    return tuple(sorted(Counter(correct_letters.values()).items()))


def _is_too_clustered(correct_letters: dict[str, str], max_fraction: float) -> bool:
    if not correct_letters:
        return False
    counts = Counter(correct_letters.values())
    total = len(correct_letters)
    return any(count / total > max_fraction for count in counts.values())


def generate_version(
    questions: list[QuestionForShuffle],
    version_number: int,
    seed: Seed,
    max_attempts: int = MAX_RESHUFFLE_ATTEMPTS,
    previous_distributions: set[tuple] | None = None,
) -> ShuffledVersion:
    """Shuffle one version. Rerolls (up to `max_attempts`) while the correct-answer
    letter distribution is too skewed, or exactly repeats a distribution already seen
    in `previous_distributions` (used by `generate_versions` for cross-version checks).
    """
    rng = random.Random(seed)

    order = option_order = correct_letters = None
    for attempt in range(1, max_attempts + 1):
        order, option_order, correct_letters = _shuffle_once(questions, rng)
        clustered = _is_too_clustered(correct_letters, CORRECT_LETTER_MAX_FRACTION)
        repeated = (
            previous_distributions is not None
            and _distribution_signature(correct_letters) in previous_distributions
        )
        if not clustered and not repeated:
            break
        # Otherwise keep rerolling (fallback: last attempt's shuffle is used as-is).

    if previous_distributions is not None:
        previous_distributions.add(_distribution_signature(correct_letters))

    return ShuffledVersion(
        version_number=version_number,
        question_order=order,
        option_order=option_order,
    )


def generate_versions(
    questions: list[QuestionForShuffle],
    count: int,
    base_seed: Seed = None,
) -> list[ShuffledVersion]:
    """Generate `count` versions for one quiz, each independently shuffled and each
    checked against the anti-clustering pass, including a repeat-distribution check
    against every other version generated in this same call.
    """
    if base_seed is None:
        base_seed = random.SystemRandom().randrange(2**32)

    previous_distributions: set[tuple] = set()
    versions = []
    for i in range(count):
        version_number = i + 1
        versions.append(
            generate_version(
                questions,
                version_number,
                seed=f"{base_seed}-{version_number}",
                previous_distributions=previous_distributions,
            )
        )
    return versions
