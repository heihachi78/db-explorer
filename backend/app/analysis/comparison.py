import math
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

def _comb2(value: int) -> int:
    return value * (value - 1) // 2


def _contingency(left: list[int], right: list[int]) -> tuple[Counter, Counter, Counter]:
    return Counter(left), Counter(right), Counter(zip(left, right, strict=True))


def adjusted_rand_index(left: list[int], right: list[int]) -> float:
    if len(left) != len(right):
        raise ValueError("A particionálások elemszámának egyeznie kell.")
    if len(left) < 2:
        return 1.0
    left_counts, right_counts, cells = _contingency(left, right)
    pairs = _comb2(len(left))
    cell_pairs = sum(_comb2(value) for value in cells.values())
    left_pairs = sum(_comb2(value) for value in left_counts.values())
    right_pairs = sum(_comb2(value) for value in right_counts.values())
    expected = left_pairs * right_pairs / pairs if pairs else 0.0
    maximum = (left_pairs + right_pairs) / 2
    denominator = maximum - expected
    return (cell_pairs - expected) / denominator if denominator else 1.0


def information_scores(left: list[int], right: list[int]) -> tuple[float, float]:
    if len(left) != len(right):
        raise ValueError("A particionálások elemszámának egyeznie kell.")
    if not left:
        return 1.0, 0.0
    left_counts, right_counts, cells = _contingency(left, right)
    total = len(left)
    left_entropy = -sum((count / total) * math.log(count / total) for count in left_counts.values())
    right_entropy = -sum((count / total) * math.log(count / total) for count in right_counts.values())
    mutual_information = 0.0
    for (left_id, right_id), count in cells.items():
        probability = count / total
        mutual_information += probability * math.log(
            count * total / (left_counts[left_id] * right_counts[right_id])
        )
    denominator = math.sqrt(left_entropy * right_entropy)
    if denominator:
        nmi = mutual_information / denominator
    else:
        nmi = 1.0 if left_entropy == 0 and right_entropy == 0 else 0.0
    vi = left_entropy + right_entropy - 2 * mutual_information
    return nmi, max(0.0, vi)


def compare_memberships(
    memberships: list[tuple[str, dict[str, int]]],
    source_edges: list[Any],
) -> dict[str, Any]:
    shared_ids = sorted(set.intersection(*(
        {node_id for node_id, community_id in membership.items() if community_id >= 0}
        for _, membership in memberships
    ))) if memberships else []
    pairwise = []
    for (left_id, left), (right_id, right) in combinations(memberships, 2):
        left_values = [left[node_id] for node_id in shared_ids]
        right_values = [right[node_id] for node_id in shared_ids]
        nmi, vi = information_scores(left_values, right_values)
        pairwise.append({
            "leftAnalysisId": left_id,
            "rightAnalysisId": right_id,
            "adjustedRandIndex": round(adjusted_rand_index(left_values, right_values), 12),
            "normalizedMutualInformation": round(nmi, 12),
            "variationOfInformation": round(vi, 12),
        })

    neighbors: dict[str, Counter[str]] = defaultdict(Counter)
    shared_set = set(shared_ids)
    for edge in source_edges:
        if edge.source in shared_set and edge.target in shared_set and edge.source != edge.target:
            neighbors[edge.source][edge.target] += 1
            neighbors[edge.target][edge.source] += 1
    node_stability: dict[str, float] = {}
    for node_id in shared_ids:
        main_neighbors = [neighbor for neighbor, _ in neighbors[node_id].most_common(10)]
        if not main_neighbors:
            node_stability[node_id] = 1.0
            continue
        observations = [
            membership[node_id] == membership[neighbor]
            for _, membership in memberships
            for neighbor in main_neighbors
        ]
        node_stability[node_id] = round(sum(observations) / len(observations), 12)

    baseline = memberships[0][1] if memberships else {}
    community_scores: dict[int, list[float]] = defaultdict(list)
    for node_id, score in node_stability.items():
        community_scores[baseline[node_id]].append(score)
    thresholds = {"stable": 0.8, "mixed": 0.55}
    communities = []
    for community_id, scores in sorted(community_scores.items()):
        score = sum(scores) / len(scores)
        label = "STABLE" if score >= thresholds["stable"] else "MIXED" if score >= thresholds["mixed"] else "UNSTABLE"
        communities.append({
            "communityId": community_id,
            "score": round(score, 12),
            "label": label,
        })
    return {
        "sharedNodeCount": len(shared_ids),
        "pairwise": pairwise,
        "nodeStability": node_stability,
        "communityStability": communities,
        "thresholds": thresholds,
    }
