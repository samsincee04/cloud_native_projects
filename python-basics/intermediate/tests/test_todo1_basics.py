from src.todo1_basics import normalize_scores, letter_grades, grade_histogram

def test_normalize_scores_clamps_values():
    assert normalize_scores([120, -4, 90]) == [100, 0, 90]
    assert normalize_scores([]) == []
    assert normalize_scores([0, 100, 50]) == [0, 100, 50]

def test_letter_grades_uses_scale():
    assert letter_grades([95, 82, 77, 61, 10]) == ["A", "B", "C", "D", "F"]

def test_letter_grades_normalizes_first():
# 120 becomes 100 -> A; -1 becomes 0 -> F
   assert letter_grades([120, -1, 89]) == ["A", "F", "B"]

def test_grade_histogram_counts_all_letters():
    h = grade_histogram(["A", "A", "C"])

    assert h == {"A": 2, "B": 0, "C": 1, "D": 0, "F": 0}
