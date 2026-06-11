"""
Scoring system for developmental and brainrot metrics.
Normalizes raw metrics and computes dimension scores and final scores.
"""

from typing import Dict, Optional
from .config import (
    AGE_BANDS, METRIC_CONFIG, DIMENSIONS,
    DEV_WEIGHTS, BRAINROT_WEIGHTS
)


def assign_age_band(child_age: float) -> str:
    """
    Assign age band based on child's age.
    
    Args:
        child_age: Age in years
        
    Returns:
        Age band code (e.g., "G3_3_5")
    """
    for band_code, band_info in AGE_BANDS.items():
        if band_info["min_age"] <= child_age < band_info["max_age"]:
            return band_code
    
    # Default to oldest band if out of range
    return "G4_5_8"


def normalize_metric(metric_name: str, value: float, age_band: str) -> float:
    """
    Normalize a raw metric value to 0-1 score based on age-appropriate ranges.
    
    Args:
        metric_name: Name of the metric
        value: Raw metric value
        age_band: Age band code
        
    Returns:
        Normalized score (0-1, where 1 is ideal)
    """
    if metric_name not in METRIC_CONFIG:
        print(f"Warning: Unknown metric {metric_name}, returning 0.5")
        return 0.5
    
    if age_band not in METRIC_CONFIG[metric_name]:
        print(f"Warning: No config for {metric_name} in {age_band}, returning 0.5")
        return 0.5
    
    config = METRIC_CONFIG[metric_name][age_band]
    direction = config["direction"]
    ideal_low = config.get("ideal_low", 0)
    ideal_high = config.get("ideal_high", 1)
    
    # Handle different optimization directions
    if direction == "higher_better":
        # Higher values are better
        hard_min = config.get("hard_min", 0)
        
        if value >= ideal_high:
            return 1.0
        elif value <= hard_min:
            return 0.0
        elif value >= ideal_low:
            # In ideal range
            return 0.8 + 0.2 * ((value - ideal_low) / (ideal_high - ideal_low))
        else:
            # Between hard_min and ideal_low
            return 0.8 * ((value - hard_min) / (ideal_low - hard_min))
    
    elif direction == "lower_better":
        # Lower values are better
        hard_max = config.get("hard_max", float('inf'))
        
        if value <= ideal_low:
            return 1.0
        elif value >= hard_max:
            return 0.0
        elif value <= ideal_high:
            # In ideal range
            return 0.8 + 0.2 * ((ideal_high - value) / (ideal_high - ideal_low))
        else:
            # Between ideal_high and hard_max
            return 0.8 * ((hard_max - value) / (hard_max - ideal_high))
    
    elif direction == "mid":
        # Middle range is ideal
        hard_min = config.get("hard_min", 0)
        hard_max = config.get("hard_max", float('inf'))
        
        if ideal_low <= value <= ideal_high:
            # In ideal range
            return 1.0
        elif value < ideal_low:
            # Below ideal
            if value <= hard_min:
                return 0.0
            else:
                return 0.5 + 0.5 * ((value - hard_min) / (ideal_low - hard_min))
        else:
            # Above ideal
            if value >= hard_max:
                return 0.0
            else:
                return 0.5 + 0.5 * ((hard_max - value) / (hard_max - ideal_high))
    
    else:
        print(f"Warning: Unknown direction {direction} for {metric_name}")
        return 0.5


def compute_dimension_scores(raw_metrics: Dict[str, float], age_band: str) -> Dict[str, float]:
    """
    Compute dimension scores from raw metrics.
    
    Args:
        raw_metrics: Dictionary of raw metric values
        age_band: Age band code
        
    Returns:
        Dictionary of dimension scores (0-100)
    """
    dimension_scores = {}
    
    for dimension, metric_names in DIMENSIONS.items():
        # Normalize each metric in this dimension
        normalized_scores = []
        
        for metric_name in metric_names:
            if metric_name in raw_metrics:
                value = raw_metrics[metric_name]
                normalized = normalize_metric(metric_name, value, age_band)
                normalized_scores.append(normalized)
            else:
                print(f"Warning: Metric {metric_name} missing from raw_metrics")
        
        # Compute average (equal weight for now, could be customized)
        if normalized_scores:
            avg_score = sum(normalized_scores) / len(normalized_scores)
            dimension_scores[dimension] = avg_score * 100  # Scale to 0-100
        else:
            dimension_scores[dimension] = 50.0  # Neutral score if no metrics
    
    return dimension_scores


def aggregate_dev_score(dimension_scores: Dict[str, float], age_band: str) -> float:
    """
    Compute overall Developmental Score from dimension scores.
    
    Args:
        dimension_scores: Dictionary of dimension scores (0-100)
        age_band: Age band code
        
    Returns:
        Overall developmental score (0-100)
    """
    if age_band not in DEV_WEIGHTS:
        print(f"Warning: No dev weights for {age_band}, using equal weights")
        weights = {dim: 1.0 / len(DIMENSIONS) for dim in DIMENSIONS}
    else:
        weights = DEV_WEIGHTS[age_band]
    
    # Weighted sum
    score = 0.0
    for dimension, weight in weights.items():
        if dimension in dimension_scores:
            score += weight * dimension_scores[dimension]
        else:
            print(f"Warning: Dimension {dimension} missing from dimension_scores")
    
    return score


def aggregate_brainrot_index(dimension_scores: Dict[str, float], age_band: str) -> float:
    """
    Compute Brainrot Index from dimension scores.
    Higher brainrot index = more concerning content.
    
    Args:
        dimension_scores: Dictionary of dimension scores (0-100)
        age_band: Age band code
        
    Returns:
        Brainrot index (0-100)
    """
    if age_band not in BRAINROT_WEIGHTS:
        print(f"Warning: No brainrot weights for {age_band}, using equal weights")
        weights = {dim: 1.0 / len(DIMENSIONS) for dim in DIMENSIONS}
    else:
        weights = BRAINROT_WEIGHTS[age_band]
    
    # For brainrot, we invert the dimension scores (lower quality = higher risk)
    # But some dimensions need custom transforms
    risk_scores = {}
    
    for dimension in DIMENSIONS:
        if dimension in dimension_scores:
            dim_score = dimension_scores[dimension]
            
            # Most dimensions: low score = high risk
            # Simple inversion
            risk_scores[dimension] = 100 - dim_score
        else:
            risk_scores[dimension] = 50.0  # Neutral
    
    # Weighted sum of risk scores
    brainrot_score = 0.0
    for dimension, weight in weights.items():
        if dimension in risk_scores:
            brainrot_score += weight * risk_scores[dimension]
    
    return brainrot_score


def generate_recommendations(dimension_scores: Dict[str, float], 
                            raw_metrics: Dict[str, float],
                            age_band: str) -> Dict[str, list]:
    """
    Generate recommendations based on scores.
    
    Args:
        dimension_scores: Dictionary of dimension scores
        raw_metrics: Dictionary of raw metrics
        age_band: Age band code
        
    Returns:
        Dictionary with 'strengths' and 'concerns' lists
    """
    strengths = []
    concerns = []
    
    # Check each dimension
    for dimension, score in dimension_scores.items():
        if score >= 75:
            strengths.append(f"{dimension}: Excellent ({score:.0f}/100)")
        elif score < 50:
            concerns.append(f"{dimension}: Needs improvement ({score:.0f}/100)")
    
    # Check specific high-risk metrics
    if "aggression_rate" in raw_metrics:
        config = METRIC_CONFIG["aggression_rate"][age_band]
        if raw_metrics["aggression_rate"] > config["ideal_high"]:
            concerns.append(f"High aggression rate: {raw_metrics['aggression_rate']:.1f} per minute")
    
    if "cuts_per_minute" in raw_metrics:
        config = METRIC_CONFIG["cuts_per_minute"][age_band]
        if raw_metrics["cuts_per_minute"] > config["hard_max"] * 0.8:
            concerns.append(f"Very fast pacing: {raw_metrics['cuts_per_minute']:.1f} cuts per minute")
    
    if "prosocial_ratio" in raw_metrics:
        if raw_metrics["prosocial_ratio"] >= 0.7:
            strengths.append(f"Strong prosocial content: {raw_metrics['prosocial_ratio']:.1%}")
    
    return {
        "strengths": strengths,
        "concerns": concerns
    }


def interpret_scores(dev_score: float, brainrot_index: float) -> Dict[str, str]:
    """
    Provide human-readable interpretations of scores.
    
    Args:
        dev_score: Developmental score (0-100)
        brainrot_index: Brainrot index (0-100)
        
    Returns:
        Dictionary with interpretations
    """
    # Interpret developmental score
    if dev_score >= 80:
        dev_interpretation = "Excellent - Highly developmentally appropriate"
    elif dev_score >= 65:
        dev_interpretation = "Good - Generally appropriate with some areas for improvement"
    elif dev_score >= 50:
        dev_interpretation = "Fair - Some concerning elements, use with caution"
    elif dev_score >= 35:
        dev_interpretation = "Poor - Multiple developmental concerns"
    else:
        dev_interpretation = "Very Poor - Not recommended for this age group"
    
    # Interpret brainrot index
    if brainrot_index <= 20:
        brainrot_interpretation = "Very Low Risk - Safe and healthy content"
    elif brainrot_index <= 40:
        brainrot_interpretation = "Low Risk - Minor concerns, generally safe"
    elif brainrot_index <= 60:
        brainrot_interpretation = "Moderate Risk - Some problematic elements"
    elif brainrot_index <= 80:
        brainrot_interpretation = "High Risk - Multiple red flags, limit exposure"
    else:
        brainrot_interpretation = "Very High Risk - Strongly discourage viewing"
    
    # Overall recommendation
    if dev_score >= 65 and brainrot_index <= 40:
        overall = "Recommended"
    elif dev_score >= 50 and brainrot_index <= 60:
        overall = "Acceptable with supervision"
    else:
        overall = "Not recommended"
    
    return {
        "developmental": dev_interpretation,
        "brainrot": brainrot_interpretation,
        "overall": overall
    }

