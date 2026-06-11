"""
Utility functions for the evaluation system.
"""

import os
import json
from typing import Dict, Any, Optional, List
from pathlib import Path


def load_evaluation_results(json_path: str) -> Dict[str, Any]:
    """
    Load evaluation results from JSON file.
    
    Args:
        json_path: Path to JSON results file
        
    Returns:
        Dictionary with evaluation results
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_score(score: float) -> str:
    """
    Format a score for display.
    
    Args:
        score: Score value (0-100)
        
    Returns:
        Formatted string with color indicator
    """
    if score >= 80:
        indicator = "🟢"
    elif score >= 65:
        indicator = "🟡"
    elif score >= 50:
        indicator = "🟠"
    else:
        indicator = "🔴"
    
    return f"{indicator} {score:.1f}/100"


def print_quick_summary(results: Dict[str, Any]):
    """
    Print a quick one-line summary of results.
    
    Args:
        results: Evaluation results dictionary
    """
    name = results["metadata"]["video_name"]
    dev = results["overall_scores"]["development_score"]
    brainrot = results["overall_scores"]["brainrot_index"]
    overall = results["interpretations"]["overall"]
    
    print(f"{name}: Dev={format_score(dev)}, Brainrot={format_score(100-brainrot)}, {overall}")


def compare_videos(results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare multiple video evaluations.
    
    Args:
        results_list: List of evaluation result dictionaries
        
    Returns:
        Comparison summary
    """
    if not results_list:
        return {}
    
    comparison = {
        "best_dev_score": max(results_list, key=lambda r: r["overall_scores"]["development_score"]),
        "worst_dev_score": min(results_list, key=lambda r: r["overall_scores"]["development_score"]),
        "lowest_brainrot": min(results_list, key=lambda r: r["overall_scores"]["brainrot_index"]),
        "highest_brainrot": max(results_list, key=lambda r: r["overall_scores"]["brainrot_index"]),
        "averages": {
            "development_score": sum(r["overall_scores"]["development_score"] for r in results_list) / len(results_list),
            "brainrot_index": sum(r["overall_scores"]["brainrot_index"] for r in results_list) / len(results_list)
        }
    }
    
    return comparison


def filter_by_recommendation(results_list: List[Dict[str, Any]], 
                             recommendation: str = "Recommended") -> List[Dict[str, Any]]:
    """
    Filter videos by recommendation status.
    
    Args:
        results_list: List of evaluation results
        recommendation: Recommendation to filter by
        
    Returns:
        Filtered list of results
    """
    return [r for r in results_list if r["interpretations"]["overall"] == recommendation]


def get_dimension_breakdown(results: Dict[str, Any]) -> str:
    """
    Get a formatted breakdown of dimension scores.
    
    Args:
        results: Evaluation results
        
    Returns:
        Formatted string with dimension breakdown
    """
    lines = []
    for dim, score in results["dimension_scores"].items():
        bar_length = int(score / 5)  # Scale to 20 chars max
        bar = "█" * bar_length + "░" * (20 - bar_length)
        lines.append(f"{dim:15s} {bar} {score:.1f}/100")
    
    return "\n".join(lines)


def export_to_csv(results_list: List[Dict[str, Any]], output_path: str):
    """
    Export evaluation results to CSV format.
    
    Args:
        results_list: List of evaluation results
        output_path: Path to save CSV file
    """
    import csv
    
    if not results_list:
        return
    
    # Determine all metric names
    all_metrics = set()
    for r in results_list:
        all_metrics.update(r["raw_metrics"].keys())
        all_metrics.update(r["dimension_scores"].keys())
    
    all_metrics = sorted(all_metrics)
    
    # Write CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        header = ["video_name", "child_age", "age_band", "duration_minutes",
                 "development_score", "brainrot_index", "overall_recommendation"]
        header.extend([f"dim_{m}" for m in sorted(results_list[0]["dimension_scores"].keys())])
        header.extend([f"metric_{m}" for m in sorted(results_list[0]["raw_metrics"].keys())])
        writer.writerow(header)
        
        # Data rows
        for r in results_list:
            row = [
                r["metadata"]["video_name"],
                r["metadata"]["child_age"],
                r["metadata"]["age_band"],
                r["metadata"]["duration_minutes"],
                r["overall_scores"]["development_score"],
                r["overall_scores"]["brainrot_index"],
                r["interpretations"]["overall"]
            ]
            
            # Add dimension scores
            for dim in sorted(r["dimension_scores"].keys()):
                row.append(r["dimension_scores"][dim])
            
            # Add raw metrics
            for metric in sorted(r["raw_metrics"].keys()):
                row.append(r["raw_metrics"][metric])
            
            writer.writerow(row)
    
    print(f"Exported {len(results_list)} results to: {output_path}")


def generate_html_report(results: Dict[str, Any], output_path: str):
    """
    Generate an HTML report for a single video evaluation.
    
    Args:
        results: Evaluation results
        output_path: Path to save HTML file
    """
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Video Evaluation: {results['metadata']['video_name']}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .score-card {{
            background-color: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .score {{
            font-size: 48px;
            font-weight: bold;
            color: #2196F3;
        }}
        .dimension {{
            margin: 10px 0;
        }}
        .bar {{
            background-color: #e0e0e0;
            height: 20px;
            border-radius: 10px;
            overflow: hidden;
        }}
        .bar-fill {{
            background-color: #4CAF50;
            height: 100%;
            transition: width 0.3s;
        }}
        .good {{ color: green; }}
        .warning {{ color: orange; }}
        .bad {{ color: red; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Video Evaluation Report</h1>
        <h2>{results['metadata']['video_name']}</h2>
        <p>Age: {results['metadata']['child_age']} years ({results['metadata']['age_band_label']})</p>
        <p>Duration: {results['metadata']['duration_minutes']:.1f} minutes</p>
        <p>Evaluated: {results['metadata']['evaluation_timestamp']}</p>
    </div>
    
    <div class="score-card">
        <h2>Overall Scores</h2>
        <div>
            <h3>Development Score</h3>
            <p class="score">{results['overall_scores']['development_score']:.1f}/100</p>
            <p>{results['interpretations']['developmental']}</p>
        </div>
        <div>
            <h3>Brainrot Index</h3>
            <p class="score">{results['overall_scores']['brainrot_index']:.1f}/100</p>
            <p>{results['interpretations']['brainrot']}</p>
        </div>
        <div>
            <h3>Overall Recommendation</h3>
            <p><strong>{results['interpretations']['overall']}</strong></p>
        </div>
    </div>
    
    <div class="score-card">
        <h2>Dimension Scores</h2>
"""
    
    for dim, score in results['dimension_scores'].items():
        html += f"""
        <div class="dimension">
            <h4>{dim}: {score:.1f}/100</h4>
            <div class="bar">
                <div class="bar-fill" style="width: {score}%"></div>
            </div>
        </div>
"""
    
    html += """
    </div>
    
    <div class="score-card">
        <h2>Strengths</h2>
        <ul>
"""
    
    for strength in results['recommendations']['strengths']:
        html += f"        <li class='good'>{strength}</li>\n"
    
    html += """
        </ul>
    </div>
    
    <div class="score-card">
        <h2>Concerns</h2>
        <ul>
"""
    
    for concern in results['recommendations']['concerns']:
        html += f"        <li class='warning'>{concern}</li>\n"
    
    html += """
        </ul>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"HTML report saved to: {output_path}")


def find_problematic_metrics(results: Dict[str, Any], threshold: float = 50.0) -> List[str]:
    """
    Identify dimensions or metrics that score below threshold.
    
    Args:
        results: Evaluation results
        threshold: Score threshold for flagging (default: 50)
        
    Returns:
        List of problematic dimension/metric names
    """
    problematic = []
    
    for dim, score in results["dimension_scores"].items():
        if score < threshold:
            problematic.append(f"{dim} (score: {score:.1f})")
    
    return problematic


def suggest_age_range(results: Dict[str, Any]) -> str:
    """
    Suggest appropriate age range based on scores.
    
    Args:
        results: Evaluation results
        
    Returns:
        Suggested age range string
    """
    dev_score = results["overall_scores"]["development_score"]
    brainrot = results["overall_scores"]["brainrot_index"]
    current_age = results["metadata"]["child_age"]
    
    if dev_score >= 65 and brainrot <= 40:
        return f"Appropriate for age {current_age:.0f}"
    elif dev_score < 50 or brainrot > 60:
        return f"Better suited for age {current_age + 1.5:.0f}+"
    else:
        return f"Marginal for age {current_age:.0f}, consider supervision"

