from typing import List, Dict
def normalize_scores(scores: List[int]) -> List[int]:
    """
    Return a new list where each score is clamped to the range [0, 100].
    Example:
    [120, -4, 90] -> [100, 0, 90]
    """
    normalized = []
    for score in scores:
        if score > 100:
            normalized.append(100)
        elif score < 0:
            normalized.append(0)
        else:
            normalized.append(score)
    return normalized


def letter_grades(scores: List[int]) -> List[str]:
    """
    Convert numeric scores to letter grades using this scale:
    A: 90-100
    B: 80-89
    C: 70-79
    D: 60-69
    F: 0-59
    Notes:
    - First call normalize_scores(scores)
    - Return a list of letters with the same length as scores
    """
    normalized = normalize_scores(scores)
    letters = []
    for score in normalized:
        if score >= 90:
            letter = "A"
        elif score >= 80:
            letter = "B"
        elif score >= 70:
            letter = "C"
        elif score >= 60:
            letter = "D"
        else:
            letter = "F"
        letters.append(letter)
    return letters


def grade_histogram(grades: List[str]) -> Dict[str, int]:
    """
    Return a dictionary mapping each letter in {"A","B","C","D","F"} to its count.

    Example:
    ["A","A","C"] -> {"A":2,"B":0,"C":1,"D":0,"F":0}
    """
    histogram = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for grade in grades:
        if grade in histogram:
            histogram[grade] += 1
    return histogram
