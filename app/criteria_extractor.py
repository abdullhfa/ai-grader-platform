"""
Extract required criteria from assignment file
"""
import re
from typing import List, Set

def extract_required_criteria_from_text(assignment_text: str) -> List[str]:
    """
    Extract criteria codes mentioned in the assignment text.
    
    Looks for patterns like:
    - A.P1, B.P2, C.P3 (Pass)
    - A.M1, B.M2 (Merit)
    - A.D1, B.D1 (Distinction)
    - 21/A.P1 (with unit number prefix)
    
    Args:
        assignment_text: The text content of the assignment file
        
    Returns:
        List of unique criteria codes found (e.g., ['A.P1', 'A.P2', 'A.M1'])
    """
    criteria_set: Set[str] = set()
    
    # Improved Pattern: Matches standard and variations
    # Group 1 (Optional): Learning Aim (A, B, AB, etc.) + Separator (. - or space)
    # Group 2: Level (P, M, D)
    # Group 3: Number (1-99)
    # Matches: A.P1, B-M2, C P3, AB.D1, P4, etc.
    pattern = r'\b(?:([A-Z]{1,2})[\s\.\-])?([PMD])(\d{1,2})\b'
    
    # Find all matches (Case Insensitive)
    for match in re.finditer(pattern, assignment_text, re.IGNORECASE):
        learning_aim = match.group(1).upper() if match.group(1) else ""
        level = match.group(2).upper()
        number = match.group(3)
        
        if learning_aim:
            criteria_code = f"{learning_aim}.{level}{number}"
        else:
            criteria_code = f"{level}{number}"
            
        criteria_set.add(criteria_code)
    
    # Pattern for unit number prefix (21/A.P1, 4/B.M2, etc.)
    pattern_prefix = r'\b\d+/([A-Z]{1,2})\.([PMD])(\d{1,2})\b'
    for match in re.finditer(pattern_prefix, assignment_text, re.IGNORECASE):
        learning_aim = match.group(1).upper()
        level = match.group(2).upper()
        number = match.group(3)
        criteria_code = f"{learning_aim}.{level}{number}"
        criteria_set.add(criteria_code)
    
    # Convert to sorted list
    criteria_list = sorted(list(criteria_set))
    
    return criteria_list


def filter_unit_criteria(all_criteria: List[dict], required_codes: List[str]) -> List[dict]:
    """
    Filter unit criteria to include only those mentioned in the assignment.
    
    Args:
        all_criteria: All criteria from the unit specification
        required_codes: Codes mentioned in the assignment (e.g., ['A.P1', 'A.P2'])
        
    Returns:
        Filtered list of criteria matching the required codes
    """
    # Safety check for None inputs
    if all_criteria is None:
        return []
        
    if not required_codes:
        # If no criteria found in assignment, return all criteria
        return all_criteria
    
    filtered = []
    for criterion in all_criteria:
        # Safety check for criterion being None (unlikely but possible)
        if criterion and criterion.get('code') in required_codes:
            filtered.append(criterion)
    
    return filtered


# Example usage
if __name__ == "__main__":
    # Test with sample assignment text
    sample_text = """
    موجز واجب BTEC
    
    21/A.P1 | وصف المفاهيم الأساسية للذكاء الاصطناعي
    21/A.P2 | شرح الفوائد والمخاطر المرتبطة بالذكاء الاصطناعي
    21/A.M1 | تحليل كيفية تطبيق الذكاء الاصطناعي في المجالات المختلفة
    """
    
    criteria = extract_required_criteria_from_text(sample_text)
    print("Required Criteria Found:")
    for c in criteria:
        print(f"  - {c}")
    
    # Test filtering
    all_unit_criteria = [
        {"code": "A.P1", "description": "Describe..."},
        {"code": "A.P2", "description": "Explain..."},
        {"code": "A.M1", "description": "Analyse..."},
        {"code": "A.D1", "description": "Evaluate..."},
        {"code": "B.P3", "description": "Another..."},
    ]
    
    filtered = filter_unit_criteria(all_unit_criteria, criteria)
    print(f"\nFiltered Criteria ({len(filtered)} out of {len(all_unit_criteria)}):")
    for c in filtered:
        print(f"  - {c['code']}: {c['description'][:30]}...")
